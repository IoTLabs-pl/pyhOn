from pyhon.appliances._base import Appliance, MachModeActivityMixin


class WasherDryer(MachModeActivityMixin, Appliance):
    appliance_type = "WD"
