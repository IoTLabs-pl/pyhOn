from typing import TYPE_CHECKING

from ._base import SessionWrapper

if TYPE_CHECKING:
    from httpx import AsyncClient

    from pyhon.apis.auth import Authenticator


# TODO: Install Throttler on Data session


class DataSessionWrapper(SessionWrapper):
    def __init__(
        self,
        auth: "Authenticator",
        session: "AsyncClient",
    ) -> None:
        super().__init__(session=session)
        self._auth = auth

    async def _extra_headers(self) -> dict[str, str]:
        return {
            "cognito-token": await self._auth.get_cognito_token(),
            "id-token": await self._auth.get_id_token(),
            **(await super()._extra_headers()),
        }
