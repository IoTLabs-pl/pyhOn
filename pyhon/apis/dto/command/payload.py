from datetime import UTC, datetime
from typing import Annotated

from pydantic import (
    Field,
    SerializerFunctionWrapHandler,
    field_serializer,
    model_serializer,
)

from ...device import descriptor
from .._base import BaseModel, Data_T_Union

_DEVICE = descriptor(True)
_ATTRIBUTES = {
    "channel": "mobileApp",
    "origin": "standardProgram",
    "energyLabel": "0",
}


class CommandPayload(BaseModel):
    ancillary_parameters: dict[str, Data_T_Union]
    appliance_options: dict[str, str]
    appliance_type: str
    attributes: Annotated[dict[str, str], Field(default=_ATTRIBUTES)]
    command_name: str
    device: Annotated[dict[str, Data_T_Union], Field(default=_DEVICE)]
    mac_address: str
    parameters: dict[str, Data_T_Union]
    program_name: str
    timestamp: Annotated[datetime, Field(default=lambda: datetime.now(UTC))]
    transaction_id: Annotated[str, Field(default=None)]

    @field_serializer("ancillary_parameters", "parameters", mode="wrap")
    @staticmethod
    def _serialize_values_as_str(
        v: dict[str, Data_T_Union],
        nxt: SerializerFunctionWrapHandler,
    ) -> dict[str, Data_T_Union]:
        return {k: str(v) for k, v in nxt(v).items()}

    @field_serializer("timestamp", mode="wrap")
    @staticmethod
    def _trim_microseconds(v: datetime, nxt: SerializerFunctionWrapHandler) -> str:
        return nxt(v).replace("000Z", "Z")

    @model_serializer(mode="wrap")
    def _match_transaction_id(self, nxt: SerializerFunctionWrapHandler):
        s = nxt(self)

        if not s["transaction_id"].endswith(s["timestamp"]):
            s["transaction_id"] = f'{s['mac_address']}_{s['timestamp']}'

        return s
