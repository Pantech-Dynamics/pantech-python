"""Every operation in the spec has an SDK method, and that method calls it.

The table is ``pantech._operations.OPERATIONS``. Adding an operation to
``openapi/public-api.yaml`` without a table entry fails here.
"""

from __future__ import annotations

import inspect
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import httpx
import pytest

import pantech
from pantech._operations import NO_REPLAY, NOT_IN_SDK, OPERATIONS

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from _spec import iter_operations, load_spec  # noqa: E402

SPEC_OPS: Dict[str, Tuple[str, str]] = {
    op_id: (method, path) for op_id, method, path, _op, _item in iter_operations(load_spec())
}


def resolve(root: Any, dotted: str) -> Callable[..., Any]:
    target = root
    for part in dotted.split("."):
        target = getattr(target, part)
    return target  # type: ignore[no-any-return]


def dummy_args(fn: Callable[..., Any]) -> Tuple[List[Any], Dict[str, Any]]:
    args: List[Any] = []
    kwargs: Dict[str, Any] = {}
    for name, p in inspect.signature(fn).parameters.items():
        if p.default is not inspect.Parameter.empty:
            continue
        if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD:
            args.append(f"{name}_1")
            continue
        ann = str(p.annotation)
        if ann.startswith("List"):
            kwargs[name] = []
        elif ann.startswith("Dict"):
            kwargs[name] = {}
        elif ann == "int":
            kwargs[name] = 1
        elif ann == "bool":
            kwargs[name] = True
        else:
            kwargs[name] = "x"
    return args, kwargs


def expected_path(template: str) -> str:
    return "/public/v1" + re.sub(r"{([^}]+)}", lambda m: f"{m.group(1)}_1", template)


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/events"):
        return httpx.Response(
            200, content=b"event: operation\ndata: {}\n\n", headers={"Content-Type": "text/event-stream"}
        )
    return httpx.Response(200, json={"data": [], "next_cursor": None, "status": "succeeded"})


def test_spec_has_operations() -> None:
    assert len(SPEC_OPS) >= 157


def test_every_spec_operation_is_in_the_table() -> None:
    missing = sorted(set(SPEC_OPS) - set(OPERATIONS) - set(NOT_IN_SDK))
    assert not missing, f"add these to src/pantech/_operations.py: {missing}"


def test_table_has_no_stale_operations() -> None:
    stale = sorted(set(OPERATIONS) - set(SPEC_OPS))
    assert not stale, f"no longer in the spec: {stale}"


def test_not_in_sdk_is_in_the_spec_and_not_the_table() -> None:
    assert set(NOT_IN_SDK) <= set(SPEC_OPS), sorted(set(NOT_IN_SDK) - set(SPEC_OPS))
    assert not set(NOT_IN_SDK) & set(OPERATIONS), "remove these from NOT_IN_SDK: they have methods"


def test_no_replay_names_are_real() -> None:
    assert set(NO_REPLAY) <= set(OPERATIONS)


def test_method_names_are_unique() -> None:
    names = [target for _m, _p, target in OPERATIONS.values()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("op_id", sorted(OPERATIONS))
def test_table_matches_spec_route(op_id: str) -> None:
    method, path, _target = OPERATIONS[op_id]
    assert SPEC_OPS.get(op_id) == (method, path)


@pytest.mark.parametrize("op_id", sorted(OPERATIONS))
def test_sync_method_calls_its_route(op_id: str) -> None:
    method, path, target = OPERATIONS[op_id]
    requests: List[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = pantech.Pantech(
        api_key="PAN_x",
        base_url="https://api.test/public/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(record)),
    )
    fn = resolve(client, target)
    args, kwargs = dummy_args(fn)
    result = fn(*args, **kwargs)
    if inspect.isgenerator(result):
        list(result)
    assert [(r.method, r.url.path) for r in requests] == [(method, expected_path(path))]
    if method != "GET":
        assert "idempotency-key" in requests[0].headers


@pytest.mark.parametrize("op_id", sorted(OPERATIONS))
async def test_async_method_calls_its_route(op_id: str) -> None:
    method, path, target = OPERATIONS[op_id]
    requests: List[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = pantech.AsyncPantech(
        api_key="PAN_x",
        base_url="https://api.test/public/v1",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(record)),
    )
    fn = resolve(client, target)
    args, kwargs = dummy_args(fn)
    result = fn(*args, **kwargs)
    if inspect.isawaitable(result):
        await result
    else:
        [x async for x in result]
    assert [(r.method, r.url.path) for r in requests] == [(method, expected_path(path))]


def test_sync_and_async_have_the_same_methods() -> None:
    sync = pantech.Pantech(api_key="PAN_x")
    asyn = pantech.AsyncPantech(api_key="PAN_x")
    for _m, _p, target in OPERATIONS.values():
        a, b = resolve(sync, target), resolve(asyn, target)
        assert list(inspect.signature(a).parameters) == list(inspect.signature(b).parameters), target


@pytest.mark.parametrize("script", ["generate_types.py", "generate_resources.py"])
def test_generated_code_is_up_to_date(script: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
