"""Host a zone on Pantech DNS, point a name at an address, and look for a domain to buy.

    export PANTECH_API_KEY=PAN_...
    python examples/dns_and_domains.py example.com --www 203.0.113.10 [--search example]

The zone is created if your organization has none with this name. It answers once your registrar
delegates the domain to the name servers printed here. Hosting a zone is free; nothing is bought.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

import pantech


def money(minor: int, currency: str) -> str:
    return f"{currency} {minor // 100:,}.{minor % 100:02d}"


def find_zone(client: pantech.Pantech, name: str) -> Optional[pantech.types.DNSZone]:
    for zone in client.dns.zones.list_all(q=name):
        if zone["name"] == name and zone["status"] not in ("deleting", "deleted", "failed"):
            return zone
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("zone", help="the zone's name, e.g. example.com")
    parser.add_argument("--www", required=True, help="the IPv4 address www should answer with")
    parser.add_argument("--search", default=None, help="a name to look for across the TLDs for sale")
    args = parser.parse_args()

    with pantech.Pantech() as client:
        try:
            zone = find_zone(client, args.zone) or client.dns.zones.create(name=args.zone)
            zone = client.dns.zones.wait(zone["id"])
            print(f"Zone {zone['id']} {zone['name']}: {zone['status']}")

            # Create www, or change it if it is there already. if_match refuses the change if
            # someone else changed the record set since it was read.
            existing = client.dns.records.list(zone["id"], name="www", type="A")["data"]
            if existing:
                rec = client.dns.records.update(
                    zone["id"], existing[0]["id"], if_match=existing[0]["version"], values=[args.www]
                )
            else:
                rec = client.dns.records.create(zone["id"], name="www", type="A", values=[args.www], ttl=300)
            rec = client.dns.records.wait(zone["id"], rec["id"])
            print(f"{rec['fqdn']} {rec['type']} {', '.join(rec['values'])}: {rec['status']}")

            if zone["status"] == "awaiting_delegation":
                print("\nSet these name servers at your domain's registrar:")
                for ns in zone["name_servers"]:
                    print(f"  {ns}")

            print("\nZone file:")
            print(client.dns.zones.export_zone_file(zone["id"]))

            if args.search:
                print(f"Domains for {args.search!r}:")
                for result in client.domains.search(query=args.search)["data"]:
                    price = result["price"]
                    cost = money(price["register_minor"], price["currency"]) + "/year" if price else ""
                    print(f"  {result['name']:<40} {result['status']:<12} {cost}")
                # To buy one: client.domains.register(name=..., contact={...}, accept_terms=True),
                # then client.domains.wait_for_order(result["order"]["id"]). It is paid from credit.
        except pantech.DNSFailedError as err:
            print(f"{err} ({err.kind}).", file=sys.stderr)
            return 1
        except pantech.APIError as err:
            print(f"{err.status} {err.code}: {err.detail}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
