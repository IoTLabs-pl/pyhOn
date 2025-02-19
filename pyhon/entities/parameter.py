from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..apis.dto.parameter import Parameter as ParameterDTO
from .observer import Observable

if TYPE_CHECKING:
    from .appliance import Appliance


@dataclass
class Parameter(Observable[ParameterDTO]):
    appliance: "Appliance" = field(repr=False)

    @classmethod
    async def fetch(cls, appliance: "Appliance") -> list["Parameter"]:
        response = await appliance.api.context(appliance=appliance)
        return [cls(_data=param, appliance=appliance) for param in response.parameters.values()]
