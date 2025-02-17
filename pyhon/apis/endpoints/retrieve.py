from typing import Annotated, Any

from ..dto._base import Cluster, ExtrasContainer
from ..dto.command.descriptor import Command
from ._base import ApplianceEndpoint, ResponseModel


class RetrieveResponse(ResponseModel):
    options: dict[str, str]
    commands: Annotated[Cluster[Command], ExtrasContainer]

    appliance_model: Any
    dictionary_id: Any


RetrieveEndpoint = ApplianceEndpoint(
    url="/retrieve",
    response_model=RetrieveResponse,
    params=(
        "OS",
        "APP_VERSION",
        "appliance_type",
        "appliance_model_id",
        "mac_address",
        "code",
        "series",
        "fw_version",
        "firmware_id",
    ),
)
