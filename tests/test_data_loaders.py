from pathlib import Path

import pytest
from mock_server import MockDevice, MockServer

from pyhon import Hon


@pytest.fixture(
    params=Path(__file__).parent.joinpath("hon_test_data", "test_data").iterdir(),
    ids=lambda p: p.name,
    autouse=True,
)
def mock_device(request: pytest.FixtureRequest, mock_server: MockServer):
    device = MockDevice.from_dir(request.param)
    device_routes = mock_server.register_device(device)

    yield device

    for route in device_routes:
        assert (
            route.called
        ), f"{route.name.rsplit(':').pop()} was not called for {device.slug}"


async def test_load_data(mock_server: MockServer):
    async with Hon(mock_server.username, mock_server.password, start_mqtt=False):
        pass
