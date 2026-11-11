"""Give a team restart-and-resize access to staging machines, and check it.

    export PANTECH_API_KEY=PAN_...
    python examples/access_policies.py usr_... [--team Platform]

Creates (or reuses) the team and a "staging-operators" policy, attaches the policy to the team,
adds the member, and asks the simulator whether they may stop and delete a staging machine.
Owners and admins only.
"""

from __future__ import annotations

import argparse
import sys
from typing import List

import pantech
from pantech import iam

POLICY = "staging-operators"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("user_id", help="the member to add, usr_...")
    parser.add_argument("--team", default="Platform")
    args = parser.parse_args()

    statements: List[pantech.types.IamStatement] = [
        iam.allow(
            ["instances:Read", "instances:Start", "instances:Stop", "instances:Reboot", "instances:Resize"],
            ["name:staging-*"],
            sid="OperateStaging",
        ),
        iam.deny(["instances:Delete"], sid="NoDeletes"),
    ]

    with pantech.Pantech() as client:
        try:
            team = next((t for t in client.iam.teams.list_all() if t["name"] == args.team), None)
            team = team or client.iam.teams.create(name=args.team)

            pol = next((p for p in client.iam.policies.list_all(managed=False) if p["name"] == POLICY), None)
            if pol is None:
                pol = client.iam.policies.create(name=POLICY, statements=statements)
            else:
                # if_match refuses the change if someone else edited the policy since it was read.
                pol = client.iam.policies.update(pol["id"], name=POLICY, statements=statements, if_match=pol["version"])

            if pol["id"] not in team["policy_ids"]:
                client.iam.policies.attachments.attach(pol["id"], principal_type="team", principal_id=team["id"])
            client.iam.teams.members.add(team["id"], args.user_id)
            print(f"Team {team['name']} ({team['id']}) has {pol['name']} ({pol['id']}) and {args.user_id}")

            for action in ("instances:Stop", "instances:Delete"):
                sim = client.iam.simulate(user_id=args.user_id, action=action, resource_name="staging-web-1")
                verdict = "allowed" if sim["allowed"] else "denied"
                print(f"  {action} on staging-web-1: {verdict} ({sim['decision']})")
        except pantech.ValidationError as err:
            for fe in err.errors:
                print(f"{fe['field']}: {fe['message']}", file=sys.stderr)
            return 1
        except pantech.APIError as err:
            print(f"{err.status} {err.code}: {err.detail}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
