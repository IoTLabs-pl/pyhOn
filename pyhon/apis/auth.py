import json
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from html import unescape
from logging import getLogger
from re import compile as re_compile
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

import aiohttp

from pyhon import const
from pyhon.exceptions import HonAuthenticationError

from . import device as HonDevice
from .wrappers import AuthSessionWrapper

_LOGGER = getLogger(__name__)

_HREF_REGEX = re_compile(r"""(?:url|href)\s*=\s*["'](.+?)["']""")
_HON_REDIRECT_REGEX = re_compile(r"""["'](hon://.+?)['"]""")


def _parse_query_string(url: str, from_fragment: bool = False) -> dict[str, str]:
    """Parse a query string from a URL.

    Args:
        url (str): URL to parse.
        from_fragment (bool, optional): Parse from fragment instead of query.
          Defaults to False.

    Returns:
        query_params (dict[str,str]): Parsed query string.
    """
    splitted = urlsplit(url)
    base = splitted.fragment if from_fragment else splitted.query

    return dict(parse_qsl(base))


def message_action_data(email: str, password: str, url: str) -> dict[str, str]:
    action = {
        "id": "79;a",
        "descriptor": "apex://LightningLoginCustomController/ACTION$login",
        "callingDescriptor": "markup://c:loginForm",
        "params": {
            "username": email,
            "password": password,
            "startUrl": _parse_query_string(url)["startURL"],
        },
    }

    data = {
        "message": {"actions": [action]},
        "aura.context": {"mode": "PROD", "app": "siteforce:loginApp2"},
        "aura.pageURI": url.removeprefix(const.AUTH_API_URL),
        "aura.token": None,
    }

    return {k: json.dumps(v) for k, v in data.items()}


@dataclass
class _Tokens:
    __TOKEN_LIFETIME = timedelta(hours=8)
    __TOKEN_LIFETIME_WARNING_TIME = __TOKEN_LIFETIME - timedelta(hours=1)

    access_token: str | None = None
    id_token: str | None = None
    refresh_token: str | None = None
    cognito_token: str | None = None
    iot_core_token: str | None = None

    __created_at: datetime = field(default_factory=datetime.now, init=False)

    @classmethod
    def from_html(cls, html: str) -> "_Tokens":
        """Parse access_token, id_token and refresh_token from the HTML
        page redirecting to hOn app URI with OAuth data in fragment.

        Args:
            html (str): HTML page content.
        """
        redirect_uri = _HON_REDIRECT_REGEX.search(html)

        if not redirect_uri:
            raise ValueError("No redirect URI found in HTML", html)

        uri = unescape(redirect_uri[1])

        parsed = _parse_query_string(uri, from_fragment=True)
        return cls.from_dict(parsed)

    @classmethod
    def initializable_field_names(cls) -> set[str]:
        return {f.name for f in fields(cls) if f.init}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "_Tokens":
        """Create a _Tokens object from a dictionary.

        Args:
            data (dict): Dictionary containing the tokens.
        """
        field_names = cls.initializable_field_names().intersection(data.keys())
        if len(field_names) == 0:
            raise ValueError("No tokens found in data", data)

        return cls(**{k: v for k, v in data.items() if k in field_names})

    @property
    def expired(self) -> bool:
        return datetime.now() >= self.__created_at + self.__TOKEN_LIFETIME

    @property
    def expires_soon(self) -> bool:
        return datetime.now() >= self.__created_at + self.__TOKEN_LIFETIME_WARNING_TIME

    @property
    def initialized(self) -> bool:
        return all([self.access_token, self.id_token, self.refresh_token])


