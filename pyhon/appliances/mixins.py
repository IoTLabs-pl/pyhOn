from typing import Any

from pyhon.appliances.base import HonAppliance
from pyhon.attributes import HonAttribute


class MachModeActivityMixin(HonAppliance):
    async def load_attributes(self) -> dict[str, Any]:
        payload = await super().load_attributes()
        data = self._attributes
        params = data["parameters"]

        if data["connected"].value == "0":
            params["machMode"].value = "0"
        data["active"] = HonAttribute(str(int(bool(payload.get("activity")))))

        data["pause"] = HonAttribute(str(int(params["machMode"].value == "3")))
