import json
from contextlib import AsyncExitStack
from dataclasses import dataclass, field, fields
from datetime import datetime, timedelta
from html import unescape
from logging import getLogger
from re import compile as re_compile
from typing import cast
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from httpx import AsyncClient, HTTPStatusError

from pyhon import const
from pyhon.exceptions import AuthorizationFlowException, InvalidCredentialsException

from . import device as HonDevice
from .wrappers import AuthSessionWrapper, api_call

_LOGGER = getLogger(__name__)

_HREF_REGEX = re_compile(r"""(?:href|action)\s*=\s*["'](.+?)["']""")


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


def _handle_js_redirect(html: str) -> str:
    """Handle JavaScript redirect in HTML.

    Args:
        html (str): HTML to parse.

    Returns:
        str: URL to redirect to.
    """
    ## TODO: Sometimes html form with action to redirect is used?
    match = _HREF_REGEX.search(html)
    if not match:
        raise AuthorizationFlowException("No redirect URL found")

    location = unescape(match.group(1))

    if location.startswith("/"):
        location = f"{const.AUTH_API_URL}{location}"

    return location


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
        "aura.pageURI": url,
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
    def from_redirect_url(cls, url: str) -> "_Tokens":
        """Parse access_token, id_token and refresh_token from redirect URL.

        Args:
            url (str): URL to parse.

        Returns:
            _Tokens: Tokens parsed from URL.
        """
        parsed = _parse_query_string(url, from_fragment=True)
        return cls.from_dict(parsed)

    @classmethod
    def initializable_field_names(cls) -> set[str]:
        return {f.name for f in fields(cls) if f.init}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "_Tokens":
        """Create a _Tokens object from a dictionary.

        Args:
            data (dict): Dictionary containing the tokens.

        Returns:
            _Tokens: Tokens parsed from the dictionary.
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
        session: AsyncClient,
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
            with self._session.history_tracker:
                if self._tokens.refresh_token:
                    await self._refresh()

                if not self._tokens.initialized:
                    await self._retrieve_tokens()

            if not self._tokens.initialized:
                raise AuthorizationFlowException("Could not authenticate")

    # async def get_access_token(self, force: bool = False) -> str:
    #     """Get the access token.

    #     Returns:
    #         access_token (str): The access token.
    #     """
    #     await self._ensure_authenticated(force)
    #     return cast(str, self._tokens.access_token)

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
            with self._session.history_tracker:
                await self._retrieve_cognito_token()
        return cast(str, self._tokens.cognito_token)

    async def get_iot_core_token(self, force: bool = False) -> str:
        """Get the IoT Core token.

        Returns:
            iot_core_token (str): The AWS IoT Core token.
        """
        if not self._tokens.iot_core_token or force:
            with self._session.history_tracker:
                await self._retrieve_cognito_token()
        return cast(str, self._tokens.iot_core_token)

    @api_call
    async def _get_login_url(self) -> str:
        """Authorize the hOn account.

        Returns:
            url (str|None): The URL to login to the hOn account.
        """
        self._tokens = _Tokens()
        self._session.clear_cookies()

        _LOGGER.info("Starting OAuth2 authorization")

        response = await self._session.get(
            f"{const.AUTH_API_URL}/services/oauth2/authorize/expid_Login",
            params={
                "response_type": "token id_token",
                "client_id": const.CLIENT_ID,
                "redirect_uri": "hon://mobilesdk/detect/oauth/done",
                "display": "touch",
                "scope": "api openid refresh_token web",
                "nonce": str(uuid4()),
            },
        )
        return _handle_js_redirect(response.text).replace(
            "/NewhOnLogin", "/s/login/NewhOnLogin", 1
        )

    @api_call
    async def _login(self) -> str:
        """Login to the hOn account. Retrieve the token_url.

        Returns:
            token_url (str): The URL to retrieve the tokens.
        """
        login_url = await self._get_login_url()

        _LOGGER.info("Logging in")
        response = await self._session.post(
            f"{const.AUTH_API_URL}/s/sfsites/aura",
            data=message_action_data(self._email, self._password, login_url),
            params={"r": 3, "other.LightningLoginCustom.login": 1},
        )
        try:
            result = response.json()
            token_url: str = result["events"][0]["attributes"]["values"]["url"]
            return token_url
        except KeyError as e:
            raise InvalidCredentialsException() from e

    async def _retrieve_tokens(self) -> None:
        """Retrieve the access_token, id_token and refresh_token from the token_url."""
        url = await self._login()

        _LOGGER.info("Getting tokens")
        while True:
            response = await self._session.get(url)
            url = _handle_js_redirect(response.text)
            if url.startswith("hon"):
                break

        self._tokens = _Tokens.from_redirect_url(url)

    @api_call
    async def _retrieve_cognito_token(self) -> None:
        """Retrieve the Cognito token."""

        _LOGGER.info("Trying to retrieve Cognito token")
        with self._session.history_tracker:
            response = await self._session.post(
                f"{const.API_URL}/auth/v1/login",
                headers={"id-token": await self.get_id_token()},
                json=HonDevice.descriptor(),
            )
            response_data = response.json()

            self._tokens.cognito_token = response_data["cognitoUser"]["Token"]
            self._tokens.iot_core_token = response_data["tokenSigned"]

    @api_call
    async def _refresh(self) -> None:
        try:
            refresh_token = self._tokens.refresh_token
            response = await self._session.post(
                f"{const.AUTH_API_URL}/services/oauth2/token",
                params={
                    "client_id": const.CLIENT_ID,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            data = response.json()
            self._tokens = _Tokens.from_dict(data)
            self._tokens.refresh_token = refresh_token
        except HTTPStatusError as e:
            _LOGGER.warning(
                "Failed to obtain access token with refresh token: [%s: %s] %s",
                e.response.status_code,
                e.response.reason_phrase,
                e.response.text,
            )
