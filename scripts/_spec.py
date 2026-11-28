"""Loads the vendored public API spec for the generators and the tests.

The spec is ``openapi/public-api.yaml``, a copy of the published spec
(https://docs.pantechdynamics.com/openapi/public-api.yaml). ``_apply_pending``
adds what the API has committed to but the copy does not describe yet (DELETE
/me, the key's ``kind`` and ``client_name``, and the files in
``openapi/pending/``: Pantech DNS and domains). Each addition is applied only
while it is missing, so a newer spec always wins.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, Iterator, Tuple

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "openapi" / "public-api.yaml"
PENDING_DIR = ROOT / "openapi" / "pending"
PREFIX = "/public/v1"
METHODS = ("get", "post", "put", "patch", "delete")


def _pending_revoke_me() -> Dict[str, Any]:
    return {
        "tags": ["Account"],
        "summary": "Revoke this API key",
        "description": "The key making the call revokes itself. A second call is a 401: the key is gone.",
        "operationId": "revokeMe",
        "responses": {204: {"description": "Revoked."}},
    }


def _pending_dynamic_ip_schemas() -> Dict[str, Any]:
    return {
        "PutAddressRotationRequest": {
            "type": "object",
            "additionalProperties": False,
            "required": ["schedule"],
            "properties": {
                "schedule": {
                    "type": "string",
                    "description": "How often the dynamic IP changes.",
                    "enum": ["every_12_hours", "daily", "weekly", "monthly"],
                },
                "connections": {
                    "type": "string",
                    "description": (
                        "`keep` (default): open connections keep the old address until they close. "
                        "`move`: they move to the new address at once."
                    ),
                    "enum": ["keep", "move"],
                },
                "on_demand": {
                    "type": "boolean",
                    "description": "Allow rotate now. Needs it enabled for your organization.",
                },
            },
        },
        "AddressRotation": {
            "type": "object",
            "required": [
                "instance_id",
                "schedule",
                "connections",
                "on_demand",
                "state",
                "surcharge_percent",
                "on_demand_used",
                "on_demand_limit",
                "events",
            ],
            "properties": {
                "instance_id": {"type": "string"},
                "schedule": {
                    "type": "string",
                    "enum": ["every_12_hours", "daily", "weekly", "monthly"],
                },
                "connections": {
                    "type": "string",
                    "enum": ["keep", "move"],
                },
                "on_demand": {
                    "type": "boolean",
                    "description": "Whether rotate now is allowed.",
                },
                "state": {
                    "type": "string",
                    "description": (
                        "`enabling` until the first dynamic IP is ready, `active`, `degraded` "
                        "(dynamic IP is on with reduced capacity, or unreachable so the instance uses its own "
                        "address until it is restored; see `failure_reason`), `disabling`, `off`, or `failed` "
                        "(see `failure_reason`)."
                    ),
                    "enum": ["enabling", "active", "degraded", "disabling", "off", "failed"],
                },
                "current_address": {
                    "type": ["string", "null"],
                    "description": (
                        "The dynamic IP the instance uses now. Null before the first one is ready, "
                        "and while the instance uses its own address (`degraded`)."
                    ),
                },
                "next_rotation_at": {"type": ["string", "null"], "format": "date-time"},
                "last_rotated_at": {"type": ["string", "null"], "format": "date-time"},
                "surcharge_percent": {
                    "type": "number",
                    "description": "Added to the instance's hourly price while dynamic IP is on.",
                },
                "on_demand_used": {
                    "type": "integer",
                    "description": "Rotate-now changes in the last 24 hours.",
                },
                "on_demand_limit": {"type": "integer"},
                "failure_reason": {
                    "type": ["string", "null"],
                    "description": (
                        "Why dynamic IP is `failed`, or why it is `degraded` while the instance uses its own address."
                    ),
                },
                "events": {
                    "type": "array",
                    "description": "Recent dynamic IP changes, newest first.",
                    "items": {"$ref": "#/components/schemas/AddressRotationEvent"},
                },
            },
        },
        "AddressRotationEvent": {
            "type": "object",
            "required": ["kind", "degraded", "occurred_at"],
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["enabled", "scheduled", "on_demand", "failover", "handover", "disabled"],
                },
                "from_address": {"type": ["string", "null"]},
                "to_address": {"type": ["string", "null"]},
                "degraded": {"type": "boolean"},
                "occurred_at": {"type": "string", "format": "date-time"},
            },
        },
    }


def _pending_create_instance_address_rotation() -> Dict[str, Any]:
    return {
        "type": "object",
        "description": (
            "Turns on dynamic IP once the instance runs: outbound traffic leaves from a dynamic IP that "
            "changes on the schedule, while inbound still reaches the instance's static address."
        ),
        "required": ["schedule"],
        "additionalProperties": False,
        "properties": {
            "schedule": {
                "type": "string",
                "enum": ["every_12_hours", "daily", "weekly", "monthly"],
            },
            "connections": {
                "type": "string",
                "enum": ["keep", "move"],
                "default": "keep",
                "description": "`keep` lets open connections finish on the old address; `move` moves them at once.",
            },
        },
    }


def _pending_dynamic_ip_paths() -> Dict[str, Dict[str, Any]]:
    instance_id_param: Dict[str, Any] = {
        "name": "instance_id",
        "in": "path",
        "required": True,
        "description": "The resource's id.",
        "schema": {"type": "string"},
    }
    idempotency_ref: Dict[str, Any] = {"$ref": "#/components/parameters/IdempotencyKey"}
    rotation_response: Dict[str, Any] = {
        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/AddressRotation"}}}
    }
    return {
        PREFIX + "/instances/{instance_id}/address-rotation": {
            "get": {
                "tags": ["Instances"],
                "summary": "Get an instance's dynamic IP",
                "description": (
                    "Whether the instance's dynamic IP is on, on what schedule, the address it has now, "
                    "when it changes next, and its recent changes (`events`, newest first)."
                ),
                "operationId": "getInstanceAddressRotation",
                "parameters": [instance_id_param],
                "responses": {200: {"description": "The dynamic IP state.", **rotation_response}},
            },
            "put": {
                "tags": ["Instances"],
                "summary": "Turn on or change dynamic IP",
                "description": "Turns on dynamic IP for the instance, or changes its settings.",
                "operationId": "putInstanceAddressRotation",
                "parameters": [instance_id_param, idempotency_ref],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {"schema": {"$ref": "#/components/schemas/PutAddressRotationRequest"}}
                    },
                },
                "responses": {
                    200: {"description": "The updated dynamic IP settings.", **rotation_response},
                    201: {"description": "Dynamic IP was turned on.", **rotation_response},
                },
            },
            "delete": {
                "tags": ["Instances"],
                "summary": "Turn off dynamic IP",
                "description": "Turns off dynamic IP for the instance and ends the surcharge.",
                "operationId": "deleteInstanceAddressRotation",
                "parameters": [instance_id_param, idempotency_ref],
                "responses": {
                    200: {"description": "The dynamic IP state, now `disabling` or `off`.", **rotation_response}
                },
            },
        },
        PREFIX + "/instances/{instance_id}/address-rotation/rotate": {
            "post": {
                "tags": ["Instances"],
                "summary": "Rotate the dynamic IP now",
                "description": "Gives the instance a new dynamic IP now, outside its schedule.",
                "operationId": "rotateInstanceAddressNow",
                "parameters": [instance_id_param, idempotency_ref],
                "responses": {200: {"description": "The dynamic IP with its new address.", **rotation_response}},
            },
        },
    }


def _has_pointer(spec: Dict[str, Any], pointer: str) -> bool:
    node: Any = spec
    for part in pointer.lstrip("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def _merge_pending_file(spec: Dict[str, Any], path: pathlib.Path) -> None:
    """Adds a pending file's operations, and the components they use, where the spec lacks them.

    A file with ``x-pending-replace-until: <JSON pointer>`` instead replaces the spec's
    operations and components with its own, as long as the pointer is not in the spec:
    for an endpoint the vendored spec has, but without fields the API has added since.
    """
    with path.open(encoding="utf-8") as f:
        pending: Dict[str, Any] = yaml.safe_load(f)
    until = pending.get("x-pending-replace-until")
    if until is not None and _has_pointer(spec, until):
        return
    replace = until is not None
    for route, item in (pending.get("paths") or {}).items():
        target = spec["paths"].setdefault(route, {})
        for key, value in item.items():
            if replace:
                target[key] = value
            else:
                target.setdefault(key, value)
    components = spec.setdefault("components", {})
    for section, entries in (pending.get("components") or {}).items():
        existing = components.setdefault(section, {})
        for name, value in entries.items():
            if replace:
                existing[name] = value
            else:
                existing.setdefault(name, value)


def _apply_pending(spec: Dict[str, Any]) -> None:
    for path in sorted(PENDING_DIR.glob("*.yaml")):
        _merge_pending_file(spec, path)

    me = spec["paths"].setdefault(PREFIX + "/me", {})
    if "delete" not in me:
        me["delete"] = _pending_revoke_me()

    api_key = spec["components"]["schemas"]["Me"]["properties"]["api_key"]
    props = api_key.setdefault("properties", {})
    props.setdefault("kind", {"type": "string", "enum": ["standard", "ai_app"]})
    props.setdefault("client_name", {"type": ["string", "null"]})
    scopes = props.get("scopes", {}).get("items", {})
    if "enum" in scopes and "delete" not in scopes["enum"]:
        scopes["enum"] = [*scopes["enum"], "delete"]

    schemas = spec.setdefault("components", {}).setdefault("schemas", {})
    for name, schema in _pending_dynamic_ip_schemas().items():
        schemas.setdefault(name, schema)
    create_instance = schemas.get("CreateInstanceRequest")
    if isinstance(create_instance, dict):
        create_instance.setdefault("properties", {}).setdefault(
            "address_rotation", _pending_create_instance_address_rotation()
        )
    for route, methods in _pending_dynamic_ip_paths().items():
        target = spec["paths"].setdefault(route, {})
        for method, operation in methods.items():
            target.setdefault(method, operation)

    # Disambiguate duplicate operationId if a synced spec assigns putBucketObjectLock
    # to both /buckets/{bucket_id}/object-lock and /buckets/{bucket_id}/objects/lock.
    obj_lock = spec["paths"].get(PREFIX + "/buckets/{bucket_id}/objects/lock", {}).get("put")
    if isinstance(obj_lock, dict) and obj_lock.get("operationId") == "putBucketObjectLock":
        obj_lock["operationId"] = "putObjectLock"


def load_spec() -> Dict[str, Any]:
    with SPEC_PATH.open(encoding="utf-8") as f:
        spec: Dict[str, Any] = yaml.safe_load(f)
    _apply_pending(spec)
    return spec


def iter_operations(spec: Dict[str, Any]) -> Iterator[Tuple[str, str, str, Dict[str, Any], Dict[str, Any]]]:
    """Yields (operationId, METHOD, path under /public/v1, operation, path item)."""
    for path, item in spec["paths"].items():
        for method in METHODS:
            op = item.get(method)
            if op is None:
                continue
            rel = path[len(PREFIX) :] if path.startswith(PREFIX) else path
            yield op["operationId"], method.upper(), rel, op, item
