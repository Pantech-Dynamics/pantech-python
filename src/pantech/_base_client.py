"""The HTTP core shared by ``Pantech`` and ``AsyncPantech``.

Everything that decides *what* is sent and *whether* to retry lives in
``BaseClient`` and is pure; ``SyncAPIClient`` and ``AsyncAPIClient`` only add
the I/O loop around it, so the two clients cannot drift apart.

The rules, from the API's conventions:

* ``Authorization: Bearer <key>`` on every request. The key is never logged
  and never shown in ``repr``.
* Every POST, PUT, PATCH and DELETE carries an ``Idempotency-Key`` (a UUIDv4
  unless the caller passes one). Retries resend the same key, so the API
  returns the first attempt's result instead of repeating the change.
* Retries (default 3) on connection errors, timeouts, 429, 500, 502, 503 and
  504, with jittered exponential backoff, or the server's ``Retry-After``.
* Writes the API does not replay (``_operations.NO_REPLAY``) are sent once;
  only a 429 is retried, because the API refuses it before doing anything.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import time
import uuid
from typing import (
    Any,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Union,
)

import httpx

from ._exceptions import (
    APIConnectionError,
    APITimeoutError,
    PantechError,
    make_api_error,
    parse_retry_after,
)
from ._streaming import ServerSentEvent, SSEDecoder
from ._types import NOT_GIVEN, NotGiven, Timeout
from ._version import __version__

__all__ = ["BaseClient", "SyncAPIClient", "AsyncAPIClient", "DEFAULT_BASE_URL"]

log = logging.getLogger("pantech")

DEFAULT_BASE_URL = "https://api.pantechdynamics.com/public/v1"
# Single requests of 20 to 48 seconds have been seen on busy days, so the read
# timeout is generous. It bounds each attempt, not the whole call.
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
DEFAULT_MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 0.5
MAX_RETRY_DELAY = 8.0
MAX_RETRY_AFTER = 60.0

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

ParseAs = str  # "json" (default), "bytes"


def _strip_not_given(values: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not values:
        return {}
    return {k: v for k, v in values.items() if not isinstance(v, NotGiven)}


def _query_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


class BaseClient:
    """Configuration and the pure parts of every request."""

    api_key: str
    base_url: str
    max_retries: int
    timeout: Timeout

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        timeout: Union[Timeout, NotGiven],
        max_retries: int,
        default_headers: Optional[Mapping[str, str]],
        user_agent: Optional[str],
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("PANTECH_API_KEY")
        if not key:
            raise PantechError(
                "No API key. Pass api_key=... or set PANTECH_API_KEY. "
                "Create a key in the console under Organization › API keys."
            )
        self.api_key = key
        url = base_url or os.environ.get("PANTECH_API_URL") or DEFAULT_BASE_URL
        self.base_url = url.rstrip("/")
        self.timeout = DEFAULT_TIMEOUT if isinstance(timeout, NotGiven) else timeout
        if max_retries < 0:
            raise ValueError("max_retries must be 0 or more")
        self.max_retries = max_retries
        self._default_headers = dict(default_headers or {})
        self._user_agent = user_agent or f"pantech-python/{__version__}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self.base_url!r})"

    # -- building requests ---------------------------------------------------

    def _build_request(
        self,
        http: Union[httpx.Client, httpx.AsyncClient],
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]],
        body: Any,
        idempotency_key: Optional[str],
        extra_headers: Optional[Mapping[str, str]],
        timeout: Union[Timeout, NotGiven],
        accept: str = "application/json",
    ) -> httpx.Request:
        headers: Dict[str, str] = {
            "Accept": accept,
            "User-Agent": self._user_agent,
        }
        headers.update(self._default_headers)
        headers["Authorization"] = f"Bearer {self.api_key}"
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        content: Optional[bytes] = None
        if body is not None and not isinstance(body, NotGiven):
            headers["Content-Type"] = "application/json"
            content = json.dumps(body, separators=(",", ":")).encode("utf-8")
        if extra_headers:
            headers.update(extra_headers)
        params = {k: _query_value(v) for k, v in _strip_not_given(query).items() if v is not None}
        effective_timeout = self.timeout if isinstance(timeout, NotGiven) else timeout
        return http.build_request(
            method,
            self.base_url + path,
            params=params or None,
            headers=headers,
            content=content,
            timeout=effective_timeout,
        )

    @staticmethod
    def _idempotency_key(method: str, given: Optional[str]) -> Optional[str]:
        if given is not None:
            return given
        return str(uuid.uuid4()) if method.upper() in WRITE_METHODS else None

    # -- retry decisions -----------------------------------------------------

    def _should_retry_status(self, status: int, no_replay: bool, retries_taken: int, max_retries: int) -> bool:
        if retries_taken >= max_retries or status not in RETRYABLE_STATUSES:
            return False
        return status == 429 or not no_replay

    def _should_retry_error(self, no_replay: bool, retries_taken: int, max_retries: int) -> bool:
        return retries_taken < max_retries and not no_replay

    @staticmethod
    def _retry_delay(retries_taken: int, response: Optional[httpx.Response]) -> float:
        if response is not None:
            retry_after = parse_retry_after(response.headers.get("retry-after"))
            if retry_after is not None:
                return min(retry_after, MAX_RETRY_AFTER)
        delay = min(INITIAL_RETRY_DELAY * (1 << min(retries_taken, 16)), MAX_RETRY_DELAY)
        # Half jitter: somewhere in [delay/2, delay], so throttled clients spread out.
        return delay / 2 + random.random() * delay / 2  # noqa: S311 - jitter, not a secret

    # -- responses -----------------------------------------------------------

    @staticmethod
    def _parse(response: httpx.Response, parse_as: ParseAs) -> Any:
        if parse_as == "bytes":
            return response.content
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    @staticmethod
    def _log_attempt(method: str, path: str, status: Union[int, str], attempt: int) -> None:
        # Never the headers or the body: they carry the key and customer data.
        log.debug("%s %s -> %s (attempt %d)", method, path, status, attempt)


def _connection_error(exc: Exception) -> APIConnectionError:
    if isinstance(exc, httpx.TimeoutException):
        return APITimeoutError()
    return APIConnectionError(f"Could not connect to the Pantech API: {type(exc).__name__}.")


class SyncAPIClient(BaseClient):
    """The blocking HTTP loop."""

    _http: httpx.Client

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        timeout: Union[Timeout, NotGiven],
        max_retries: int,
        default_headers: Optional[Mapping[str, str]],
        user_agent: Optional[str],
        http_client: Optional[httpx.Client],
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            user_agent=user_agent,
        )
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(follow_redirects=False)
        self._sleep: Callable[[float], None] = time.sleep
        self._clock: Callable[[], float] = time.monotonic

    def close(self) -> None:
        """Closes the connection pool (unless you passed your own ``http_client``)."""
        if self._owns_http:
            self._http.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Any = None,
        idempotency_key: Optional[str] = None,
        no_replay: bool = False,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
        max_retries: Optional[int] = None,
        parse_as: ParseAs = "json",
    ) -> Any:
        """Sends one API call with retries and returns the parsed body.

        *path* is relative to the base URL (``"/instances"``). This is the
        escape hatch for anything the typed methods do not cover yet.
        """
        response = self._send(
            method,
            path,
            query=query,
            body=body,
            idempotency_key=idempotency_key,
            no_replay=no_replay,
            extra_headers=extra_headers,
            timeout=timeout,
            max_retries=max_retries,
            accept="application/pdf" if parse_as == "bytes" else "application/json",
        )
        return self._parse(response, parse_as)

    def _send(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]],
        body: Any,
        idempotency_key: Optional[str],
        no_replay: bool,
        extra_headers: Optional[Mapping[str, str]],
        timeout: Union[Timeout, NotGiven],
        max_retries: Optional[int],
        accept: str,
        stream: bool = False,
    ) -> httpx.Response:
        method = method.upper()
        key = self._idempotency_key(method, idempotency_key)
        limit = self.max_retries if max_retries is None else max_retries
        retries_taken = 0
        while True:
            request = self._build_request(
                self._http,
                method,
                path,
                query=query,
                body=body,
                idempotency_key=key,
                extra_headers=extra_headers,
                timeout=timeout,
                accept=accept,
            )
            try:
                response = self._http.send(request, stream=stream)
            except httpx.TransportError as exc:
                self._log_attempt(method, path, type(exc).__name__, retries_taken + 1)
                if self._should_retry_error(no_replay, retries_taken, limit):
                    self._sleep(self._retry_delay(retries_taken, None))
                    retries_taken += 1
                    continue
                raise _connection_error(exc) from None
            self._log_attempt(method, path, response.status_code, retries_taken + 1)
            if response.is_success:
                return response
            if self._should_retry_status(response.status_code, no_replay, retries_taken, limit):
                response.close()
                self._sleep(self._retry_delay(retries_taken, response))
                retries_taken += 1
                continue
            if stream:
                response.read()
                response.close()
            raise make_api_error(response)

    def _paginate(
        self,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
    ) -> Iterator[Any]:
        params = _strip_not_given(query)
        seen: List[str] = []
        while True:
            page = self.request("GET", path, query=params, extra_headers=extra_headers, timeout=timeout)
            yield from page.get("data") or []
            cursor = page.get("next_cursor")
            if not cursor or cursor in seen:
                return
            seen.append(cursor)
            params = {**params, "cursor": cursor}

    def _stream_events(
        self,
        path: str,
        *,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
    ) -> Iterator[ServerSentEvent]:
        response = self._send(
            "GET",
            path,
            query=None,
            body=None,
            idempotency_key=None,
            no_replay=False,
            extra_headers=extra_headers,
            timeout=timeout,
            max_retries=None,
            accept="text/event-stream",
            stream=True,
        )
        decoder = SSEDecoder()
        try:
            for line in response.iter_lines():
                event = decoder.feed(line)
                if event is not None:
                    yield event
            event = decoder.feed("")
            if event is not None:
                yield event
        finally:
            response.close()


class AsyncAPIClient(BaseClient):
    """The asyncio HTTP loop. Same rules as ``SyncAPIClient``."""

    _http: httpx.AsyncClient

    def __init__(
        self,
        *,
        api_key: Optional[str],
        base_url: Optional[str],
        timeout: Union[Timeout, NotGiven],
        max_retries: int,
        default_headers: Optional[Mapping[str, str]],
        user_agent: Optional[str],
        http_client: Optional[httpx.AsyncClient],
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            user_agent=user_agent,
        )
        self._owns_http = http_client is None
        self._http = http_client or httpx.AsyncClient(follow_redirects=False)
        self._sleep: Callable[[float], Any] = asyncio.sleep
        self._clock: Callable[[], float] = time.monotonic

    async def close(self) -> None:
        """Closes the connection pool (unless you passed your own ``http_client``)."""
        if self._owns_http:
            await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        body: Any = None,
        idempotency_key: Optional[str] = None,
        no_replay: bool = False,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
        max_retries: Optional[int] = None,
        parse_as: ParseAs = "json",
    ) -> Any:
        """Sends one API call with retries and returns the parsed body."""
        response = await self._send(
            method,
            path,
            query=query,
            body=body,
            idempotency_key=idempotency_key,
            no_replay=no_replay,
            extra_headers=extra_headers,
            timeout=timeout,
            max_retries=max_retries,
            accept="application/pdf" if parse_as == "bytes" else "application/json",
        )
        return self._parse(response, parse_as)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Mapping[str, Any]],
        body: Any,
        idempotency_key: Optional[str],
        no_replay: bool,
        extra_headers: Optional[Mapping[str, str]],
        timeout: Union[Timeout, NotGiven],
        max_retries: Optional[int],
        accept: str,
        stream: bool = False,
    ) -> httpx.Response:
        method = method.upper()
        key = self._idempotency_key(method, idempotency_key)
        limit = self.max_retries if max_retries is None else max_retries
        retries_taken = 0
        while True:
            request = self._build_request(
                self._http,
                method,
                path,
                query=query,
                body=body,
                idempotency_key=key,
                extra_headers=extra_headers,
                timeout=timeout,
                accept=accept,
            )
            try:
                response = await self._http.send(request, stream=stream)
            except httpx.TransportError as exc:
                self._log_attempt(method, path, type(exc).__name__, retries_taken + 1)
                if self._should_retry_error(no_replay, retries_taken, limit):
                    await self._sleep(self._retry_delay(retries_taken, None))
                    retries_taken += 1
                    continue
                raise _connection_error(exc) from None
            self._log_attempt(method, path, response.status_code, retries_taken + 1)
            if response.is_success:
                return response
            if self._should_retry_status(response.status_code, no_replay, retries_taken, limit):
                await response.aclose()
                await self._sleep(self._retry_delay(retries_taken, response))
                retries_taken += 1
                continue
            if stream:
                await response.aread()
                await response.aclose()
            raise make_api_error(response)

    async def _paginate(
        self,
        path: str,
        *,
        query: Optional[Mapping[str, Any]] = None,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
    ) -> AsyncIterator[Any]:
        params = _strip_not_given(query)
        seen: List[str] = []
        while True:
            page = await self.request("GET", path, query=params, extra_headers=extra_headers, timeout=timeout)
            for item in page.get("data") or []:
                yield item
            cursor = page.get("next_cursor")
            if not cursor or cursor in seen:
                return
            seen.append(cursor)
            params = {**params, "cursor": cursor}

    async def _stream_events(
        self,
        path: str,
        *,
        extra_headers: Optional[Mapping[str, str]] = None,
        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,
    ) -> AsyncIterator[ServerSentEvent]:
        response = await self._send(
            "GET",
            path,
            query=None,
            body=None,
            idempotency_key=None,
            no_replay=False,
            extra_headers=extra_headers,
            timeout=timeout,
            max_retries=None,
            accept="text/event-stream",
            stream=True,
        )
        decoder = SSEDecoder()
        try:
            async for line in response.aiter_lines():
                event = decoder.feed(line)
                if event is not None:
                    yield event
            event = decoder.feed("")
            if event is not None:
                yield event
        finally:
            await response.aclose()
