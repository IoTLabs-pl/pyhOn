from typing import Annotated

from ..dto._base import Cluster, ExtrasContainer
from ..dto.maintenance_cycle import MaintenanceItem
from ._base import ApplianceEndpoint, ResponseModel


class MaintenanceCycleResponse(ResponseModel):
    items: Annotated[Cluster[MaintenanceItem], ExtrasContainer]


MaintenanceCycleEndpoint = ApplianceEndpoint(
    url="/maintenance-cycle",
    response_model=MaintenanceCycleResponse,
    params=("mac_address",),
)
