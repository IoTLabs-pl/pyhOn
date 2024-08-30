from pyhon.appliances._base import ActiveFromOnOffStatusMixin, Appliance


class WaterHeater(ActiveFromOnOffStatusMixin, Appliance):
    appliance_type = "WH"
