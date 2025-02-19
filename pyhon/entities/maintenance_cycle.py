from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..apis.dto.maintenance_cycle import MaintenanceItem as MaintenanceItemDTO

if TYPE_CHECKING:
    from .appliance import Appliance


@dataclass
class MaintenanceCycle:
    data: MaintenanceItemDTO
    appliance: "Appliance" = field(repr=False)

    @classmethod
    async def fetch(cls, appliance: "Appliance") -> list["MaintenanceCycle"]:
        return [
            cls(data=data, appliance=appliance)
            for data in (
                await appliance.api.maintenance_cycle(appliance=appliance)
            ).items
        ]
