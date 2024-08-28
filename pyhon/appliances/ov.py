from typing import Any

from pyhon.appliances.base import HonAppliance
from pyhon.attributes import HonAttribute


class OVAppliance(HonAppliance):
    async def load_attributes(self) -> dict[str, Any]:
        await super().load_attributes()
        data = self._attributes
        params = data['parameters']
        
        if not self.connection:
            params["temp"].value = 0
            params["onOffStatus"].value = 0
            params["remoteCtrValid"].value = 0
            params["remainingTimeMM"].value = 0

        data["active"] = HonAttribute(str(int(params["onOffStatus"].value == 1)))
