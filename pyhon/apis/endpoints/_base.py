from dataclasses import dataclass, replace
from functools import cached_property
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Generic,
    Iterable,
    Literal,
    ParamSpec,
    TypeVar,
)

from pydantic import model_validator
from pydantic.alias_generators import to_camel

from pyhon import const

from ..dto._base import BaseModel

if TYPE_CHECKING:
    from ...entities.appliance import Appliance
    from ..api import API


class ResponseModel(BaseModel):
    result_code: Literal["0"] | None = None

    @model_validator(mode="before")
    @classmethod
    def extract_payload(cls, v: dict[str, Any]) -> Any:
        try:
            v = v["payload"]
        finally:
            return v


T = TypeVar("T", bound="ResponseModel")

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True)
class Endpoint(Generic[T]):
    response_model: type[T]
    url: str
    anonymous: bool = False
    params: Iterable[str | tuple[str, str]] = ()

    _api: "API | None" = None

    @property
    def api(self) -> "API":
        if self._api is None:
            raise ValueError("API is not bound to the endpoint")
        return self._api

    def bind_api(self, api: "API"):
        if self._api is not None:
            raise ValueError("API is already bound to the endpoint")
        return replace(self, _api=api)

    @cached_property
    def _params(self):
        names = {k for k in self.params if isinstance(k, str)}
        pairs = {k for k in self.params if isinstance(k, tuple)}

        pairs |= {(name, getattr(const, name, f"{{{name}}}")) for name in names}

        return {to_camel(k): v for k, v in pairs}

    async def _call(self, url: str, params: dict[str, str], data: Any = None) -> T:
        response = await self.api.call(
            endpoint=url,
            params=params,
            data=data,
        )
        return self.response_model.model_validate_json(response.content)

    def __call__(self) -> Awaitable[T]:
        return self._call(self.url, self._params)


@dataclass(frozen=True)
class ApplianceEndpoint(Endpoint[T]):
    _appliance: "Appliance|None" = None

    @property
    def appliance(self) -> "Appliance":
        if self._appliance is None:
            raise ValueError("Appliance is not bound to the endpoint")
        return self._appliance

    def bind_appliance(self, appliance: "Appliance"):
        if self._appliance is not None:
            raise ValueError("Appliance is already bound to the endpoint")
        return replace(self, _appliance=appliance)

    def __call__(
        self, appliance: "Appliance|None" = None, data: BaseModel = None
    ) -> Awaitable[T]:
        interpolators = (appliance or self.appliance).data.model_dump()
        url = self.url.format_map(interpolators)
        params = {k: v.format_map(interpolators) for k, v in self._params.items()}

        data = data.model_dump(mode='json', by_alias=True, exclude_none=True) if data else None
        return self._call(url, params, data=data)
