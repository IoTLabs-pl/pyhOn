from typing import TYPE_CHECKING

from ._base import SessionWrapper

if TYPE_CHECKING:
    from httpx import AsyncClient

    from pyhon.apis.auth import Authenticator


class DataSessionWrapper(SessionWrapper):
    def __init__(
        self,
        auth: "Authenticator",
        session: "AsyncClient | None" = None,
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
