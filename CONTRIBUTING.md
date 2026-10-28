# Contributing to pantech-python

Thanks for helping improve the Python SDK for the Pantech Dynamics public API. Bug reports, fixes
and improvements are all welcome. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first, and
report security issues privately as described in [SECURITY.md](SECURITY.md), never in a public
issue.

## Development setup

You need Python 3.10 or newer.

```sh
git clone https://github.com/Pantech-Dynamics/pantech-python
cd pantech-python
python3 -m venv .venv
.venv/bin/pip install -e . pytest pytest-asyncio mypy ruff pyyaml types-PyYAML build twine
```

## Checks

Run these before opening a pull request; CI runs the same ones on Python 3.10 to 3.14.

```sh
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy                 # --strict over src/pantech
.venv/bin/pytest -q
.venv/bin/python -m build && .venv/bin/twine check --strict dist/*
```

## Layout

```
openapi/public-api.yaml        vendored copy of the public API spec
scripts/sync_spec.py           refreshes the vendored spec
scripts/_spec.py               loads the spec for the generators and tests
scripts/_codegen.py            schema -> TypedDict, operation -> method (shared)
scripts/generate_types.py      writes src/pantech/types/_generated.py
scripts/generate_resources.py  writes src/pantech/resources/_sync.py and _async.py
src/pantech/_operations.py     operationId -> (method, path, SDK method name), NO_REPLAY
src/pantech/_base_client.py    HTTP core: auth, Idempotency-Key, retries, pagination, SSE
src/pantech/_exceptions.py     error hierarchy and problem+json parsing
src/pantech/_client.py         Pantech and AsyncPantech
tests/                         tests; test_spec_coverage.py checks every operation
examples/                      runnable scripts
```

## Keeping in step with the API spec

The SDK is generated from the published OpenAPI spec at
<https://docs.pantechdynamics.com/openapi/public-api.yaml>. A weekly workflow opens a pull request
when it changes.

```sh
.venv/bin/python scripts/sync_spec.py                   # the published spec
.venv/bin/python scripts/sync_spec.py path/or/url.yaml  # or another copy
.venv/bin/python scripts/generate_types.py
.venv/bin/python scripts/generate_resources.py
.venv/bin/pytest -q tests/test_spec_coverage.py
```

A new operation needs a method name in `src/pantech/_operations.py` (idiomatic snake_case, nested
where the API nests, such as `networks.subnets.list`); the coverage test names any that are
missing. An operation the SDK deliberately leaves out goes in `NOT_IN_SDK` there instead, with the
reason; the generators skip it and the types only it uses. Commit the generated files, and never
edit them by hand: change the generator instead.

## Guidelines

- The only runtime dependency is `httpx`. PyYAML is for the scripts and tests only.
- Sync and async clients share one core: behaviour belongs in `BaseClient`.
- Every write goes through `request()`, which sends the Idempotency-Key and reuses it on retry. A
  route the API does not replay goes in `NO_REPLAY`.
- Never log or print the API key, and never put it in a URL or a `repr`.
- Stay compatible with Python 3.10 (`from __future__ import annotations`, `Optional`, `List`).
- Renaming a public method is a breaking change.
- Add tests for every change in behaviour.
- A change users will notice gets a line under `## Unreleased` in `CHANGELOG.md`, in the same pull
  request.

## Releasing

Maintainers release by renaming `## Unreleased` in `CHANGELOG.md` to `## X.Y.Z (YYYY-MM-DD)` and
bumping `version` in `pyproject.toml` and `src/pantech/_version.py` to match, in the same change.
On push to `main`, the release workflow tags `vX.Y.Z` if it is new, publishes the package to
PyPI with Trusted Publishing, and creates a GitHub release whose notes are that section.
