from pathlib import Path

import pytest
from mock_server import MockServer
from mock_server.dump_loader import load_dump

from pyhon import Hon


@pytest.fixture(
    params=Path(__file__).parent.joinpath("hon_test_data", "test_data").iterdir(),
    ids=lambda p: p.name,
    autouse=True,
)
def mock_device(request: pytest.FixtureRequest, mock_server: MockServer):
    dump_routes = mock_server.install_dump(dump := load_dump(request.param))

    yield dump

    for route in dump_routes:
        assert (
            route.called
        ), f"{route.name.rsplit(':').pop()} was not called for {dump.slug}"


async def test_load_data(mock_server: MockServer):
    async with Hon(mock_server.username, mock_server.password, enable_mqtt=False):
        pass
