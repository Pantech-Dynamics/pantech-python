"""A webhook receiver on the standard library's http.server.

    export PANTECH_WEBHOOK_SECRET=whsec_...
    python examples/webhook_server.py 8000

Point a webhook at https://<your host>/pantech (behind TLS in production).
Each delivery is verified against its raw body before it is trusted; a bad
signature gets 400 and Pantech retries later.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Set

import pantech

SECRET = os.environ.get("PANTECH_WEBHOOK_SECRET", "")
seen_events: Set[str] = set()  # deduplicate on the event id: deliveries can repeat


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path != "/pantech":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)  # the raw bytes, exactly as signed
        try:
            pantech.verify_webhook(SECRET, self.headers.get(pantech.SIGNATURE_HEADER), body)
        except pantech.WebhookVerificationError as err:
            self.send_error(400, str(err))
            return

        event = json.loads(body)
        if event.get("id") not in seen_events:
            seen_events.add(event.get("id"))
            print(f"{self.headers.get('Pantech-Event-Type')}: {event.get('id')}")
        # Answer 2xx within 10 seconds; do slow work after responding.
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # quieter than the default
        pass


def main() -> None:
    if not SECRET:
        sys.exit("Set PANTECH_WEBHOOK_SECRET to the webhook's signing secret.")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Listening on http://0.0.0.0:{port}/pantech")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
