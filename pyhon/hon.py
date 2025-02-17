from contextlib import AsyncExitStack
from typing import Any, Self

from httpx import AsyncClient

from pyhon.apis import API, Authenticator, MQTTClient, create_httpx_client
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
        close_session: bool = False,
    ):
        self.resources = AsyncExitStack()

        if autoload and (not email or not password):
            raise ValueError("Cannot load data without authentication")

        if session is None:
            session = create_httpx_client()
            
        if close_session:
            self.resources.push_async_exit(session)

        self._auth = auth = Authenticator(email, password, session, refresh_token)
        self._api = API(auth, session)

        self._mqtt_autostart = enable_mqtt
        self._load_appliances = autoload

    async def __aenter__(self) -> Self:
        return await self.setup()

    async def setup(self) -> Self:
        if self._load_appliances:
            await self.load_appliances()

            if self._mqtt_autostart:
                await self.resources.enter_async_context(self.mqtt_client)

        return self

    async def load_appliances(self) -> None:
        self.mqtt_client = MQTTClient(self._auth)
        self.appliances = await Appliance.fetch(
            self._api,
            self.mqtt_client,
            recursive=True,
        )

    async def __aexit__(self, *args: Any) -> None:
        return await self.resources.aclose()
