from __future__ import annotations

import json
import logging
from typing import Any, Dict

import httpx
import pytest

import pantech

from .conftest import Recorder, json_response, problem

SECRET_ACCESS_KEY = "osk_sec_super_secret_do_not_log"


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def sample_bucket(**extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "bkt_1",
        "name": "app-assets",
        "region": "af-abj",
        "endpoint": "https://s3.af-abj.pantechdynamics.com",
        "status": "active",
        "versioning": True,
        "object_lock": False,
        "quota_bytes": 0,
        "public_prefixes": [],
        "created_at": "2026-11-24T12:00:00Z",
    }
    out.update(extra)
    return out


def sample_key(**extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "osk_1",
        "name": "ci-uploads",
        "region": "af-abj",
        "access_key_id": "PANOSK123456",
        "read_only": False,
        "buckets": ["app-assets"],
        "created_at": "2026-11-24T12:00:00Z",
    }
    out.update(extra)
    return out


def test_status_usage_and_keys_sync(make_client, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
    created_key = sample_key(
        secret_access_key=SECRET_ACCESS_KEY,
        endpoint="https://s3.af-abj.pantechdynamics.com",
    )
    rec = Recorder(
        json_response(200, {"enabled": True, "regions": ["af-abj"]}),
        json_response(200, {"range": "7d", "storage_bytes": 1024, "egress_bytes": 512, "requests": 10}),
        json_response(200, {"data": [sample_key()]}),
        json_response(201, created_key),
        httpx.Response(204),
    )
    client = make_client(rec)

    assert client.object_storage.get_status()["enabled"] is True
    assert client.object_storage.get_usage(range="7d")["range"] == "7d"
    assert client.object_storage.keys.list(region="af-abj")["data"][0]["id"] == "osk_1"

    with caplog.at_level(logging.DEBUG, logger="pantech"):
        key = client.object_storage.keys.create(
            name="ci-uploads",
            region="af-abj",
            read_only=False,
            buckets=["app-assets"],
            idempotency_key="osk-create-1",
        )
    assert key["secret_access_key"] == SECRET_ACCESS_KEY
    assert SECRET_ACCESS_KEY not in repr(key)
    assert SECRET_ACCESS_KEY not in str(key)
    assert "<hidden>" in repr(key)
    assert SECRET_ACCESS_KEY not in caplog.text
    assert json.loads(json.dumps(key))["secret_access_key"] == SECRET_ACCESS_KEY

    assert client.object_storage.keys.revoke("osk_1") is None

    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("GET", "/public/v1/object-storage"),
        ("GET", "/public/v1/object-storage/usage"),
        ("GET", "/public/v1/object-storage/keys"),
        ("POST", "/public/v1/object-storage/keys"),
        ("DELETE", "/public/v1/object-storage/keys/osk_1"),
    ]
    assert rec.requests[1].url.params["range"] == "7d"
    assert rec.requests[2].url.params["region"] == "af-abj"
    assert body(rec.requests[3]) == {
        "name": "ci-uploads",
        "region": "af-abj",
        "read_only": False,
        "buckets": ["app-assets"],
    }
    assert rec.requests[3].headers["idempotency-key"] == "osk-create-1"
    assert rec.requests[4].headers["idempotency-key"]


async def test_status_usage_and_keys_async(make_async_client) -> None:  # type: ignore[no-untyped-def]
    created_key = sample_key(
        secret_access_key=SECRET_ACCESS_KEY,
        endpoint="https://s3.af-abj.pantechdynamics.com",
    )
    rec = Recorder(
        json_response(200, {"enabled": True, "regions": ["af-abj"]}),
        json_response(200, {"range": "24h", "storage_bytes": 0, "egress_bytes": 0, "requests": 0}),
        json_response(200, {"data": [sample_key()]}),
        json_response(201, created_key),
        httpx.Response(204),
    )
    client = make_async_client(rec)

    assert (await client.object_storage.get_status())["enabled"] is True
    assert (await client.object_storage.get_usage(range="24h"))["range"] == "24h"
    assert (await client.object_storage.keys.list())["data"][0]["id"] == "osk_1"
    created = await client.object_storage.keys.create(name="ci-uploads", read_only=True)
    assert created["secret_access_key"] == SECRET_ACCESS_KEY
    assert SECRET_ACCESS_KEY not in repr(created)
    assert await client.object_storage.keys.revoke("osk_1") is None


