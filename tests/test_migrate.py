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


def test_list_providers(make_client) -> None:  # type: ignore[no-untyped-def]
    providers = [
        {"slug": "gcp", "name": "Google Cloud", "access": "federated", "available": True},
        {"slug": "hetzner", "name": "Hetzner", "access": "agent", "available": True},
    ]
    rec = Recorder(json_response(200, {"data": providers, "next_cursor": None}))
    page = make_client(rec).migrate.providers.list()
    assert [p["access"] for p in page["data"]] == ["federated", "agent"]
    assert (rec.requests[0].method, rec.requests[0].url.path) == ("GET", "/public/v1/cloud-providers")


def test_create_connection_to_another_provider(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, connection("awaiting_agent")))
    make_client(rec).migrate.connections.create(provider="hetzner", name="Hetzner")
    assert body(rec.requests[0]) == {"provider": "hetzner", "name": "Hetzner"}


def test_update_connection_with_federation(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, connection("verifying")))
    azure = {"tenant_id": "t", "client_id": "c", "subscription_ids": ["s"]}
    make_client(rec).migrate.connections.update("cc_1", azure=azure)
    assert body(rec.requests[0]) == {"azure": azure}


def test_enroll_and_revoke_agent(make_client) -> None:  # type: ignore[no-untyped-def]
    enrollment = {"code": "ENR-1", "expires_at": "2026-11-25T11:00:00Z", "enroll_command": "agent enroll ENR-1"}
    rec = Recorder(json_response(201, enrollment), json_response(200, connection("awaiting_agent")))
    client = make_client(rec)
    assert client.migrate.connections.enroll_agent("cc_1")["code"] == "ENR-1"
    conn = client.migrate.connections.revoke_agent("cc_1")
    assert conn["status"] == "awaiting_agent"
    first, second = rec.requests
    assert (first.method, first.url.path) == ("POST", "/public/v1/cloud-connections/cc_1/agent-enrollments")
    assert first.content == b""
    assert (second.method, second.url.path) == ("DELETE", "/public/v1/cloud-connections/cc_1/agent")
    assert first.headers["idempotency-key"] and second.headers["idempotency-key"]


def test_send_invites(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"results": [{"key": "user:alice", "outcome": "invited"}], "migration": {}}))
    result = make_client(rec).migrate.migrations.send_invites("mig_1", keys=["user:alice"])
    assert result["results"][0]["outcome"] == "invited"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/migrations/mig_1/invites")
    assert body(req) == {"keys": ["user:alice"]}
    assert req.headers["idempotency-key"]


def test_copy_access_get_and_set(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"connection_id": "cc_1", "status": "awaiting_role"}))
    client = make_client(rec)
    client.migrate.copy_access.set("cc_1", buckets=["assets", "logs"])
    client.migrate.copy_access.get("cc_1")
    put, get = rec.requests
    assert (put.method, put.url.path) == ("PUT", "/public/v1/cloud-connections/cc_1/copy-access")
    assert body(put) == {"buckets": ["assets", "logs"]}
    assert put.headers["idempotency-key"]
    assert (get.method, get.url.path) == ("GET", "/public/v1/cloud-connections/cc_1/copy-access")


def test_bucket_imports(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"id": "bim_1", "status": "queued", "pass": 1}))
    client = make_client(rec)
    started = client.migrate.bucket_imports.start(
        connection_id="cc_1", source_bucket="assets", destination_bucket_name="assets"
    )
    assert started["pass"] == 1
    client.migrate.bucket_imports.resync("bim_1", mirror_deletes=True)
    client.migrate.bucket_imports.cancel("bim_1")
    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("POST", "/public/v1/bucket-imports"),
        ("POST", "/public/v1/bucket-imports/bim_1/resync"),
        ("POST", "/public/v1/bucket-imports/bim_1/cancel"),
    ]
    assert body(rec.requests[0]) == {
        "connection_id": "cc_1",
        "source_bucket": "assets",
        "destination_bucket_name": "assets",
    }
    assert body(rec.requests[1]) == {"mirror_deletes": True}


def test_bucket_imports_list_all_follows_the_cursor(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, {"data": [{"id": "bim_1"}], "next_cursor": "c2"}),
        json_response(200, {"data": [{"id": "bim_2"}], "next_cursor": None}),
    )
    ids = [imp["id"] for imp in make_client(rec).migrate.bucket_imports.list_all()]
    assert ids == ["bim_1", "bim_2"]
    assert rec.requests[1].url.params["cursor"] == "c2"


