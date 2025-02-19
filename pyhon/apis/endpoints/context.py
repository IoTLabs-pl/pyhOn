from typing import Annotated

from pydantic import AliasPath, Field

from ..dto._base import Cluster
from ..dto.parameter import Parameter
from ._base import ApplianceEndpoint, ResponseModel


class ContextResponse(ResponseModel):
    parameters: Annotated[
        Cluster[Parameter],
        Field(validation_alias=AliasPath("shadow", "parameters")),
    ]


ContextEndpoint = ApplianceEndpoint(
    url="/context",
    response_model=ContextResponse,
    params=("appliance_type", "mac_address", ("category", "CYCLE")),
)
