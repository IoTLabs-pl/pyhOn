from ..dto.favourite import Favourite
from ._base import ApplianceEndpoint, ResponseModel


class FavouritesResponse(ResponseModel):
    favourites: list[Favourite]


FavouritesEndpoint = ApplianceEndpoint(
    url="/appliance/{mac_address}/favourite",
    response_model=FavouritesResponse,
)
