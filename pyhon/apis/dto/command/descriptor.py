from typing import Annotated

from .._base import Cluster, ExtrasContainer, KeyedModel
from .parameter import CommandParameter


class SimpleCommand(KeyedModel):
    description: str
    protocol_type: str
    parameters: Cluster[CommandParameter]


class VariantCommand(KeyedModel):
    variants: Annotated[Cluster[SimpleCommand], ExtrasContainer]


Command = SimpleCommand | VariantCommand
