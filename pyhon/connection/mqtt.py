import asyncio
from dataclasses import dataclass
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import cached_property, partial
import json
import logging
import pprint
import random
import string
import ssl
from typing import Any, TYPE_CHECKING, AsyncIterator, cast
from urllib.parse import urlencode

from aiomqtt import Client, MqttError, ProtocolVersion, Topic
from paho.mqtt.subscribeoptions import SubscribeOptions
import backoff
from pyhon import const


if TYPE_CHECKING:
    from aiomqtt import Message
    from pyhon.appliance import HonAppliance
    from pyhon.connection.auth import HonAuth
    from pyhon.connection.device import HonDevice
    from typing import Callable

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
        authenticator: "HonAuth",
        device: "HonDevice",
        appliances: "list[HonAppliance]",
        message_callback: "Callable[[], None] | None" = None,
    ) -> None:
        self._task: asyncio.Task[None] | None = None

        self._appliances = appliances
        self._auth = authenticator
        self._message_callback = message_callback

        self._client_id = (
            f"{device.mobile_id}_{''.join(random.choices(string.hexdigits, k=16))}"
        )

    async def _get_mqtt_username(self) -> str:
        query_params = {
            "x-amz-customauthorizer-name": const.MQTT_AUTHORIZER,
            "x-amz-customauthorizer-signature": await self._auth.get_iot_core_token(
                force=True
            ),
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

            for topic in appliance.info.get("topics", {}).get("subscribe", []):
                topic_parts = topic.split("/")
                for topic_part, handler in handler_protos.items():
                    if topic_part in topic_parts:
                        t = Topic(topic)
                        handlers[t] = Subscription(topic=t, handler=handler)

        return handlers

    @staticmethod
    def _status_handler(appliance: "HonAppliance", message: "Message") -> None:
        payload = _Payload(json.loads(cast(str | bytes | bytearray, message.payload)))
        for parameter in payload["parameters"]:
            appliance.attributes["parameters"][parameter["parName"]].update(parameter)
        appliance.sync_params_to_command("settings")

        _LOGGER.debug("On topic '%s' received: \n %s", message.topic, payload)

    @staticmethod
    def _connection_handler(
        appliance: "HonAppliance", connection_status: bool, __message: "Message"
    ) -> None:
        appliance.connection = connection_status

    def _loop_break(self, task: asyncio.Task[None]) -> None:
        self._task = None
        try:
            _LOGGER.error("MQTT loop broken", exc_info=task.exception())
        except asyncio.CancelledError:
            pass

    async def __aenter__(self) -> "MQTTClient":
        self._task = asyncio.create_task(self.loop())
        self._task.add_done_callback(self._loop_break)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

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
            identifier=self._client_id,
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
