import logging
import sys
from collections.abc import AsyncGenerator, Callable
from pathlib import Path
from pprint import pformat
from typing import TYPE_CHECKING, Any, Final, Generic, TypeVar, cast, overload

from pyhon import const, diagnose, exceptions
from pyhon.apis import device as HonDevice
from pyhon.attributes import Attribute
from pyhon.command_loader import add_favourites, loader, recover_last_command_states
from pyhon.commands import HonCommand
from pyhon.parameter import Parameter, ProgramParameter, RangeParameter

if sys.version_info >= (3, 11):
    from datetime import UTC, datetime, timedelta
else:
    from datetime import datetime, timedelta, timezone

    UTC = timezone.utc

if TYPE_CHECKING:
    from pyhon.apis import API

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


MINIMAL_UPDATE_INTERVAL = 5


# pylint: disable=too-few-public-methods
class Throttle(Generic[T]):
    def __init__(self, func: Callable[..., T]) -> None:
        self.delay = timedelta(seconds=MINIMAL_UPDATE_INTERVAL)
        self.last_call = datetime.min
        self.func = func

    def __call__(self, *args: Any, force: bool = False, **kwargs: Any) -> T | None:
        now = datetime.now()
        if self.last_call + self.delay < now or force:
            self.last_call = now
            return self.func(*args, **kwargs)
        return None


