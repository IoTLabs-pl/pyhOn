from ..dto.history import HistoryItem
from ._base import ApplianceEndpoint, ResponseModel


class HistoryResponse(ResponseModel):
    history: list[HistoryItem]


HistoryEndpoint = ApplianceEndpoint(
    url="/appliance/{mac_address}/history",
    response_model=HistoryResponse,
)
