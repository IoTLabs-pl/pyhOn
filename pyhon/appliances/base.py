import logging
import sys
from pprint import pformat

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TYPE_CHECKING, TypeVar, overload, Final

from pyhon import const, diagnose, exceptions
from pyhon.attributes import HonAttribute
from pyhon.command_loader import add_favourites, recover_last_command_states, loader
from pyhon.commands import HonCommand
from pyhon.parameter.base import HonParameter
from pyhon.parameter.program import HonParameterProgram
from pyhon.parameter.range import HonParameterRange

if sys.version_info >= (3, 11):
    from datetime import datetime, UTC
else:
    from datetime import datetime, timezone

    UTC = timezone.utc

if TYPE_CHECKING:
    from pyhon import HonAPI

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


MINIMAL_UPDATE_INTERVAL = 5


class throttle:
    def __init__(self, func) -> None:
        self.delay = timedelta(seconds=MINIMAL_UPDATE_INTERVAL)
        self.last_call = datetime.min
        self.func = func

    def __call__(self, *args, force=False, **kwargs):
        now = datetime.now()
        if self.last_call + self.delay < now or force:
            self.last_call = now
            return self.func(*args, **kwargs)


# pylint: disable=too-many-public-methods,too-many-instance-attributes
class HonAppliance:
    def __init__(
        self, api: "HonAPI", appliance_data: dict[str, Any], zone: int = 0
    ) -> None:
        if attributes := appliance_data.get("attributes"):
            appliance_data["attributes"] = {
                v["parName"]: v["parValue"] for v in attributes
            }
        self._data: dict[str, Any] = appliance_data
        self._api = api
        self._appliance_model: dict[str, Any] = {}

        self._commands: dict[str, HonCommand] = {}
        self._statistics: dict[str, Any] = {}
        self._attributes: dict[str, Any] = {}
        self.zone: Final[int] = zone

        self._additional_data: dict[str, Any] = {}

    @classmethod
    def appliance_type_name(cls) -> str:
        return cls.__name__.removesuffix("Appliance").upper()

    @classmethod
    async def create_from_data(cls, api, appliance_data):
        """Create appliance objects from API data.
        There may be multiple appliances in the data if zones are present.
        """
        cls = next(
            filter(
                lambda c: c.appliance_type_name()
                == appliance_data.get("applianceTypeName"),
                cls.__subclasses__(),
            ),
            cls,
        )

        for zone in range(int(appliance_data.get("zone", "1"))):
            appliance = cls(api, appliance_data, zone=zone)
            if appliance.mac_address:
                try:
                    await appliance.load_commands()
                    await appliance.load_command_history()
                    await appliance.load_favourites()

                    await appliance.load_attributes()
                    await appliance.load_statistics()
                except (KeyError, ValueError, IndexError) as error:
                    _LOGGER.exception(error)
                    _LOGGER.error("Device data - %s", appliance_data)
                finally:
                    yield appliance

    def _get_nested_item(self, item: str) -> Any:
        result: list[Any] | dict[str, Any] = self.data
        for key in item.split("."):
            if isinstance(result, list) and key.isdecimal():
                result = result[int(key)]
            elif isinstance(result, dict):
                result = result[key]
        return result

    def __getitem__(self, item: str) -> Any:
        if self.zone:
            item += f"Z{self.zone}"
        if "." in item:
            return self._get_nested_item(item)
        if item in self.data:
            return self.data[item]
        if item in self.attributes["parameters"]:
            return self.attributes["parameters"][item].value
        return self.info[item]

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
        attribute: str = self._data.get(name, "")
        if attribute and self.zone:
            zone = " Z" if frontend else "_z"
            return f"{attribute}{zone}{self.zone}"
        return attribute

    @property
    def appliance_model_id(self) -> str:
        return str(self._data.get("applianceModelId", ""))

    @property
    def appliance_type(self) -> str:
        return str(self._data.get("applianceTypeName", ""))

    @property
    def mac_address(self) -> str:
        return str(self._data.get("macAddress", ""))

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
        if code := self._data.get("code"):
            return code

        serial_number: str = self.info.get("serialNumber", "")
        return serial_number[:8] if len(serial_number) < 18 else serial_number[:11]

    @property
    def model_id(self) -> int:
        return int(self._data.get("applianceModelId", 0))

    @property
    def options(self) -> dict[str, Any]:
        return dict(self._appliance_model.get("options", {}))

    @property
    def commands(self) -> dict[str, HonCommand]:
        return self._commands

    @property
    def attributes(self) -> dict[str, Any]:
        return self._attributes

    @property
    def statistics(self) -> dict[str, Any]:
        return self._statistics

    @property
    def info(self) -> dict[str, Any]:
        return self._data

    @property
    def additional_data(self) -> dict[str, Any]:
        return self._additional_data

    @throttle
    async def update(self) -> None:
        await self.load_attributes()
        self.sync_params_to_command("settings")

    @property
    def settings(self) -> dict[str, HonParameter]:
        return {
            f"{name}.{key}": command.settings.get(key, HonParameter("", {}, ""))
            for name, command in self._commands.items()
            for key in command.setting_keys
        }

    @property
    def available_settings(self) -> list[str]:
        return [
            f"{name}.{key}"
            for name, command in self._commands.items()
            for key in command.setting_keys
        ]

    @property
    def data(self) -> dict[str, Any]:
        result = {
            "attributes": self.attributes,
            "appliance": self.info,
            "statistics": self.statistics,
            "additional_data": self._additional_data,
        }
        return result

    @property
    def diagnose(self) -> str:
        return diagnose.yaml_export(self, anonymous=True)

    async def data_archive(self, path: Path) -> str:
        return await diagnose.zip_archive(self, path, anonymous=True)

    def sync_command_to_params(self, command_name: str) -> None:
        if command := self.commands.get(command_name):
            for key in self.attributes.get("parameters", {}):
                if new := command.parameters.get(key):
                    self.attributes["parameters"][key].update(
                        str(new.intern_value), shield=True
                    )

    def sync_params_to_command(self, command_name: str) -> None:
        if command := self.commands.get(command_name):
            for key in command.setting_keys:
                if (
                    new := self.attributes.get("parameters", {}).get(key)
                ) is not None and new.value != "":
                    setting = command.settings[key]
                    try:
                        if not isinstance(setting, HonParameterRange):
                            command.settings[key].value = str(new.value)
                        else:
                            command.settings[key].value = float(new.value)
                    except ValueError as error:
                        _LOGGER.info("Can't set %s - %s", key, error)

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

    async def load_commands(self):
        params: dict[str, str | int] = {
            "os": const.OS,
            "appVersion": const.APP_VERSION,
            "applianceType": self.appliance_type,
            "applianceModelId": self.appliance_model_id,
            "macAddress": self.mac_address,
            "code": self.code,
        }
        if firmware_id := self.info.get("eepromId"):
            params["firmwareId"] = firmware_id
        if firmware_version := self.info.get("fwVersion"):
            params["fwVersion"] = firmware_version
        if series := self.info.get("series"):
            params["series"] = series

        payload = await self._api.call("retrieve", params=params)

        if payload.get("resultCode") == "0":
            self._appliance_model = payload.pop("applianceModel", {})
            self._commands, self._additional_data = loader(self, payload)
            self.sync_params_to_command("settings")

    async def load_command_history(self):
        command_history = await self._api.call(
            f"appliance/{self.mac_address}/history",
            response_path=("payload", "history"),
        )

        recover_last_command_states(self._commands, command_history)

    async def load_favourites(self):
        favourites = (
            await self._api.call(
                f"appliance/{self.mac_address}/favourite",
                response_path=("payload", "favourites"),
            )
            or []
        )

        add_favourites(self._commands, favourites)

    # TODO: Method not used
    async def load_last_activity(self) -> dict[str, Any]:
        return await self._api.call(
            "retrieve-last-activity",
            params={"macAddress": self.mac_address},
            response_path=("attributes",),
        )

    # TODO: Method not used
    async def load_appliance_data(self) -> dict[str, Any]:
        return await self._api.call(
            "appliance-model",
            params={"code": self.code, "macAddress": self.mac_address},
            response_path=("payload", "applianceModel"),
        )

    async def load_attributes(self) -> dict[str, Any]:
        payload = await self._api.call(
            "context",
            params={
                "macAddress": self.mac_address,
                "applianceType": self.appliance_type,
                "category": "CYCLE",
            },
        )

        self_params = self._attributes.setdefault("parameters", {})
        for name, values in payload.get("shadow", {}).get("parameters", {}).items():
            if name in self_params:
                self_params[name].update(values)
            else:
                self_params[name] = HonAttribute(values)

        program = int(self_params.get("prCode", "0"))
        cmd = self.settings.get("startProgram.program")

        self._attributes["programName"] = HonAttribute(
            cmd.ids.get(program)
            if program and isinstance(cmd, HonParameterProgram)
            else "No Program"
        )

        self._attributes["connected"] = HonAttribute(
            str(int(payload.get("lastConnEvent", {}).get("category") != "DISCONNECTED"))
        )

        return payload

    async def load_statistics(self) -> dict[str, Any]:
        statistics = await self._api.call(
            "statistics",
            params={
                "macAddress": self.mac_address,
                "applianceType": self.appliance_type,
            },
        )

        maintenance = await self.load_maintenance_cycle()

        self._statistics = {**statistics, **maintenance}

    async def load_maintenance_cycle(self) -> dict[str, Any]:
        return await self._api.call(
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
            "applianceOptions": self.options,
            "device": self._api._device.get(mobile=True),
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

            result = await self._api.call("send", json=data)
            rval = result.get("resultCode") == "0"

            if rval:
                return rval

            raise exceptions.ApiError("Error sending command data", pformat(data))
