from pyhon.appliances._base import Appliance, MachModeActivityMixin


class WashingMachine(MachModeActivityMixin, Appliance):
    appliance_type = "WM"
