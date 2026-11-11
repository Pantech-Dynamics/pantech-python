from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest

import pantech

from .conftest import Recorder, json_response, problem

CONTACT: pantech.types.DomainContact = {
    "type": "person",
    "first_name": "Ada",
    "last_name": "Obi",
    "email": "ada@example.com",
    "phone": "+234.8012345678",
    "organization_name": "",
    "address_line1": "1 Marina",
    "address_line2": "",
    "city": "Lagos",
    "state": "Lagos",
    "country_code": "NG",
    "postal_code": "101001",
}


def domain(status: str = "registering", **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "dom_1",
        "name": "example.com",
        "tld": "com",
        "status": status,
        "failure_code": None,
        "auto_renew": True,
        "transfer_lock": True,
        "privacy": True,
        "name_server_mode": "pantech",
        "name_servers": [],
        "zone_id": None,
        "registered_at": None,
        "expires_at": None,
        "contact_verified": False,
        "settings_pending": False,
        "auth_code_pending": False,
        "suspended_reason": None,
        "created_at": "2026-11-10T10:04:41Z",
        "updated_at": "2026-11-10T10:04:41Z",
        "version": 1,
    }
    out.update(extra)
    return out


def order(status: str = "pending", **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "dor_1",
        "domain_id": "dom_1",
        "domain_name": "example.com",
        "kind": "register",
        "years": 1,
        "amount_minor": 1500,
        "currency": "USD",
        "status": status,
        "failure_code": None,
        "refunded": False,
        "created_at": "2026-11-10T10:04:41Z",
        "completed_at": None,
    }
    out.update(extra)
    return out


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_search_sends_the_query(make_client) -> None:  # type: ignore[no-untyped-def]
    price = {
        "tld": "com",
        "currency": "USD",
        "register_minor": 1500,
        "renew_minor": 1500,
        "transfer_minor": 1500,
        "featured": True,
    }
    rec = Recorder(
        json_response(200, {"data": [{"name": "example.com", "tld": "com", "status": "available", "price": price}]})
    )
    out = make_client(rec).domains.search(query="example")
    assert out["data"][0]["price"] == price
    assert rec.requests[0].url.path == "/public/v1/domains/search"
    assert rec.requests[0].url.params["query"] == "example"


def test_check_transfer(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, {"name": "example.com", "transferable": False, "reason": "locked", "price": None})
    )
    out = make_client(rec).domains.check_transfer(name="example.com")
    assert out["transferable"] is False
    assert rec.requests[0].url.path == "/public/v1/domains/transfer-check"
    assert rec.requests[0].url.params["name"] == "example.com"


def test_register_sends_the_order_with_a_key(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"domain": domain(), "order": order()}))
    out = make_client(rec).domains.register(name="example.com", years=2, contact=CONTACT, accept_terms=True)
    assert out["order"]["id"] == "dor_1"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/domains")
    assert body(req) == {"name": "example.com", "years": 2, "contact": CONTACT, "accept_terms": True}
    assert req.headers["idempotency-key"]


def test_a_retried_register_reuses_its_key(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "SERVICE_UNAVAILABLE"), json_response(202, {"domain": domain(), "order": order()}))
    make_client(rec).domains.register(name="example.com", contact=CONTACT, accept_terms=True)
    keys = [r.headers["idempotency-key"] for r in rec.requests]
    assert len(keys) == 2
    assert keys[0] == keys[1]


def test_transfer(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"domain": domain("transferring"), "order": order(kind="transfer")}))
    make_client(rec).domains.transfer(name="example.com", auth_code="s3cret", contact=CONTACT, accept_terms=True)
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/domains/transfers")
    assert body(req)["auth_code"] == "s3cret"


