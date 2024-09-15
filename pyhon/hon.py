from collections.abc import Callable
from contextlib import AsyncExitStack
from typing import Any, Self

from aiohttp import ClientSession

from pyhon.apis import API, Authenticator, MQTTClient
from pyhon.appliances import Appliance


class Hon:
    def __init__(
        self,
        email: str,
        password: str,
        session: ClientSession | None = None,
        refresh_token: str | None = None,
        *,
        start_mqtt: bool = False,
        load_data: bool = True,
    ):
        self._resources = AsyncExitStack()
        self._notify_function: Callable[[], None] | None = None

        self.appliances: list[Appliance] = []
        if load_data and (not email or not password):
            raise ValueError("Cannot load data without authentication")

        self._auth = auth = Authenticator(email, password, session, refresh_token)

        self.mqtt_client = MQTTClient(auth, self.appliances, self.notify)
        self._api = API(auth, session)

        self._mqtt_autostart = start_mqtt
        self._load_data = load_data

    async def __aenter__(self) -> Self:
        return await self.setup()

    async def get_translations(self, language: str)-> dict[str, str]:
        return await self._api.get_translations(language)

    async def setup(self) -> Self:
        await self._resources.enter_async_context(self._api)

        if self._load_data:
            await self.load_data()

        if self._mqtt_autostart:
            await self._resources.enter_async_context(self.mqtt_client)

        return self

    async def load_data(self) -> None:
        appliances_data = await self._api.load_appliances_data()

        self.appliances.extend(
            [
                await Appliance.create_from_data(self._api, appliance_data)
                for appliance_data in appliances_data
            ]
        )

    async def aclose(self) -> None:
        return await self._resources.aclose()

    def subscribe_updates(self, notify_function: Callable[[], None]) -> None:
        self._notify_function = notify_function

    def notify(self) -> None:
        if self._notify_function:
            self._notify_function()

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()
