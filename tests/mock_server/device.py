import json
from abc import ABC, abstractmethod
from collections.abc import Generator
from functools import cache, cached_property
from hashlib import md5
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from pyhon.diagnostic.tool import CallMetadata, DumpMetadata


class __MockDeviceABC(ABC):
    def __init__(self, dump_dir: Path):
        self.dump_dir = dump_dir

    @classmethod
    def from_dir(cls, dump_dir: Path | str) -> "MockDevice|LegacyMockDevice":
        dump_dir = Path(dump_dir)
        if (dump_dir / "metadata.json").exists():
            return MockDevice(dump_dir)
        else:
            return LegacyMockDevice(dump_dir)

    @property
    @abstractmethod
    def slug(self) -> str: ...

    @property
    @abstractmethod
    def calls(self) -> "Generator[tuple[CallMetadata, Any]]": ...


class LegacyMockDevice(__MockDeviceABC):
    @cache
    def __load_file(self, filename: str) -> Any:
        try:
            with (self.dump_dir / filename).open() as file:
                return json.load(file)
        except FileNotFoundError:
            return None

    @property
    def slug(self) -> str:
        appliance_data = self.__load_file("appliance_data.json")
        return f'{appliance_data["applianceTypeName"]}_{appliance_data["id"]}'.lower()

    def __call_factory(
        self,
        url: str,
        payload: Any,
        *,
        query_params: Iterable[str | tuple[str, str]] = (),
        status: int = 200,
        raw_payload: bool = False,
    ) -> "tuple[CallMetadata, Any]":
        filename = f'{url.rsplit("/", 1).pop()}.json'
        url = self.__build_url(url, *query_params)

        if not raw_payload:
            payload = {
                "payload": payload,
                "authInfo": {},
            }

        return (
            {
                "method": "GET",
                "status": status,
                "url": url,
                "filename": filename,
            },
            payload,
        )

    def __build_url(self, path: str, *query_params: str | tuple[str, str]) -> str:
        BASE_URL = "https://api-iot.he.services/commands/v1"
        url = f"{BASE_URL}{path}"
        if query_params:
            query_string = "&".join(
                f"{key}={{{key}}}" if isinstance(key, str) else f"{key[0]}={key[1]}"
                for key in query_params
            )
            url += f"?{query_string}"

        appliance_data = self.__load_file("appliance_data.json")
        appliance_data.update(
            {
                "applianceType": appliance_data["applianceTypeName"],
                "firmwareId": appliance_data["eepromId"],
            }
        )

        return url.format_map(appliance_data)

    @property
    def calls(self) -> "Generator[tuple[CallMetadata, Any]]":
        yield self.__call_factory(
            "/appliance",
            {"appliances": [self.__load_file("appliance_data.json")]},
        )
        yield self.__call_factory(
            "/context",
            self.__load_file("attributes.json"),
            query_params=("macAddress", "applianceType", ("category", "CYCLE")),
        )
        yield self.__call_factory(
            "/appliance/{macAddress}/history",
            {"history": self.__load_file("command_history.json")},
        )
        yield self.__call_factory(
            "/retrieve",
            self.__load_file("commands.json"),
            query_params=(
                ("os", "android"),
                ("appVersion", "2.6.5"),
                "applianceType",
                "applianceModelId",
                "macAddress",
                "series",
                "code",
                "fwVersion",
                "firmwareId",
            ),
        )
        yield self.__call_factory(
            "/appliance/{macAddress}/favourite",
            {"favourites": []},
        )
        if self.slug.startswith("ac"):
            yield self.__call_factory(
                "/maintenance-cycle",
                {
                    "error": {
                        "message": "IAT",
                        "statusCode": 400,
                        "detail": "Invalid applianceType",
                    }
                },
                query_params=("macAddress",),
                status=400,
                raw_payload=True,
            )
        else:
            yield self.__call_factory(
                "/maintenance-cycle",
                self.__load_file("maintenance.json"),
                query_params=("macAddress",),
            )
        yield self.__call_factory(
            "/statistics",
            self.__load_file("statistics.json"),
            query_params=("macAddress", "applianceType"),
        )


class MockDevice(__MockDeviceABC):
    @cached_property
    def __dump_metadata(self) -> "DumpMetadata":
        with (self.dump_dir / "metadata.json").open() as file:
            return json.load(file)

    @property
    def slug(self) -> str:
        return self.__dump_metadata["slug"]

    @property
    def calls(self) -> "Generator[tuple[CallMetadata, Any]]":
        for call in self.__dump_metadata["calls"]:
            body = (self.dump_dir / call["filename"]).read_bytes()
            assert call["md5"] == md5(body).hexdigest()

            yield call, json.loads(body)
