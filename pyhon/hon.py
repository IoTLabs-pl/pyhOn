from contextlib import AsyncExitStack
from functools import partial
from typing import Any, Self

from httpx import AsyncClient

from pyhon.apis import API, Authenticator, MQTTClient, create_tls_context
from pyhon.entities.appliance import Appliance


class Hon:
    def __init__(
        self,
        email: str,
        password: str,
        session: AsyncClient | None = None,
        refresh_token: str | None = None,
        *,
        enable_mqtt: bool = False,
        autoload: bool = True,
    ):
        self._session = session
        self._auth_factory = partial(
            Authenticator, email, password, refresh_token=refresh_token
        )

        self._mqtt_autostart = enable_mqtt
        self._load_appliances = autoload

        self._resources = AsyncExitStack()

    async def __aenter__(self) -> Self:
        if self._session is None:
            self._session = await self._resources.enter_async_context(
                AsyncClient(verify=await create_tls_context("http"))
            )

        self._auth = self._auth_factory(session=self._session)
        self._api = API(self._auth, self._session)
        self.mqtt_client = MQTTClient(self._auth)

        if self._load_appliances:
            self.appliances = await self.get_appliances()

        if self._mqtt_autostart:
            self.mqtt_client = await self._resources.enter_async_context(
                self.mqtt_client
            )

        return self

    async def __aexit__(self, *args: Any) -> None:
        return await self._resources.aclose()

    async def get_appliances(self, recursive: bool = True) -> list[Appliance]:
        return await Appliance.fetch(
            self._api,
            self.mqtt_client,
            recursive=recursive,
        )
