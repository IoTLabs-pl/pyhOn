from typing import Any

from pyhon.appliances.base import HonAppliance
from pyhon.attributes import HonAttribute


class WHAppliance(HonAppliance):
    async def load_attributes(self) -> dict[str, Any]:
        await super().load_attributes()
        data = self._attributes
        data["active"] = HonAttribute(str(int(data["parameters"]["onOffStatus"].value == 1)))
