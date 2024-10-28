import pytest
from mock_server import MockServer

from pyhon.apis import Authenticator
from pyhon.exceptions import InvalidCredentialsException


async def test_auth_base_flow(mock_server: MockServer):
    async with Authenticator(
        mock_server.username,
        mock_server.password,
    ) as auth:
        print(*mock_server.router.routes, sep="\n")
        assert await auth.get_id_token() == mock_server.id_token


@pytest.mark.parametrize(
    ("username", "password"),
    (
        ("bad_username", None),
        (None, "bad_password"),
        ("bad_username", "bad_password"),
    ),
)
async def test_auth_bad_credentials(
    mock_server: MockServer, username: str, password: str
):
    with pytest.raises(InvalidCredentialsException):
        async with Authenticator(
            username or mock_server.username,
            password or mock_server.password,
        ) as auth:
            await auth.get_id_token()


async def test_auth_refresh_token_flow(mock_server: MockServer):
    async with Authenticator(
        mock_server.username,
        mock_server.password,
        refresh_token=mock_server.refresh_token,
    ) as auth:
        assert await auth.get_id_token() == mock_server.id_token

    refresh_token_endpoint = mock_server.router.pop("refresh-token-endpoint")

    assert refresh_token_endpoint.called

    for r in mock_server.router.routes:
        assert not r.called


async def test_auth_refresh_token_flow_fallback(mock_server: MockServer):
    async with Authenticator(
        mock_server.username,
        mock_server.password,
        refresh_token="somerandomtoken",
    ) as auth:
        assert await auth.get_id_token() == mock_server.id_token

    assert mock_server.router["refresh-token-endpoint"].called
    assert mock_server.router["login-endpoint"].called
    assert mock_server.router["token-page"].called
