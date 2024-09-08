import asyncio
import json
import logging
import pprint
import ssl
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from functools import cached_property, partial
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlencode

import backoff
from aiomqtt import Client, MqttError, ProtocolVersion, Topic
from paho.mqtt.subscribeoptions import SubscribeOptions

from pyhon import const
from pyhon.apis import device as HonDevice

if TYPE_CHECKING:
    from collections.abc import Callable

    from aiomqtt import Message

    from pyhon.apis.auth import Authenticator
    from pyhon.appliances import Appliance

_LOGGER = logging.getLogger(__name__)
_BACKOFF_LOGGER = logging.getLogger(f"{__name__}.backoff")
_PAHO_LOGGER = logging.getLogger(f"{__name__}.paho")


_PAHO_LOGGER.addFilter(lambda record: "PINGRESP" not in record.msg)
_PAHO_LOGGER.addFilter(lambda record: "PINGREQ" not in record.msg)


class _Payload(dict[Any, Any]):
    def __str__(self) -> str:
        return pprint.pformat(self)


@dataclass(frozen=True)
class Subscription:
    topic: Topic
    handler: partial[None]
    options: SubscribeOptions = SubscribeOptions()

    def as_subscription_tuple(self) -> tuple[str, SubscribeOptions]:
        return str(self.topic), self.options


class MQTTClient(AbstractAsyncContextManager["MQTTClient"]):
    def __init__(
        self,
        authenticator: "Authenticator",
        appliances: "list[Appliance]",
        message_callback: "Callable[[], None] | None" = None,
    ) -> None:
        self.task: asyncio.Task[None] | None = None

        self._appliances = appliances
        self._auth = authenticator
        self._message_callback = message_callback

    async def _get_mqtt_username(self) -> str:
        query_params = {
            "x-amz-customauthorizer-name": const.MQTT_AUTHORIZER,
            "x-amz-customauthorizer-signature": await self._auth.get_iot_core_token(),
            "token": await self._auth.get_id_token(),
        }
        return "?" + urlencode(query_params)

    @cached_property
    def _subscriptions(self) -> dict[Topic, Subscription]:
        handlers = {}

        for appliance in self._appliances:
            handler_protos = {
                "appliancestatus": partial(self._status_handler, appliance),
                "disconnected": partial(self._connection_handler, appliance, False),
                "connected": partial(self._connection_handler, appliance, True),
            }

            topic: str
            for topic in appliance.data.get("topics", {}).get("subscribe", []):
                topic_parts = topic.split("/")
                for topic_part, handler in handler_protos.items():
                    if topic_part in topic_parts:
                        t = Topic(topic)
                        handlers[t] = Subscription(topic=t, handler=handler)

        return handlers

    @staticmethod
    def _status_handler(appliance: "Appliance", message: "Message") -> None:
        payload = _Payload(json.loads(cast(str | bytes | bytearray, message.payload)))
        for parameter in payload["parameters"]:
            appliance.attributes[parameter["parName"]].update(parameter)
        appliance.sync_params_to_command("settings")

        _LOGGER.debug("On topic '%s' received: \n %s", message.topic, payload)

    @staticmethod
    def _connection_handler(
        appliance: "Appliance", connection_status: bool, __message: "Message"
    ) -> None:
        appliance.attributes["connected"].update(connection_status)

    def _loop_break(self, task: asyncio.Task[None]) -> None:
        self.task = None
        with suppress(asyncio.CancelledError):
            _LOGGER.error("MQTT loop broken", exc_info=task.exception())

    async def __aenter__(self) -> "MQTTClient":
        self.task = asyncio.create_task(self.loop())
        self.task.add_done_callback(self._loop_break)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self.task:
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task

    @asynccontextmanager
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_value=300,
        logger=_BACKOFF_LOGGER,
    )
    async def connect_and_subscribe(self) -> AsyncIterator[Client]:
        tls_context = ssl.create_default_context()
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
            await client.subscribe(
                [s.as_subscription_tuple() for s in self._subscriptions.values()]
            )
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
        while True:
            async with self.connect_and_subscribe() as client:
                async for message in client.messages:
                    self._subscriptions[message.topic].handler(message)

                    if self._message_callback:
                        self._message_callback()
