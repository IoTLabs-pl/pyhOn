from pyhon import const

from ._base import SessionWrapper


class AnonymousSessionWrapper(SessionWrapper):
    _HEADERS = SessionWrapper._HEADERS | {"x-api-key": const.API_KEY}
