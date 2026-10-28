"""Connect an AWS account, scan it, plan the move to Pantech, and write the plan as Terraform.

    export PANTECH_API_KEY=PAN_...
    python examples/migrate_from_aws.py --name "Production AWS" [--region af-abj] [--out pantech-migration]

It prints a link that creates a read-only role in your AWS account. Create the stack, then paste
its RoleArn output when asked, or pass it up front with --role-arn or PANTECH_ROLE_ARN. No AWS
access keys are ever sent. Planning creates nothing on Pantech.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

import pantech


def money(minor: Optional[int], currency: Optional[str]) -> str:
    if minor is None:
        return "unknown"
    return f"{currency or ''} {minor // 100:,}.{minor % 100:02d}".strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", default="AWS account", help="a name for the connection and the plan")
    parser.add_argument("--region", default=None, help="the Pantech region to plan for (default: the first)")
    parser.add_argument(
        "--role-arn",
        default=os.environ.get("PANTECH_ROLE_ARN"),
        help="the stack's RoleArn output (default: $PANTECH_ROLE_ARN, else asked for)",
    )
    parser.add_argument("--out", default="pantech-migration", help="directory to write the Terraform files to")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with pantech.Pantech() as client:
        try:
            # 1. Start a connection. Nothing is shared yet.
            conn = client.migrate.connections.create(name=args.name)
            print(f"Connection {conn['id']}")

            # 2. Create the read-only role in AWS, from the one-click link or the template.
            setup = conn["setup"]
            if setup.get("quick_create_url"):
                print("\nOpen this link, signed in to AWS, and create the stack:")
                print(f"  {setup['quick_create_url']}")
            else:
                template = out / "pantech-role.template.json"
                template.write_text(setup["template"], encoding="utf-8")
                print(f"\nCreate a CloudFormation stack in AWS from {template}")

            # 3. Send the stack's RoleArn output.
            role_arn = (args.role_arn or "").strip() or input("\nPaste the stack's RoleArn output: ").strip()
            if not role_arn:
                print("No role ARN given.", file=sys.stderr)
                return 1
            client.migrate.connections.update(conn["id"], role_arn=role_arn)

            # 4. Wait for Pantech to assume the role.
            conn = client.migrate.connections.wait(conn["id"], timeout=600)
            print(f"Connected to AWS account {conn.get('aws_account_id')}")

            # 5. Scan the account.
            scan = client.migrate.scans.start(conn["id"])
            print(f"Scanning ({scan['id']}); most accounts take under five minutes...")
            scan = client.migrate.scans.wait(scan["id"], timeout=1800)
            counts = scan.get("counts") or {}
            print(
                f"Found {counts.get('instances', 0)} servers, {counts.get('volumes', 0)} disks, "
                f"{counts.get('networks', 0)} networks, {counts.get('databases', 0)} databases "
                f"in {', '.join(scan.get('regions') or [])}"
            )
            for warning in scan.get("warnings") or []:
                print(f"  not read: {warning}")

            # 6. Plan the move. Nothing is created on Pantech.
            plan = client.migrate.migrations.create(
                scan_id=scan["id"], name=args.name, region=args.region or pantech.NOT_GIVEN
            )
            summary = plan["summary"]
            print(
                f"\nPlan {plan['id']} for {plan['region']}: {summary['planned']} planned, "
                f"{summary['excluded']} excluded, {summary['unsupported']} not supported yet"
            )
            for item in plan.get("items") or []:
                for flag in item["flags"]:
                    if flag["blocking"]:
                        print(f"  {item['key']}: {flag['message']}")

            # 7. The price comparison.
            estimate = plan.get("estimate")
            if estimate:
                if estimate["pantech_priced"]:
                    print(
                        f"Pantech: {money(estimate['pantech_monthly_minor'], estimate['currency'])} a month "
                        f"(covers {', '.join(estimate['covers'])})"
                    )
                else:
                    print("Pantech: part of the plan could not be priced")
                if estimate["not_covered"]:
                    print(f"  not in the price: {', '.join(estimate['not_covered'])}")
                if estimate["source_known"]:
                    print(
                        f"AWS: {money(estimate['source_monthly_minor'], estimate['source_currency'])} a month, "
                        f"the whole bill averaged over {estimate['source_months']} months"
                    )

            # 8. Export Terraform.
            terraform = client.migrate.migrations.export_terraform(plan["id"])
            for f in terraform["files"]:
                path = out / Path(f["name"]).name
                path.write_text(f["content"], encoding="utf-8")
                print(f"Wrote {path}")
        except pantech.CloudFailedError as err:
            # err.message says what to do; branch on err.code.
            print(f"The {err.kind} failed: {err.message} ({err.code})", file=sys.stderr)
            return 1
        except pantech.ValidationError as err:
            for field in err.errors:
                print(f"{field['field']}: {field['message']}", file=sys.stderr)
            return 1
        except pantech.APIError as err:
            print(f"{err.detail or err.title} (request_id: {err.request_id})", file=sys.stderr)
            return 1
        except pantech.PantechError as err:
            print(err, file=sys.stderr)
            return 1

    print(f"\nReview the files, fill in the variables, then run terraform init and terraform plan in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
