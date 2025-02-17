import asyncio
import logging
import ssl
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import backoff
from aiomqtt import Client, MqttError, ProtocolVersion, Topic

from pyhon import const
from pyhon.apis import device as HonDevice

if TYPE_CHECKING:
    from collections.abc import Callable

    from aiomqtt.types import PayloadType

    from pyhon.apis.auth import Authenticator


_LOGGER = logging.getLogger(__name__)
_BACKOFF_LOGGER = logging.getLogger(f"{__name__}.backoff")
_PAHO_LOGGER = logging.getLogger(f"{__name__}.paho")


_PAHO_LOGGER.addFilter(lambda record: "PINGRESP" not in record.msg)
_PAHO_LOGGER.addFilter(lambda record: "PINGREQ" not in record.msg)


class MQTTClient(AbstractAsyncContextManager["MQTTClient"]):
    """
    MQTTClient is a context manager that handles the connection to the MQTT broker.
    It is responsible for subscribing to topics and dispatching messages to the appropriate callbacks.
    Subscription topic must be defined before entering the context manager.

    TODO: Maybe implement a way to dynamically subscribe to topics while the client is running.
    """

    def __init__(
        self,
        authenticator: "Authenticator",
    ) -> None:
        self.loop_task: asyncio.Task[None] | None = None

        self._auth = authenticator
        self._subscriptions: dict[Topic, set["Callable[[PayloadType], None]"]] = {}

    def subscribe(self, topic: str, callback: "Callable[[PayloadType], None]") -> None:
        self._subscriptions.setdefault(Topic(topic), set()).add(callback)

    async def _get_mqtt_username(self) -> str:
        query_params = {
            "x-amz-customauthorizer-name": const.MQTT_AUTHORIZER,
            "x-amz-customauthorizer-signature": await self._auth.get_iot_core_token(),
            "token": await self._auth.get_id_token(),
        }
        return "?" + urlencode(query_params)

    def _loop_break(self, task: asyncio.Task[None]) -> None:
        self.loop_task = None
        with suppress(asyncio.CancelledError):
            _LOGGER.error("MQTT loop broken", exc_info=task.exception())

    async def __aenter__(self) -> "MQTTClient":
        self.loop_task = asyncio.create_task(self.loop())
        self.loop_task.add_done_callback(self._loop_break)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self.loop_task:
            self.loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self.loop_task

    @asynccontextmanager
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_value=300,
        max_tries=10,
        logger=_BACKOFF_LOGGER,
    )
    async def connect(self) -> AsyncIterator[Client]:
        # tls_context = ssl.create_default_context()
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        tls_context.check_hostname = False
        tls_context.verify_mode = ssl.VerifyMode.CERT_NONE
        tls_context.set_alpn_protocols([const.MQTT_ALPN_PROTOCOL])

        async with Client(
            hostname=const.MQTT_ENDPOINT,
            port=const.MQTT_PORT,
            identifier=HonDevice.MQTT_CLIENT_ID,
            username=await self._get_mqtt_username(),
            protocol=ProtocolVersion.V5,
            logger=_PAHO_LOGGER,
            tls_context=tls_context,
        ) as client:
            _LOGGER.info("Connected to MQTT broker successfully")
            await client.subscribe([(str(topic), 0) for topic in self._subscriptions])
            _LOGGER.info("Subscribed to topics %s", list(self._subscriptions))

            try:
                yield client
            finally:
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
                if message.topic in self._subscriptions:
                    for callback in self._subscriptions[message.topic]:
                        try:
                            callback(message.payload)
                        except Exception:
                            _LOGGER.error(
                                "Error while executing callback %s",
                                callback,
                                exc_info=True,
                            )
