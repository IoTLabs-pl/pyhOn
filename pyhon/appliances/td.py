from pyhon.appliances.base import HonAppliance
from pyhon.appliances.mixins import MachModeActivityMixin
from pyhon.parameter.base import HonParameter
from pyhon.parameter.fixed import HonParameterFixed


class TDAppliance(MachModeActivityMixin, HonAppliance):

    @property
    def settings(self) -> dict[str, HonParameter]:
        settings = super().settings
        dry_level = settings.get("startProgram.dryLevel")
        if isinstance(dry_level, HonParameterFixed) and dry_level.value == "11":
            settings.pop("startProgram.dryLevel")
        return settings
