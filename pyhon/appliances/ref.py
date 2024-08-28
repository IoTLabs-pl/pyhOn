from typing import Any

from pyhon.appliances.base import HonAppliance
from pyhon.attributes import HonAttribute


class RefAppliance(HonAppliance):
    async def load_attributes(self) -> dict[str, Any]:
        await super().load_attributes()
        data = self._attributes
        params = data["parameters"]

        match params:
            case {"holidayMode": HonAttribute(value="1")}:
                data["modeZ1"] = HonAttribute("holiday")
            case {"intelligenceMode": HonAttribute(value="1")}:
                data["modeZ1"] = HonAttribute("auto_set")
            case {"quickModeZ1": HonAttribute(value="1")}:
                data["modeZ1"] = HonAttribute("super_cool")
            case _:
                data["modeZ1"] = HonAttribute("no_mode")

        match params:
            case {"quickModeZ2": HonAttribute(value="1")}:
                data["modeZ2"] = HonAttribute("super_freeze")
            case {"intelligenceMode": HonAttribute(value="1")}:
                data["modeZ2"] = HonAttribute("auto_set")
            case _:
                data["modeZ2"] = HonAttribute("no_mode")
