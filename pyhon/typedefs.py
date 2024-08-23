from typing import Union, TYPE_CHECKING


if TYPE_CHECKING:
    from pyhon.parameter.base import HonParameter
    from pyhon.parameter.enum import HonParameterEnum
    from pyhon.parameter.fixed import HonParameterFixed
    from pyhon.parameter.program import HonParameterProgram
    from pyhon.parameter.range import HonParameterRange


Parameter = Union[
    "HonParameter",
    "HonParameterRange",
    "HonParameterEnum",
    "HonParameterFixed",
    "HonParameterProgram",
]
