from typing import Annotated

from pydantic import Field

from ._base import KeyedModel


class ComplexMaintenanceItem(KeyedModel):
    total: Annotated[int, Field(alias="tot")]
    count: int
    remaining: int
    percentage: int


class SimpleMaintenanceItem(KeyedModel):
    value: int | None


MaintenanceItem = ComplexMaintenanceItem | SimpleMaintenanceItem
