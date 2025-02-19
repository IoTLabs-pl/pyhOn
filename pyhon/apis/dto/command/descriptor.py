from typing import Annotated

from pydantic import BeforeValidator, Field

from .._base import Cluster, ExtrasContainer, KeyedModel
from .parameter import CommandParameter


# Fix for Haier broken API data
def no_fixed_value_drop(v: dict):
    return {
        k: v
        for k, v in v.items()
        if not (v["typology"] == "fixed" and v["fixedValue"] is None)
    }


def no_typology_drop(v: dict):
    return {k: v for k, v in v.items() if "typology" in v}


class SimpleCommand(KeyedModel):
    description: str
    protocol_type: str
    parameters: Cluster[CommandParameter]
    ancillary_parameters: Annotated[
        Cluster[CommandParameter],
        BeforeValidator(no_fixed_value_drop),
        BeforeValidator(no_typology_drop),
        Field(default_factory=Cluster),
    ]


class VariantCommand(KeyedModel):
    variants: Annotated[Cluster[SimpleCommand], ExtrasContainer]


Command = SimpleCommand | VariantCommand
