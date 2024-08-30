from pyhon.appliances._base import Appliance, MachModeActivityMixin
from pyhon.parameter import FixedParameter, Parameter


class TumbleDryer(MachModeActivityMixin, Appliance):
    appliance_type = "TD"

    @property
    def settings(self) -> dict[str, Parameter]:
        settings = super().settings
        dry_level = settings.get("startProgram.dryLevel")
        if isinstance(dry_level, FixedParameter) and dry_level.value == "11":
            settings.pop("startProgram.dryLevel")
        return settings
