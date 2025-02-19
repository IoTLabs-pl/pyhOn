import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Any, TypeAlias
from urllib.parse import urlencode

import backoff
from aiomqtt import Client, Message, MqttError, ProtocolVersion, Topic

from pyhon import const
from pyhon.apis import device

from .tls import create_tls_context

if TYPE_CHECKING:
    from collections.abc import Callable

    from aiomqtt.types import PayloadType

    from pyhon.apis.auth import Authenticator

    Callback: TypeAlias = Callable[[PayloadType], None]


_LOGGER = logging.getLogger(__name__)
_BACKOFF_LOGGER = logging.getLogger(f"{__name__}.backoff")
_PAHO_LOGGER = logging.getLogger(f"{__name__}.paho")


_PAHO_LOGGER.addFilter(lambda record: "PINGRESP" not in record.msg)
_PAHO_LOGGER.addFilter(lambda record: "PINGREQ" not in record.msg)


class Subscription:
    def __init__(self, topic: Topic):
        self.topic = topic
        self.callbacks = set()
        self.active = False

    def add_callback(self, callback: "Callback"):
        self.callbacks.add(callback)

    def as_subscription_tuple(self):
        return str(self.topic), 0


class SubscriptionManager:
    def __init__(self):
        self.entries: dict[Topic, Subscription] = {}
        self.outdated = asyncio.Event()

    def add(self, topic: Topic, callback: "Callback"):
        self.entries.setdefault(topic, Subscription(topic)).add_callback(callback)
        self.outdated.set()

    def __call__(self, message: Message):
        if message.topic in self.entries:
            for callback in self.entries[message.topic].callbacks:
                try:
                    callback(message.payload)
                except Exception:
                    _LOGGER.error(
                        "Error while executing callback %s",
                        callback,
                        exc_info=True,
                    )

    async def subscribe_on_broker(self, client: Client):
        unsubscribed = [sub for sub in self.entries.values() if not sub.active]
        if not unsubscribed:
            return

        to_subscribe = [sub.as_subscription_tuple() for sub in unsubscribed]

        await client.subscribe(to_subscribe)

        for sub in unsubscribed:
            sub.active = True

        _LOGGER.info("Subscribed to topics: %s", to_subscribe)
        self.outdated.clear()

    def mark_inactive(self):
        for sub in self.entries.values():
            sub.active = False
        self.outdated.set()

    async def watchdog_task(self, client: Client):
        try:
            while True:
                await self.outdated.wait()
                await self.subscribe_on_broker(client)
        finally:
            self.mark_inactive()


class MQTTClient(AbstractAsyncContextManager["MQTTClient"]):
    """
    MQTTClient is a context manager that handles the connection to the MQTT broker.
    It is responsible for subscribing to topics and dispatching messages to the appropriate callbacks.
    Subscription topic must be defined before entering the context manager.

    TODO: Implement a way to dynamically subscribe to topics while the client is running.
    """

    def __init__(
        self,
        authenticator: "Authenticator",
    ) -> None:
        self.loop_task: asyncio.Task | None = None

        self._auth = authenticator
        self._subscriptions = SubscriptionManager()

    def subscribe(self, topic: str, callback: "Callable[[PayloadType], None]") -> None:
        self._subscriptions.add(Topic(topic), callback)

    async def _get_mqtt_username(self) -> str:
        query_params = {
            "x-amz-customauthorizer-name": const.MQTT_AUTHORIZER,
            "x-amz-customauthorizer-signature": await self._auth.get_iot_core_token(),
            "token": await self._auth.get_id_token(),
        }
        return "?" + urlencode(query_params)

    async def __aenter__(self) -> "MQTTClient":
        self.loop_task = asyncio.create_task(self.loop())
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.loop_task.cancel()
        try:
            await self.loop_task
        except asyncio.CancelledError:
            pass

    @asynccontextmanager
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_value=300,
        max_tries=10,
        logger=_BACKOFF_LOGGER,
    )
    async def connect(self) -> AsyncIterator[Client]:
        async with Client(
            hostname=const.MQTT_ENDPOINT,
            port=const.MQTT_PORT,
            identifier=device.MQTT_CLIENT_ID,
            username=await self._get_mqtt_username(),
            protocol=ProtocolVersion.V5,
            tls_context=await create_tls_context("mqtt"),
            timeout=15,
            logger=_PAHO_LOGGER,
        ) as client:
            _LOGGER.info("Connected to MQTT broker successfully")
            watchdog_task = asyncio.create_task(
                self._subscriptions.watchdog_task(client)
            )

            try:
                yield client
            finally:
                watchdog_task.cancel()
                try:
                    await watchdog_task
                except asyncio.CancelledError:
                    pass

    @backoff.on_exception(
        backoff.constant,
        MqttError,
        interval=1,
        logger=_BACKOFF_LOGGER,
    )
    async def loop(self) -> None:
        async with self.connect() as client:
            async for message in client.messages:
                _LOGGER.debug(
                    "Received message on topic %s: %s", message.topic, message.payload
                )
                self._subscriptions(message)
