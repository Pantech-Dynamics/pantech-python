from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import httpx
import pytest

import pantech

from .conftest import Recorder, json_response, problem

KEY = "-----BEGIN PRIVATE KEY-----\nMIGHAgEAMBMGSECRETKEYMATERIAL\n-----END PRIVATE KEY-----\n"
CERT = "-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIU\n-----END CERTIFICATE-----\n"


def certificate(status: str = "pending_validation", **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "cert_1",
        "kind": "public",
        "names": ["example.com", "*.example.com"],
        "common_name": "example.com",
        "description": "",
        "key_type": "ecdsa-p256",
        "exportable": True,
        "status": status,
        "pending_reason": "awaiting_dns" if status == "pending_validation" else None,
        "failure_code": None,
        "validations": [],
        "in_use_by": [],
        "revocation_pending": False,
        "version": 1,
    }
    out.update(extra)
    return out


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_request_sends_names_with_a_key(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, certificate()))
    out = make_client(rec).certificates.request(names=["example.com", "*.example.com"], exportable=True)
    assert out["status"] == "pending_validation"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/certificates")
    assert body(req) == {"names": ["example.com", "*.example.com"], "exportable": True}
    assert req.headers["idempotency-key"]


def test_list_filters(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"data": [], "next_cursor": None}))
    make_client(rec).certificates.list(status="issued", kind="imported", q="example")
    params = rec.requests[0].url.params
    assert (params["status"], params["kind"], params["q"]) == ("issued", "imported", "example")


def test_wait_until_issued(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, certificate("pending_validation")),
        json_response(200, certificate("issuing")),
        json_response(200, certificate("issued")),
    )
    out = make_client(rec).certificates.wait("cert_1")
    assert out["status"] == "issued"
    assert sleeps == [5.0, 5.0]
    assert rec.requests[0].url.path == "/public/v1/certificates/cert_1"


@pytest.mark.parametrize(
    ("status", "failure", "code"),
    [("failed", "caa_forbidden", "caa_forbidden"), ("revoked", None, "revoked"), ("expired", None, "expired")],
)
def test_wait_raises_when_it_cannot_be_issued(make_client, status: str, failure: Any, code: str) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, certificate(status, failure_code=failure)))
    with pytest.raises(pantech.CertificateFailedError) as info:
        make_client(rec).certificates.wait("cert_1")
    assert info.value.code == code
    assert "example.com" in str(info.value)


def test_wait_times_out(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    client = make_client(Recorder(json_response(200, certificate())))
    now: List[float] = [0.0]
    client._clock = lambda: now[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client._sleep = fake_sleep
    with pytest.raises(pantech.WaitTimeoutError, match="still pending_validation"):
        client.certificates.wait("cert_1", timeout=8, poll_interval=5)


def test_export_hides_the_private_key(make_client, caplog) -> None:  # type: ignore[no-untyped-def]
    exported = {"certificate_pem": CERT, "chain_pem": "", "private_key_pem": KEY, "not_after": "2027-02-08T10:00:00Z"}
    rec = Recorder(json_response(200, exported))
    with caplog.at_level(logging.DEBUG, logger="pantech"):
        out = make_client(rec).certificates.export("cert_1")
    assert out["private_key_pem"] == KEY
    assert "SECRETKEYMATERIAL" not in repr(out)
    assert "SECRETKEYMATERIAL" not in str(out)
    assert "<hidden>" in repr(out)
    assert "SECRETKEYMATERIAL" not in caplog.text
    assert json.loads(json.dumps(out))["private_key_pem"] == KEY
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/certificates/cert_1/export")


async def test_async_export_hides_the_private_key(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"certificate_pem": CERT, "chain_pem": "", "private_key_pem": KEY}))
    out = await make_async_client(rec).certificates.export("cert_1")
    assert "SECRETKEYMATERIAL" not in repr(out)


def test_import_never_logs_the_key(make_client, caplog) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, certificate("issued", kind="imported")))
    with caplog.at_level(logging.DEBUG, logger="pantech"):
        make_client(rec).certificates.import_(certificate_pem=CERT, private_key_pem=KEY, description="legacy")
    assert "SECRETKEYMATERIAL" not in caplog.text
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/certificates/import")
    assert body(req) == {"certificate_pem": CERT, "private_key_pem": KEY, "description": "legacy"}


def test_reimport_and_revoke(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, certificate("issued")))
    client = make_client(rec)
    client.certificates.reimport("cert_1", certificate_pem=CERT, private_key_pem=KEY)
    client.certificates.revoke("cert_1", reason="key_compromise")
    client.certificates.verify("cert_1")
    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("POST", "/public/v1/certificates/cert_1/reimport"),
        ("POST", "/public/v1/certificates/cert_1/revoke"),
        ("POST", "/public/v1/certificates/cert_1/verify"),
    ]
    assert body(rec.requests[1]) == {"reason": "key_compromise"}


def test_in_use_and_not_exportable_are_typed(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        problem(409, "CERTIFICATE_IN_USE", "A load balancer uses it."),
        problem(409, "CERTIFICATE_NOT_EXPORTABLE", "Created without exportable."),
    )
    client = make_client(rec)
    with pytest.raises(pantech.ConflictError) as in_use:
        client.certificates.delete("cert_1")
    with pytest.raises(pantech.ConflictError) as not_exportable:
        client.certificates.export("cert_1")
    assert in_use.value.code == "CERTIFICATE_IN_USE"
    assert not_exportable.value.code in pantech.CERTIFICATE_ERROR_CODES


def test_certificate_rate_limit_is_retried_then_raised(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        problem(429, "CERTIFICATE_RATE_LIMITED", "Requested 5 times this week.", headers={"Retry-After": "1"})
    )
    with pytest.raises(pantech.RateLimitError) as info:
        make_client(rec, max_retries=1).certificates.request(names=["example.com"])
    assert info.value.code == "CERTIFICATE_RATE_LIMITED"
    assert info.value.retry_after == 1.0
    keys = {r.headers["idempotency-key"] for r in rec.requests}
    assert len(rec.requests) == 2
    assert len(keys) == 1


def test_certificate_codes_cover_the_contract() -> None:
    assert len(pantech.CERTIFICATE_ERROR_CODES) == 13
