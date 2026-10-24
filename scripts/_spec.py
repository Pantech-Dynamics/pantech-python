"""Loads the vendored public API spec for the generators and the tests.

The spec is ``openapi/public-api.yaml``, a copy of the published spec
(https://docs.pantechdynamics.com/openapi/public-api.yaml). ``_apply_pending``
adds what the API has committed to but the copy does not describe yet (DELETE
/me, the key's ``kind`` and ``client_name``). Each addition is applied only
while it is missing, so a newer spec always wins.
"""

from __future__ import annotations

import pathlib
from typing import Any, Dict, Iterator, Tuple

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "openapi" / "public-api.yaml"
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


def _apply_pending(spec: Dict[str, Any]) -> None:
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
