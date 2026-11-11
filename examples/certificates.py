"""Request a TLS certificate and wait until it is issued.

    export PANTECH_API_KEY=PAN_...
    python examples/certificates.py example.com '*.example.com' [--wait-hours 72]

Names in an active Pantech DNS zone of your organization are validated automatically, usually
within two minutes. For any other name the script prints the CNAME to add at your DNS host once;
it keeps renewals automatic as long as it stays. Pantech renews the certificate by itself.
"""

from __future__ import annotations

import argparse
import sys

import pantech


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="+", help="1 to 100 DNS names, e.g. example.com '*.example.com'")
    parser.add_argument("--wait-hours", type=float, default=0.25, help="how long to wait for issue (CNAMEs: up to 72)")
    args = parser.parse_args()

    with pantech.Pantech() as client:
        try:
            cert = client.certificates.request(names=args.names, description="Requested by examples/certificates.py")
            print(f"Certificate {cert['id']} for {', '.join(cert['names'])}: {cert['status']}")

            cnames = [v for v in cert["validations"] if v["method"] == "cname"]
            if cnames:
                print("\nAdd these CNAME records at your DNS host:")
                for v in {(v["cname_name"], v["cname_target"]) for v in cnames}:
                    print(f"  {v[0]}  CNAME  {v[1]}")
                client.certificates.verify(cert["id"])  # checks them within seconds once they exist

            cert = client.certificates.wait(cert["id"], timeout=args.wait_hours * 3600)
            print(f"\nIssued by {cert['issuer']}, valid until {cert['not_after']}, renewed from {cert['renew_after']}")
        except pantech.CertificateFailedError as err:
            print(f"{err} ({err.code})", file=sys.stderr)
            return 1
        except pantech.WaitTimeoutError as err:
            print(f"{err} Run verify once the CNAMEs exist.", file=sys.stderr)
            return 1
        except pantech.APIError as err:
            print(f"{err.status} {err.code}: {err.detail}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
