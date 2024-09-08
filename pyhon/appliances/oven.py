from typing import Any

from pyhon.appliances._base import ActiveFromOnOffStatusMixin, Appliance


class Oven(ActiveFromOnOffStatusMixin, Appliance):
    appliance_type = "OV"

    async def load_attributes(self) -> dict[str, Any]:
        payload = await super().load_attributes()
        attributes = self.attributes

        if attributes["connected"] == 0:
            attributes["temp"].update(0)
            attributes["onOffStatus"].update(0)
            attributes["remoteCtrValid"].update(0)
            attributes["remainingTimeMM"].update(0)

        return payload
