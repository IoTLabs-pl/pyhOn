from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..apis.dto.statistics import Statistics as StatisticsDTO
    from .appliance import Appliance


@dataclass
class Statistics:
    data: "StatisticsDTO"
    appliance: "Appliance" = field(repr=False)

    @classmethod
    async def fetch(cls, appliance: "Appliance") -> "Statistics":
        data = (await appliance.api.statistics(appliance=appliance)).data
        return cls(data=data, appliance=appliance)
