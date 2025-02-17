# Diagnostic tool have to inspect the internal APIs
# ruff: noqa: SLF001

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from pyhon import __version__
from pyhon.entities.appliance import Appliance

if TYPE_CHECKING:
    from httpx import Response

    from pyhon.apis.api import API
    from pyhon.entities.appliance import Appliance
    from pyhon.hon import Hon


from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    FieldSerializationInfo,
    HttpUrl,
    Json,
    RootModel,
    SerializerFunctionWrapHandler,
    field_serializer,
)


class Call(BaseModel, frozen=True):
    url: Annotated[HttpUrl, BeforeValidator(str)]
    caller: str
    method: str
    status: int
    content: Json[Any]

    @classmethod
    def from_history_entry(cls, entry: tuple["Response", str]):
        response, caller = entry
        return cls(
            url=response.request.url,
            method=response.request.method,
            status=response.status_code,
            content=response.content,
            caller=caller,
        )

    @field_serializer("url", "content", mode="wrap")
    def anonymiser(
        self,
        value: Any,
        next: SerializerFunctionWrapHandler,
        info: FieldSerializationInfo,
    ) -> Any:
        if info.context and (a := info.context.get("anonymiser")):
            value = a(value)

        return next(value, info)
    
    @property
    def url_suffix(self)-> str:
        return self.url.path.rsplit("/", 1).pop()


class Dump(BaseModel):
    slug: str
    calls: list[Call]
    pyhon_version: str = __version__
    timestamp: datetime = Field(default_factory=datetime.now)

    @classmethod
    def from_dir(cls, dump_dir: Path) -> "Dump":
        data: dict[str, list[dict[str, str]]] = json.loads(
            (dump_dir / "metadata.json").read_bytes()
        )

        for call in data["calls"]:
            filename = call.pop("filename")
            md5 = call.pop("md5")

            content = (dump_dir / filename).read_bytes()

            if md5 != hashlib.md5(content).hexdigest():
                raise ValueError(f"MD5 mismatch for {filename}")

            call["content"] = json.loads(content)

        return cls.model_validate(data)

    def to_dir(self, dump_dir: Path) -> None:
        dump_dir.mkdir(parents=True, exist_ok=True)

        data = self.model_dump(mode="json", exclude={"calls"})
        calls_data = data["calls"] = []

        for call in self.calls:
            filename = call.url_suffix
            content = json.dumps(call.content, indent=2)
            md5 = hashlib.md5(content).hexdigest()

            calls_data.append(
                call.model_dump(mode="json", exclude={"content"})
                | {
                    "filename": filename,
                    "md5": md5,
                }
            )

            (dump_dir / f"{filename}.json").write_text(content)

        (dump_dir / "metadata.json").write_text(json.dumps(data, indent=2))


FullDump = RootModel[list[Dump]]


class Diagnoser:
    def __init__(self, hon: "Hon") -> None:
        self.hon = hon

    @property
    def api(self) -> "API":
        return self.hon._api

    @property
    def history_tracker(self):
        return self.api._session.history_tracker

    async def appliance_dump(
        self, appliance: "Appliance", factory_call: Call | None = None
    ) -> Dump:
        if factory_call is None:
            with self.history_tracker as history:
                await Appliance.fetch(self.api, recursive=False)
                factory_call = Call.from_history_entry(history[-1])

        factory_call = factory_call.model_copy(deep=True)
        appliances_data = factory_call.content["payload"]["appliances"]
        appliances_data[:] = [
            a
            for a in appliances_data
            if a["serialNumber"] == appliance.data.serial_number
        ]

        with self.history_tracker as history:
            await appliance.load_all()

            return Dump(
                slug=appliance.data.slug,
                calls=[
                    factory_call,
                    *(Call.from_history_entry(entry) for entry in history),
                ],
            )

    async def full_dump(self) -> FullDump:
        with self.history_tracker as history:
            appliances = await Appliance.fetch(self.api, recursive=False)
            factory_call = Call.from_history_entry(history[-1])

        return FullDump.model_construct(
            [
                await self.appliance_dump(appliance, factory_call)
                for appliance in appliances
            ]
        )

    async def tokens(self) -> dict[str, str]:
        await Appliance.fetch(self.api, recursive=False)

        return asdict(self.hon._auth._tokens)
