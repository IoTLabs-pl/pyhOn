from pyhon import const

from ._base import SessionWrapper

_DOMAIN = const.AUTH_API_URL.rsplit("/", 1).pop()


class AuthSessionWrapper(SessionWrapper):
    def clear_cookies(self) -> None:
        if self._session is not None:
            self._session.cookie_jar.clear_domain(_DOMAIN)