def test_settings_name_servers_contact_and_renew(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, domain("active")))
    client = make_client(rec)
    client.domains.update("dom_1", auto_renew=False)
    client.domains.set_name_servers("dom_1", use_pantech_dns=False, name_servers=["ns1.example.net"])
    client.domains.update_contact("dom_1", contact=CONTACT)
    client.domains.renew("dom_1", years=3)
    got = [(r.method, r.url.path, body(r)) for r in rec.requests]
    assert got == [
        ("PATCH", "/public/v1/domains/dom_1", {"auto_renew": False}),
        (
            "PUT",
            "/public/v1/domains/dom_1/name-servers",
            {"use_pantech_dns": False, "name_servers": ["ns1.example.net"]},
        ),
        ("PUT", "/public/v1/domains/dom_1/contact", {"contact": CONTACT}),
        ("POST", "/public/v1/domains/dom_1/renew", {"years": 3}),
    ]


def test_auth_code_pending_then_ready(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(202, domain("active", auth_code_pending=True)),
        json_response(202, {"status": "pending"}),
        json_response(200, {"auth_code": "abc-123", "expires_at": "2026-11-11T10:00:00Z"}),
    )
    client = make_client(rec)
    assert client.domains.request_auth_code("dom_1")["auth_code_pending"] is True
    assert client.domains.get_auth_code("dom_1") == {"status": "pending"}
    ready = client.domains.get_auth_code("dom_1")
    assert "auth_code" in ready
    assert [r.method for r in rec.requests] == ["POST", "GET", "GET"]


def test_locked_domain_code_is_typed(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(409, "DOMAIN_LOCKED", "Turn the transfer lock off first."))
    with pytest.raises(pantech.ConflictError) as info:
        make_client(rec).domains.request_auth_code("dom_1")
    assert info.value.code == "DOMAIN_LOCKED"
    assert info.value.code in pantech.DOMAIN_ERROR_CODES


def test_orders(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"data": [order("succeeded")]}), json_response(200, order("succeeded")))
    client = make_client(rec)
    assert client.domains.orders.list("dom_1")["data"][0]["id"] == "dor_1"
    assert client.domains.orders.get("dor_1")["status"] == "succeeded"
    assert [r.url.path for r in rec.requests] == ["/public/v1/domains/dom_1/orders", "/public/v1/domain-orders/dor_1"]


def test_retry_payment_sends_the_key(make_client) -> None:  # type: ignore[no-untyped-def]
    unpaid = order("awaiting_payment", payment_url=None, payment_expires_at="2026-11-10T12:00:00Z")
    rec = Recorder(json_response(202, unpaid))
    out = make_client(rec).domains.orders.retry_payment("dor_1", idempotency_key="retry-1")
    assert out["status"] == "awaiting_payment"
    assert out["payment_expires_at"] == "2026-11-10T12:00:00Z"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/domain-orders/dor_1/retry-payment")
    assert req.headers["idempotency-key"] == "retry-1"
    assert len(rec.requests) == 1


def test_retry_payment_not_awaiting_is_typed(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(409, "DOMAIN_ORDER_NOT_AWAITING_PAYMENT", "The order is not waiting for a payment."))
    with pytest.raises(pantech.ConflictError) as info:
        make_client(rec).domains.orders.retry_payment("dor_1")
    assert info.value.code == "DOMAIN_ORDER_NOT_AWAITING_PAYMENT"
    assert info.value.code in pantech.DOMAIN_ERROR_CODES
    assert len(rec.requests) == 1


async def test_async_retry_payment(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, order("awaiting_payment")))
    out = await make_async_client(rec).domains.orders.retry_payment("dor_1")
    assert out["id"] == "dor_1"
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/domain-orders/dor_1/retry-payment")
    assert req.headers["idempotency-key"]


def test_wait_for_order_until_succeeded(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, order("paid")),
        json_response(200, order("submitted")),
        json_response(200, order("succeeded")),
    )
    out = make_client(rec).domains.wait_for_order("dor_1")
    assert out["status"] == "succeeded"
    assert sleeps == [5.0, 5.0]


def test_wait_for_order_raises_on_failure(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, order("failed", failure_code="insufficient_credit", refunded=True)))
    with pytest.raises(pantech.OrderFailedError) as info:
        make_client(rec).domains.wait_for_order("dor_1")
    assert info.value.code == "insufficient_credit"
    assert str(info.value) == "Domain order dor_1 failed: insufficient_credit"


