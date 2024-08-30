from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import aiohttp

from ._base import SessionWrapper, SessionWrapperMethod

if TYPE_CHECKING:
    from pyhon.apis.auth import Authenticator


class DataSessionWrapper(SessionWrapper):
    def __init__(
        self,
        auth: "Authenticator",
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        super().__init__(session=session)
        self._auth = auth

    async def _extra_headers(self) -> dict[str, str]:
        return {
            "cognito-token": await self._auth.get_cognito_token(),
            "id-token": await self._auth.get_id_token(),
            **(await super()._extra_headers()),
        }

    async def __aenter__(self) -> "DataSessionWrapper":
        await super().__aenter__()
        await self._resources.enter_async_context(self._auth)
        return self

    @asynccontextmanager
    async def request(
        self, method: SessionWrapperMethod, *args: Any, **kwargs: Any
    ) -> AsyncIterator[aiohttp.ClientResponse]:
        async with super().request(method, *args, **kwargs) as response:
            await response.json()  # Throws exception if response is not JSON
            yield response
