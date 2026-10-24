"""Copies the public API spec into ``openapi/public-api.yaml``.

    python scripts/sync_spec.py                  # the published spec
    python scripts/sync_spec.py <path-or-url>    # a local file or another URL

Then run ``scripts/generate_types.py`` and ``scripts/generate_resources.py``.
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import urllib.request

PUBLISHED_URL = "https://docs.pantechdynamics.com/openapi/public-api.yaml"
DEST = pathlib.Path(__file__).resolve().parent.parent / "openapi" / "public-api.yaml"


def main(argv: list[str]) -> int:
    src = argv[1] if len(argv) > 1 else PUBLISHED_URL
    if src.startswith(("https://", "http://")):
        with urllib.request.urlopen(src, timeout=60) as resp:  # noqa: S310 - the URL is http(s) only
            DEST.write_bytes(resp.read())
    else:
        shutil.copyfile(src, DEST)
    print(f"wrote {DEST.relative_to(DEST.parent.parent)} from {src}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
