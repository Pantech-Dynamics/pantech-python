"""Building access policy statements.

    from pantech import iam

    client.iam.policies.create(
        name="staging-operators",
        statements=[
            iam.allow(["instances:Read", "instances:Start", "instances:Stop"], ["name:staging-*"],
                      source_ip=["102.89.0.0/16"], sid="RestartStaging"),
            iam.deny(["*:Delete"], sid="NoDeletes"),
        ],
    )

The helpers check the limits the API enforces (1 to 50 actions and resources, at most 20 source
CIDRs, a ``sid`` of 1 to 64 letters, digits, ``_`` or ``-``) so a mistake fails before the call;
the API still validates every statement, including that each action exists.
"""

from __future__ import annotations

import re
from typing import FrozenSet, Iterable, Literal, Optional

from .types import IamStatement, IamStatementConditions

__all__ = ["allow", "deny", "statement", "MANAGED_POLICY_IDS"]

# Pantech's managed policies: attach them by id; they cannot be changed.
MANAGED_POLICY_IDS: FrozenSet[str] = frozenset(
    {
        "pol_pantech_read_only",
        "pol_pantech_developer",
        "pol_pantech_network_admin",
        "pol_pantech_database_admin",
        "pol_pantech_dns_manager",
        "pol_pantech_domain_manager",
        "pol_pantech_registry_push",
        "pol_pantech_registry_pull",
        "pol_pantech_billing_manager",
        "pol_pantech_support",
        "pol_pantech_deny_delete",
        "pol_pantech_require_mfa_for_writes",
    }
)

_SID = re.compile(r"[A-Za-z0-9_-]{1,64}")
_MAX_ITEMS = 50
_MAX_SOURCE_IPS = 20


def _strings(name: str, values: Iterable[str], limit: int, *, allow_empty: bool = False) -> list[str]:
    if isinstance(values, str):
        raise TypeError(f"{name} must be a list of strings, not one string")
    out = list(values)
    if not out and not allow_empty:
        raise ValueError(f"{name} needs at least one entry")
    if len(out) > limit:
        raise ValueError(f"{name} takes at most {limit} entries, got {len(out)}")
    for v in out:
        if not isinstance(v, str) or not v:
            raise ValueError(f"{name} entries must be non-empty strings, got {v!r}")
    return out


def statement(
    effect: Literal["allow", "deny"],
    actions: Iterable[str],
    resources: Iterable[str] = ("*",),
    *,
    source_ip: Optional[Iterable[str]] = None,
    mfa: Optional[bool] = None,
    sid: Optional[str] = None,
) -> IamStatement:
    """One policy statement. ``resources`` defaults to every resource (``*``)."""
    if effect not in ("allow", "deny"):
        raise ValueError(f"effect must be 'allow' or 'deny', got {effect!r}")
    out: IamStatement = {
        "effect": effect,
        "actions": _strings("actions", actions, _MAX_ITEMS),
        "resources": _strings("resources", resources, _MAX_ITEMS),
    }
    if sid is not None:
        if not _SID.fullmatch(sid):
            raise ValueError("sid must be 1 to 64 letters, digits, '_' or '-'")
        out["sid"] = sid
    conditions: IamStatementConditions = {}
    if source_ip is not None:
        conditions["source_ip"] = _strings("source_ip", source_ip, _MAX_SOURCE_IPS)
    if mfa is not None:
        conditions["mfa"] = mfa
    if conditions:
        out["conditions"] = conditions
    return out


def allow(
    actions: Iterable[str],
    resources: Iterable[str] = ("*",),
    *,
    source_ip: Optional[Iterable[str]] = None,
    mfa: Optional[bool] = None,
    sid: Optional[str] = None,
) -> IamStatement:
    """An ``allow`` statement: ``allow(["instances:Start"], ["name:staging-*"])``."""
    return statement("allow", actions, resources, source_ip=source_ip, mfa=mfa, sid=sid)


def deny(
    actions: Iterable[str],
    resources: Iterable[str] = ("*",),
    *,
    source_ip: Optional[Iterable[str]] = None,
    mfa: Optional[bool] = None,
    sid: Optional[str] = None,
) -> IamStatement:
    """A ``deny`` statement, which wins over every allow: ``deny(["*:Delete"], ["vm_..."])``."""
    return statement("deny", actions, resources, source_ip=source_ip, mfa=mfa, sid=sid)
