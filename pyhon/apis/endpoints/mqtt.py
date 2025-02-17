from datetime import datetime

from pydantic import ValidationInfo, field_validator

from ..dto._base import BaseModel
from ..dto.parameter import Parameter


class MQTTUpdatePayload(BaseModel):
    appliance_type_name: str
    event_id: int
    mac_address: str
    timestamp: datetime
    transaction_id: str

    parameters: list[Parameter]

    @field_validator("parameters", mode="before")
    def inject_timestamp(cls, v, info: ValidationInfo):
        try:
            for parameter in v:
                parameter["last_update"] = info.data["timestamp"]
        finally:
            return v
