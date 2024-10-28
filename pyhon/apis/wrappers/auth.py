from contextlib import suppress

from pyhon import const

from ._base import SessionWrapper

_DOMAIN = const.AUTH_API_URL.removeprefix("https://")


class AuthSessionWrapper(SessionWrapper):
    def clear_cookies(self) -> None:
        with suppress(AttributeError, KeyError):
            assert self._session is not None
            self._session.cookies.clear(_DOMAIN)
