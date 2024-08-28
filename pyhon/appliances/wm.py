from pyhon.appliances.base import HonAppliance
from pyhon.appliances.mixins import MachModeActivityMixin


class WMAppliance(MachModeActivityMixin, HonAppliance):
    pass
