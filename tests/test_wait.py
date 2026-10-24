from __future__ import annotations

from typing import Any, Dict, List

import httpx
import pytest

import pantech

from .conftest import Recorder, json_response


def op(status: str, failure: Any = None) -> httpx.Response:
    return json_response(200, {"id": "op_1", "status": status, "failure": failure})


def test_wait_polls_until_succeeded(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(op("submitting"), op("submitted"), op("succeeded"))
    result = make_client(rec).operations.wait("op_1", poll_interval=1.5)
    assert result["status"] == "succeeded"
    assert len(rec.requests) == 3
    assert rec.requests[0].url.path == "/public/v1/operations/op_1"
    assert sleeps == [1.5, 1.5]


def test_wait_raises_on_failure(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(op("failed", {"code": "INSTANCE_BUSY", "reason": "The instance kept changing."}))
    with pytest.raises(pantech.OperationFailedError) as info:
        make_client(rec).operations.wait("op_1")
    assert info.value.code == "INSTANCE_BUSY"
    assert "kept changing" in str(info.value)


def test_wait_can_return_a_failed_operation(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(op("failed", {"code": "X", "reason": "y"}))
    result = make_client(rec).operations.wait("op_1", raise_on_failure=False)
    assert result["status"] == "failed"


def test_wait_times_out(make_client, sleeps) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(op("submitted"))
    client = make_client(rec)
    now: List[float] = [0.0]
    client._clock = lambda: now[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    client._sleep = fake_sleep
    with pytest.raises(pantech.WaitTimeoutError, match="still submitted") as info:
        client.operations.wait("op_1", timeout=5, poll_interval=2)
    assert isinstance(info.value, TimeoutError)
    assert sleeps == [2, 2, 1]


def test_wait_rejects_bad_arguments(make_client) -> None:  # type: ignore[no-untyped-def]
    client = make_client(Recorder(op("succeeded")))
    with pytest.raises(ValueError):
        client.operations.wait("op_1", poll_interval=0)


def order(status: str, **extra: Any) -> httpx.Response:
    body: Dict[str, Any] = {"id": "ord_1", "status": status, "failure_code": None}
    body.update(extra)
    return json_response(200, body)


def test_instance_order_wait(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(order("awaiting_payment"), order("provisioning"), order("provisioned", operation_id="op_9"))
    result = make_client(rec).instances.wait_for_order("ord_1")
    assert result["status"] == "provisioned"
    assert rec.requests[0].url.path == "/public/v1/instance-orders/ord_1"


@pytest.mark.parametrize("status", ["failed", "payment_failed"])
def test_database_order_failure(make_client, status: str) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(order("paid"), order(status, failure_code="database_name_taken"))
    with pytest.raises(pantech.OrderFailedError) as info:
        make_client(rec).databases.wait_for_order("ord_1")
    assert info.value.status == status
    assert info.value.code == "database_name_taken"
    assert rec.requests[0].url.path == "/public/v1/database-orders/ord_1"


async def test_async_wait(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(op("submitted"), op("succeeded"))
    client = make_async_client(rec)
    result = await client.operations.wait("op_1")
    assert result["status"] == "succeeded"
    rec = Recorder(order("provisioned"))
    client = make_async_client(rec)
    assert (await client.instances.wait_for_order("ord_1"))["status"] == "provisioned"


def test_stream_operation_events(make_client) -> None:  # type: ignore[no-untyped-def]
    body = (
        b": keepalive\n\n"
        b'event: operation\ndata: {"id":"op_1","status":"submitted"}\n\n'
        b": keepalive\n\n"
        b'event: operation\ndata: {"id":"op_1","status":"succeeded"}\n\n'
    )
    rec = Recorder(httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"}))
    events = list(make_client(rec).operations.stream("op_1"))
    assert [e["event"] for e in events] == ["operation", "operation"]
    assert events[-1]["data"]["status"] == "succeeded"
    assert rec.requests[0].headers["accept"] == "text/event-stream"


async def test_async_stream_operation_events(make_async_client) -> None:  # type: ignore[no-untyped-def]
    body = b'event: error\ndata: {"code":"OPERATION_STREAM_TIMEOUT"}\n\n'
    rec = Recorder(httpx.Response(200, content=body, headers={"Content-Type": "text/event-stream"}))
    events = [e async for e in make_async_client(rec).operations.stream("op_1")]
    assert events == [{"event": "error", "data": {"code": "OPERATION_STREAM_TIMEOUT"}, "id": None}]
