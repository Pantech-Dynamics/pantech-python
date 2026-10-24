# Pantech Dynamics Python SDK

[![CI](https://github.com/Pantech-Dynamics/pantech-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Pantech-Dynamics/pantech-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pantech.svg)](https://pypi.org/project/pantech/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The official Python library for the [Pantech Dynamics public API](https://docs.pantechdynamics.com/api):
instances, VPC networks, firewalls, public IPs, load balancers, volumes, snapshots, managed databases,
managed Kubernetes, SSH keys, webhooks, billing and usage.

- Sync (`Pantech`) and asyncio (`AsyncPantech`) clients with the same methods
- Every operation in the public API, with typed keyword arguments and TypedDict results
- Automatic `Idempotency-Key`s, safe retries, cursor pagination, operation and order waiting
- Webhook signature verification
- One dependency: `httpx`. Python 3.10+.

Full documentation: https://docs.pantechdynamics.com/sdks/python

## Install

```sh
pip install pantech
```

## Quickstart

Create an API key in the console under **Organization › API keys**, then:

```sh
export PANTECH_API_KEY=PAN_...
```

```python
import pantech

with pantech.Pantech() as client:
    me = client.me.get()
    print("Organization", me["organization_id"])

    for instance in client.instances.list_all():
        print(instance["id"], instance["name"], instance["observed_state"])
```

### Create an instance and wait for it

```python
order = client.instances.create(
    name="web-1",
    plan_slug="starter",
    image_slug="ubuntu-24-04",
    ssh_key_id="sshk_...",
)
client.instances.wait_for_order(order["order_id"])  # raises OrderFailedError if it fails
instance = client.instances.get(order["instance_id"])
print(instance["public_ipv4"])
```

Most changes return `202 Accepted` with an operation. Wait for it:

```python
accepted = client.instances.stop("vm_...")
client.operations.wait(accepted["operation_id"], timeout=300)  # raises OperationFailedError on failure
```

### Async

```python
import asyncio
import pantech


async def main() -> None:
    async with pantech.AsyncPantech() as client:
        async for volume in client.volumes.list_all():
            print(volume["name"])


asyncio.run(main())
```

### Resources

Families are attributes of the client and nest where the API does:

```python
client.networks.create(name="prod", cidr="10.10.0.0/16")
client.networks.subnets.list("net_...")
client.networks.firewall_rules.create("snet_...", ...)
client.public_ips.port_forwarding_rules.list("pip_...")
client.databases.snapshots.create("db_...", name="before-migration")
client.kubernetes.node_pools.scale("k8s_...", "k8spool_...", workers=3)
client.catalog.list_plans(placement="vpc")
client.billing.receipts.get_pdf("rcpt_...")  # bytes
```

Arguments are keyword-only, except the ids in the path. Optional arguments you leave out are not
sent; passing `None` sends JSON `null`. Results are plain dicts typed with the TypedDicts in
`pantech.types`. `client.request("GET", "/me")` calls any route directly.

## Configuration

| Option | Environment | Default |
|---|---|---|
| `api_key` | `PANTECH_API_KEY` | (required) |
| `base_url` | `PANTECH_API_URL` | `https://api.pantechdynamics.com/public/v1` |
| `timeout` | | 60 s per attempt (10 s to connect); a number or an `httpx.Timeout` |
| `max_retries` | | 3 |
| `default_headers`, `user_agent`, `http_client` | | |

Every method also takes `timeout=`, `extra_headers=`, `extra_query=` and (with a body)
`extra_body=`. Writes take `idempotency_key=`.

## Retries and idempotency

Every POST, PUT, PATCH and DELETE gets a fresh UUIDv4 `Idempotency-Key`, and retries resend the
same key, so the API returns the first result instead of repeating the change. Connection errors,
timeouts, `429`, `500`, `502`, `503` and `504` are retried up to `max_retries` times with jittered
exponential backoff, or after the `Retry-After` the API sends.

A few writes are not replayed by the API, so the SDK sends them once and retries only a `429`:
creating and deleting SSH keys, opening a console, issuing a volume key credential, revoking the
calling key (`client.me.revoke()`), and the webhook test, delete, secret rotation and redelivery calls.

## Errors

```python
try:
    client.networks.subnets.get("snet_...")
except pantech.NotFoundError as err:
    print(err.detail, err.request_id)
except pantech.ValidationError as err:
    for field in err.errors:
        print(field["field"], field["code"], field["message"])
except pantech.APIError as err:
    print(err.status, err.code, err.detail)
```

`APIError` carries `status`, `code` (stable: branch on it), `title`, `detail` (safe to show),
`request_id` (quote it to support) and `errors`. Subclasses: `BadRequestError` (400),
`AuthenticationError` (401), `PaymentRequiredError` (402), `PermissionDeniedError` (403),
`NotFoundError` (404), `ConflictError` (409), `ValidationError` (422), `RateLimitError` (429),
`InternalServerError` (5xx). No answer at all is `APIConnectionError` (or `APITimeoutError`).
Waiting raises `OperationFailedError`, `OrderFailedError` or `WaitTimeoutError`. All of them are
`PantechError`.

## Webhooks

```python
import pantech


def handle(headers, raw_body: bytes) -> None:
    pantech.verify_webhook(
        secret="whsec_...",
        header=headers.get("Pantech-Signature"),
        body=raw_body,  # the raw bytes, before JSON parsing
        tolerance=300,  # seconds; the default
    )  # raises WebhookVerificationError
```

The comparison is constant-time, and any of several `v1` signatures may match (there are two for
24 hours after a secret rotation). See `examples/webhook_server.py`.

## Examples

- [`examples/create_instance.py`](examples/create_instance.py): order an instance and wait for it
- [`examples/async_list.py`](examples/async_list.py): concurrent listing with `AsyncPantech`
- [`examples/webhook_server.py`](examples/webhook_server.py): a verified webhook receiver on `http.server`

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e . pytest pytest-asyncio mypy ruff pyyaml types-PyYAML
.venv/bin/python scripts/sync_spec.py   # download the published spec into openapi/public-api.yaml
.venv/bin/python scripts/generate_types.py && .venv/bin/python scripts/generate_resources.py
.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q
```

The SDK is generated from the published [OpenAPI spec](https://docs.pantechdynamics.com/openapi/public-api.yaml).
See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow and how releases are made. Report security
issues as described in [SECURITY.md](SECURITY.md).

## License

MIT. See [LICENSE](LICENSE).
