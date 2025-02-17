from typing import Annotated

from ..dto._base import ExtrasContainer
from ..dto.statistics import Statistics
from ._base import ApplianceEndpoint, ResponseModel


class StatisticsResponse(ResponseModel):
    data: Annotated[Statistics, ExtrasContainer]


StatisticsEndpoint = ApplianceEndpoint(
    url="/statistics",
    response_model=StatisticsResponse,
    params=("mac_address", "appliance_type"),
)
