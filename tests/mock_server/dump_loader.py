import json
from collections.abc import Generator
from pathlib import Path
from typing import Iterable

from pyhon.diagnostic.tool import Call, Dump


def load_dump(dump_dir: Path) -> Dump:
    if (dump_dir / "metadata.json").exists():
        return Dump.from_dir(dump_dir)
    else:
        mock_device = LegacyMockDevice(dump_dir)
        return Dump(
            slug=mock_device.slug,
            calls=list(mock_device.calls),
            pyhon_version="0.0.0",
        )


class LegacyMockDevice:
    def __init__(self, dump_dir: Path):
        self.dump_dir = dump_dir

        self.appliance_data_call = self.__call_factory(
            "/appliance",
            f'{{"appliances": [{self.__load_file("appliance_data.json")}]}}',
        )

    @property
    def appliance_data(self) -> dict:
        try:
            return self.appliance_data_call.content["payload"]["appliances"][0]
        except AttributeError:
            return None

    def __load_file(self, filename: str) -> str:
        try:
            return (self.dump_dir / filename).read_text()
        except FileNotFoundError:
            return None

    @property
    def slug(self) -> str:
        return f'{self.appliance_data["applianceTypeName"]}_{self.appliance_data["id"]}'.lower()

    def __call_factory(
        self,
        url: str,
        payload: str,
        *,
        query_params: Iterable[str | tuple[str, str]] = (),
        status: int = 200,
        raw_payload: bool = False,
    ) -> "Call":
        url = self.__build_url(url, *query_params)

        if not raw_payload:
            payload = f"""{{
                "payload": {payload},
                "authInfo": {{}}
            }}"""

        return Call(
            method="GET",
            status=status,
            url=url,
            content=payload,
            caller="<unknown>",
        )

    def __build_url(self, path: str, *query_params: str | tuple[str, str]) -> str:
        BASE_URL = "https://api-iot.he.services/commands/v1"
        url = f"{BASE_URL}{path}"
        if self.appliance_data:
            if query_params:
                query_string = "&".join(
                    f"{key}={{{key}}}" if isinstance(key, str) else f"{key[0]}={key[1]}"
                    for key in query_params
                )
                url += f"?{query_string}"

            url = url.format(
                **self.appliance_data,
                applianceType=self.appliance_data["applianceTypeName"],
                firmwareId=self.appliance_data["eepromId"],
            )
        return url

    @property
    def calls(self) -> "Generator[Call]":
        yield self.appliance_data_call

        yield self.__call_factory(
            "/context",
            self.__load_file("attributes.json"),
            query_params=("macAddress", "applianceType", ("category", "CYCLE")),
        )
        yield self.__call_factory(
            "/appliance/{macAddress}/history",
            f'{{"history": {self.__load_file("command_history.json")}}}',
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
        # TODO: How we can use favourites?
        # yield self.__call_factory(
        #     "/appliance/{macAddress}/favourite",
        #     '{"favourites": []}',
        # )
        if self.slug.startswith("ac"):
            yield self.__call_factory(
                "/maintenance-cycle",
                json.dumps(
                    {
                        "error": {
                            "message": "IAT",
                            "statusCode": 400,
                            "detail": "Invalid applianceType",
                        }
                    }
                ),
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
