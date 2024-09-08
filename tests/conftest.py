import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from pyhon.apis import API


class Loader:
    def __init__(self, data: Any = None, postprocessor: callable = None) -> None:
        self.data = data
        self.postprocessor = postprocessor

    def load(self):
        if self.postprocessor:
            return self.postprocessor(self.data)
        return self.data


def pytest_generate_tests(metafunc: pytest.Metafunc):

    if "mock_api" in metafunc.fixturenames:

        test_data_dir = Path(__file__).parent / "hon-test-data" / "test_data"

        test_data = {
            appliance_dir.name: {
                file.name: file.read_bytes()
                for file in appliance_dir.iterdir()
                if file.is_file() and file.suffix == ".json"
            }
            for appliance_dir in test_data_dir.iterdir()
            if appliance_dir.is_dir()
        }

        metafunc.parametrize(
            "mock_api", test_data.values(), ids=test_data.keys(), indirect=True
        )


@pytest.fixture
def mock_api(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    data: dict[str, str] = request.param

    print(data)

    PATH_TO_LOADER = {
        "appliance": Loader(data["appliance_data.json"], lambda x: [json.loads(x)]),
        "retrieve": Loader(data["commands.json"], lambda x: json.loads(x)),
        "history": Loader(data["command_history.json"], lambda x: json.loads(x)),
        "context": Loader(data["attributes.json"], lambda x: json.loads(x)),
        "statistics": Loader(data["statistics.json"], lambda x: json.loads(x)),
        "maintenance-cycle": Loader(data["maintenance.json"], lambda x: json.loads(x)),
        "favourite": Loader(postprocessor=lambda x: []),
        "retrieve-last-activity": Loader(postprocessor=lambda x: {}),
        "send": Loader(postprocessor=lambda x: {"payload": {"resultCode": "0"}}),
    }

    async def __aenter__(self) -> "API":
        return self

    async def call(
        self,
        endpoint: str,
        *,
        params: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        response_path: Sequence[str] = ("payload",),
    ) -> Any:
        path_suffix = endpoint.rsplit("/")[-1]

        return PATH_TO_LOADER[path_suffix].load()

    monkeypatch.setattr(API, "__aenter__", __aenter__)
    monkeypatch.setattr(API, "call", call)
