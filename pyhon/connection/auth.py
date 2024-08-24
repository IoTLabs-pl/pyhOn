from contextlib import AsyncExitStack
import json
from logging import getLogger
from re import compile as re_compile
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

import aiohttp

from pyhon import const, exceptions
from pyhon.connection.device import HonDevice
from pyhon.connection.handler.auth import AuthSessionWrapper

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
    if from_fragment:
        base = splitted.fragment
    else:
        base = splitted.query
    return dict(parse_qsl(base))


@dataclass
class _LoginData:
    email: str | None = None
    password: str | None = None

    url: str | None = None
    token_url: str | None = None

    @property
    def message_action_data(self) -> dict[str, Any]:
        if not self.email or not self.password or not self.url:
            raise ValueError("Missing data", self.email, self.password, self.url)
        action = {
            "id": "79;a",
            "descriptor": "apex://LightningLoginCustomController/ACTION$login",
            "callingDescriptor": "markup://c:loginForm",
            "params": {
                "username": self.email,
                "password": self.password,
                "startUrl": _parse_query_string(self.url)["startURL"],
            },
        }
        return {
            "message": {"actions": [action]},
            "aura.context": {"mode": "PROD", "app": "siteforce:loginApp2"},
            "aura.pageURI": self.url.removeprefix(const.AUTH_API_URL),
            "aura.token": None,
        }


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

        parsed = _parse_query_string(redirect_uri[1], from_fragment=True)
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


class HonAuth:
    def __init__(
        self,
        email: str,
        password: str,
        device: HonDevice,
        session: aiohttp.ClientSession | None = None,
        refresh_token: str | None = None,
    ) -> None:
        self._session = AuthSessionWrapper(session)
        self._resources = AsyncExitStack()
        self._login_data = _LoginData(email=email, password=password)
        self._device = device
        self._tokens = _Tokens(refresh_token=refresh_token)

    async def _ensure_authenticated(self, force: bool = False) -> None:
        """Ensure that the user is authenticated.
        If the tokens are about to expiry, refresh them.
        After this method is called, the access_token,
        refresh_token and id_token are guaranteed to be set.
        """
        with self._session.session_history_tracker:
            if not self._tokens.initialized or self._tokens.expires_soon or force:
                if self._tokens.refresh_token:
                    await self._refresh()

                if not self._tokens.initialized:
                    await self._retrieve_tokens()

            if not self._tokens.initialized:
                raise exceptions.HonAuthenticationError("Could not authenticate")

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
        with self._session.session_history_tracker:
            if not self._tokens.cognito_token or force:
                await self._retrieve_cognito_token()
            return cast(str, self._tokens.cognito_token)

    async def get_iot_core_token(self, force: bool = False) -> str:
        """Get the IoT Core token.

        Returns:
            iot_core_token (str): The AWS IoT Core token.
        """
        with self._session.session_history_tracker:
            if not self._tokens.iot_core_token or force:
                await self._retrieve_iot_core_token()
            return cast(str, self._tokens.iot_core_token)

    async def _authorize(self) -> None:
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
                return

            login_url = _HREF_REGEX.search(text)

            if not login_url:
                raise exceptions.HonAuthenticationError("No login URL found")

            if login_url[1].startswith("/NewhOnLogin"):
                self._login_data.url = f"{const.AUTH_API_URL}/s/login{login_url[1]}"
            else:
                self._login_data.url = login_url[1]

    async def _login(self) -> None:
        """Login to the hOn account. Retrieve the token_url."""
        await self._authorize()

        if self._tokens.initialized:
            return

        _LOGGER.debug("Logging in")
        async with self._session.post(
            f"{const.AUTH_API_URL}/s/sfsites/aura",
            data={
                k: json.dumps(v)
                for k, v in self._login_data.message_action_data.items()
            },
            params={"r": 3, "other.LightningLoginCustom.login": 1},
        ) as response:
            result = await response.json()
            token_url = result["events"][0]["attributes"]["values"]["url"]
            self._login_data.token_url = token_url

    async def _retrieve_tokens(self) -> None:
        """Retrieve the access_token, id_token and refresh_token from the token_url."""
        await self._login()

        if self._tokens.initialized:
            return

        _LOGGER.debug("Getting tokens")
        url = self._login_data.token_url
        for _ in range(2):
            async with self._session.get(url) as response:
                url_search = _HREF_REGEX.search(await response.text())
                if not url_search:
                    raise exceptions.HonAuthenticationError("No URL found in response")

                url = url_search[1]
                if "ProgressiveLogin" not in url:
                    break

        async with self._session.get(f"{const.AUTH_API_URL}{url}") as response:
            self._tokens = _Tokens.from_html(await response.text())

    async def _retrieve_cognito_token(self) -> None:
        """Retrieve the Cognito token."""
        await self._ensure_authenticated()

        _LOGGER.debug("Trying to retrieve Cognito token")
        async with self._session.post(
            f"{const.API_URL}/auth/v1/login",
            headers={"id-token": await self.get_id_token()},
            json=self._device.get(),
        ) as response:
            token = (await response.json())["cognitoUser"]["Token"]
            self._tokens.cognito_token = token

    async def _retrieve_iot_core_token(self) -> None:
        """Retrieve the IoT Core token."""
        await self._ensure_authenticated()

        _LOGGER.debug("Trying to retrieve IoT Core token")
        async with self._session.get(
            f"{const.API_URL}/auth/v1/introspection",
            headers={
                "cognito-token": await self.get_cognito_token(),
                "id-token": await self.get_id_token(),
            },
        ) as response:
            iot_core_token = (await response.json())["payload"]["tokenSigned"]
            self._tokens.iot_core_token = iot_core_token

    async def _refresh(self) -> None:
        try:
            async with self._session.post(
                f"{const.AUTH_API_URL}/services/oauth2/token",
                params={
                    "client_id": const.CLIENT_ID,
                    "refresh_token": self._tokens.refresh_token,
                    "grant_type": "refresh_token",
                },
            ) as response:
                data = await response.json()
                self._tokens = _Tokens.from_dict(data)
        except aiohttp.ClientResponseError as e:
            _LOGGER.warning(
                "Failed to obtain access token with refresh token: [%s] %s",
                e.status,
                e.message,
            )

    async def __aenter__(self) -> "HonAuth":
        await self._resources.enter_async_context(self._session)
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._resources.aclose()
