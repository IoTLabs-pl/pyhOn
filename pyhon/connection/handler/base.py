from dataclasses import dataclass
from functools import update_wrapper
import logging
from collections import deque
from collections.abc import AsyncIterator, Generator
from contextlib import (
    AsyncExitStack,
    asynccontextmanager,
    AbstractAsyncContextManager,
    contextmanager,
)
from typing import Any, Literal

from aiohttp import ClientSession, ClientResponse


from pyhon import const

_LOGGER = logging.getLogger(__name__)


@dataclass
class ResponseWrapper:
    code: int
    url: str

    def __str__(self) -> str:
        return f"{self.code} - {self.url}"


SessionWrapperMethod = Literal["GET", "POST"]


class SessionWrapper:
    __MAX_HISTORY_LEN = 15
    _HEADERS = {"User-Agent": const.USER_AGENT}

    def __init__(self, session: ClientSession | None = None) -> None:

        self._resources = AsyncExitStack()
        self._history: deque[ResponseWrapper] = deque(maxlen=self.__MAX_HISTORY_LEN)
        self._history_tracking = False
        self._session = session

    async def _extra_headers(self) -> dict[str, str]:
        return self._HEADERS

    @property
    @contextmanager
    def session_history_tracker(self) -> Generator[None, None, None]:
        if self._history_tracking:
            yield
        else:
            self._history_tracking = True
            try:
                yield
            except Exception as e:
                self._log_history(str(e))
                raise
            finally:
                self._history_tracking = False

    @asynccontextmanager
    async def _request(
        self, method: SessionWrapperMethod, *args: Any, **kwargs: Any
    ) -> AsyncIterator[ClientResponse]:
        headers = kwargs.pop("headers", {}) | (await self._extra_headers())

        with self.session_history_tracker:
            if self._session is None:
                raise RuntimeError("Session not initialized")

            async with self._session.request(
                method, *args, headers=headers, **kwargs
            ) as response:
                self._history.append(
                    ResponseWrapper(response.status, str(response.request_info.url))
                )
                response.raise_for_status()
                yield response

    def get(
        self, *args: Any, **kwargs: Any
    ) -> AbstractAsyncContextManager[ClientResponse]:
        return self._request("GET", *args, **kwargs)

    def post(
        self, *args: Any, **kwargs: Any
    ) -> AbstractAsyncContextManager[ClientResponse]:
        return self._request("POST", *args, **kwargs)

    async def __aenter__(self) -> "SessionWrapper":
        if self._session is None:
            self._session = await self._resources.enter_async_context(ClientSession())
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._resources.aclose()

    def _log_history(self, text: str, flush: bool = True) -> None:
        lines = (
            ["hOn Authentication Error"]
            + [f" {i: 2d}     {resp}" for i, resp in enumerate(self._history, 1)]
            + [" Error ".center(40, "="), text, 40 * "="]
        )

        _LOGGER.error("\n".join(lines))

        if flush:
            self._history.clear()


update_wrapper(SessionWrapper.get, ClientSession.get)
update_wrapper(SessionWrapper.post, ClientSession.post)
