from __future__ import annotations

import json
import logging
from typing import Any, Dict

import httpx
import pytest

import pantech

from .conftest import Recorder, json_response, problem

SECRET = "prt_01JD_s3cr3tvalue"


def namespace(**extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "name": "acme",
        "registry_host": "registry.pantechdynamics.com",
        "create_on_push": True,
        "repository_count": 0,
        "storage_bytes": 0,
        "storage_limit_bytes": 53687091200,
        "repository_limit": 100,
        "created_at": "2026-11-10T09:00:00Z",
        "updated_at": "2026-11-10T09:00:00Z",
        "version": 1,
    }
    out.update(extra)
    return out


def token(**extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "prt_01JD",
        "name": "github-actions",
        "permission": "push",
        "repositories": ["api/server"],
        "expires_at": None,
        "last_used_at": None,
        "created_at": "2026-11-10T09:00:00Z",
        "revoked_at": None,
    }
    out.update(extra)
    return out


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_namespace_get_and_set(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, namespace()))
    client = make_client(rec)
    assert client.registry.namespace.get()["name"] == "acme"
    client.registry.namespace.set(name="acme", create_on_push=False)
    get, put = rec.requests
    assert (get.method, get.url.path) == ("GET", "/public/v1/registry")
    assert (put.method, put.url.path) == ("PUT", "/public/v1/registry")
    assert body(put) == {"name": "acme", "create_on_push": False}
    assert put.headers["idempotency-key"]


def test_namespace_not_set_is_a_typed_not_found(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(404, "REGISTRY_NAMESPACE_NOT_SET", "Claim a namespace first."))
    with pytest.raises(pantech.NotFoundError) as info:
        make_client(rec).registry.namespace.get()
    assert info.value.code == "REGISTRY_NAMESPACE_NOT_SET"
    assert info.value.code in pantech.REGISTRY_ERROR_CODES


def test_create_and_update_repository(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, {"id": "crr_1", "name": "api/server"}))
    client = make_client(rec)
    client.registry.repositories.create(
        name="api/server", immutable_tags=True, retention={"keep_last": 50, "keep_pattern": "v*"}
    )
    client.registry.repositories.update("crr_1", visibility="public", retention={"untagged_after_days": None})
    create, update = rec.requests
    assert (create.method, create.url.path) == ("POST", "/public/v1/registry/repositories")
    assert body(create) == {
        "name": "api/server",
        "immutable_tags": True,
        "retention": {"keep_last": 50, "keep_pattern": "v*"},
    }
    assert (update.method, update.url.path) == ("PATCH", "/public/v1/registry/repositories/crr_1")
    assert body(update) == {"visibility": "public", "retention": {"untagged_after_days": None}}


def test_list_all_repositories_follows_the_cursor(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, {"data": [{"id": "crr_1"}], "next_cursor": "c2"}),
        json_response(200, {"data": [{"id": "crr_2"}], "next_cursor": None}),
    )
    ids = [r["id"] for r in make_client(rec).registry.repositories.list_all(q="api")]
    assert ids == ["crr_1", "crr_2"]
    assert rec.requests[1].url.params["cursor"] == "c2"


def test_tag_names_are_escaped_in_the_path(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"name": "v1.4.2"}))
    client = make_client(rec)
    client.registry.tags.get("crr_1", "v1.4.2")
    client.registry.tags.get("crr_1", "a/b")
    assert rec.requests[0].url.raw_path == b"/public/v1/registry/repositories/crr_1/tags/v1.4.2"
    assert rec.requests[1].url.raw_path == b"/public/v1/registry/repositories/crr_1/tags/a%2Fb"


def test_deleting_an_immutable_tag_is_a_typed_conflict(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(409, "TAG_IMMUTABLE", "The repository has immutable tags."))
    with pytest.raises(pantech.ConflictError) as info:
        make_client(rec).registry.tags.delete("crr_1", "v1")
    assert info.value.code == "TAG_IMMUTABLE"
    assert rec.requests[0].method == "DELETE"


def test_create_token_returns_the_secret_but_never_shows_it(make_client, caplog) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, token(secret=SECRET)))
    with caplog.at_level(logging.DEBUG, logger="pantech"):
        created = make_client(rec).registry.tokens.create(
            name="github-actions", permission="push", repositories=["api/server"]
        )
    assert created["secret"] == SECRET
    assert SECRET not in repr(created)
    assert SECRET not in str(created)
    assert SECRET not in f"{created}"
    assert "<hidden>" in repr(created)
    assert SECRET not in caplog.text
    # Storing it is the point: it serializes and copies like any dict.
    assert json.loads(json.dumps(created))["secret"] == SECRET
    assert dict(created)["secret"] == SECRET
    assert body(rec.requests[0]) == {"name": "github-actions", "permission": "push", "repositories": ["api/server"]}


async def test_async_create_token_hides_the_secret(make_async_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, token(secret=SECRET)))
    created = await make_async_client(rec).registry.tokens.create(name="ci", permission="pull")
    assert created["secret"] == SECRET
    assert SECRET not in repr(created)


def test_list_and_revoke_tokens(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"data": [token()], "next_cursor": None}), httpx.Response(204))
    client = make_client(rec)
    assert client.registry.tokens.list()["data"][0]["id"] == "prt_01JD"
    assert client.registry.tokens.delete("prt_01JD") is None
    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("GET", "/public/v1/registry/tokens"),
        ("DELETE", "/public/v1/registry/tokens/prt_01JD"),
    ]


def test_registry_codes_cover_the_contract() -> None:
    assert len(pantech.REGISTRY_ERROR_CODES) == 15
    assert {
        "REPOSITORY_EXISTS",
        "REGISTRY_STORAGE_LIMIT_REACHED",
        "REPOSITORY_SUSPENDED",
    } <= pantech.REGISTRY_ERROR_CODES
