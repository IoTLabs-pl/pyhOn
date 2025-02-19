from typing import Any

from httpx import AsyncClient, Response

from pyhon import const
from pyhon.apis.auth import Authenticator
from pyhon.apis.wrappers import DataSessionWrapper

from .endpoints._base import Endpoint
from .endpoints.appliance import AppliancesEndpoint
from .endpoints.context import ContextEndpoint
from .endpoints.favourite import FavouritesEndpoint
from .endpoints.history import HistoryEndpoint
from .endpoints.maintenance_cycle import MaintenanceCycleEndpoint
from .endpoints.retrieve import RetrieveEndpoint
from .endpoints.send import SendEndpoint
from .endpoints.statistics import StatisticsEndpoint


class API:
    appliances = AppliancesEndpoint
    context = ContextEndpoint
    retrieve = RetrieveEndpoint
    statistics = StatisticsEndpoint
    maintenance_cycle = MaintenanceCycleEndpoint
    favourites = FavouritesEndpoint
    history = HistoryEndpoint
    send = SendEndpoint

    def __init__(
        self,
        authenticator: Authenticator,
        session: AsyncClient,
    ) -> None:
        self._session = DataSessionWrapper(authenticator, session)

        for name in dir(self):
            endpoint = getattr(self, name, None)
            if isinstance(endpoint, Endpoint):
                setattr(self, name, endpoint.bind_api(self))

    @property
    def history_tracker(self):
        return self._session.history_tracker

    async def call(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
    ) -> Response:
        if not endpoint.startswith("http"):
            endpoint = f"{const.API_URL}/commands/v1{endpoint}"

        return await self._session.request(
            "POST" if data else "GET", endpoint, params=params, json=data
        )
