from __future__ import annotations

import httpx
import pytest

import pantech

from .conftest import Recorder, problem


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (400, pantech.BadRequestError),
        (401, pantech.AuthenticationError),
        (402, pantech.PaymentRequiredError),
        (403, pantech.PermissionDeniedError),
        (404, pantech.NotFoundError),
        (409, pantech.ConflictError),
        (422, pantech.ValidationError),
        (429, pantech.RateLimitError),
        (500, pantech.InternalServerError),
        (418, pantech.APIError),
    ],
)
def test_status_maps_to_exception(make_client, status: int, cls: type) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(status, "SOME_CODE", "Subnet not found.", request_id="req_123"))
    with pytest.raises(cls) as info:
        make_client(rec, max_retries=0).networks.subnets.get("snet_1")
    err = info.value
    assert isinstance(err, pantech.APIError)
    assert isinstance(err, pantech.PantechError)
    assert err.status == status
    assert err.code == "SOME_CODE"
    assert err.detail == "Subnet not found."
    assert err.title == "Problem"
    assert err.request_id == "req_123"
    assert "SOME_CODE" in str(err)
    assert "req_123" in str(err)


def test_validation_errors_carry_fields(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        problem(
            422,
            "VALIDATION_FAILED",
            "name: is required.",
            request_id="req_9",
            errors=[{"field": "name", "code": "REQUIRED", "message": "is required"}],
        )
    )
    with pytest.raises(pantech.ValidationError) as info:
        make_client(rec).networks.create(name="", cidr="10.0.0.0/16")
    err = info.value
    assert err.errors == [{"field": "name", "code": "REQUIRED", "message": "is required"}]
    # The detail repeats the field list, so it is not printed twice.
    assert str(err) == "422 VALIDATION_FAILED: Problem; name: is required (REQUIRED) (request_id: req_9)"


def test_request_id_falls_back_to_header_and_body_need_not_be_json(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        httpx.Response(502, content=b"<html>temporarily unavailable</html>", headers={"X-Request-Id": "req_h"})
    )
    with pytest.raises(pantech.InternalServerError) as info:
        make_client(rec, max_retries=0).me.get()
    assert info.value.request_id == "req_h"
    assert info.value.title == "Bad Gateway"
    assert info.value.code == ""


def test_no_route_hints_at_base_url(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(404, "NO_ROUTE", "No route."))
    with pytest.raises(pantech.NotFoundError, match="/public/v1"):
        make_client(rec).me.get()


def test_rate_limit_error_exposes_retry_after(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(429, "RATE_LIMITED", headers={"Retry-After": "12"}))
    with pytest.raises(pantech.RateLimitError) as info:
        make_client(rec, max_retries=0).me.get()
    assert info.value.retry_after == 12.0


def test_ai_app_refusals_are_permission_errors(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(403, "INSUFFICIENT_SCOPE", "This AI app was connected without permission to delete."))
    with pytest.raises(pantech.PermissionDeniedError) as info:
        make_client(rec).instances.delete("vm_1")
    assert info.value.code == "INSUFFICIENT_SCOPE"
