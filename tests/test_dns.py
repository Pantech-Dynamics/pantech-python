from __future__ import annotations

import json
from typing import Any, Dict, List

import httpx
import pytest

import pantech

from .conftest import Recorder, json_response, problem


def zone(status: str = "awaiting_delegation", **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "dnsz_1",
        "name": "example.com",
        "description": "",
        "status": status,
        "failure_code": None,
        "name_servers": ["ns-1.example-dns.net", "ns-2.example-dns.org"],
        "domain_id": None,
        "record_count": 2,
        "last_checked_at": None,
        "activated_at": None,
        "suspended_reason": None,
        "created_at": "2026-11-10T10:00:00Z",
        "updated_at": "2026-11-10T10:00:00Z",
        "version": 1,
    }
    out.update(extra)
    return out


def record(status: str = "pending", **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "dnsr_1",
        "zone_id": "dnsz_1",
        "name": "www",
        "fqdn": "www.example.com",
        "type": "A",
        "ttl": 300,
        "values": ["203.0.113.10"],
        "allow_private": False,
        "comment": "",
        "managed": False,
        "status": status,
        "failure_code": None,
        "version": 2,
        "created_at": "2026-11-10T10:01:00Z",
        "updated_at": "2026-11-10T10:01:00Z",
    }
    out.update(extra)
    return out


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_create_zone_sends_the_body_and_a_key(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, zone("pending", name_servers=[])))
    z = make_client(rec).dns.zones.create(name="example.com", idempotency_key="key-1")
    assert z["status"] == "pending"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/dns/zones")
    assert body(req) == {"name": "example.com"}
    assert req.headers["idempotency-key"] == "key-1"


def test_list_zones_filters_and_pages(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, {"data": [zone()], "next_cursor": "c2"}),
        json_response(200, {"data": [zone(id="dnsz_2")], "next_cursor": None}),
    )
    ids = [z["id"] for z in make_client(rec).dns.zones.list_all(status="active", q="example")]
    assert ids == ["dnsz_1", "dnsz_2"]
    assert rec.requests[0].url.params["status"] == "active"
    assert rec.requests[1].url.params["cursor"] == "c2"
    assert rec.requests[1].url.params["q"] == "example"


def test_verify_zone_posts_without_a_body(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, zone()))
    make_client(rec).dns.zones.verify("dnsz_1")
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/dns/zones/dnsz_1/verify")
    assert req.content == b""
    assert req.headers["idempotency-key"]


def test_export_returns_the_zone_file_as_text(make_client) -> None:  # type: ignore[no-untyped-def]
    text = "$ORIGIN example.com.\nwww 300 IN A 203.0.113.10\n"
    rec = Recorder(httpx.Response(200, content=text.encode(), headers={"Content-Type": "text/dns"}))
    out = make_client(rec).dns.zones.export_zone_file("dnsz_1")
    assert out == text
    req = rec.requests[0]
    assert req.url.path == "/public/v1/dns/zones/dnsz_1/export"
    assert req.headers["accept"].startswith("text/dns")


def test_zone_wait_until_it_has_name_servers(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, zone("pending", name_servers=[])), json_response(200, zone()))
    out = make_client(rec).dns.zones.wait("dnsz_1")
    assert out["status"] == "awaiting_delegation"
    assert sleeps == [3.0]


def test_zone_wait_raises_when_it_fails(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, zone("failed", failure_code="provider_rejected")))
    with pytest.raises(pantech.DNSFailedError) as info:
        make_client(rec).dns.zones.wait("dnsz_1")
    assert info.value.kind == "zone"
    assert info.value.code == "provider_rejected"


def test_zone_wait_raises_when_it_is_deleted(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, zone("deleting")))
    with pytest.raises(pantech.DNSFailedError, match="is deleting"):
        make_client(rec).dns.zones.wait("dnsz_1")


async def test_async_zone_wait(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, zone("active")))
    assert (await make_async_client(rec).dns.zones.wait("dnsz_1"))["status"] == "active"


def test_import_sends_the_file_and_replace(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"data": [record()]}))
    out = make_client(rec).dns.zones.import_zone_file("dnsz_1", zone_file="www 300 IN A 203.0.113.10", replace=True)
    assert out["data"][0]["id"] == "dnsr_1"
    assert body(rec.requests[0]) == {"zone_file": "www 300 IN A 203.0.113.10", "replace": True}


def test_create_record(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, record()))
    make_client(rec).dns.records.create("dnsz_1", name="www", type="A", values=["203.0.113.10"], ttl=300)
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/dns/zones/dnsz_1/records")
    assert body(req) == {"name": "www", "type": "A", "ttl": 300, "values": ["203.0.113.10"]}


def test_update_record_sends_if_match(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, record()))
    make_client(rec).dns.records.update("dnsz_1", "dnsr_1", if_match=2, ttl=60)
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("PATCH", "/public/v1/dns/zones/dnsz_1/records/dnsr_1")
    assert req.headers["if-match"] == "2"
    assert body(req) == {"ttl": 60}


def test_update_record_without_if_match_sends_none(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, record()))
    make_client(rec).dns.records.update("dnsz_1", "dnsr_1", values=["203.0.113.11"], extra_headers={"X-Trace": "1"})
    req = rec.requests[0]
    assert "if-match" not in req.headers
    assert req.headers["x-trace"] == "1"


