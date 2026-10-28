from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest

import pantech
from pantech._operations import NOT_IN_SDK

from .conftest import Recorder, json_response

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _codegen import schemas_only_for
from _spec import load_spec


def connection(status: str, failure: Any = None) -> Dict[str, Any]:
    return {
        "id": "cc_1",
        "provider": "aws",
        "name": "Production",
        "status": status,
        "failure": failure,
        "role_arn": None,
        "aws_account_id": None,
        "verified_at": None,
        "created_at": "2026-10-27T10:00:00Z",
        "updated_at": "2026-10-27T10:00:00Z",
        "setup": {
            "issuer_url": "https://id.example.test",
            "audience": "aud",
            "subject": "cc_1",
            "quick_create_url": "https://console.example.test/stack",
            "template": "{}",
        },
    }


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_create_connection_sends_the_body_and_a_key(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, connection("awaiting_role")))
    conn = make_client(rec).migrate.connections.create(name="Production")
    assert conn["setup"]["quick_create_url"] == "https://console.example.test/stack"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/cloud-connections")
    assert body(req) == {"name": "Production"}
    assert req.headers["idempotency-key"]


def test_update_connection_sends_only_what_is_given(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, connection("verifying")))
    arn = "arn:aws:iam::123456789012:role/PantechMigrateReadOnly"
    make_client(rec).migrate.connections.update("cc_1", role_arn=arn)
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("PATCH", "/public/v1/cloud-connections/cc_1")
    assert body(req) == {"role_arn": arn}


def test_get_scan_with_inventory(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"id": "cs_1", "status": "succeeded", "inventory": {"instances": []}}))
    scan = make_client(rec).migrate.scans.get("cs_1", include="inventory")
    assert scan["inventory"] == {"instances": []}
    assert rec.requests[0].url.path == "/public/v1/cloud-scans/cs_1"
    assert rec.requests[0].url.params["include"] == "inventory"


def test_get_scan_without_include_sends_no_query(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"id": "cs_1", "status": "running"}))
    make_client(rec).migrate.scans.get("cs_1")
    assert rec.requests[0].url.query == b""


def test_start_scan_is_a_write_without_a_body(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"id": "cs_1", "status": "queued"}))
    scan = make_client(rec).migrate.scans.start("cc_1")
    assert scan["status"] == "queued"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/cloud-connections/cc_1/scans")
    assert req.headers["idempotency-key"]


def test_update_item_and_export_terraform(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, {"id": "mig_1", "summary": {"planned": 1, "excluded": 1, "unsupported": 0, "by_kind": {}}}),
        json_response(200, {"files": [{"name": "main.tf", "content": "terraform {}\n"}]}),
    )
    client = make_client(rec)
    plan = client.migrate.migrations.update_item("mig_1", key="volume:us-east-1:vol-1", excluded=True)
    assert plan["summary"]["excluded"] == 1
    assert (rec.requests[0].method, rec.requests[0].url.path) == ("PATCH", "/public/v1/migrations/mig_1/items")
    assert body(rec.requests[0]) == {"key": "volume:us-east-1:vol-1", "excluded": True}
    tf = client.migrate.migrations.export_terraform("mig_1")
    assert tf["files"][0]["name"] == "main.tf"
    assert rec.requests[1].url.path == "/public/v1/migrations/mig_1/terraform"


def test_connection_wait_polls_until_connected(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, connection("verifying")), json_response(200, connection("connected")))
    conn = make_client(rec).migrate.connections.wait("cc_1", poll_interval=1)
    assert conn["status"] == "connected"
    assert len(rec.requests) == 2
    assert sleeps == [1]


def test_connection_wait_raises_on_failure(make_client) -> None:  # type: ignore[no-untyped-def]
    failure = {"code": "assume_role_denied", "message": "Check the role's trust policy."}
    rec = Recorder(json_response(200, connection("failed", failure)))
    with pytest.raises(pantech.CloudFailedError) as info:
        make_client(rec).migrate.connections.wait("cc_1")
    assert info.value.code == "assume_role_denied"
    assert info.value.kind == "connection"
    assert "trust policy" in str(info.value)


def test_scan_wait_polls_until_succeeded(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, {"id": "cs_1", "status": "queued"}),
        json_response(200, {"id": "cs_1", "status": "running"}),
        json_response(200, {"id": "cs_1", "status": "succeeded"}),
    )
    scan = make_client(rec).migrate.scans.wait("cs_1")
    assert scan["status"] == "succeeded"
    assert rec.requests[0].url.path == "/public/v1/cloud-scans/cs_1"
    assert sleeps == [10.0, 10.0]


def test_scan_wait_times_out(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    client = make_client(Recorder(json_response(200, {"id": "cs_1", "status": "running"})))
    now: List[float] = [0.0]
    client._clock = lambda: now[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client._sleep = fake_sleep
    with pytest.raises(pantech.WaitTimeoutError, match="still running"):
        client.migrate.scans.wait("cs_1", timeout=15, poll_interval=10)
    assert sleeps == [10, 5]


async def test_async_scan_wait_raises_on_failure(make_async_client) -> None:  # type: ignore[no-untyped-def]
    failure = {"code": "scan_too_large", "message": "Too much to read."}
    rec = Recorder(json_response(200, {"id": "cs_2", "status": "failed", "failure": failure}))
    with pytest.raises(pantech.CloudFailedError) as info:
        await make_async_client(rec).migrate.scans.wait("cs_2")
    assert info.value.kind == "scan"
    assert info.value.code == "scan_too_large"


async def test_async_connection_wait(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, connection("connected")))
    conn = await make_async_client(rec).migrate.connections.wait("cc_1")
    assert conn["id"] == "cc_1"


def test_types_leave_out_what_only_skipped_operations_use() -> None:
    skipped = schemas_only_for(load_spec(), frozenset(NOT_IN_SDK))
    assert skipped
    assert not [name for name in skipped if hasattr(pantech.types, name)]
    assert hasattr(pantech.types, "CloudConnection")
    assert hasattr(pantech.types, "Migration")
