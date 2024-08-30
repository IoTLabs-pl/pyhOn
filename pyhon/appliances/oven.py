from typing import Any

from pyhon.appliances._base import ActiveFromOnOffStatusMixin, Appliance


class Oven(ActiveFromOnOffStatusMixin, Appliance):
    appliance_type = "OV"

    async def load_attributes(self) -> dict[str, Any]:
        payload = await super().load_attributes()
        params = self.attributes["parameters"]

        if params["connected"] == 0:
            params["temp"].update(0)
            params["onOffStatus"].update(0)
            params["remoteCtrValid"].update(0)
            params["remainingTimeMM"].update(0)

        return payload