def test_buckets_crud_stats_empty_and_rules_sync(make_client) -> None:  # type: ignore[no-untyped-def]
    bkt = sample_bucket()
    rec = Recorder(
        json_response(200, {"data": [bkt]}),
        json_response(201, bkt),
        json_response(200, bkt),
        json_response(200, sample_bucket(quota_bytes=1024, public_prefixes=["public/"])),
        json_response(200, {"object_count": 3, "storage_bytes": 4096}),
        json_response(200, {"rules": []}),
        json_response(200, {"rules": [{"allowed_origins": ["https://example.com"], "allowed_methods": ["GET"]}]}),
        json_response(200, {"rules": []}),
        json_response(
            200,
            {"rules": [{"id": "expire-logs", "prefix": "logs/", "enabled": True, "expiration_days": 30}]},
        ),
        json_response(200, {"tags": []}),
        json_response(200, {"tags": [{"key": "env", "value": "prod"}]}),
        json_response(200, {"enabled": False, "mode": "", "days": 0, "years": 0}),
        json_response(200, {"enabled": True, "mode": "GOVERNANCE", "days": 30, "years": 0}),
        json_response(200, {"deleted": 3}),
        json_response(202, {"operation_id": "op_1", "resource_id": "bkt_1", "status": "submitted"}),
    )
    client = make_client(rec)

    assert client.buckets.list()["data"][0]["id"] == "bkt_1"
    assert client.buckets.create(name="app-assets", region="af-abj", versioning=True)["id"] == "bkt_1"
    assert client.buckets.get("bkt_1")["name"] == "app-assets"
    assert client.buckets.update("bkt_1", quota_bytes=1024, public_prefixes=["public/"])["quota_bytes"] == 1024
    assert client.buckets.get_stats("bkt_1")["object_count"] == 3

    assert client.buckets.get_cors("bkt_1")["rules"] == []
    assert client.buckets.set_cors(
        "bkt_1",
        rules=[{"allowed_origins": ["https://example.com"], "allowed_methods": ["GET"]}],
    )["rules"][0]["allowed_origins"] == ["https://example.com"]
    assert client.buckets.get_lifecycle("bkt_1")["rules"] == []
    assert (
        client.buckets.set_lifecycle(
            "bkt_1",
            rules=[{"id": "expire-logs", "prefix": "logs/", "enabled": True, "expiration_days": 30}],
        )["rules"][0]["id"]
        == "expire-logs"
    )
    assert client.buckets.get_tags("bkt_1")["tags"] == []
    assert client.buckets.set_tags("bkt_1", tags=[{"key": "env", "value": "prod"}])["tags"][0]["key"] == "env"
    assert client.buckets.get_object_lock("bkt_1")["enabled"] is False
    assert (
        client.buckets.set_object_lock("bkt_1", enabled=True, mode="GOVERNANCE", days=30, years=0)["mode"]
        == "GOVERNANCE"
    )
    assert client.buckets.empty("bkt_1")["deleted"] == 3
    assert client.buckets.delete("bkt_1", force=True)["operation_id"] == "op_1"

    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("GET", "/public/v1/buckets"),
        ("POST", "/public/v1/buckets"),
        ("GET", "/public/v1/buckets/bkt_1"),
        ("PATCH", "/public/v1/buckets/bkt_1"),
        ("GET", "/public/v1/buckets/bkt_1/stats"),
        ("GET", "/public/v1/buckets/bkt_1/cors"),
        ("PUT", "/public/v1/buckets/bkt_1/cors"),
        ("GET", "/public/v1/buckets/bkt_1/lifecycle"),
        ("PUT", "/public/v1/buckets/bkt_1/lifecycle"),
        ("GET", "/public/v1/buckets/bkt_1/tags"),
        ("PUT", "/public/v1/buckets/bkt_1/tags"),
        ("GET", "/public/v1/buckets/bkt_1/object-lock"),
        ("PUT", "/public/v1/buckets/bkt_1/object-lock"),
        ("POST", "/public/v1/buckets/bkt_1/empty"),
        ("DELETE", "/public/v1/buckets/bkt_1"),
    ]
    assert body(rec.requests[12]) == {"enabled": True, "mode": "GOVERNANCE", "days": 30, "years": 0}
    assert rec.requests[14].url.params["force"] == "true"


