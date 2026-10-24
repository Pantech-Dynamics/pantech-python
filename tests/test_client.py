from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import httpx
import pytest

import pantech
from pantech import NOT_GIVEN

from .conftest import KEY, Recorder, json_response


def test_reads_key_and_url_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PANTECH_API_KEY", "PAN_env")
    monkeypatch.setenv("PANTECH_API_URL", "https://api.example.com/public/v1/")
    client = pantech.Pantech()
    assert client.api_key == "PAN_env"
    assert client.base_url == "https://api.example.com/public/v1"
    client.close()


def test_defaults_to_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PANTECH_API_URL", raising=False)
    with pantech.Pantech(api_key="PAN_x") as client:
        assert client.base_url == "https://api.pantechdynamics.com/public/v1"


def test_missing_key_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PANTECH_API_KEY", raising=False)
    with pytest.raises(pantech.PantechError, match="PANTECH_API_KEY"):
        pantech.Pantech()


def test_key_never_in_repr() -> None:
    client = pantech.Pantech(api_key=KEY)
    assert KEY not in repr(client)
    client.close()


def test_sends_auth_user_agent_and_json(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"operation_id": "op_1", "resource_id": "vm_1", "status": "submitted"}))
    client = make_client(rec)
    out = client.instances.rename("vm_1", name="web-2")
    assert out["operation_id"] == "op_1"
    req = rec.requests[0]
    assert req.method == "POST"
    assert str(req.url) == "https://api.test/public/v1/instances/vm_1/rename"
    assert req.headers["authorization"] == f"Bearer {KEY}"
    assert req.headers["user-agent"] == f"pantech-python/{pantech.__version__}"
    assert req.headers["content-type"] == "application/json"
    assert json.loads(req.content) == {"name": "web-2"}


def test_not_given_is_left_out_and_none_is_null(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {}))
    client = make_client(rec)
    client.load_balancers.update("lb_1", name=NOT_GIVEN, extra_body={"x": None})
    assert json.loads(rec.requests[0].content) == {"x": None}


def test_query_filters_and_extra_query(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"data": [], "next_cursor": None}))
    client = make_client(rec)
    client.instances.list(q="web", limit=10, extra_query={"flag": True})
    params = rec.requests[0].url.params
    assert params["q"] == "web"
    assert params["limit"] == "10"
    assert params["flag"] == "true"
    assert "cursor" not in params


def test_path_params_are_escaped(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {}))
    client = make_client(rec)
    client.instances.get("../me")
    assert rec.requests[0].url.raw_path == b"/public/v1/instances/..%2Fme"
    with pytest.raises(ValueError):
        client.instances.get("")


def test_extra_headers_and_default_headers(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {}))
    client = make_client(rec, default_headers={"X-Team": "a"})
    client.me.get(extra_headers={"X-Trace": "t1"})
    assert rec.requests[0].headers["x-team"] == "a"
    assert rec.requests[0].headers["x-trace"] == "t1"


def test_no_content_returns_none(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(httpx.Response(204))
    client = make_client(rec)
    assert client.me.revoke() is None
    assert rec.requests[0].method == "DELETE"
    assert str(rec.requests[0].url).endswith("/public/v1/me")


def test_receipt_pdf_is_bytes(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(httpx.Response(200, content=b"%PDF-1.7", headers={"Content-Type": "application/pdf"}))
    client = make_client(rec)
    assert client.billing.receipts.get_pdf("rcpt_1") == b"%PDF-1.7"
    assert rec.requests[0].headers["accept"] == "application/pdf"


def test_low_level_request(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"ok": True}))
    client = make_client(rec)
    assert client.request("GET", "/me") == {"ok": True}


def test_key_is_never_logged(make_client, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(503, {}), json_response(200, {}))
    client = make_client(rec)
    with caplog.at_level(logging.DEBUG):
        client.me.get()
    assert caplog.records, "expected debug logs"
    assert KEY not in caplog.text


def test_timeout_is_passed_per_request(make_client) -> None:  # type: ignore[no-untyped-def]
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return json_response(200, {})

    client = make_client(handler, timeout=5.0)
    client.me.get()
    client.me.get(timeout=1.5)
    assert seen[0]["read"] == 5.0
    assert seen[1]["read"] == 1.5


async def test_async_client_basics(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"organization_id": "org_1"}))
    async with make_async_client(rec) as client:
        me = await client.me.get()
    assert me["organization_id"] == "org_1"
    assert rec.requests[0].headers["authorization"] == f"Bearer {KEY}"


def test_versions_agree() -> None:
    root = Path(__file__).resolve().parent.parent
    declared = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(), re.M)
    assert declared and declared.group(1) == pantech.__version__
    heading = re.search(r"^## (\d+\.\d+\.\d+) \(", (root / "CHANGELOG.md").read_text(), re.M)
    assert heading and heading.group(1) == pantech.__version__
