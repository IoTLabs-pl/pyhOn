from typing import Any
from pyhon.appliances.base import HonAppliance


class ACAppliance(HonAppliance):

    async def load_maintenance_cycle(self) -> dict[str, Any]:
        return {}
