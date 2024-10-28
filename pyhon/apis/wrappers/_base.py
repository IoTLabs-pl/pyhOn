from collections.abc import Awaitable, Generator
from contextlib import AsyncExitStack, contextmanager
from functools import wraps
from typing import Any, Literal

from httpx import AsyncClient, Response

SessionWrapperMethod = Literal["GET", "POST"]


class SessionWrapper:
    _HEADERS: dict[str, str] = {}

    def __init__(self, session: AsyncClient | None = None) -> None:
        self._resources = AsyncExitStack()
        self._history: list["Response"] | None = None
        self._session = session

    async def _extra_headers(self) -> dict[str, str]:
        return self._HEADERS

    @property
    @contextmanager
    def history_tracker(self) -> Generator[list[Response]]:
        if self._history is None:
            self._history = []
            try:
                yield self._history
            except Exception as e:
                if self._history:
                    *history, last = self._history

                    body = (
                        f"{last.text[:1000]}... ({len(last.text)} bytes)"
                        if last.text
                        else "<EMPTY>"
                    )

                    e.add_note(f"Body: {body}")

                    for i, response in enumerate(history, -len(history)):
                        e.add_note(f"[{i}][{response.status_code}] {response.url}")

                raise
            finally:
                self._history = None
        else:
            yield self._history

    async def request(
        self,
        method: SessionWrapperMethod,
        *args: Any,
        headers: dict[str, str] = {},
        **kwargs: Any,
    ) -> "Response":
        headers = headers | (await self._extra_headers())

        with self.history_tracker as history:
            if self._session is None:
                raise RuntimeError("Session not initialized")

            response = await self._session.request(
                method, *args, headers=headers, follow_redirects=True, **kwargs
            )
            history.append(response)
            
            if response.is_error:
                response.raise_for_status()

            return response

    @wraps(AsyncClient.get)
    def get(self, *args: Any, **kwargs: Any) -> Awaitable[Response]:
        return self.request("GET", *args, **kwargs)

    @wraps(AsyncClient.post)
    def post(self, *args: Any, **kwargs: Any) -> Awaitable[Response]:
        return self.request("POST", *args, **kwargs)

    async def __aenter__(self) -> "SessionWrapper":
        if self._session is None:
            self._session = await self._resources.enter_async_context(AsyncClient())
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self._resources.aclose()
