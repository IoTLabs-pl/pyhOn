from pyhon.appliances._base import Appliance


class AirConditioner(Appliance):
    appliance_type = "AC"

    async def load_maintenance_cycle(self) -> None:
        pass
