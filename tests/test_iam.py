from __future__ import annotations

import json
from typing import Any, Dict

import httpx
import pytest

import pantech
from pantech import iam

from .conftest import Recorder, json_response, problem


def policy(**extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "id": "pol_1",
        "name": "staging-operators",
        "description": "",
        "managed": False,
        "statements": [],
        "attachment_count": 0,
        "created_at": "2026-11-10T09:00:00Z",
        "updated_at": "2026-11-10T09:00:00Z",
        "version": 5,
    }
    out.update(extra)
    return out


def body(request: httpx.Request) -> Any:
    return json.loads(request.content)


def test_allow_builds_a_statement() -> None:
    s = iam.allow(
        ["instances:Read", "instances:Start"], ["name:staging-*"], source_ip=["102.89.0.0/16"], sid="RestartStaging"
    )
    assert s == {
        "effect": "allow",
        "actions": ["instances:Read", "instances:Start"],
        "resources": ["name:staging-*"],
        "sid": "RestartStaging",
        "conditions": {"source_ip": ["102.89.0.0/16"]},
    }


def test_deny_defaults_to_every_resource_and_keeps_mfa_false() -> None:
    assert iam.deny(["*:Delete"], mfa=False) == {
        "effect": "deny",
        "actions": ["*:Delete"],
        "resources": ["*"],
        "conditions": {"mfa": False},
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"actions": []}, "at least one"),
        ({"actions": "instances:Read"}, "not one string"),
        ({"actions": ["a:B"] * 51}, "at most 50"),
        ({"actions": ["a:B"], "resources": [""]}, "non-empty"),
        ({"actions": ["a:B"], "sid": "has space"}, "sid"),
        ({"actions": ["a:B"], "source_ip": ["10.0.0.0/8"] * 21}, "at most 20"),
    ],
)
def test_builder_checks_the_limits(kwargs: Dict[str, Any], message: str) -> None:
    with pytest.raises((ValueError, TypeError), match=message):
        iam.allow(**kwargs)


def test_managed_policy_ids() -> None:
    assert "pol_pantech_read_only" in iam.MANAGED_POLICY_IDS
    assert len(iam.MANAGED_POLICY_IDS) == 12


def test_create_policy_with_built_statements(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(201, policy()))
    statements = [iam.allow(["instances:Start"], ["name:staging-*"]), iam.deny(["*:Delete"])]
    make_client(rec).iam.policies.create(name="staging-operators", statements=statements)
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("POST", "/public/v1/iam/policies")
    assert body(req) == {"name": "staging-operators", "statements": statements}
    assert req.headers["idempotency-key"]


def test_update_policy_sends_if_match(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, policy(version=6)))
    make_client(rec).iam.policies.update(
        "pol_1", name="staging-operators", statements=[iam.allow(["instances:Read"])], if_match=5
    )
    req = rec.requests[0]
    assert (req.method, req.url.path) == ("PUT", "/public/v1/iam/policies/pol_1")
    assert req.headers["if-match"] == "5"


def test_version_conflict_and_invalid_policy_are_typed(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        problem(412, "VERSION_CONFLICT", "The policy changed."),
        problem(
            422,
            "INVALID_POLICY",
            "A statement is invalid.",
            errors=[{"field": "statements[0].actions[0]", "code": "UNKNOWN_ACTION", "message": "No such action."}],
        ),
    )
    client = make_client(rec)
    with pytest.raises(pantech.PreconditionFailedError):
        client.iam.policies.update("pol_1", name="p", statements=[iam.allow(["x:Y"])], if_match=1)
    with pytest.raises(pantech.ValidationError) as info:
        client.iam.policies.create(name="p", statements=[iam.allow(["x:Y"])])
    assert info.value.code == "INVALID_POLICY"
    assert info.value.code in pantech.IAM_ERROR_CODES
    assert info.value.errors[0]["field"] == "statements[0].actions[0]"