def test_server_copies(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"id": "scp_1", "status": "copying"}))
    client = make_client(rec)
    client.migrate.server_copies.start("mig_1", item_key="instance:us-east-1:i-1", subnet_id="sn_1")
    client.migrate.server_copies.get_template("mig_1", item_key="instance:us-east-1:i-1", create_snapshots=True)
    client.migrate.server_copies.sync("scp_1", snapshots={"vol-1": "snap-2"})
    client.migrate.server_copies.cut_over("scp_1")
    client.migrate.server_copies.cancel("scp_1")
    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("POST", "/public/v1/migrations/mig_1/server-copies"),
        ("GET", "/public/v1/migrations/mig_1/server-copy-template"),
        ("POST", "/public/v1/server-copies/scp_1/sync"),
        ("POST", "/public/v1/server-copies/scp_1/cutover"),
        ("POST", "/public/v1/server-copies/scp_1/cancel"),
    ]
    assert body(rec.requests[0]) == {"item_key": "instance:us-east-1:i-1", "subnet_id": "sn_1"}
    template = rec.requests[1].url.params
    assert (template["item_key"], template["create_snapshots"]) == ("instance:us-east-1:i-1", "true")
    assert body(rec.requests[2]) == {"snapshots": {"vol-1": "snap-2"}}


def test_database_imports(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"id": "dbi_1", "status": "ready"}))
    client = make_client(rec)
    client.migrate.database_imports.start(
        "mig_1",
        item_key="database:us-east-1:orders",
        destination_database_id="db_1",
        source_ref="prod-db",
        mode="replicate",
    )
    client.migrate.database_imports.check_readiness("dbi_1")
    client.migrate.database_imports.cut_over("dbi_1")
    client.migrate.database_imports.cancel("dbi_1")
    client.migrate.database_imports.revoke_access("dbi_1")
    assert [r.url.path for r in rec.requests] == [
        "/public/v1/migrations/mig_1/database-imports",
        "/public/v1/database-imports/dbi_1/readiness",
        "/public/v1/database-imports/dbi_1/cutover",
        "/public/v1/database-imports/dbi_1/cancel",
        "/public/v1/database-imports/dbi_1/revoke-access",
    ]
    assert body(rec.requests[0])["mode"] == "replicate"
    assert all(r.method == "POST" and r.headers["idempotency-key"] for r in rec.requests)
    assert all(r.content == b"" for r in rec.requests[1:])


def test_kubernetes_moves(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"id": "kmv_1", "status": "exporting"}))
    client = make_client(rec)
    client.migrate.kubernetes_moves.start(
        "mig_1", item_key="kubernetes_cluster:us-east-1:prod", cluster_id="k8s_1", copy_volumes=True
    )
    ref = {"group": "apps", "kind": "DaemonSet", "namespace": "kube-system", "name": "agent"}
    client.migrate.kubernetes_moves.preview("kmv_1", allow_privileged=[ref])
    client.migrate.kubernetes_moves.apply("kmv_1")
    client.migrate.kubernetes_moves.sync_volumes("kmv_1")
    client.migrate.kubernetes_moves.cut_over("kmv_1", source_writes_stopped=True)
    client.migrate.kubernetes_moves.cancel("kmv_1")
    client.migrate.kubernetes_moves.get_source_access()
    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("POST", "/public/v1/migrations/mig_1/kubernetes-moves"),
        ("POST", "/public/v1/kubernetes-moves/kmv_1/preview"),
        ("POST", "/public/v1/kubernetes-moves/kmv_1/apply"),
        ("POST", "/public/v1/kubernetes-moves/kmv_1/sync-volumes"),
        ("POST", "/public/v1/kubernetes-moves/kmv_1/cutover"),
        ("POST", "/public/v1/kubernetes-moves/kmv_1/cancel"),
        ("GET", "/public/v1/kubernetes-moves/source-access"),
    ]
    assert body(rec.requests[1]) == {"allow_privileged": [ref]}
    assert body(rec.requests[4]) == {"source_writes_stopped": True}


def test_download_kubernetes_manifests_as_yaml(make_client) -> None:  # type: ignore[no-untyped-def]
    manifests = "apiVersion: v1\nkind: Namespace\n"
    rec = Recorder(httpx.Response(200, text=manifests, headers={"content-type": "application/yaml"}))
    text = make_client(rec).migrate.kubernetes_moves.download_manifests("kmv_1")
    assert text == manifests
    req = rec.requests[0]
    assert req.url.path == "/public/v1/kubernetes-moves/kmv_1/manifests"
    assert req.headers["accept"] == "application/yaml"


async def test_async_bucket_import_start(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"id": "bim_1", "status": "queued"}))
    started = await make_async_client(rec).migrate.bucket_imports.start(
        connection_id="cc_1", source_bucket="assets", destination_bucket_id="bkt_1"
    )
    assert started["id"] == "bim_1"
    assert rec.requests[0].headers["idempotency-key"]


def test_keyword_fields_are_typed() -> None:
    from pantech.types import BucketImport, ServerCopy

    assert "pass" in BucketImport.__required_keys__
    assert "pass" in ServerCopy.__optional_keys__
