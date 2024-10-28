import pytest
from mock_server import MockServer


@pytest.fixture
def mock_server(respx_mock):
    return MockServer(respx_mock)
