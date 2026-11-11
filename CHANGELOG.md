# Changelog

All notable changes to the `pantech` package. The newest version heading
(`## X.Y.Z (YYYY-MM-DD)`) is released when it reaches `main`: see
`.github/workflows/release.yml`. Put work in progress under `## Unreleased`.

## 0.4.0 (2026-11-10)

FEATURES:

- `client.dns`, Pantech DNS on Pantech's own name servers (two per zone): `dns.zones` (`list`, `create`, `get`, `update`, `delete`, `verify`, `export_zone_file` returning the BIND zone file as text, `import_zone_file`) and `dns.records` (`list`, `create`, `get`, `update` and `delete` with `if_match=` for the record's `version`, `batch` for up to 1000 changes at once). Sync and async.
- `client.domains`: `list_tlds`, `search`, `check_transfer`, `list`, `get`, `register`, `transfer`, `update` (auto-renew, transfer lock, privacy), `set_name_servers`, `get_contact`, `update_contact`, `renew`, `request_auth_code`, `get_auth_code`, and `domains.orders` (`list`, `get`). Sync and async.
- `dns.zones.wait(zone_id)` (until the zone has its name servers) and `dns.records.wait(zone_id, record_id)` (until the record set answers), which raise the new `DNSFailedError` when the zone or change fails, and `domains.wait_for_order(order_id)`, which raises `OrderFailedError` with the order's `failure_code`.
- `PreconditionFailedError` for `412` (`VERSION_CONFLICT`), and `DNSErrorCode`, `DomainErrorCode`, `DNS_ERROR_CODES` and `DOMAIN_ERROR_CODES` for every DNS and domain problem code.
- `examples/dns_and_domains.py`.
- `client.registry`, the private container registry: `registry.namespace` (`get`, `set`), `registry.repositories` (`list`, `list_all`, `create`, `get`, `update` for visibility, tag immutability and retention, `delete`), `registry.tags` (`list`, `list_all`, `get`, `delete`) and `registry.tokens` (`list`, `list_all`, `create`, `delete`). Sync and async. The token `create` returns its `secret` in a dict whose `repr()` and `str()` show `<hidden>`.
- `RegistryErrorCode` and `REGISTRY_ERROR_CODES` for every registry problem code.
- `examples/container_registry.py`.
- `client.iam`, teams and access policies: `iam.actions.list`, `iam.settings` (`get`, `update`), `iam.teams` (`list`, `list_all`, `create`, `get`, `update`, `delete`) with `iam.teams.members` (`list`, `list_all`, `add`, `remove`), `iam.policies` (`list`, `list_all`, `create`, `get`, `update` with `if_match=`, `delete`) with `iam.policies.attachments` (`list`, `attach`, `detach`), `iam.effective_access(user_id)` and `iam.simulate(...)`. Sync and async.
- `pantech.iam.allow(...)`, `pantech.iam.deny(...)` and `pantech.iam.statement(...)`, which build typed policy statements and check the API's limits first, and `pantech.iam.MANAGED_POLICY_IDS`.
- `IamErrorCode` and `IAM_ERROR_CODES` for every access policy problem code.
- `examples/access_policies.py`.
- `iam.members.list` / `list_all`: the organization's members with their teams and policy counts.
- `client.certificates`, Certificate Manager: `list`, `list_all`, `request`, `import_`, `get`, `update`, `verify`, `reimport`, `export`, `revoke`, `delete`, and `wait(certificate_id)` until it is issued, which raises the new `CertificateFailedError`. Sync and async. `export` returns the private key in a dict whose `repr()` and `str()` show `<hidden>`.
- `CertificateErrorCode` and `CERTIFICATE_ERROR_CODES` for every certificate problem code.
- `examples/certificates.py`.
- `dns.zones.quote()`: the free zone allowance and the monthly price of each further zone.
- `domains.wait_for_order(...)` raises `PaymentRequiredError` with `payment_url`, `payment_expires_at` and `order` when an order is `awaiting_payment` (your credit does not cover it), instead of waiting silently; `wait_for_payment=True` keeps waiting while the user pays. Domain orders carry `payment_url` and `payment_expires_at`; TLD offers and search results carry `privacy_always_on`.
- `domains.orders.retry_payment(order_id)` (`POST /domain-orders/{order_id}/retry-payment`): an order waiting in `awaiting_payment` tries its payment again at once and waits another hour; it never charges twice. Sync and async. A `409` `DOMAIN_ORDER_NOT_AWAITING_PAYMENT` (in `DOMAIN_ERROR_CODES`) when the order is not waiting for a payment. `payment_url` is now set only when the bank asks the customer to confirm a saved-card payment in US dollars, so `PaymentRequiredError.payment_url` can be None.
- HTTPS load balancers: `load_balancers.create` and `update` take `protocol="https"`, `certificate_id`, `tls_policy` and `redirect_http`, and a load balancer reports `certificate_fingerprint_sha256`.

NOTES:

- The vendored spec is the current public API, with DNS, domains, the container registry, IAM, certificates and HTTPS load balancers, so `openapi/pending/` is empty again. The generators now support a request header parameter (`If-Match`), text responses and nullable or multi-status response unions.

## 0.3.0 (2026-11-06)

FEATURES:

- `KubernetesFixedNodeSize` and `fixed_node_sizes` on the Kubernetes versions list: the zones that build nodes only at fixed sizes, one entry per size. Types regenerated from the current public API spec.

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
