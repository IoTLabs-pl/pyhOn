import pytest

from pyhon import Hon


@pytest.mark.asyncio()
async def test_load_data(mock_api):
    async with Hon("email@example.com", "SomePassword", mqtt=False):
        pass
