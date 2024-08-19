from pyhon import const
from pyhon.connection.handler.base import SessionWrapper


class AnonymousSessionWrapper(SessionWrapper):
    _HEADERS = SessionWrapper._HEADERS | {"x-api-key": const.API_KEY}