# pylint: disable=too-many-public-methods,too-many-instance-attributes
class Appliance:
    def __init__(
        self, api: "API", appliance_data: dict[str, Any], zone: int = 0
    ) -> None:
        if attributes := appliance_data.get("attributes"):
            appliance_data["attributes"] = {
                v["parName"]: v["parValue"] for v in attributes
            }
        self.data: dict[str, Any] = appliance_data
        self._api = api

        self.commands: dict[str, HonCommand] = {}
        self.statistics: dict[str, Any] = {}
        self.maintenance_cycle: dict[str, Any] = {}
        self.attributes: dict[str, Any] = {}
        self.options: dict[str, Any] = {}
        self.zone: Final[int] = zone

        self.additional_data: dict[str, Any] = {}

    @classmethod
    async def create_from_data(
        cls, api: "API", appliance_data: dict[str, Any]
    ) -> AsyncGenerator["Appliance", None]:
        """Create appliance objects from API data.
        There may be multiple appliances in the data if zones are present.
        """
        appliance_type: str = appliance_data.get("applianceTypeName", "")
        target_classes = {cast(str, c.appliance_type): c for c in cls.__subclasses__()}
        target_cls: type["Appliance"] = target_classes.get(appliance_type, cls)

        for zone in range(int(appliance_data.get("zone", "1"))):
            appliance = target_cls(api, appliance_data, zone=zone)
            if appliance.mac_address:
                try:
                    await appliance.load_commands()
                    await appliance.load_command_history()
                    await appliance.load_favourites()

                    await appliance.load_attributes()
                    await appliance.load_statistics()
                    await appliance.load_maintenance_cycle()
                except (KeyError, ValueError, IndexError) as error:
                    _LOGGER.exception(error)
                    _LOGGER.error("Device data - %s", appliance_data)
                finally:
                    yield appliance

    def __getitem__(self, item: str) -> Any:  # noqa: C901
        if item in {
            "attributes",
            "data",
            "statistics",
            "maintenance_cycle",
            "additional_data",
        }:
            return getattr(self, item)

        if self.zone:
            item += f"Z{self.zone}"
        if "." in item:
            path = item.split(".")
            result = self[path[0]]
            for key in path[1:]:
                try:
                    # result may be a list or a dict
                    # first try to convert key to int
                    # and index result as a list
                    result = result[int(key)]
                except (ValueError, KeyError):
                    result = result[key]
            return result
        if item in self.attributes["parameters"]:
            return self.attributes["parameters"][item].value

        raise KeyError(f'Key not found: "{item}"')

    @overload
    def get(self, item: str, default: None = None) -> Any: ...

    @overload
    def get(self, item: str, default: T) -> T: ...

    def get(self, item: str, default: T | None = None) -> Any:
        try:
            return self[item]
        except (KeyError, IndexError):
            return default

    def _check_name_zone(self, name: str, frontend: bool = True) -> str:
        attribute: str = self.data.get(name, "")
        if attribute and self.zone:
            zone = " Z" if frontend else "_z"
            return f"{attribute}{zone}{self.zone}"
        return attribute

    @property
    def appliance_model_id(self) -> str:
        return str(self.data.get("applianceModelId", ""))

    @property
    def appliance_type(self) -> str:
        return str(self.data.get("applianceTypeName", ""))

    @property
    def mac_address(self) -> str:
        return str(self.data.get("macAddress", ""))

    @property
    def unique_id(self) -> str:
        default_mac = "xx-xx-xx-xx-xx-xx"
        import_name = f"{self.appliance_type.lower()}_{self.appliance_model_id}"
        result = self._check_name_zone("macAddress", frontend=False)
        result = result.replace(default_mac, import_name)
        return result

    @property
    def model_name(self) -> str:
        return self._check_name_zone("modelName")

    @property
    def brand(self) -> str:
        return self._check_name_zone("brand").capitalize()

    @property
    def nick_name(self) -> str:
        result = self._check_name_zone("nickName")
        if not result or set("xX1\r\n\t\f\v-").issuperset(result):
            return self.model_name
        return result

    @property
    def code(self) -> str:
        if code := self.data.get("code"):
            return cast(str, code)

        serial_number: str = self.data.get("serialNumber", "")
        return serial_number[:8] if len(serial_number) < 18 else serial_number[:11]

    @property
    def model_id(self) -> int:
        return int(self.data.get("applianceModelId", 0))

    @Throttle
    async def update(self) -> None:
        await self.load_attributes()
        self.sync_params_to_command("settings")

    @property
    def settings(self) -> dict[str, Parameter]:
        return {
            f"{name}.{key}": command.parameters.get(key, Parameter("", {}, ""))
            for name, command in self.commands.items()
            for key in command.setting_keys
        }

    @property
    def available_settings(self) -> list[str]:
        return [
            f"{name}.{key}"
            for name, command in self.commands.items()
            for key in command.setting_keys
        ]

    def data_dump(self) -> dict[str, Any]:
        return {
            name: getattr(self, name).copy()
            for name in (
                "attributes",
                "data",
                "statistics",
                "maintenance_cycle",
                "additional_data",
                "commands",
            )
        }

    def yaml_export(self) -> str:
        return diagnose.yaml_export(self.data_dump(), anonymous=True)

    async def zip_archive(self, path: Path, anonymous: bool = True) -> str:
        return await diagnose.zip_archive(self, path, anonymous)

    def sync_command_to_params(self, command_name: str) -> None:
        if command := self.commands.get(command_name):
            for key in self.attributes.get("parameters", {}):
                if new := command.parameters.get(key):
                    self.attributes["parameters"][key].update(
                        new.intern_value, shield=True
                    )

    def sync_params_to_command(self, command_name: str) -> None:
        if command := self.commands.get(command_name):
            for key in command.setting_keys:
                if (
                    new := self.attributes.get("parameters", {}).get(key)
                ) is not None and new.value != "":
                    setting = command.parameters[key]
                    try:
                        if not isinstance(setting, RangeParameter):
                            command.parameters[key].value = str(new.value)
                        else:
                            command.parameters[key].value = float(new.value)
                    except ValueError as error:
                        _LOGGER.info("Can't set %s - %s", key, error)

    # pylint: disable=too-many-nested-blocks
    def sync_command(
        self,
        main: str,
        target: list[str] | str | None = None,
        to_sync: list[str] | bool | None = None,
    ) -> None:
        if base := self.commands.get(main):
            for command, data in self.commands.items():
                if command != main and (not target or command in target):
                    for name, target_param in data.parameters.items():
                        if base_param := base.parameters.get(name):
                            if to_sync and (
                                (isinstance(to_sync, list) and name not in to_sync)
                                or not base_param.mandatory
                            ):
                                continue
                            target_param.sync(base_param)

    async def load_commands(self) -> None:
        raw_params = {
            "os": const.OS,
            "appVersion": const.APP_VERSION,
            "applianceType": self.appliance_type,
            "applianceModelId": self.appliance_model_id,
            "macAddress": self.mac_address,
            "code": self.code,
            "series": self.data.get("series"),
            "fwVersion": self.data.get("fwVersion"),
            "firmwareId": self.data.get("eepromId"),
        }
        params = {k: str(v) for k, v in raw_params.items() if v}

        payload = await self._api.call("retrieve", params=params)

        if payload.get("resultCode") == "0":
            self.options = payload.pop("applianceModel", {}).get("options", {})
            self.commands, self.additional_data = loader(self, payload)
            self.sync_params_to_command("settings")

    async def load_command_history(self) -> None:
        command_history = await self._api.call(
            f"appliance/{self.mac_address}/history",
            response_path=("payload", "history"),
        )

        recover_last_command_states(self.commands, command_history)

    async def load_favourites(self) -> None:
        favourites = (
            await self._api.call(
                f"appliance/{self.mac_address}/favourite",
                response_path=("payload", "favourites"),
            )
            or []
        )

        add_favourites(self.commands, favourites)

    # TODO: Method not used
    async def load_last_activity(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._api.call(
                "retrieve-last-activity",
                params={"macAddress": self.mac_address},
                response_path=("attributes",),
            ),
        )

    # TODO: Method not used
    async def load_appliance_data(self) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._api.call(
                "appliance-model",
                params={"code": self.code, "macAddress": self.mac_address},
                response_path=("payload", "applianceModel"),
            ),
        )

    async def load_attributes(self) -> dict[str, Any]:
        payload: dict[str, Any] = await self._api.call(
            "context",
            params={
                "macAddress": self.mac_address,
                "applianceType": self.appliance_type,
                "category": "CYCLE",
            },
        )

        self_params = self.attributes.setdefault("parameters", {})
        for name, values in payload.get("shadow", {}).get("parameters", {}).items():
            if name in self_params:
                self_params[name].update(values)
            else:
                self_params[name] = Attribute(values)

        program = int(self_params.get("prCode", "0"))
        cmd = self.settings.get("startProgram.program")

        program_name = "No Program"
        if program and isinstance(cmd, ProgramParameter):
            program_name = cmd.ids.get(program, program_name)

        self_params["programName"] = Attribute(program_name)

        self_params["connected"] = Attribute(
            payload.get("lastConnEvent", {}).get("category") != "DISCONNECTED"
        )

        return payload

    async def load_statistics(self) -> None:
        self.statistics = await self._api.call(
            "statistics",
            params={
                "macAddress": self.mac_address,
                "applianceType": self.appliance_type,
            },
        )

    async def load_maintenance_cycle(self) -> None:
        self.maintenance_cycle = await self._api.call(
            "maintenance-cycle", params={"macAddress": self.mac_address}
        )

    async def send_command(
        self,
        command: str,
        parameters: dict[str, Any],
        ancillary_parameters: dict[str, Any],
        program_name: str = "",
    ) -> bool:
        # TODO: Check if this is correct (non Zulu Specifier)
        now = datetime.now(UTC).isoformat(timespec="milliseconds")
        data: dict[str, Any] = {
            "macAddress": self.mac_address,
            "timestamp": now,
            "commandName": command,
            "transactionId": f"{self.mac_address}_{now}",
            # "applianceOptions": self.options,
            "device": HonDevice.descriptor(mobile=True),
            "attributes": {
                "channel": "mobileApp",
                "origin": "standardProgram",
                "energyLabel": "0",
            },
            "ancillaryParameters": ancillary_parameters,
            "parameters": parameters,
            "applianceType": self.appliance_type,
        }
        if command == "startProgram" and program_name:
            data |= {"programName": program_name.upper()}

        result = await self._api.call("send", data=data)
        rval: bool = result.get("resultCode") == "0"

        if rval:
            return rval

        raise exceptions.ApiError("Error sending command data", pformat(data))


class MachModeActivityMixin(Appliance):
    async def load_attributes(self) -> dict[str, Any]:
        payload = await super().load_attributes()
        params = self.attributes["parameters"]

        if params["connected"] == 0:
            params["machMode"].update(0)
        params["active"] = Attribute(bool(payload.get("activity")))

        params["pause"] = Attribute(params["machMode"] == 3)

        return payload


class ActiveFromOnOffStatusMixin(Appliance):
    async def load_attributes(self) -> dict[str, Any]:
        payload = await super().load_attributes()
        params = self.attributes["parameters"]
        params["active"] = Attribute(params["onOffStatus"] == 1)
        return payload
