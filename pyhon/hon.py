from collections.abc import Callable
from contextlib import AsyncExitStack
import json
import logging
from pathlib import Path
from types import TracebackType

from aiohttp import ClientSession
from typing_extensions import Self

from pyhon.appliance import HonAppliance
from pyhon.connection.device import HonDevice
from pyhon.const import MOBILE_ID
from pyhon.connection.api import HonAPI, TestAPI
from pyhon.connection.auth import HonAuth
from pyhon.connection.mqtt import MQTTClient

_LOGGER = logging.getLogger(__name__)


# pylint: disable=too-many-instance-attributes
class Hon:
    def __init__(
        self,
        email: str,
        password: str,
        session: ClientSession | None = None,
        mobile_id: str = MOBILE_ID,
        refresh_token: str | None = None,
        test_data_path: Path | None = None,
    ):
        self._test_data_path = test_data_path or Path().cwd()
        self._resources = AsyncExitStack()
        self._notify_function: Callable[[], None] | None = None

        self.appliances: list[HonAppliance] = []

        device = HonDevice(mobile_id)
        authenticator = HonAuth(email, password, device, session, refresh_token)

        self._api = HonAPI(device, authenticator, session)
        self._mqtt_client = MQTTClient(
            authenticator, device, self.appliances, self.notify
        )

    async def __aenter__(self) -> Self:
        return await self.setup()

    async def setup(self) -> Self:
        await self._resources.enter_async_context(self._api)

        appliances_data = await self._api.load_appliances_data()

        self.appliances.extend(
            [
                appliance
                for appliance_data in appliances_data
                async for appliance in HonAppliance.create_from_data(
                    self._api, appliance_data
                )
            ]
        )

        if (
            self._test_data_path
            and (
                test_data := self._test_data_path / "hon-test-data" / "test_data"
            ).exists()
            or (test_data := test_data / "..").exists()
        ):
            api = TestAPI(test_data)
            for appliance in await api.load_appliances():
                await self._create_appliance(appliance, api)

        await self._resources.enter_async_context(self._mqtt_client)

        return self

    def subscribe_updates(self, notify_function: Callable[[], None]) -> None:
        self._notify_function = notify_function

    def notify(self) -> None:
        if self._notify_function:
            self._notify_function()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._resources.aclose()
