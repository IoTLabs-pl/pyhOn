from ..dto.appliance import Appliance
from ._base import Endpoint, ResponseModel


class AppliancesResponse(ResponseModel):
    appliances: list[Appliance]


AppliancesEndpoint = Endpoint(
    url="/appliance",
    response_model=AppliancesResponse,
)
