from collections.abc import Callable
from contextlib import AsyncExitStack, nullcontext
from pathlib import Path
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
        mqtt: bool = False,
        refresh_token: str | None = None,
        test_data_path: Path | None = None,
    ):
        self._test_data_path = test_data_path or Path().cwd()
        self._resources = AsyncExitStack()
        self._notify_function: Callable[[], None] | None = None

        self.appliances: list[Appliance] = []

        self.auth = auth = Authenticator(email, password, session, refresh_token)

        self._api = API(auth, session)
        self.mqtt_client = (
            MQTTClient(auth, self.appliances, self.notify) if mqtt else nullcontext()
        )

    @property
    def is_mqtt_enabled(self) -> bool:
        return isinstance(self.mqtt_client, MQTTClient)

    async def __aenter__(self) -> Self:
        return await self.setup()

    async def setup(self) -> Self:
        await self._resources.enter_async_context(self._api)

        appliances_data = await self._api.load_appliances_data()

        self.appliances.extend(
            [
                await Appliance.create_from_data(self._api, appliance_data)
                for appliance_data in appliances_data
            ]
        )

        await self._resources.enter_async_context(self.mqtt_client)

        return self

    async def aclose(self) -> None:
        return await self._resources.aclose()

    def subscribe_updates(self, notify_function: Callable[[], None]) -> None:
        self._notify_function = notify_function

    def notify(self) -> None:
        if self._notify_function:
            self._notify_function()

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()
