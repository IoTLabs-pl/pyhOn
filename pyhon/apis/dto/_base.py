from decimal import Decimal
from re import compile, split
from typing import Annotated, Any, TypeVar

from pydantic import BaseModel as PydanticBaseModel
from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    model_validator,
)
from pydantic.alias_generators import to_camel, to_snake

Data_T = TypeVar("Data_T", int, Decimal, str)
Data_T_Union = Annotated[Data_T, Field(union_mode="left_to_right")]
# TODO: How to mix Data_T and Data_T_Union in the same type annotation?

_DIGIT_PART_RE = compile(r"(\d+)")


class ExtrasContainer:
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        frozen=True,
        populate_by_name=True,
    )

    @model_validator(mode="before")
    @classmethod
    def reassign_extra_fields(cls, v: Any) -> Any:
        extras_containers = {
            k for k, v in cls.model_fields.items() if ExtrasContainer in v.metadata
        }
        # TODO: How to enforce this check at the model definition stage?
        if len(extras_containers) > 1:
            raise ValueError(f"Only one {ExtrasContainer} is allowed")

        if extras_containers and isinstance(v, dict):
            target = extras_containers.pop()
            reallocated_keys = {
                k for k in v.keys() if to_snake(k) not in cls.model_fields
            }
            v[target] = {k: v.pop(k) for k in reallocated_keys}

        return v


class KeyedModel(BaseModel):
    key: Annotated[str, Field(exclude=True)]


T = TypeVar("T", bound=KeyedModel)


def _natural_key(key):
    return tuple(
        int(part) if part.isdigit() else part for part in split(_DIGIT_PART_RE, key)
    )


def _ensure_dict(value):
    if isinstance(value, dict):
        return value
    return {"value": value}


def _clusterize(value: dict):
    try:
        return {
            k: ({"key": k} | _ensure_dict(value[k]))
            for k in sorted(value, key=_natural_key)
        }
    except (AttributeError, TypeError) as e:
        raise ValueError("Cluster must be a dict of dicts") from e


Cluster = Annotated[dict[str, T], BeforeValidator(_clusterize)]
