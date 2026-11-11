"""Set up the private container registry for CI: a namespace, a repository and a push token.

    export PANTECH_API_KEY=PAN_...
    python examples/container_registry.py acme api/server [--token-file registry-token.txt]

The namespace is claimed if your organization has none yet. The token's secret is shown only
once: it is written to --token-file (readable by you alone), never printed.
"""

from __future__ import annotations

import argparse
import os
import sys

import pantech


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("namespace", help="3 to 30 lower-case letters, digits and hyphens, e.g. acme")
    parser.add_argument("repository", help="the repository's name, e.g. api/server")
    parser.add_argument("--token-file", default="registry-token.txt", help="where to write the token's secret")
    args = parser.parse_args()

    with pantech.Pantech() as client:
        try:
            try:
                ns = client.registry.namespace.get()
            except pantech.NotFoundError as err:
                if err.code != "REGISTRY_NAMESPACE_NOT_SET":
                    raise
                ns = client.registry.namespace.set(name=args.namespace)
            print(f"Namespace {ns['name']} on {ns['registry_host']}")

            repo = next(
                (r for r in client.registry.repositories.list_all(q=args.repository) if r["name"] == args.repository),
                None,
            )
            if repo is None:
                repo = client.registry.repositories.create(
                    name=args.repository,
                    immutable_tags=True,
                    retention={"keep_last": 50, "untagged_after_days": 7, "keep_pattern": "v*"},
                )
            print(f"Repository {repo['full_name']} ({repo['visibility']})")

            token = client.registry.tokens.create(name="ci", permission="push", repositories=[repo["name"]])
            if token["secret"] is None:  # a replayed create: the secret is never stored, so it is gone
                print("The token's secret was shown once already; revoke it and create another.", file=sys.stderr)
                return 1
            fd = os.open(args.token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(token["secret"])
            print(f"Token {token['id']} ({token['permission']}): secret written to {args.token_file}")

            print("\nIn CI:")
            print(f"  docker login {ns['registry_host']} -u pantech --password-stdin < {args.token_file}")
            print(f"  docker build -t {repo['full_name']}:v1 . && docker push {repo['full_name']}:v1")
        except pantech.APIError as err:
            print(f"{err.status} {err.code}: {err.detail}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