class Authenticator:
    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._email = email
        self._password = password
        self._session = AuthSessionWrapper(session)
        self._resources = AsyncExitStack()
        self._tokens = _Tokens(refresh_token=refresh_token)

    @property
    def refresh_token(self) -> str | None:
        return self._tokens.refresh_token

    async def _ensure_authenticated(self, force: bool = False) -> None:
        """Ensure that the user is authenticated.
        If the tokens are about to expiry, refresh them.
        After this method is called, the access_token,
        refresh_token and id_token are guaranteed to be set.
        """

        if not self._tokens.initialized or self._tokens.expires_soon or force:
            async with self._session.history_tracker:
                if self._tokens.refresh_token:
                    await self._refresh()

                if not self._tokens.initialized:
                    await self._retrieve_tokens()

            if not self._tokens.initialized:
                raise HonAuthenticationError("Could not authenticate")

    async def get_access_token(self, force: bool = False) -> str:
        """Get the access token.

        Returns:
            access_token (str): The access token.
        """
        await self._ensure_authenticated(force)
        return cast(str, self._tokens.access_token)

    async def get_id_token(self, force: bool = False) -> str:
        """Get the ID token.

        Returns:
            id_token (str): The ID token.
        """
        await self._ensure_authenticated(force)
        return cast(str, self._tokens.id_token)

    async def get_cognito_token(self, force: bool = False) -> str:
        """Get the Cognito token.

        Returns:
            cognito_token (str): The Cognito token.
        """
        if not self._tokens.cognito_token or force:
            async with self._session.history_tracker:
                await self._retrieve_cognito_token()
        return cast(str, self._tokens.cognito_token)

    async def get_iot_core_token(self, force: bool = False) -> str:
        """Get the IoT Core token.

        Returns:
            iot_core_token (str): The AWS IoT Core token.
        """
        if not self._tokens.iot_core_token or force:
            async with self._session.history_tracker:
                await self._retrieve_cognito_token()
        return cast(str, self._tokens.iot_core_token)

    async def _authorize(self) -> str | None:
        """Authorize the hOn account.

        Returns:
            url (str|None): The URL to login to the hOn account or
            None if the user is already authorized.
        """
        self._tokens = _Tokens()
        self._session.clear_cookies()

        _LOGGER.debug("Starting OAuth2 authorization")

        async with self._session.get(
            f"{const.AUTH_API_URL}/services/oauth2/authorize/expid_Login",
            params={
                "response_type": "token id_token",
                "client_id": const.CLIENT_ID,
                "redirect_uri": "hon://mobilesdk/detect/oauth/done",
                "display": "touch",
                "scope": "api openid refresh_token web",
                "nonce": str(uuid4()),
            },
        ) as response:
            text = await response.text()

            try:
                self._tokens = _Tokens.from_html(text)
            except ValueError:
                pass
            else:
                return None

            login_url = _HREF_REGEX.search(text)
            if not login_url:
                raise HonAuthenticationError("No login URL found")

            url = login_url[1]
            if url.startswith("/NewhOnLogin"):
                url = f"{const.AUTH_API_URL}/s/login{url}"

            return url

    async def _login(self) -> str | None:
        """Login to the hOn account. Retrieve the token_url.

        Returns:
            token_url (str|None): The URL to retrieve the tokens or
            None if the user is already logged in.
        """
        if login_url := await self._authorize():
            _LOGGER.debug("Logging in")
            async with self._session.post(
                f"{const.AUTH_API_URL}/s/sfsites/aura",
                data=message_action_data(self._email, self._password, login_url),
                params={"r": 3, "other.LightningLoginCustom.login": 1},
            ) as response:
                result = await response.json()
                token_url: str = result["events"][0]["attributes"]["values"]["url"]
                return token_url

        return None

    async def _retrieve_tokens(self) -> None:
        """Retrieve the access_token, id_token and refresh_token from the token_url."""
        if url := await self._login():
            _LOGGER.debug("Getting tokens")
            for _ in range(2):
                async with self._session.get(url) as response:
                    url_match = _HREF_REGEX.search(await response.text())
                    if not url_match:
                        raise HonAuthenticationError("No URL found in response")
                    url = url_match[1]
                    if "ProgressiveLogin" not in url:
                        break

            async with self._session.get(f"{const.AUTH_API_URL}{url}") as response:
                self._tokens = _Tokens.from_html(await response.text())

    async def _retrieve_cognito_token(self) -> None:
        """Retrieve the Cognito token."""

        _LOGGER.debug("Trying to retrieve Cognito token")
        async with self._session.post(
            f"{const.API_URL}/auth/v1/login",
            headers={"id-token": await self.get_id_token()},
            json=HonDevice.descriptor(),
        ) as response:
            response_data = await response.json()
            cognito_token = response_data["cognitoUser"]["Token"]
            self._tokens.cognito_token = cognito_token

            iot_core_token = response_data["tokenSigned"]
            self._tokens.iot_core_token = iot_core_token

    async def _refresh(self) -> None:
        try:
            refresh_token = self._tokens.refresh_token
            async with self._session.post(
                f"{const.AUTH_API_URL}/services/oauth2/token",
                params={
                    "client_id": const.CLIENT_ID,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            ) as response:
                data = await response.json()
                self._tokens = _Tokens.from_dict(data)
                self._tokens.refresh_token = refresh_token
        except aiohttp.ClientResponseError as e:
            _LOGGER.warning(
                "Failed to obtain access token with refresh token: [%s] %s",
                e.status,
                e.message,
            )

    async def __aenter__(self) -> "Authenticator":
        await self._resources.enter_async_context(self._session)
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._resources.aclose()