async def test_buckets_and_rules_async(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(201, sample_bucket()),
        json_response(200, {"enabled": True, "mode": "COMPLIANCE", "days": 7, "years": 0}),
        json_response(200, {"deleted": 0}),
        json_response(202, {"operation_id": "op_2", "resource_id": "bkt_1", "status": "submitted"}),
    )
    client = make_async_client(rec)

    assert (await client.buckets.create(name="app-assets"))["id"] == "bkt_1"
    assert (await client.buckets.set_object_lock("bkt_1", enabled=True, mode="COMPLIANCE", days=7, years=0))[
        "mode"
    ] == "COMPLIANCE"
    assert (await client.buckets.empty("bkt_1"))["deleted"] == 0
    assert (await client.buckets.delete("bkt_1"))["operation_id"] == "op_2"


def test_objects_upload_download_and_ops_sync(make_client) -> None:  # type: ignore[no-untyped-def]
    payload = b"\x00\x01binary-body\xff"
    rec = Recorder(
        json_response(200, {"key": "raw.bin", "size_bytes": len(payload), "etag": '"e1"'}),
        json_response(200, {"key": "notes.txt", "size_bytes": 5, "etag": '"e2"'}),
        json_response(200, {"key": "empty.bin", "size_bytes": 0, "etag": '"e0"'}),
        httpx.Response(200, content=payload, headers={"Content-Type": "application/octet-stream"}),
        json_response(200, {"objects": [{"key": "raw.bin"}], "prefixes": []}),
        json_response(200, {"key": "raw.bin", "size_bytes": len(payload)}),
        json_response(200, {"url": "https://s3.test/signed-get", "expires_at": "2026-11-24T13:00:00Z"}),
        json_response(200, {"url": "https://s3.test/signed-put", "expires_at": "2026-11-24T13:00:00Z"}),
        json_response(200, {"prefix": "logs/"}),
        json_response(200, {"key": "archive/raw.bin", "etag": '"e1"'}),
        json_response(200, {"tags": [{"key": "tier", "value": "hot"}]}),
        json_response(200, {"ok": True}),
        json_response(200, {"key": "raw.bin", "public": True, "public_url": "https://s3.test/bkt/raw.bin"}),
        json_response(200, {"deleted": 1}),
    )
    client = make_client(rec)

    assert client.buckets.objects.upload("bkt_1", key="raw.bin", body=payload)["key"] == "raw.bin"
    assert (
        client.buckets.objects.upload("bkt_1", key="notes.txt", body=b"hello", content_type="text/plain")["key"]
        == "notes.txt"
    )
    assert client.buckets.objects.upload("bkt_1", key="empty.bin", body=b"")["size_bytes"] == 0
    assert client.buckets.objects.download("bkt_1", key="raw.bin", inline=True) == payload
    assert client.buckets.objects.list("bkt_1", prefix="raw", limit=50, versions=True)["objects"][0]["key"] == "raw.bin"
    assert client.buckets.objects.get_meta("bkt_1", key="raw.bin")["size_bytes"] == len(payload)
    assert client.buckets.objects.presign_download("bkt_1", key="raw.bin", expires_in_seconds=600)["url"].startswith(
        "https://"
    )
    assert client.buckets.objects.presign_upload("bkt_1", key="new.bin", content_type="application/octet-stream")[
        "url"
    ].startswith("https://")
    assert client.buckets.objects.create_folder("bkt_1", prefix="logs/")["prefix"] == "logs/"
    assert client.buckets.objects.copy("bkt_1", source_key="raw.bin", destination_key="archive/raw.bin")["key"] == (
        "archive/raw.bin"
    )
    assert client.buckets.objects.set_tags("bkt_1", key="raw.bin", tags=[{"key": "tier", "value": "hot"}])["tags"] == [
        {"key": "tier", "value": "hot"}
    ]
    assert (
        client.buckets.objects.set_lock(
            "bkt_1",
            key="raw.bin",
            retention_mode="GOVERNANCE",
            retain_until="2026-12-31T00:00:00Z",
            legal_hold=True,
        )["ok"]
        is True
    )
    assert client.buckets.objects.set_visibility("bkt_1", key="raw.bin", public=True)["public"] is True
    assert client.buckets.objects.delete("bkt_1", items=[{"key": "raw.bin"}])["deleted"] == 1

    up_default, up_text, up_empty, dl = rec.requests[:4]
    assert (up_default.method, up_default.url.path) == ("PUT", "/public/v1/buckets/bkt_1/objects/upload")
    assert up_default.url.params["key"] == "raw.bin"
    assert up_default.headers["content-type"] == "application/octet-stream"
    assert up_default.content == payload
    assert "idempotency-key" in up_default.headers

    assert up_text.headers["content-type"] == "text/plain"
    assert up_text.content == b"hello"

    assert up_empty.headers["content-type"] == "application/octet-stream"
    assert up_empty.content == b""

    assert (dl.method, dl.url.path) == ("GET", "/public/v1/buckets/bkt_1/objects/download")
    assert dl.url.params["key"] == "raw.bin"
    assert dl.url.params["inline"] == "true"
    assert dl.headers["accept"] == "application/octet-stream"

    lock_req = rec.requests[11]
    assert (lock_req.method, lock_req.url.path) == ("PUT", "/public/v1/buckets/bkt_1/objects/lock")
    assert body(lock_req) == {
        "key": "raw.bin",
        "retention_mode": "GOVERNANCE",
        "retain_until": "2026-12-31T00:00:00Z",
        "legal_hold": True,
    }
    vis_req = rec.requests[12]
    assert (vis_req.method, vis_req.url.path) == ("PUT", "/public/v1/buckets/bkt_1/objects/visibility")
    assert body(vis_req) == {"key": "raw.bin", "public": True}


