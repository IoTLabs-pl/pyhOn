from collections.abc import Sequence
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any, Self, cast

from httpx import AsyncClient

from pyhon import const, exceptions
from pyhon.apis.auth import Authenticator
from pyhon.apis.wrappers import AnonymousSessionWrapper, DataSessionWrapper


class API:
    def __init__(
        self,
        authenticator: Authenticator | None = None,
        session: AsyncClient | None = None,
    ) -> None:
        self._resources = AsyncExitStack()

        self._anonymous_session = AnonymousSessionWrapper(session)
        self.__session = (
            DataSessionWrapper(authenticator, session) if authenticator else None
        )

    @property
    def _session(self) -> DataSessionWrapper:
        if self.__session is None:
            raise exceptions.MissingCredentialsException()
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
        anonymous: bool = False,
    ) -> Any:
        result: dict[str, Any] = {}
        session: AnonymousSessionWrapper | DataSessionWrapper

        if anonymous:
            session = self._anonymous_session
            url = f"{const.API_URL}/{endpoint}"
        else:
            session = self._session
            url = f"{const.API_URL}/commands/v1/{endpoint}"

        if endpoint.startswith("http"):
            url = endpoint

        response = await session.request(
            "POST" if data else "GET", url, params=params, json=data
        )
        result = response.json()
        for field in response_path:
            result = result.get(field, {})

        return result

    async def load_appliances_data(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self.call("appliance", response_path=("payload", "appliances")),
        )

    async def get_translations(self, language: str) -> dict[str, str]:
        lang_url: str = await self.call(
            "app-config",
            data={
                "languageCode": language,
                "beta": True,
                "appVersion": const.APP_VERSION,
                "os": const.OS,
            },
            anonymous=True,
            response_path=("payload", "language", "jsonPath"),
        )

        return cast(
            dict[str, str], await self.call(lang_url, anonymous=True, response_path=())
        )