def test_delete_record_sends_if_match(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, record("deleting")))
    out = make_client(rec).dns.records.delete("dnsz_1", "dnsr_1", if_match=3)
    assert out["status"] == "deleting"
    assert rec.requests[0].method == "DELETE"
    assert rec.requests[0].headers["if-match"] == "3"


def test_version_conflict_is_a_precondition_failed_error(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(412, "VERSION_CONFLICT", "The record set changed since you read it."))
    with pytest.raises(pantech.PreconditionFailedError) as info:
        make_client(rec).dns.records.update("dnsz_1", "dnsr_1", if_match=1, ttl=60)
    assert info.value.code == "VERSION_CONFLICT"
    assert info.value.code in pantech.DNS_ERROR_CODES
    assert len(rec.requests) == 1


def test_batch_sends_every_change(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"data": [record(), record(id="dnsr_2", status="deleting")]}))
    changes: List[pantech.types.DNSRecordChange] = [
        {"action": "create", "record": {"name": "api", "type": "CNAME", "values": ["www.example.com"]}},
        {"action": "delete", "record_id": "dnsr_2", "version": 4},
    ]
    out = make_client(rec).dns.records.batch("dnsz_1", changes=changes)
    assert [r["id"] for r in out["data"]] == ["dnsr_1", "dnsr_2"]
    req = rec.requests[0]
    assert req.url.path == "/public/v1/dns/zones/dnsz_1/records/batch"
    assert body(req) == {"changes": changes}


def test_conflict_codes_are_typed(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(409, "DNS_CNAME_CONFLICT", "A CNAME must stand alone at its name."))
    with pytest.raises(pantech.ConflictError) as info:
        make_client(rec).dns.records.create("dnsz_1", name="www", type="CNAME", values=["example.net"])
    assert info.value.code == "DNS_CNAME_CONFLICT"
    assert info.value.code in pantech.DNS_ERROR_CODES


def test_record_wait_polls_until_active(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, record("pending")), json_response(200, record("active")))
    out = make_client(rec).dns.records.wait("dnsz_1", "dnsr_1")
    assert out["status"] == "active"
    assert [r.url.path for r in rec.requests] == ["/public/v1/dns/zones/dnsz_1/records/dnsr_1"] * 2
    assert sleeps == [3.0]


def test_record_wait_raises_on_failure(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, record("failed", failure_code="invalid_change")))
    with pytest.raises(pantech.DNSFailedError) as info:
        make_client(rec).dns.records.wait("dnsz_1", "dnsr_1")
    assert info.value.kind == "record"
    assert info.value.code == "invalid_change"
    assert "www.example.com" in str(info.value)


def test_record_wait_times_out(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    client = make_client(Recorder(json_response(200, record("pending"))))
    now: List[float] = [0.0]
    client._clock = lambda: now[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client._sleep = fake_sleep
    with pytest.raises(pantech.WaitTimeoutError, match="still pending"):
        client.dns.records.wait("dnsz_1", "dnsr_1", timeout=5, poll_interval=3)
    assert sleeps == [3, 2]


def test_record_wait_refuses_an_empty_id(make_client) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="non-empty id"):
        make_client(Recorder()).dns.records.wait("dnsz_1", "")


async def test_async_record_wait(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, record("pending")), json_response(200, record("active")))
    out = await make_async_client(rec).dns.records.wait("dnsz_1", "dnsr_1")
    assert out["status"] == "active"


async def test_async_export_returns_text(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(httpx.Response(200, content=b"$ORIGIN example.com.\n", headers={"Content-Type": "text/dns"}))
    assert await make_async_client(rec).dns.zones.export_zone_file("dnsz_1") == "$ORIGIN example.com.\n"


async def test_async_update_record_sends_if_match(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, record()))
    await make_async_client(rec).dns.records.update("dnsz_1", "dnsr_1", if_match=7, comment="web")
    assert rec.requests[0].headers["if-match"] == "7"


def test_zone_quote(make_client) -> None:  # type: ignore[no-untyped-def]
    quote = {"free_zones": 5, "live_zones": 7, "billable_zones": 2, "monthly_per_zone_minor": 50, "currency": "USD"}
    rec = Recorder(json_response(200, quote))
    out = make_client(rec).dns.zones.quote()
    assert out["free_zones"] == 5
    assert (rec.requests[0].method, rec.requests[0].url.path) == ("GET", "/public/v1/dns/zones/quote")


def test_https_load_balancer_fields(make_client) -> None:  # type: ignore[no-untyped-def]
    refused = problem(
        422,
        "VALIDATION_FAILED",
        "One or more fields are invalid.",
        errors=[{"field": "protocol", "code": "LOAD_BALANCER_TLS_NOT_SUPPORTED", "message": "Appliance only."}],
    )
    rec = Recorder(json_response(200, {"id": "lb_1", "protocol": "https"}), refused)
    client = make_client(rec)
    client.load_balancers.update("lb_1", certificate_id="cert_1", tls_policy="tls13", redirect_http=True)
    assert body(rec.requests[0]) == {"certificate_id": "cert_1", "tls_policy": "tls13", "redirect_http": True}
    with pytest.raises(pantech.ValidationError) as info:
        client.load_balancers.update("lb_2", certificate_id="cert_1")
    assert info.value.errors[0]["code"] == "LOAD_BALANCER_TLS_NOT_SUPPORTED"
