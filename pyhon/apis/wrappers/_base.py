import logging
from collections import deque
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager
from functools import update_wrapper
from typing import Any, Literal

from aiohttp import ClientResponse, ClientSession

_LOGGER = logging.getLogger(__name__)


SessionWrapperMethod = Literal["GET", "POST"]


class SessionWrapper:
    __MAX_HISTORY_LEN = 15
    _HEADERS: dict[str, str] = {}

    def __init__(self, session: ClientSession | None = None) -> None:
        self._resources = AsyncExitStack()
        self._history: deque[ClientResponse] = deque(maxlen=self.__MAX_HISTORY_LEN)
        self._history_tracking = False
        self._session = session

    async def _extra_headers(self) -> dict[str, str]:
        return self._HEADERS

    @property
    @asynccontextmanager
    async def history_tracker(self) -> AsyncGenerator[None, None, None]:
        if self._history_tracking:
            yield
        else:
            self._history_tracking = True
            try:
                yield
            except Exception as e:
                await self._log_history(str(e))
                raise
            finally:
                self._history_tracking = False

    @asynccontextmanager
    async def request(
        self,
        method: SessionWrapperMethod,
        *args: Any,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ClientResponse]:
        headers = (headers or {}) | (await self._extra_headers())

        async with self.history_tracker:
            if self._session is None:
                raise RuntimeError("Session not initialized")

            async with self._session.request(
                method, *args, headers=headers, **kwargs
            ) as response:
                await response.read()
                self._history.append(response)
                response.raise_for_status()
                yield response

    def get(
        self, *args: Any, **kwargs: Any
    ) -> AbstractAsyncContextManager[ClientResponse]:
        return self.request("GET", *args, **kwargs)

    def post(
        self, *args: Any, **kwargs: Any
    ) -> AbstractAsyncContextManager[ClientResponse]:
        return self.request("POST", *args, **kwargs)

    async def __aenter__(self) -> "SessionWrapper":
        if self._session is None:
            self._session = await self._resources.enter_async_context(ClientSession())
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._resources.aclose()

    async def _log_history(self, text: str, flush: bool = True) -> None:
        lines = (
            ["hOn Authentication Error"]
            + [
                f" {i: 2d}     {resp.status}-{resp.url}"
                for i, resp in enumerate(self._history, 1)
            ]
            + [
                " Error ".center(40, "="),
                text,
                40 * "=",
                await self._history[-1].text(),  # noqa: SLF001
                40 * "=",
            ]
        )

        _LOGGER.error("\n".join(lines))

        if flush:
            self._history.clear()


update_wrapper(SessionWrapper.get, ClientSession.get)
update_wrapper(SessionWrapper.post, ClientSession.post)