async def test_async_wait_for_order(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, order("submitted")), json_response(200, order("succeeded")))
    out = await make_async_client(rec).domains.wait_for_order("dor_1")
    assert out["status"] == "succeeded"


def test_contact_is_not_logged(make_client, caplog) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"domain": domain(), "order": order()}))
    with caplog.at_level("DEBUG", logger="pantech"):
        make_client(rec).domains.register(name="example.com", contact=CONTACT, accept_terms=True)
    assert "ada@example.com" not in caplog.text
    assert "+234.8012345678" not in caplog.text


def test_error_code_sets_cover_the_contract() -> None:
    assert "DNS_ZONE_IN_USE_BY_DOMAIN" in pantech.DNS_ERROR_CODES
    assert "DOMAIN_ZONE_MISMATCH" in pantech.DOMAIN_ERROR_CODES
    assert len(pantech.DNS_ERROR_CODES) == 17
    assert "DOMAIN_ORDER_NOT_AWAITING_PAYMENT" in pantech.DOMAIN_ERROR_CODES
    assert len(pantech.DOMAIN_ERROR_CODES) == 14


def test_wait_for_order_raises_payment_required_with_the_url(make_client) -> None:  # type: ignore[no-untyped-def]
    unpaid = order(
        "awaiting_payment", payment_url="https://pay.example.test/c/1", payment_expires_at="2026-11-10T11:00:00Z"
    )
    rec = Recorder(json_response(200, order("pending")), json_response(200, unpaid))
    with pytest.raises(pantech.PaymentRequiredError) as info:
        make_client(rec).domains.wait_for_order("dor_1")
    err = info.value
    assert err.payment_url == "https://pay.example.test/c/1"
    assert err.payment_expires_at == "2026-11-10T11:00:00Z"
    assert err.order is not None and err.order["id"] == "dor_1"
    assert err.code == "AWAITING_PAYMENT"
    assert "pay.example.test" not in str(err)


def test_payment_required_without_a_link(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, order("awaiting_payment", payment_url=None)))
    with pytest.raises(pantech.PaymentRequiredError) as info:
        make_client(rec).domains.wait_for_order("dor_1")
    assert info.value.payment_url is None
    assert "payment_url" not in str(info.value)


def test_wait_for_order_can_wait_through_the_payment(make_client) -> None:  # type: ignore[no-untyped-def]
    unpaid = order("awaiting_payment", payment_url="https://pay.example.test/c/1", payment_expires_at="x")
    rec = Recorder(
        json_response(200, unpaid), json_response(200, order("paid")), json_response(200, order("succeeded"))
    )
    out = make_client(rec).domains.wait_for_order("dor_1", wait_for_payment=True)
    assert out["status"] == "succeeded"


def test_an_unpaid_order_that_expires_fails_insufficient_credit(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, order("awaiting_payment")),
        json_response(200, order("failed", failure_code="insufficient_credit")),
    )
    with pytest.raises(pantech.OrderFailedError) as info:
        make_client(rec).domains.wait_for_order("dor_1", wait_for_payment=True)
    assert info.value.code == "insufficient_credit"


async def test_async_wait_for_order_raises_payment_required(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, order("awaiting_payment", payment_url="https://pay.example.test/c/2")))
    with pytest.raises(pantech.PaymentRequiredError) as info:
        await make_async_client(rec).domains.wait_for_order("dor_1")
    assert info.value.payment_url == "https://pay.example.test/c/2"


def test_privacy_always_on_refusal_names_the_field(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        problem(
            422,
            "VALIDATION_FAILED",
            "One or more fields are invalid.",
            errors=[{"field": "privacy", "code": "PRIVACY_ALWAYS_ON", "message": "The .ng registry hides it."}],
        )
    )
    with pytest.raises(pantech.ValidationError) as info:
        make_client(rec).domains.update("dom_1", privacy=False)
    assert info.value.errors[0]["code"] == "PRIVACY_ALWAYS_ON"