async def test_objects_upload_download_and_visibility_async(make_async_client) -> None:  # type: ignore[no-untyped-def]
    payload = b"async-binary-data"
    rec = Recorder(
        json_response(200, {"key": "file.bin", "size_bytes": len(payload), "etag": '"e3"'}),
        httpx.Response(200, content=payload, headers={"Content-Type": "application/octet-stream"}),
        json_response(200, {"key": "file.bin", "public": False, "public_url": ""}),
    )
    client = make_async_client(rec)

    assert (await client.buckets.objects.upload("bkt_1", key="file.bin", body=payload, content_type="application/zip"))[
        "key"
    ] == "file.bin"
    assert await client.buckets.objects.download("bkt_1", key="file.bin") == payload
    assert (await client.buckets.objects.set_visibility("bkt_1", key="file.bin", public=False))["public"] is False

    assert rec.requests[0].headers["content-type"] == "application/zip"
    assert rec.requests[0].content == payload
    assert rec.requests[1].headers["accept"] == "application/octet-stream"


def test_multipart_sync(make_client) -> None:  # type: ignore[no-untyped-def]
    chunk = b"part-1-bytes"
    rec = Recorder(
        json_response(200, {"upload_id": "up_1", "key": "big.bin"}),
        json_response(200, {"url": "https://s3.test/part1", "part_number": 1}),
        json_response(200, {"part_number": 1, "etag": '"p1"'}),
        json_response(200, {"key": "big.bin", "etag": '"final"', "size_bytes": len(chunk)}),
        httpx.Response(204),
    )
    client = make_client(rec)

    started = client.buckets.multipart.start("bkt_1", key="big.bin", content_type="application/octet-stream")
    assert started["upload_id"] == "up_1"
    signed = client.buckets.multipart.sign_part("bkt_1", key="big.bin", upload_id="up_1", part_number=1)
    assert signed["part_number"] == 1
    uploaded = client.buckets.multipart.upload_part(
        "bkt_1",
        key="big.bin",
        upload_id="up_1",
        part_number=1,
        body=chunk,
    )
    assert uploaded["etag"] == '"p1"'
    done = client.buckets.multipart.complete(
        "bkt_1",
        key="big.bin",
        upload_id="up_1",
        parts=[{"part_number": 1, "etag": '"p1"'}],
    )
    assert done["etag"] == '"final"'
    assert client.buckets.multipart.abort("bkt_1", key="big.bin", upload_id="up_1") is None

    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("POST", "/public/v1/buckets/bkt_1/objects/multipart/start"),
        ("POST", "/public/v1/buckets/bkt_1/objects/multipart/sign-part"),
        ("PUT", "/public/v1/buckets/bkt_1/objects/multipart/part"),
        ("POST", "/public/v1/buckets/bkt_1/objects/multipart/complete"),
        ("POST", "/public/v1/buckets/bkt_1/objects/multipart/abort"),
    ]
    part_req = rec.requests[2]
    assert part_req.url.params["key"] == "big.bin"
    assert part_req.url.params["upload_id"] == "up_1"
    assert part_req.url.params["part_number"] == "1"
    assert part_req.headers["content-type"] == "application/octet-stream"
    assert part_req.content == chunk


