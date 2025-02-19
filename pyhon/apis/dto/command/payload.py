from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_serializer,
    model_serializer,
)

from ...device import descriptor as DeviceDescriptor
from .._base import BaseModel, Data_T_Union

_DEVICE = DeviceDescriptor(mobile=True)
_ATTRIBUTES = {
    "channel": "mobileApp",
    "origin": "standardProgram",
    "energyLabel": "0",
}


class CommandPayload(BaseModel):
    ancillary_parameters: dict[str, Data_T_Union]
    appliance_options: Annotated[dict[str, str], Field(default_factory=dict)]
    appliance_type: str
    attributes: Annotated[dict[str, str], Field(default=_ATTRIBUTES)]
    command_name: str
    device: Annotated[dict[str, Data_T_Union], Field(default=_DEVICE)]
    mac_address: str
    parameters: dict[str, Data_T_Union]
    program_name: Annotated[str | None, Field(default=None)]
    timestamp: Annotated[datetime, Field(default_factory=lambda: datetime.now(UTC))]
    transaction_id: Annotated[str | None, Field(default=None)]

    @field_serializer("ancillary_parameters", "parameters", mode="wrap")
    @staticmethod
    def _serialize_values_as_str(
        v: dict[str, Data_T_Union],
        nxt: SerializerFunctionWrapHandler,
    ) -> dict[str, Data_T_Union]:
        return {k: str(v) for k, v in nxt(v).items()}

    # TODO: Maybe remove?
    @field_serializer("timestamp", mode="wrap")
    @staticmethod
    def _trim_microseconds(v: datetime, nxt: SerializerFunctionWrapHandler) -> str:
        return nxt(v).replace("000Z", "Z")

    @model_serializer(mode="wrap")
    def _match_transaction_id(self, nxt: SerializerFunctionWrapHandler):
        s = nxt(self)

        if not s.get("transactionId"):
            s["transactionId"] = f"{s['macAddress']}_{s['timestamp']}"

        return s
