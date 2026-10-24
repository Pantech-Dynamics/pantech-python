"""Create an instance, wait until it runs, and print its address.

    export PANTECH_API_KEY=PAN_...
    python examples/create_instance.py web-1 --plan starter --image ubuntu-24-04 --ssh-key sshk_...

Creating an instance costs money: the order is paid from your credit.
"""

from __future__ import annotations

import argparse
import sys

import pantech


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name")
    parser.add_argument("--plan", default="starter", help="a plan slug from catalog.list_plans()")
    parser.add_argument("--image", default="ubuntu-24-04", help="an image slug from catalog.list_images()")
    parser.add_argument("--ssh-key", required=True, help="an SSH key id (sshk_...) from ssh_keys.list()")
    parser.add_argument("--region", default=None)
    args = parser.parse_args()

    with pantech.Pantech() as client:
        try:
            order = client.instances.create(
                name=args.name,
                plan_slug=args.plan,
                image_slug=args.image,
                ssh_key_id=args.ssh_key,
                region=args.region or pantech.NOT_GIVEN,
            )
            print(f"Ordered {order['instance_id']} (order {order['order_id']}), waiting for it to be provisioned...")
            client.instances.wait_for_order(order["order_id"], timeout=900)
            instance = client.instances.get(order["instance_id"])
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

    address = instance.get("public_ipv4") or instance.get("private_ipv4")
    print(f"{instance['name']} is {instance.get('observed_state')} at {address}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
