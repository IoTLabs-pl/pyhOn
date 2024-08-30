import json
import logging
from collections.abc import Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from types import TracebackType
from typing import Any, cast, no_type_check

from aiohttp import ClientSession
from typing_extensions import Self

from pyhon import const, exceptions
from pyhon.apis.auth import Authenticator
from pyhon.apis.wrappers import AnonymousSessionWrapper, DataSessionWrapper
from pyhon.appliances import Appliance

_LOGGER = logging.getLogger(__name__)


# pylint: disable=too-many-instance-attributes
class API:
    def __init__(
        self,
        authenticator: Authenticator | None = None,
        session: ClientSession | None = None,
    ) -> None:
        self._resources = AsyncExitStack()

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

    async def call(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        response_path: Sequence[str] = ("payload",),
    ) -> Any:
        result: dict[str, Any] = {}
        async with self._session.request(
            "POST" if data else "GET",
            f"{const.API_URL}/commands/v1/{endpoint}",
            params=params,
            json=data,
        ) as response:
            result = await response.json()
            for field in response_path:
                result = result.get(field, {})

        return result

    async def load_appliances_data(self) -> list[dict[str, Any]]:
        return (
            await self.call("appliance", response_path=("payload", "appliances")) or []
        )

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


class TestAPI(API):
    def __init__(self, path: Path):
        super().__init__()
        self._anonymous = True
        self._path: Path = path

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        pass

    def _load_json(self, appliance: Appliance, file: str) -> dict[str, Any]:
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

    async def load_commands(self, appliance: Appliance) -> dict[str, Any]:
        return self._load_json(appliance, "commands")

    @no_type_check
    async def load_command_history(self, appliance: Appliance) -> list[dict[str, Any]]:
        return self._load_json(appliance, "command_history")

    async def load_favourites(self, _appliance: Appliance) -> list[dict[str, Any]]:
        return []

    async def load_last_activity(self, _appliance: Appliance) -> dict[str, Any]:
        return {}

    async def load_appliance_data(self, appliance: Appliance) -> dict[str, Any]:
        return self._load_json(appliance, "appliance_data")

    async def load_attributes(self, appliance: Appliance) -> dict[str, Any]:
        return self._load_json(appliance, "attributes")

    async def load_statistics(self, appliance: Appliance) -> dict[str, Any]:
        return self._load_json(appliance, "statistics")

    async def load_maintenance(self, appliance: Appliance) -> dict[str, Any]:
        return self._load_json(appliance, "maintenance")

    async def send_command(
        self,
        _appliance: Appliance,
        _command: str,
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
