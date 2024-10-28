from contextlib import suppress

from httpx import HTTPStatusError

from pyhon.appliances._base import Appliance


class AirConditioner(Appliance):
    appliance_type = "AC"

    async def load_maintenance_cycle(self) -> None:
        with suppress(HTTPStatusError):
            # Air conditioners throws HTTP 400 on maintenance cycle request (?)
            await super().load_maintenance_cycle()
