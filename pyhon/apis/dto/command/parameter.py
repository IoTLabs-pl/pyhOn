from typing import Annotated, Generic, Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from .._base import Data_T, Data_T_Union, KeyedModel


class _BaseParameter(KeyedModel):
    category: Literal["general", "time", "command", "cluster", "rule"]
    mandatory: bool


class FixedParameter(_BaseParameter, Generic[Data_T]):
    typology: Literal["fixed"]
    fixed_value: Data_T | None = None

    @field_validator("fixed_value", mode="after")
    def fixed_in_mandatory(cls, v, info: ValidationInfo):
        if info.data["mandatory"] and v is None:
            raise ValueError("fixed_value is mandatory")
        return v


class _VariableParameter(_BaseParameter, Generic[Data_T]):
    default_value: Data_T=None


class RangeParameter(_VariableParameter[Data_T], Generic[Data_T]):
    typology: Literal["range"]
    minimum_value: Data_T
    maximum_value: Data_T
    increment_value: Data_T


# TODO: Migrate to Python enum.Flag?
class EnumParameter(_VariableParameter[Data_T], Generic[Data_T]):
    typology: Literal["enum"]
    enum_values: set[Data_T]
    default_value: set[Data_T]

    @field_validator("default_value", mode="before")
    def default_value_to_set(cls, v):
        if isinstance(v, str):
            return v.strip("[]").split("|")
        return v

    @model_validator(mode="after")
    def default_value_in_allowed_values(self):
        if any(v not in self.enum_values for v in self.default_value):
            raise ValueError("default_value must be in enum_values")
        return self


CommandParameter = Annotated[
    EnumParameter[Data_T_Union]
    | FixedParameter[Data_T_Union]
    | RangeParameter[Data_T_Union],
    # | _BaseParameter,
    Field(discriminator="typology"),
]
