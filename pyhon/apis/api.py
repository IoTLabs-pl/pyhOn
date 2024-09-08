import json
import logging
from collections.abc import Sequence
from contextlib import AsyncExitStack
from pathlib import Path
from types import TracebackType
from typing import Any, Self, cast, no_type_check

from aiohttp import ClientSession

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