def test_policy_list_filters_managed(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"data": [], "next_cursor": None}))
    make_client(rec).iam.policies.list(managed=False)
    assert rec.requests[0].url.params["managed"] == "false"


def test_attach_and_detach(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(
            201,
            {
                "policy_id": "pol_1",
                "principal_type": "team",
                "principal_id": "team_1",
                "attached_at": "2026-11-10T09:00:00Z",
            },
        ),
        httpx.Response(204),
    )
    client = make_client(rec)
    client.iam.policies.attachments.attach("pol_1", principal_type="team", principal_id="team_1")
    assert client.iam.policies.attachments.detach("pol_1", "team", "team_1") is None
    attach, detach = rec.requests
    assert (attach.method, attach.url.path) == ("POST", "/public/v1/iam/policies/pol_1/attachments")
    assert body(attach) == {"principal_type": "team", "principal_id": "team_1"}
    assert (detach.method, detach.url.path) == ("DELETE", "/public/v1/iam/policies/pol_1/attachments/team/team_1")


def test_team_members(make_client) -> None:  # type: ignore[no-untyped-def]
    member = {"user_id": "usr_1", "email": "ada@example.com", "name": "Ada", "role": "member", "added_at": "x"}
    rec = Recorder(json_response(200, member), httpx.Response(204))
    client = make_client(rec)
    assert client.iam.teams.members.add("team_1", "usr_1")["user_id"] == "usr_1"
    client.iam.teams.members.remove("team_1", "usr_1")
    assert [(r.method, r.url.path) for r in rec.requests] == [
        ("PUT", "/public/v1/iam/teams/team_1/members/usr_1"),
        ("DELETE", "/public/v1/iam/teams/team_1/members/usr_1"),
    ]
    assert rec.requests[0].content == b""


def test_admin_target_is_typed(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(problem(403, "IAM_ADMIN_TARGET", "Only owners act on admins."))
    with pytest.raises(pantech.PermissionDeniedError) as info:
        make_client(rec).iam.teams.members.add("team_1", "usr_admin")
    assert info.value.code == "IAM_ADMIN_TARGET"


def test_simulate_and_effective_access(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(
        json_response(200, {"allowed": False, "decision": "explicit_deny", "policy_id": "pol_1", "sid": "NoProd"}),
        json_response(
            200,
            {
                "user_id": "usr_1",
                "role": "member",
                "teams": ["team_1"],
                "policies": [{"policy_id": "pol_1", "team_id": "team_1"}],
                "member_baseline": "read",
            },
        ),
    )
    client = make_client(rec)
    sim = client.iam.simulate(user_id="usr_1", action="instances:Delete", resource="vm_1", mfa=True)
    assert sim["decision"] == "explicit_deny"
    access = client.iam.effective_access("usr_1")
    assert access["policies"][0]["team_id"] == "team_1"
    assert body(rec.requests[0]) == {"user_id": "usr_1", "action": "instances:Delete", "resource": "vm_1", "mfa": True}
    assert rec.requests[1].url.path == "/public/v1/iam/members/usr_1/effective-access"


def test_settings(make_client) -> None:  # type: ignore[no-untyped-def]
    rec = Recorder(json_response(200, {"member_baseline": "none", "version": 2, "updated_at": "x"}))
    client = make_client(rec)
    client.iam.settings.update(member_baseline="none")
    assert body(rec.requests[0]) == {"member_baseline": "none"}
    assert rec.requests[0].method == "PUT"


async def test_async_actions_list(make_async_client) -> None:  # type: ignore[no-untyped-def]
    action = {
        "action": "instances:Stop",
        "service": "instances",
        "description": "",
        "resource_types": [],
        "read": False,
    }
    rec = Recorder(json_response(200, {"data": [action]}))
    out = await make_async_client(rec).iam.actions.list()
    assert out["data"][0]["action"] == "instances:Stop"


def test_iam_codes_cover_the_contract() -> None:
    assert len(pantech.IAM_ERROR_CODES) == 13
    assert "ACCESS_DENIED" in pantech.IAM_ERROR_CODES
