# Changelog

All notable changes to the `pantech` package. The newest version heading
(`## X.Y.Z (YYYY-MM-DD)`) is released when it reaches `main`: see
`.github/workflows/release.yml`. Put work in progress under `## Unreleased`.

## 0.2.0 (2026-10-28)

FEATURES:

- `client.migrate`, for moving from another cloud: `migrate.connections` (`list`, `create`, `get`, `update` for the name, role ARN or a retry, `delete`) connects an AWS account through a read-only role; `migrate.scans` (`list`, `start`, `get` with `include="inventory"`) reads what runs there; `migrate.migrations` (`list`, `create`, `get`, `rename`, `delete`, `update_item`, `export_terraform`) plans the move with a price comparison and a Terraform export. Sync and async.
- `migrate.connections.wait(...)` and `migrate.scans.wait(...)`, which raise the new `CloudFailedError` when the connection or scan fails.
- `examples/migrate_from_aws.py`.
- Types follow the current public API, including Kubernetes clusters' `node_health`, `ready_nodes` and `nodes_checked_at`, and a load balancer's `protocol`.

NOTES:

- Agent sessions, which answer only AI apps connected through Pantech's MCP server, have no methods yet. `NOT_IN_SDK` in `src/pantech/_operations.py` lists them; the generators leave out their types.

## 0.1.0 (2026-10-24)

FEATURES:

- First release of the official Python SDK for the Pantech Dynamics public API (`/public/v1`).
- `pantech.Pantech` (blocking) and `pantech.AsyncPantech` (asyncio) clients with the same methods, as context managers.
- Every operation in the public API, grouped by family (`client.instances`, `client.networks.subnets`, `client.kubernetes.node_pools`, `client.billing.receipts`…), with typed keyword arguments and TypedDict results in `pantech.types`.
- `api_key` and `base_url` from arguments or `PANTECH_API_KEY` / `PANTECH_API_URL`.
- An automatic `Idempotency-Key` on every write, reused across retries. Retries (default 3) on connection errors, timeouts, 429, 500, 502, 503 and 504 with jittered backoff and `Retry-After`; writes the API does not replay are sent once.
- Errors as `APIError` subclasses carrying `status`, `code`, `title`, `detail`, `request_id` and field `errors`.
- `list_all()` iterators that follow `next_cursor`, sync and async.
- `client.operations.wait(...)`, `client.operations.stream(...)` (Server-Sent Events), and `instances.wait_for_order(...)` / `databases.wait_for_order(...)`.
- `client.me.get()` reports the key's `kind` and `client_name`; `client.me.revoke()` revokes the calling key.
- `pantech.verify_webhook(secret, header, body, tolerance=300)` for `Pantech-Signature`.
