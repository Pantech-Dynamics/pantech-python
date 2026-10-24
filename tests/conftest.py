from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest

import pantech

Handler = Callable[[httpx.Request], httpx.Response]
KEY = "PAN_test_key_do_not_log"


def json_response(status: int = 200, body: Any = None, headers: Optional[Dict[str, str]] = None) -> httpx.Response:
    content = b"" if body is None else json.dumps(body).encode()
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    return httpx.Response(status, content=content, headers=hdrs)


def problem(
    status: int, code: str, detail: str = "", headers: Optional[Dict[str, str]] = None, **extra: Any
) -> httpx.Response:
    body = {"type": "about:blank", "title": "Problem", "status": status, "code": code, "detail": detail}
    body.update(extra)
    return httpx.Response(
        status,
        content=json.dumps(body).encode(),
        headers={"Content-Type": "application/problem+json", **(headers or {})},
    )


class Recorder:
    """A MockTransport handler that answers from a script and records every request."""

    def __init__(self, *responses: Any) -> None:
        self.responses: List[Any] = list(responses)
        self.requests: List[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.responses:
            return json_response(200, {})
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(request)  # type: ignore[no-any-return]
        return item  # type: ignore[no-any-return]


@pytest.fixture
def sleeps() -> List[float]:
    return []


@pytest.fixture
def make_client(sleeps: List[float]) -> Callable[..., pantech.Pantech]:
    clients: List[pantech.Pantech] = []

    def make(handler: Handler, **kwargs: Any) -> pantech.Pantech:
        client = pantech.Pantech(
            api_key=kwargs.pop("api_key", KEY),
            base_url=kwargs.pop("base_url", "https://api.test/public/v1"),
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
            **kwargs,
        )
        client._sleep = sleeps.append
        clients.append(client)
        return client

    return make


@pytest.fixture
def make_async_client(sleeps: List[float]) -> Callable[..., pantech.AsyncPantech]:
    def make(handler: Handler, **kwargs: Any) -> pantech.AsyncPantech:
        client = pantech.AsyncPantech(
            api_key=kwargs.pop("api_key", KEY),
            base_url=kwargs.pop("base_url", "https://api.test/public/v1"),
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            **kwargs,
        )

        async def fake_sleep(seconds: float) -> None:
            sleeps.append(seconds)

        client._sleep = fake_sleep
        return client

    return make
