from collections.abc import Awaitable, Generator
from contextlib import AsyncExitStack, contextmanager
from contextvars import ContextVar
from functools import update_wrapper, wraps
from typing import TYPE_CHECKING, Any, Literal

from httpx import AsyncClient, Response

SessionWrapperMethod = Literal["GET", "POST"]


CALLER = ContextVar("invokers", default="<unknown>")


def api_call(invoker: Any):
    @wraps(invoker)
    async def wrapper(*args: Any, **kwargs: Any):
        old_caller = CALLER.get()
        CALLER.set(invoker.__qualname__)
        rval =  await invoker(*args, **kwargs)
        CALLER.set(old_caller)
        return rval

    return wrapper


class SessionWrapper:
    _HEADERS: dict[str, str] = {}

    def __init__(self, session: AsyncClient) -> None:
        self._resources = AsyncExitStack()
        self._history: list[tuple["Response", str]] | None = None
        self._session = session

    async def _extra_headers(self) -> dict[str, str]:
        return self._HEADERS

    @property
    @contextmanager
    def history_tracker(self) -> Generator[list[tuple[Response, str]]]:
        if self._history is None:
            self._history = []
            try:
                yield self._history
            except Exception as e:
                if self._history:
                    *history, (last, caller) = self._history

                    body = (
                        f"{last.text[:1000]}... ({len(last.text)} bytes)"
                        if last.text
                        else "<EMPTY>"
                    )

                    e.add_note(f"Body: {body}")

                    for i, (response, caller) in enumerate(history, -len(history)):
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
            history.append((response, CALLER.get()))

            if response.is_error:
                response.raise_for_status()

            return response

    def get(self, *args: Any, **kwargs: Any) -> Awaitable[Response]:
        return self.request("GET", *args, **kwargs)

    def post(self, *args: Any, **kwargs: Any) -> Awaitable[Response]:
        return self.request("POST", *args, **kwargs)

    if TYPE_CHECKING:
        update_wrapper(get, AsyncClient.get)
        update_wrapper(post, AsyncClient.post)
