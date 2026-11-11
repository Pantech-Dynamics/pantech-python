# Pantech Dynamics Python SDK

[![CI](https://github.com/Pantech-Dynamics/pantech-python/actions/workflows/ci.yml/badge.svg)](https://github.com/Pantech-Dynamics/pantech-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pantech.svg)](https://pypi.org/project/pantech/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

The official Python library for the [Pantech Dynamics public API](https://docs.pantechdynamics.com/api):
instances, VPC networks, firewalls, public IPs, load balancers, volumes, snapshots, managed databases,
managed Kubernetes, SSH keys, webhooks, billing, usage, and moving from another cloud.

- Sync (`Pantech`) and asyncio (`AsyncPantech`) clients with the same methods
- Every operation in the public API, with typed keyword arguments and TypedDict results (agent
  sessions, which answer only AI apps connected through Pantech's MCP server, are not covered yet)
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

### Move from another cloud

`client.migrate` connects an AWS account through a read-only role that only Pantech can assume (no
access keys are shared), scans what runs there, and plans the move with a price comparison and a
Terraform export. Nothing is created on Pantech until you apply the Terraform.

```python
conn = client.migrate.connections.create(name="Production AWS")
print(conn["setup"]["quick_create_url"])  # create the stack in AWS, then send its RoleArn output
client.migrate.connections.update(conn["id"], role_arn="arn:aws:iam::...:role/...")
client.migrate.connections.wait(conn["id"])  # raises CloudFailedError if the role cannot be assumed

scan = client.migrate.scans.start(conn["id"])
scan = client.migrate.scans.wait(scan["id"])

plan = client.migrate.migrations.create(scan_id=scan["id"], name="Move to Pantech")
print(plan["estimate"]["pantech_monthly_minor"], plan["estimate"]["source_monthly_minor"])
for f in client.migrate.migrations.export_terraform(plan["id"])["files"]:
    print(f["name"])  # main.tf, variables.tf
```

`client.migrate.migrations.update_item(plan_id, key=..., excluded=True)` leaves an item out, or
changes its plan, size, address range or role, before you export. See
`examples/migrate_from_aws.py`.

### Certificates

`client.certificates` issues TLS certificates through a publicly trusted CA and renews them by
itself, or holds certificates you import, for Pantech load balancers and your own servers.

```python
cert = client.certificates.request(names=["example.com", "*.example.com"], exportable=True)
for v in cert["validations"]:
    if v["method"] == "cname":  # names outside your Pantech DNS zones: add this CNAME once
        print(v["cname_name"], "CNAME", v["cname_target"])
cert = client.certificates.wait(cert["id"])  # CertificateFailedError if it cannot be issued

exported = client.certificates.export(cert["id"])  # needs the delete scope; owners are emailed
write_key_file(exported["private_key_pem"])  # repr(exported) and logs show <hidden>
```

`client.certificates.import_(certificate_pem=..., private_key_pem=...)` imports one (`import` is a
Python keyword), `reimport` replaces it before it expires, `verify` re-checks CNAMEs now, and
`revoke` and `delete` retire it. The SDK never logs request or response bodies, so an imported key
is not logged either. See `examples/certificates.py`.

An appliance load balancer can end TLS with one: `client.load_balancers.create(...,
protocol="https", certificate_id=cert["id"], tls_policy="modern", redirect_http=True)`; renewals
reach it by themselves. VPC native load balancers pass TLS through as `tcp`, and a certificate in
use cannot be revoked or deleted (`CERTIFICATE_IN_USE`).

### Teams and access policies

`client.iam` controls who in your organization may do what. Policies are statements that allow or
deny actions (`instances:Stop`, `dns:*`, `*:Read`) on resources (`*`, an id, or `name:staging-*`),
optionally only from some addresses or with MFA; attach them to members or teams. `pantech.iam`
builds statements and checks the API's limits before the call.

```python
from pantech import iam

team = client.iam.teams.create(name="Platform")
pol = client.iam.policies.create(
    name="staging-operators",
    statements=[
        iam.allow(
            ["instances:Read", "instances:Start", "instances:Stop"], ["name:staging-*"], source_ip=["102.89.0.0/16"]
        ),
        iam.deny(["*:Delete"]),
    ],
)
client.iam.policies.attachments.attach(pol["id"], principal_type="team", principal_id=team["id"])
client.iam.teams.members.add(team["id"], "usr_...")

sim = client.iam.simulate(user_id="usr_...", action="instances:Delete", resource="vm_...")
print(sim["allowed"], sim["decision"])  # False explicit_deny
```

`client.iam.policies.update(id, ..., if_match=pol["version"])` refuses a lost update.
`client.iam.actions.list()` is the action catalogue, `client.iam.effective_access(user_id)` what
applies to a member, `client.iam.settings` the organization's `member_baseline`, and
`iam.MANAGED_POLICY_IDS` Pantech's ready-made policies. See `examples/access_policies.py`.

### Container registry

`client.registry` manages your private registry at `registry.pantechdynamics.com`: one namespace per
organization, repositories (private by default), their tags, and registry-only tokens for CI and
clusters. Push and pull with `docker`, logged in with an API key or a registry token.

```python
client.registry.namespace.set(name="acme")  # once; images are registry.pantechdynamics.com/acme/...
repo = client.registry.repositories.create(
    name="api/server", immutable_tags=True, retention={"keep_last": 50, "keep_pattern": "v*"}
)
for tag in client.registry.tags.list_all(repo["id"]):
    print(tag["name"], tag["digest"], tag["size_bytes"])

token = client.registry.tokens.create(name="github-actions", permission="push", repositories=["api/server"])
save_to_ci_secrets(token["secret"])  # shown only now (None on a replayed create); repr shows <hidden>
```

`docker login registry.pantechdynamics.com -u pantech -p <secret>` then works for that repository.
`registry.tokens.delete(token_id)` revokes one. See `examples/container_registry.py`.

### DNS and domains

`client.dns` hosts zones on Pantech DNS, Pantech's own name servers, and `client.domains` buys,
transfers in and renews domains, paid from your credit. Each zone gets its own two name servers to
set at your registrar. Changes go live in the background: a record set is `pending` until it
answers, usually within a minute, and records added before the zone is `active` (delegated) stay
`pending` until it is. The first 5 zones are free; `client.dns.zones.quote()` gives the price of
the rest in your currency.

```python
zone = client.dns.zones.create(name="example.com")
zone = client.dns.zones.wait(zone["id"])  # until it has its name servers
print(zone["name_servers"])  # set these at your registrar

rec = client.dns.records.create(zone["id"], name="www", type="A", values=["203.0.113.10"], ttl=300)
client.dns.records.wait(zone["id"], rec["id"])  # raises DNSFailedError if the change fails

# Change it only if nobody else did since you read it (412 PreconditionFailedError otherwise).
client.dns.records.update(zone["id"], rec["id"], if_match=rec["version"], values=["203.0.113.11"])

client.dns.records.batch(
    zone["id"],
    changes=[
        {"action": "create", "record": {"name": "@", "type": "MX", "values": ["10 mail.example.com"]}},
        {"action": "delete", "record_id": "dnsr_..."},
    ],
)
print(client.dns.zones.export_zone_file(zone["id"]))  # BIND zone file, as text

found = client.domains.search(query="example")
result = client.domains.register(name="example.com", years=1, contact={...}, accept_terms=True)
try:
    client.domains.wait_for_order(result["order"]["id"])  # raises OrderFailedError (amount refunded)
except pantech.PaymentRequiredError as err:
    # Your credit does not cover it: the order waits for a payment until err.payment_expires_at.
    # In US dollars your saved card is charged the difference; in naira, add credit.
    if err.payment_url:  # only when the bank asks to confirm the payment
        send_user_to(err.payment_url)
    client.domains.wait_for_order(result["order"]["id"], wait_for_payment=True)
    # Or, after saving a new card or adding credit: client.domains.orders.retry_payment(result["order"]["id"])
```

Prices are before VAT. A TLD whose offer has `privacy_always_on: true` (the `.ng` family) has
privacy protection that cannot be turned off: asking for `privacy=False` is a `422` naming field
`privacy` with code `PRIVACY_ALWAYS_ON`. `.ng` contacts need `state` and `postal_code`, and
`name.ng` registrants must be people (`type: "person"`).

`client.dns.zones.import_zone_file(zone_id, zone_file=..., replace=False)` loads a BIND file.
`client.domains` also has `list_tlds`, `check_transfer`, `transfer`, `update` (auto-renew, transfer
lock, privacy), `set_name_servers`, `get_contact`/`update_contact`, `renew`,
`request_auth_code`/`get_auth_code` and `orders` (`list`, `get`, `retry_payment`). The registrant contact is personal data: the SDK
never logs request or response bodies. See `examples/dns_and_domains.py`.

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
`NotFoundError` (404), `ConflictError` (409), `PreconditionFailedError` (412), `ValidationError`
(422), `RateLimitError` (429), `InternalServerError` (5xx). No answer at all is
`APIConnectionError` (or `APITimeoutError`). Waiting raises `OperationFailedError`,
`OrderFailedError`, `CloudFailedError`, `DNSFailedError`, `CertificateFailedError` or
`WaitTimeoutError`. All of them
are `PantechError`.

DNS and domain codes are typed: `pantech.DNSErrorCode` and `pantech.DomainErrorCode` are `Literal`s
of every code those endpoints answer with (`DNS_RECORD_EXISTS`, `VERSION_CONFLICT`,
`DOMAIN_NOT_AVAILABLE`…), and `pantech.DNS_ERROR_CODES` / `pantech.DOMAIN_ERROR_CODES` hold them
as sets; `pantech.RegistryErrorCode` and `pantech.REGISTRY_ERROR_CODES` do the same for the
container registry (`REGISTRY_NAMESPACE_NOT_SET`, `TAG_IMMUTABLE`, `REPOSITORY_LIMIT_REACHED`…), and
`pantech.IamErrorCode` / `pantech.IAM_ERROR_CODES` for access policies (`ACCESS_DENIED`,
`INVALID_POLICY`, `IAM_ADMIN_TARGET`…), and `pantech.CertificateErrorCode` /
`pantech.CERTIFICATE_ERROR_CODES` for certificates (`CERTIFICATE_IN_USE`,
`CERTIFICATE_NOT_EXPORTABLE`…).

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
- [`examples/migrate_from_aws.py`](examples/migrate_from_aws.py): connect an AWS account, scan it, plan the move
  and write the Terraform
- [`examples/certificates.py`](examples/certificates.py): request a certificate, print any CNAMEs, wait for it
- [`examples/access_policies.py`](examples/access_policies.py): a team with a staging-only policy, checked with the
  simulator
- [`examples/container_registry.py`](examples/container_registry.py): a namespace, a repository with retention,
  and a push token for CI
- [`examples/dns_and_domains.py`](examples/dns_and_domains.py): host a zone, add records and wait for them, find a
  domain

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