async def test_multipart_async(make_async_client) -> None:  # type: ignore[no-untyped-def]
    chunk = b"async-part"
    rec = Recorder(
        json_response(200, {"upload_id": "up_2", "key": "big.bin"}),
        json_response(200, {"part_number": 1, "etag": '"p1"'}),
        json_response(200, {"key": "big.bin", "etag": '"final"'}),
        httpx.Response(204),
    )
    client = make_async_client(rec)

    assert (await client.buckets.multipart.start("bkt_1", key="big.bin"))["upload_id"] == "up_2"
    part = await client.buckets.multipart.upload_part(
        "bkt_1",
        key="big.bin",
        upload_id="up_2",
        part_number=1,
        body=chunk,
        content_type="application/x-binary",
    )
    assert part["etag"] == '"p1"'
    assert rec.requests[1].headers["content-type"] == "application/x-binary"
    assert rec.requests[1].content == chunk
    assert (
        await client.buckets.multipart.complete(
            "bkt_1",
            key="big.bin",
            upload_id="up_2",
            parts=[{"part_number": 1, "etag": '"p1"'}],
        )
    )["etag"] == '"final"'
    assert await client.buckets.multipart.abort("bkt_1", key="big.bin", upload_id="up_2") is None


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.object_storage.keys.create(name="ci"),
        lambda c: c.buckets.empty("bkt_1"),
        lambda c: c.buckets.multipart.start("bkt_1", key="big.bin"),
        lambda c: c.buckets.multipart.complete(
            "bkt_1", key="big.bin", upload_id="up_1", parts=[{"part_number": 1, "etag": '"p1"'}]
        ),
    ],
)
def test_no_replay_operations_sync(make_client, call) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "OBJECT_STORAGE_UNAVAILABLE"))
    with pytest.raises(pantech.InternalServerError):
        call(make_client(rec))
    assert len(rec.requests) == 1

    rec = Recorder(httpx.ConnectError("boom"))
    with pytest.raises(pantech.APIConnectionError):
        call(make_client(rec))
    assert len(rec.requests) == 1

    rec = Recorder(problem(429, "RATE_LIMITED", headers={"Retry-After": "1"}), json_response(200, {"ok": True}))
    call(make_client(rec))
    assert len(rec.requests) == 2
    assert rec.requests[0].headers["idempotency-key"] == rec.requests[1].headers["idempotency-key"]


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.object_storage.keys.create(name="ci"),
        lambda c: c.buckets.empty("bkt_1"),
        lambda c: c.buckets.multipart.start("bkt_1", key="big.bin"),
        lambda c: c.buckets.multipart.complete(
            "bkt_1", key="big.bin", upload_id="up_1", parts=[{"part_number": 1, "etag": '"p1"'}]
        ),
    ],
)
async def test_no_replay_operations_async(make_async_client, call) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "OBJECT_STORAGE_UNAVAILABLE"))
    with pytest.raises(pantech.InternalServerError):
        await call(make_async_client(rec))
    assert len(rec.requests) == 1


def test_request_rejects_both_body_and_content(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {}))
    with pytest.raises(ValueError, match="body or content"):
        make_client(rec).request("PUT", "/buckets/bkt_1/objects/upload", body={"a": 1}, content=b"raw")
