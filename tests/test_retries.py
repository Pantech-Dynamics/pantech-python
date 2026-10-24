from __future__ import annotations

import uuid

import httpx
import pytest

import pantech

from .conftest import Recorder, json_response, problem

ACCEPTED = {"operation_id": "op_1", "resource_id": "vm_1", "status": "submitted"}


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_retries_retryable_statuses_with_the_same_idempotency_key(make_client, status: int) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(status, "INTERNAL"), json_response(202, ACCEPTED))
    client = make_client(rec)
    assert client.instances.stop("vm_1")["operation_id"] == "op_1"
    assert len(rec.requests) == 2
    keys = {r.headers["idempotency-key"] for r in rec.requests}
    assert len(keys) == 1
    uuid.UUID(keys.pop(), version=4)


def test_every_write_gets_a_fresh_key(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, ACCEPTED))
    client = make_client(rec)
    client.instances.stop("vm_1")
    client.instances.stop("vm_1")
    assert rec.requests[0].headers["idempotency-key"] != rec.requests[1].headers["idempotency-key"]


def test_caller_key_is_used_and_reused(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(502, "BAD_GATEWAY"), json_response(202, ACCEPTED))
    client = make_client(rec)
    client.volumes.delete("vol_1", idempotency_key="my-key")
    assert [r.headers["idempotency-key"] for r in rec.requests] == ["my-key", "my-key"]


def test_get_has_no_idempotency_key(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {}))
    make_client(rec).me.get()
    assert "idempotency-key" not in rec.requests[0].headers


def test_honours_retry_after(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(429, "RATE_LIMITED", headers={"Retry-After": "7"}), json_response(200, {}))
    make_client(rec).me.get()
    assert sleeps == [7.0]


def test_backoff_grows_with_jitter(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "UNAVAILABLE"))
    client = make_client(rec)
    with pytest.raises(pantech.InternalServerError):
        client.me.get()
    assert len(rec.requests) == 4  # 1 + 3 retries
    assert len(sleeps) == 3
    for i, s in enumerate(sleeps):
        full = 0.5 * 2**i
        assert full / 2 <= s <= full


def test_max_retries_zero(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "UNAVAILABLE"))
    with pytest.raises(pantech.InternalServerError):
        make_client(rec, max_retries=0).me.get()
    assert len(rec.requests) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422])
def test_client_errors_are_not_retried(make_client, status: int) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(status, "X"))
    with pytest.raises(pantech.APIError):
        make_client(rec).instances.start("vm_1")
    assert len(rec.requests) == 1


def test_network_errors_are_retried_then_raised(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(httpx.ConnectError("boom"), json_response(200, {"ok": 1}))
    assert make_client(rec).me.get() == {"ok": 1}

    rec = Recorder(httpx.ConnectError("boom"))
    with pytest.raises(pantech.APIConnectionError):
        make_client(rec).me.get()
    assert len(rec.requests) == 4


def test_timeouts_raise_api_timeout_error(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(httpx.ReadTimeout("slow"))
    with pytest.raises(pantech.APITimeoutError):
        make_client(rec, max_retries=1).me.get()
    assert len(rec.requests) == 2


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.ssh_keys.create(name="k"),
        lambda c: c.ssh_keys.delete("sshk_1"),
        lambda c: c.instances.open_console("vm_1"),
        lambda c: c.webhooks.test("whk_1"),
        lambda c: c.webhooks.delete("whk_1"),
        lambda c: c.webhooks.rotate_secret("whk_1"),
        lambda c: c.webhooks.deliveries.redeliver("whk_1", "dlv_1"),
    ],
)
def test_routes_that_do_not_replay_are_sent_once(make_client, call) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "UNAVAILABLE"))
    with pytest.raises(pantech.InternalServerError):
        call(make_client(rec))
    assert len(rec.requests) == 1

    rec = Recorder(httpx.ConnectError("boom"))
    with pytest.raises(pantech.APIConnectionError):
        call(make_client(rec))
    assert len(rec.requests) == 1


def test_routes_that_do_not_replay_still_retry_429(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(429, "RATE_LIMITED", headers={"Retry-After": "1"}), json_response(201, {"id": "sshk_1"}))
    assert make_client(rec).ssh_keys.create(name="k")["id"] == "sshk_1"
    assert len(rec.requests) == 2


async def test_async_retries_reuse_the_key(make_async_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(500, "INTERNAL"), httpx.ConnectError("x"), json_response(202, ACCEPTED))
    client = make_async_client(rec)
    out = await client.instances.reboot("vm_1")
    assert out["operation_id"] == "op_1"
    assert len({r.headers["idempotency-key"] for r in rec.requests}) == 1
    assert len(rec.requests) == 3
    assert len(sleeps) == 2
