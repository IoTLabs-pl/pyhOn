from collections.abc import Callable
from contextlib import AsyncExitStack, nullcontext
from pathlib import Path
from typing import Any

from aiohttp import ClientSession
from typing_extensions import Self

from pyhon.apis.api import API, TestAPI
from pyhon.apis.auth import Authenticator
from pyhon.apis.mqtt import MQTTClient
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

        self._auth = auth = Authenticator(email, password, session, refresh_token)

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

        for appliance_data in appliances_data:
            async for a in Appliance.create_from_data(self._api, appliance_data):
                self.appliances.append(a)

        if (
            self._test_data_path
            and (
                test_data := self._test_data_path / "hon-test-data" / "test_data"
            ).exists()
            or (test_data := test_data / "..").exists()
        ):
            appliances_data = await TestAPI(test_data).load_appliances()
            for appliance_data in appliances_data:
                async for a in Appliance.create_from_data(self._api, appliance_data):
                    self.appliances.append(a)

        await self._resources.enter_async_context(self.mqtt_client)

        return self

    async def close(self) -> str | None:
        await self._resources.aclose()
        return self._auth.refresh_token

    def subscribe_updates(self, notify_function: Callable[[], None]) -> None:
        self._notify_function = notify_function

    def notify(self) -> None:
        if self._notify_function:
            self._notify_function()

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
