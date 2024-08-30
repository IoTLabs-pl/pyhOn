from typing import Any

from pyhon.appliances._base import Appliance
from pyhon.attributes import Attribute


class Fridge(Appliance):
    appliance_type = "REF"

    async def load_attributes(self) -> dict[str, Any]:
        payload = await super().load_attributes()
        params = self.attributes["parameters"]

        match params:
            case {"holidayMode": Attribute(value="1")}:
                params["modeZ1"] = Attribute("holiday")
            case {"intelligenceMode": Attribute(value="1")}:
                params["modeZ1"] = Attribute("auto_set")
            case {"quickModeZ1": Attribute(value="1")}:
                params["modeZ1"] = Attribute("super_cool")
            case _:
                params["modeZ1"] = Attribute("no_mode")

        match params:
            case {"quickModeZ2": Attribute(value="1")}:
                params["modeZ2"] = Attribute("super_freeze")
            case {"intelligenceMode": Attribute(value="1")}:
                params["modeZ2"] = Attribute("auto_set")
            case _:
                params["modeZ2"] = Attribute("no_mode")

        return payload
