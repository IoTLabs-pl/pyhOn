import asyncio
from dataclasses import InitVar, dataclass, field
from functools import partial
from logging import getLogger

from ..apis import API, api_call
from ..apis.dto.appliance import Appliance as ApplianceDTO
from ..apis.endpoints.mqtt import MQTTUpdatePayload
from ..apis.mqtt import MQTTClient
from .command import Command
from .maintenance_cycle import MaintenanceCycle
from .parameter import Parameter
from .statistics import Statistics

_LOGGER = getLogger(__name__)


@dataclass
class Appliance:
    data: ApplianceDTO
    parameters: dict[str, Parameter] = field(default_factory=dict, init=False)
    commands: dict[str, Command] = field(default_factory=dict, init=False)
    statistics: Statistics | None = field(default=None, init=False)
    maintenance_cycles: dict[str, MaintenanceCycle] = field(
        default_factory=dict, init=False
    )

    api: API = field(repr=False)  # TODO: change to hon instance?
    mqtt_client: InitVar["MQTTClient|None"] = None

    def __post_init__(self, mqtt_client: "MQTTClient|None"):
        if mqtt_client is None:
            return

        for topic in self.data.mqtt_topics:
            match topic.split("/"):
                case [
                    "$aws",
                    "events",
                    "presence",
                    "disconnected",
                    self.data.mac_address,
                ]:
                    callback = partial(self._connection_callback, False)
                case [
                    "$aws",
                    "events",
                    "presence",
                    "connected",
                    self.data.mac_address,
                ]:
                    callback = partial(self._connection_callback, True)
                case [
                    "haier",
                    "things",
                    self.data.mac_address,
                    "event",
                    "appliancestatus",
                    "update",
                ]:
                    callback = self._update_callback
                case _:
                    continue

            mqtt_client.subscribe(topic, callback)

    def _connection_callback(self, connection_state: bool) -> None:
        print(f"Connection state changed to {connection_state}")

    def _update_callback(self, payload) -> None:
        payload = MQTTUpdatePayload.model_validate_json(payload)
        for payload in payload.parameters:
            if parameter := self.parameters.get(payload.key):
                parameter.data = payload
            else:
                _LOGGER.warning(f"Received update for unknown parameter {payload.key}")

    @classmethod
    @api_call
    async def fetch(
        cls,
        api: API,
        mqtt_client: "MQTTClient|None" = None,
        recursive: bool = False,
    ) -> list["Appliance"]:
        response = await api.appliances()
        appliances = [
            cls(api=api, data=data, mqtt_client=mqtt_client)
            for data in response.appliances
        ]

        if recursive:
            await asyncio.gather(*(appliance.load_all() for appliance in appliances))

        return appliances

    async def load_all(self):
        return await asyncio.gather(
            self.load_parameters(),
            self.load_commands(),
            self.load_statistics(),
            self.load_maintenance_cycles(),
            return_exceptions=True,
        )

    @api_call
    async def load_parameters(self) -> None:
        self.parameters.update((p.data.key, p) for p in await Parameter.fetch(self))

    @api_call
    async def load_commands(self) -> None:
        self.commands.update((c.descriptor.key, c) for c in await Command.fetch(self))

    @api_call
    async def load_statistics(self) -> None:
        self.statistics = await Statistics.fetch(self)

    @api_call
    async def load_maintenance_cycles(self) -> None:
        self.maintenance_cycles.update(
            (mc.data.key, mc) for mc in await MaintenanceCycle.fetch(self)
        )
