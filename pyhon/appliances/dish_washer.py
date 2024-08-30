from pyhon.appliances._base import Appliance, MachModeActivityMixin


class DishWasher(MachModeActivityMixin, Appliance):
    appliance_type = "DW"
