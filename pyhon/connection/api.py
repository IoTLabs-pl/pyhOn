import json
from contextlib import AsyncExitStack
import logging
from pathlib import Path
from pprint import pformat
from types import TracebackType
from typing import Any, cast, no_type_check
import sys

from aiohttp import ClientSession, ClientResponseError
from typing_extensions import Self

from pyhon import const, exceptions
from pyhon.appliance import HonAppliance
from pyhon.connection.device import HonDevice
from pyhon.connection.handler.anonym import AnonymousSessionWrapper
from pyhon.connection.handler.hon import DataSessionWrapper
from pyhon.connection.auth import HonAuth

if sys.version_info >= (3, 11):
    from datetime import datetime, UTC
else:
    from datetime import datetime, timezone

    UTC = timezone.utc

_LOGGER = logging.getLogger(__name__)


# pylint: disable=too-many-instance-attributes
class HonAPI:
    def __init__(
        self,
        device: HonDevice | None = None,
        authenticator: HonAuth | None = None,
        session: ClientSession | None = None,
    ) -> None:
        self._resources = AsyncExitStack()
        self._device = device or HonDevice(const.MOBILE_ID)

        self._anonymous_session = AnonymousSessionWrapper(session)
        self.__session = (
            DataSessionWrapper(authenticator, session) if authenticator else None
        )

    @property
    def _session(self) -> DataSessionWrapper:
        if self.__session is None:
            raise exceptions.NoAuthenticationException(
                "No authentication data provided"
            )
        return self.__session

    async def __aenter__(self) -> Self:
        await self._resources.enter_async_context(self._anonymous_session)
        if self.__session:
            await self._resources.enter_async_context(self.__session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._resources.aclose()

    async def load_appliances(self) -> list[dict[str, Any]]:
        async with self._session.get(f"{const.API_URL}/commands/v1/appliance") as resp:
            result = await resp.json()
            if result and (payload := result.get("payload")):
                return cast(list[dict[str, Any]], payload.get("appliances", []))
            return []

    async def load_commands(self, appliance: HonAppliance) -> dict[str, Any]:
        params: dict[str, str | int] = {
            "applianceType": appliance.appliance_type,
            "applianceModelId": appliance.appliance_model_id,
            "macAddress": appliance.mac_address,
            "os": const.OS,
            "appVersion": const.APP_VERSION,
            "code": appliance.code,
        }
        # TODO: Check if this is correct
        if firmware_id := appliance.info.get("eepromId"):
            params["firmwareId"] = firmware_id
        if firmware_version := appliance.info.get("fwVersion"):
            params["fwVersion"] = firmware_version
        if series := appliance.info.get("series"):
            params["series"] = series

        async with self._session.get(
            f"{const.API_URL}/commands/v1/retrieve", params=params
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                if payload.get("resultCode") == "0":
                    return cast(dict[str, Any], payload)

            return {}

    async def load_command_history(
        self, appliance: HonAppliance
    ) -> list[dict[str, Any]]:
        async with self._session.get(
            f"{const.API_URL}/commands/v1/appliance/{appliance.mac_address}/history"
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(list[dict[str, Any]], payload.get("history", []))

            return []

    async def load_favourites(self, appliance: HonAppliance) -> list[dict[str, Any]]:
        async with self._session.get(
            f"{const.API_URL}/commands/v1/appliance/{appliance.mac_address}/favourite"
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(list[dict[str, Any]], payload.get("favourites", []))

            return []

    async def load_last_activity(self, appliance: HonAppliance) -> dict[str, Any]:
        async with self._session.get(
            f"{const.API_URL}/commands/v1/retrieve-last-activity",
            params={"macAddress": appliance.mac_address},
        ) as response:
            result = await response.json()
            if result and (attributes := result.get("attributes")):
                return cast(dict[str, Any], attributes)

        return {}

    async def load_appliance_data(self, appliance: HonAppliance) -> dict[str, Any]:
        async with self._session.get(
            f"{const.API_URL}/commands/v1/appliance-model",
            params={"code": appliance.code, "macAddress": appliance.mac_address},
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(dict[str, Any], payload.get("applianceModel", {}))

        return {}

    async def load_attributes(self, appliance: HonAppliance) -> dict[str, Any]:
        async with self._session.get(
            f"{const.API_URL}/commands/v1/context",
            params={
                "macAddress": appliance.mac_address,
                "applianceType": appliance.appliance_type,
                "category": "CYCLE",
            },
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(dict[str, Any], payload)

            return {}

    async def load_statistics(self, appliance: HonAppliance) -> dict[str, Any]:
        async with self._session.get(
            f"{const.API_URL}/commands/v1/statistics",
            params={
                "macAddress": appliance.mac_address,
                "applianceType": appliance.appliance_type,
            },
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(dict[str, Any], payload)

            return {}

    async def load_maintenance(self, appliance: HonAppliance) -> dict[str, Any]:
        try:

            async with self._session.get(
                f"{const.API_URL}/commands/v1/maintenance",
                params={"macAddress": appliance.mac_address},
            ) as response:
                result = await response.json()
                if result and (payload := result.get("payload")):
                    return cast(dict[str, Any], payload)

        except ClientResponseError:
            pass

        return {}

    async def send_command(
        self,
        appliance: HonAppliance,
        command: str,
        parameters: dict[str, Any],
        ancillary_parameters: dict[str, Any],
        program_name: str = "",
    ) -> bool:
        # TODO: Check if this is correct (non Zulu Specifier)
        now = datetime.now(UTC).isoformat(timespec="milliseconds")
        data: dict[str, Any] = {
            "macAddress": appliance.mac_address,
            "timestamp": now,
            "commandName": command,
            "transactionId": f"{appliance.mac_address}_{now}",
            "applianceOptions": appliance.options,
            "device": self._device.get(mobile=True),
            "attributes": {
                "channel": "mobileApp",
                "origin": "standardProgram",
                "energyLabel": "0",
            },
            "ancillaryParameters": ancillary_parameters,
            "parameters": parameters,
            "applianceType": appliance.appliance_type,
        }
        if command == "startProgram" and program_name:
            data |= {"programName": program_name.upper()}

        async with self._session.post(
            f"{const.API_URL}/commands/v1/send", json=data
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(bool, payload.get("resultCode") == "0")

            raise exceptions.ApiError("Error sending command", pformat(data))

    async def appliance_configuration(self) -> dict[str, Any]:
        async with self._anonymous_session.get(
            f"{const.API_URL}/config/v1/program-list-rules"
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(dict[str, Any], payload)

            return {}

    async def app_config(
        self, language: str = "en", beta: bool = True
    ) -> dict[str, Any]:

        async with self._anonymous_session.post(
            f"{const.API_URL}/app-config",
            json={
                "languageCode": language,
                "beta": beta,
                "appVersion": const.APP_VERSION,
                "os": const.OS,
            },
        ) as response:
            result = await response.json()
            if result and (payload := result.get("payload")):
                return cast(dict[str, Any], payload)

            return {}

    async def translation_keys(self, language: str = "en") -> dict[str, Any]:
        config = await self.app_config(language=language)
        if url := config.get("language", {}).get("jsonPath"):
            async with self._anonymous_session.get(url) as response:
                return cast(dict[str, Any], await response.json())

        return {}


class TestAPI(HonAPI):
    def __init__(self, path: Path):
        super().__init__()
        self._anonymous = True
        self._path: Path = path

    def _load_json(self, appliance: HonAppliance, file: str) -> dict[str, Any]:
        directory = f"{appliance.appliance_type}_{appliance.appliance_model_id}".lower()
        if not (path := self._path / directory / f"{file}.json").exists():
            _LOGGER.warning("Can't open %s", str(path))
            return {}
        with open(path, "r", encoding="utf-8") as json_file:
            text = json_file.read()
        try:
            data: dict[str, Any] = json.loads(text)
            return data
        except json.decoder.JSONDecodeError as error:
            _LOGGER.error("%s - %s", str(path), error)
            return {}

    async def load_appliances(self) -> list[dict[str, Any]]:
        result = []
        for appliance in self._path.glob("*/"):
            file = appliance / "appliance_data.json"
            with open(file, "r", encoding="utf-8") as json_file:
                try:
                    result.append(json.loads(json_file.read()))
                except json.decoder.JSONDecodeError as error:
                    _LOGGER.error("%s - %s", str(file), error)
        return result

    async def load_commands(self, appliance: HonAppliance) -> dict[str, Any]:
        return self._load_json(appliance, "commands")

    @no_type_check
    async def load_command_history(
        self, appliance: HonAppliance
    ) -> list[dict[str, Any]]:
        return self._load_json(appliance, "command_history")

    async def load_favourites(self, appliance: HonAppliance) -> list[dict[str, Any]]:
        return []

    async def load_last_activity(self, appliance: HonAppliance) -> dict[str, Any]:
        return {}

    async def load_appliance_data(self, appliance: HonAppliance) -> dict[str, Any]:
        return self._load_json(appliance, "appliance_data")

    async def load_attributes(self, appliance: HonAppliance) -> dict[str, Any]:
        return self._load_json(appliance, "attributes")

    async def load_statistics(self, appliance: HonAppliance) -> dict[str, Any]:
        return self._load_json(appliance, "statistics")

    async def load_maintenance(self, appliance: HonAppliance) -> dict[str, Any]:
        return self._load_json(appliance, "maintenance")

    async def send_command(
        self,
        appliance: HonAppliance,
        command: str,
        parameters: dict[str, Any],
        ancillary_parameters: dict[str, Any],
        program_name: str = "",
    ) -> bool:
        _LOGGER.info(
            "%s - %s - %s",
            str(parameters),
            str(ancillary_parameters),
            str(program_name),
        )
        return True
