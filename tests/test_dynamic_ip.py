from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest

import pantech
from pantech.types import (
    AddressRotation,
    AddressRotationEvent,
    DynamicIP,
    DynamicIPEvent,
    PutAddressRotationRequest,
    PutDynamicIPRequest,
)

from .conftest import Recorder, json_response, problem


def sample_dynamic_ip(**extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "instance_id": "vm_1",
        "schedule": "weekly",
        "connections": "keep",
        "on_demand": False,
        "state": "active",
        "current_address": "198.51.100.42",
        "next_rotation_at": "2026-12-01T12:00:00Z",
        "last_rotated_at": "2026-11-24T12:00:00Z",
        "surcharge_percent": 40,
        "on_demand_used": 0,
        "on_demand_limit": 10,
        "failure_reason": None,
        "events": [
            {
                "kind": "enabled",
                "from_address": None,
                "to_address": "198.51.100.42",
                "degraded": False,
                "occurred_at": "2026-11-24T12:00:00Z",
            }
        ],
    }
    out.update(extra)
    return out


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_type_aliases_exported() -> None:
    assert DynamicIP is AddressRotation
    assert DynamicIPEvent is AddressRotationEvent
    assert PutDynamicIPRequest is PutAddressRotationRequest


def test_sync_get_set_disable_rotate(make_client) -> None:  # type: ignore[no-untyped-def]
    enabling = sample_dynamic_ip(state="enabling", current_address=None, events=[])
    active = sample_dynamic_ip(schedule="daily", connections="move", on_demand=True, surcharge_percent=95)
    rotated = sample_dynamic_ip(current_address="198.51.100.99", on_demand=True, on_demand_used=1, surcharge_percent=95)
    disabling = sample_dynamic_ip(state="disabling")

    rec = Recorder(
        json_response(201, enabling),
        json_response(200, active),
        json_response(200, active),
        json_response(200, rotated),
        json_response(200, disabling),
    )
    client = make_client(rec)

    assert client.instances.dynamic_ip.set("vm_1", schedule="weekly") == enabling
    assert (
        client.instances.dynamic_ip.set(
            "vm_1",
            schedule="daily",
            connections="move",
            on_demand=True,
            idempotency_key="dyn-key-2",
        )
        == active
    )
    assert client.instances.dynamic_ip.get("vm_1") == active
    assert client.instances.dynamic_ip.rotate("vm_1", idempotency_key="rot-1") == rotated
    assert client.instances.dynamic_ip.disable("vm_1") == disabling

    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("PUT", "/public/v1/instances/vm_1/address-rotation"),
        ("PUT", "/public/v1/instances/vm_1/address-rotation"),
        ("GET", "/public/v1/instances/vm_1/address-rotation"),
        ("POST", "/public/v1/instances/vm_1/address-rotation/rotate"),
        ("DELETE", "/public/v1/instances/vm_1/address-rotation"),
    ]
    assert body(rec.requests[0]) == {"schedule": "weekly"}
    assert body(rec.requests[1]) == {"schedule": "daily", "connections": "move", "on_demand": True}
    assert rec.requests[0].headers["idempotency-key"]
    assert rec.requests[1].headers["idempotency-key"] == "dyn-key-2"
    assert "idempotency-key" not in rec.requests[2].headers
    assert rec.requests[3].headers["idempotency-key"] == "rot-1"
    assert rec.requests[4].headers["idempotency-key"]


async def test_async_get_set_disable_rotate(make_async_client) -> None:  # type: ignore[no-untyped-def]
    active = sample_dynamic_ip(on_demand=True, surcharge_percent=95)
    rotated = sample_dynamic_ip(current_address="198.51.100.77", on_demand=True, on_demand_used=1, surcharge_percent=95)
    disabling = sample_dynamic_ip(state="disabling")

    rec = Recorder(
        json_response(201, active),
        json_response(200, active),
        json_response(200, rotated),
        json_response(200, disabling),
    )
    client = make_async_client(rec)

    assert await client.instances.dynamic_ip.set("vm_1", schedule="weekly", on_demand=True) == active
    assert await client.instances.dynamic_ip.get("vm_1") == active
    assert await client.instances.dynamic_ip.rotate("vm_1") == rotated
    assert await client.instances.dynamic_ip.disable("vm_1") == disabling

    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("PUT", "/public/v1/instances/vm_1/address-rotation"),
        ("GET", "/public/v1/instances/vm_1/address-rotation"),
        ("POST", "/public/v1/instances/vm_1/address-rotation/rotate"),
        ("DELETE", "/public/v1/instances/vm_1/address-rotation"),
    ]
    assert body(rec.requests[0]) == {"schedule": "weekly", "on_demand": True}


def test_rotate_is_no_replay_sync(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "UNAVAILABLE"))
    with pytest.raises(pantech.InternalServerError):
        make_client(rec).instances.dynamic_ip.rotate("vm_1")
    assert len(rec.requests) == 1

    rec = Recorder(httpx.ConnectError("boom"))
    with pytest.raises(pantech.APIConnectionError):
        make_client(rec).instances.dynamic_ip.rotate("vm_1")
    assert len(rec.requests) == 1

    rotated = sample_dynamic_ip(current_address="198.51.100.88", on_demand=True, on_demand_used=1)
    rec = Recorder(problem(429, "RATE_LIMITED", headers={"Retry-After": "1"}), json_response(200, rotated))
    assert make_client(rec).instances.dynamic_ip.rotate("vm_1") == rotated
    assert len(rec.requests) == 2
    assert rec.requests[0].headers["idempotency-key"] == rec.requests[1].headers["idempotency-key"]


async def test_rotate_is_no_replay_async(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(503, "UNAVAILABLE"))
    with pytest.raises(pantech.InternalServerError):
        await make_async_client(rec).instances.dynamic_ip.rotate("vm_1")
    assert len(rec.requests) == 1


def test_create_instance_with_address_rotation_sync(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"order_id": "ord_1", "instance_id": "vm_1", "status": "pending"}))
    out = make_client(rec).instances.create(
        name="web-1",
        plan_slug="starter",
        image_slug="ubuntu-24-04",
        ssh_key_id="sshk_1",
        security_group_id="sg_1",
        address_rotation={"schedule": "weekly"},
    )
    assert out["instance_id"] == "vm_1"
    assert body(rec.requests[0]) == {
        "name": "web-1",
        "plan_slug": "starter",
        "image_slug": "ubuntu-24-04",
        "ssh_key_id": "sshk_1",
        "security_group_id": "sg_1",
        "address_rotation": {"schedule": "weekly"},
    }


async def test_create_instance_with_address_rotation_async(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(202, {"order_id": "ord_1", "instance_id": "vm_1", "status": "pending"}))
    out = await make_async_client(rec).instances.create(
        name="web-1",
        plan_slug="starter",
        image_slug="ubuntu-24-04",
        ssh_key_id="sshk_1",
        security_group_id="sg_1",
        address_rotation={"schedule": "weekly", "connections": "move"},
    )
    assert out["instance_id"] == "vm_1"
    assert body(rec.requests[0])["address_rotation"] == {"schedule": "weekly", "connections": "move"}
