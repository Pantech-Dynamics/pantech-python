"""Writes the resource classes for Pantech and AsyncPantech.

    .venv/bin/python scripts/generate_resources.py

Method names come from ``src/pantech/_operations.py`` (the hand-kept table);
arguments, types and docs come from ``openapi/public-api.yaml``. Path
parameters are positional, everything else keyword-only. Writes
``src/pantech/resources/_sync.py`` and ``_async.py``. Commit the output.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from _codegen import (
    OperationSpec,
    Param,
    TypeRegistry,
    build_operations,
    comment_lines,
    docstring_text,
    ruff_format,
)
from _spec import ROOT, load_spec

OUT_DIR = ROOT / "src" / "pantech" / "resources"

# Families with hand-written helpers (src/pantech/_resource.py) as their base.
BASES = {
    "operations": "OperationsWaiter",
    "instances": "InstanceOrderWaiter",
    "databases": "DatabaseOrderWaiter",
}

FAMILY_DOCS = {
    "me": "The API key making the call.",
    "billing": "Your credit, credit purchases and receipts.",
    "billing.receipts": "Receipts for payments.",
    "usage": "What has been used, and what it cost.",
    "catalog": "What you can buy, and what it costs: regions, plans, images, disk offerings, versions, engines.",
    "instances": "Virtual machines (VPS): create, power, change, delete.",
    "instances.ssh_access": "Short-lived SSH access grants to an instance.",
    "instances.orders": "How a new instance is paid for and provisioned.",
    "networks": "VPC networks.",
    "networks.subnets": "Subnets of a VPC network.",
    "networks.firewall_rules": "Firewall rules of a subnet.",
    "public_ips": "Public addresses for VPC instances.",
    "public_ips.port_forwarding_rules": "Port forwarding from a public IP to instances.",
    "load_balancers": "Spread traffic on one public port across several instances in a private network.",
    "security_groups": "Reusable firewalls for standard instances.",
    "volumes": "Data disks.",
    "snapshots": "Point-in-time copies of root disks and volumes.",
    "databases": "Managed PostgreSQL, MySQL and MariaDB databases.",
    "databases.snapshots": "Snapshots of a managed database.",
    "databases.orders": "How a new database is paid for and provisioned.",
    "kubernetes": "Managed Kubernetes clusters.",
    "kubernetes.node_pools": "Node pools of a Kubernetes cluster.",
    "kubernetes.addons": "Add-ons of a Kubernetes cluster.",
    "ssh_keys": "Keys installed on new instances.",
    "webhooks": "Events sent to your own URL when something changes.",
    "webhooks.deliveries": "Deliveries of a webhook's events.",
    "operations": "Follow asynchronous changes.",
}

RESERVED = {
    "self",
    "idempotency_key",
    "extra_headers",
    "extra_query",
    "extra_body",
    "timeout",
    "cast",
    "path_param",
    "merge_params",
}


def load_table() -> Tuple[Dict[str, Tuple[str, str, str]], frozenset]:  # type: ignore[type-arg]
    path = ROOT / "src" / "pantech" / "_operations.py"
    spec = importlib.util.spec_from_file_location("_pantech_operations", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.OPERATIONS, mod.NO_REPLAY


@dataclass
class Node:
    path: Tuple[str, ...]
    children: Dict[str, Node] = field(default_factory=dict)
    methods: List[Tuple[str, OperationSpec]] = field(default_factory=list)

    @property
    def dotted(self) -> str:
        return ".".join(self.path)

    def class_name(self, prefix: str) -> str:
        return prefix + "".join(p.title().replace("_", "") for p in self.path) + "Resource"


def build_tree(ops: Dict[str, OperationSpec], table: Dict[str, Tuple[str, str, str]]) -> Node:
    root = Node(())
    missing = sorted(set(ops) - set(table))
    if missing:
        raise SystemExit(f"operations missing from src/pantech/_operations.py: {missing}")
    for op_id, (method, path, target) in table.items():
        if op_id not in ops:
            raise SystemExit(f"{op_id} is in the table but not in the spec")
        op = ops[op_id]
        if (op.method, op.path) != (method, path):
            raise SystemExit(f"{op_id}: table says {method} {path}, spec says {op.method} {op.path}")
        *parents, name = target.split(".")
        node = root
        for i, part in enumerate(parents):
            node = node.children.setdefault(part, Node(tuple(parents[: i + 1])))
        node.methods.append((name, op))
    return root


def walk(node: Node) -> List[Node]:
    out: List[Node] = []
    for child in node.children.values():
        out.extend(walk(child))
    if node.path:
        out.append(node)
    return out


TYPE_NAME = re.compile(r"\b[A-Z][A-Za-z0-9]*\b")
TYPING = {"Any", "Dict", "List", "Literal", "Optional", "Union"}


class Renderer:
    def __init__(self, reg: TypeRegistry, no_replay: frozenset, is_async: bool) -> None:  # type: ignore[type-arg]
        self.reg = reg
        self.no_replay = no_replay
        self.is_async = is_async
        self.prefix = "Async" if is_async else ""
        self.used_types: Set[str] = set()
        self.used_typing: Set[str] = {"Optional", "Union"}
        self.plain_base = "AsyncResource" if is_async else "SyncResource"

    def note(self, expr: str) -> str:
        for name in TYPE_NAME.findall(expr):
            if name in TYPING:
                self.used_typing.add(name)
            elif name in self.reg.defs:
                self.used_types.add(name)
        return expr

    # -- one method ---------------------------------------------------------

    def method(self, name: str, op: OperationSpec) -> List[str]:
        params = self._check_names(op)
        lines: List[str] = []
        lines += self._method(name, op, params, paginate=False)
        if op.page_item is not None:
            all_name = name.replace("list", "list_all", 1) if name.startswith("list") else name + "_all"
            lines += self._method(all_name, op, params, paginate=True)
        return lines

    def _check_names(self, op: OperationSpec) -> List[Param]:
        seen: Set[str] = set()
        for p in op.path_params + op.query_params + op.body_params:
            if p.name in RESERVED or p.name in seen:
                raise SystemExit(f"{op.operation_id}: argument {p.name!r} collides; rename it in the generator")
            seen.add(p.name)
        return op.path_params + op.query_params + op.body_params

    def _signature(self, op: OperationSpec, paginate: bool) -> List[str]:
        sig = ["        self,"]
        for p in op.path_params:
            sig.append(f"        {p.name}: str,")
        kw: List[Param] = [q for q in op.query_params if not (paginate and q.wire == "cursor")]
        kw += [] if paginate else op.body_params
        sig.append("        *,")
        for p in [p for p in kw if p.required]:
            sig.append(f"        {p.name}: {self.note(p.type)},")
        for p in [p for p in kw if not p.required]:
            sig.append(f"        {p.name}: Union[{self.note(p.type)}, NotGiven] = NOT_GIVEN,")
        if op.method != "GET" and not paginate:
            sig.append("        idempotency_key: Optional[str] = None,")
        sig.append("        extra_headers: Optional[Headers] = None,")
        if op.returns != "stream":
            sig.append("        extra_query: Optional[Query] = None,")
        if op.has_body and not paginate:
            sig.append("        extra_body: Optional[Body] = None,")
        sig.append("        timeout: Union[Timeout, NotGiven] = NOT_GIVEN,")
        return sig

    def _return_type(self, op: OperationSpec, paginate: bool) -> str:
        if paginate:
            it = "AsyncIterator" if self.is_async else "Iterator"
            return f"{it}[{self.note(op.page_item or 'Any')}]"
        if op.returns == "stream":
            return "AsyncIterator[ServerSentEvent]" if self.is_async else "Iterator[ServerSentEvent]"
        if op.returns in ("None", "bytes"):
            return op.returns
        return self.note(op.returns)

    def _doc(self, op: OperationSpec, paginate: bool) -> List[str]:
        summary = op.summary.rstrip(".")
        if paginate:
            summary = f"{summary}, following ``next_cursor`` through every page"
        doc = [f'        """{docstring_text(summary)}.', "", f"        ``{op.method} {op.path}``"]
        documented = [p for p in op.path_params + op.query_params + op.body_params if p.doc]
        if paginate:
            documented = [p for p in documented if p.wire != "cursor" and p not in op.body_params]
        if op.operation_id in self.no_replay and not paginate:
            doc += ["", "        Not replayed by the API, so it is sent once and not retried after an error."]
        if documented:
            doc += ["", "        Args:"]
            for p in documented:
                text = docstring_text(f"{p.name}: {p.doc}")
                wrapped = comment_lines(text, "", 84)
                doc.append("          " + wrapped[0][2:])
                doc += ["              " + w[2:] for w in wrapped[1:]]
        doc.append('        """')
        return doc

    def _path_expr(self, op: OperationSpec) -> str:
        if not op.path_params:
            return f'"{op.path}"'
        expr = op.path
        for p in op.path_params:
            expr = expr.replace("{" + p.wire + "}", "{path_param(" + p.name + ")}")
        return 'f"' + expr + '"'

    def _dict(self, params: List[Param]) -> str:
        if not params:
            return "{}"
        return "{" + ", ".join(f'"{p.wire}": {p.name}' for p in params) + "}"

    def _method(self, name: str, op: OperationSpec, params: List[Param], paginate: bool) -> List[str]:
        ret = self._return_type(op, paginate)
        is_coroutine = self.is_async and not paginate and op.returns != "stream"
        lines = [""]
        lines.append(f"    {'async def' if is_coroutine else 'def'} {name}(")
        lines += self._signature(op, paginate)
        lines.append(f"    ) -> {ret}:")
        lines += self._doc(op, paginate)
        path = self._path_expr(op)
        query_params = [q for q in op.query_params if not (paginate and q.wire == "cursor")]
        query = f"merge_params({self._dict(query_params)}, extra_query)"
        aw = "await " if is_coroutine else ""
        if paginate:
            lines.append(
                f"        return self._client._paginate({path}, query={query}, "
                "extra_headers=extra_headers, timeout=timeout)"
            )
            return lines
        if op.returns == "stream":
            lines.append(
                f"        return self._client._stream_events({path}, extra_headers=extra_headers, timeout=timeout)"
            )
            return lines
        call = [f"{aw}self._client.request(", f'    "{op.method}",', f"    {path},", f"    query={query},"]
        if op.has_body:
            call.append(f"    body=merge_params({self._dict(op.body_params)}, extra_body),")
        if op.method != "GET":
            call.append("    idempotency_key=idempotency_key,")
        if op.operation_id in self.no_replay:
            call.append("    no_replay=True,")
        call.append("    extra_headers=extra_headers,")
        call.append("    timeout=timeout,")
        if op.returns == "bytes":
            call.append('    parse_as="bytes",')
        call.append(")")
        if op.returns == "None":
            lines.append("        " + call[0])
            lines += ["        " + c for c in call[1:]]
            lines.append("        return None")
        else:
            lines.append(f'        return cast("{ret}", {call[0]}')
            lines += ["            " + c for c in call[1:-1]]
            lines.append("            ),")
            lines.append("        )")
        return lines

    # -- one class ----------------------------------------------------------

    def klass(self, node: Node) -> List[str]:
        base = BASES.get(node.dotted)
        base_name = (self.prefix + base) if base else self.plain_base
        client_type = "AsyncAPIClient" if self.is_async else "SyncAPIClient"
        lines = ["", "", f"class {node.class_name(self.prefix)}({base_name}):"]
        lines.append(f'    """{FAMILY_DOCS.get(node.dotted, node.dotted)}"""')
        if node.children:
            lines.append("")
            for attr, child in node.children.items():
                lines.append(f"    {attr}: {child.class_name(self.prefix)}")
            lines.append("")
            lines.append(f"    def __init__(self, client: {client_type}) -> None:")
            lines.append("        super().__init__(client)")
            for attr, child in node.children.items():
                lines.append(f"        self.{attr} = {child.class_name(self.prefix)}(client)")
        for name, op in node.methods:
            lines += self.method(name, op)
        return lines

    def root(self, root: Node) -> List[str]:
        client_type = "AsyncAPIClient" if self.is_async else "SyncAPIClient"
        lines = ["", "", f"class {self.prefix}Resources:"]
        lines += ['    """Every resource family, as attributes of the client."""', ""]
        for attr, child in root.children.items():
            lines.append(f"    {attr}: {child.class_name(self.prefix)}")
        lines += ["", f"    def _init_resources(self, client: {client_type}) -> None:"]
        for attr, child in root.children.items():
            lines.append(f"        self.{attr} = {child.class_name(self.prefix)}(client)")
        return lines

    def module(self, root: Node) -> str:
        body: List[str] = []
        for node in walk(root):
            body += self.klass(node)
        body += self.root(root)
        client_type = "AsyncAPIClient" if self.is_async else "SyncAPIClient"
        iter_name = "AsyncIterator" if self.is_async else "Iterator"
        typing_names = ", ".join(sorted(self.used_typing | {iter_name, "TYPE_CHECKING", "cast"}))
        header = [
            "# Generated by scripts/generate_resources.py from src/pantech/_operations.py and",
            "# openapi/public-api.yaml. Do not edit.",
            f'"""{"Asynchronous" if self.is_async else "Synchronous"} resources: one class per family, '
            'one method per operation."""',
            "",
            "from __future__ import annotations",
            "",
            f"from typing import {typing_names}",
            "",
            "from .._resource import (",
        ]
        res_names = sorted({self.prefix + b for b in BASES.values()} | {self.plain_base, "merge_params", "path_param"})
        header += [f"    {n}," for n in res_names]
        header += [
            ")",
            "from .._streaming import ServerSentEvent",
            "from .._types import NOT_GIVEN, Body, Headers, NotGiven, Query, Timeout",
            "from ..types._generated import (",
        ]
        header += [f"    {n}," for n in sorted(self.used_types)]
        header += [
            ")",
            "",
            "if TYPE_CHECKING:",
            f"    from .._base_client import {client_type}",
        ]
        return "\n".join(header + body) + "\n"


def render(is_async: bool) -> str:
    reg = TypeRegistry(load_spec())
    reg.build_components()
    ops = build_operations(reg)
    table, no_replay = load_table()
    root = build_tree(ops, table)
    out = OUT_DIR / ("_async.py" if is_async else "_sync.py")
    return ruff_format(Renderer(reg, no_replay, is_async).module(root), str(out))


def main() -> int:
    status = 0
    for is_async, fname in ((False, "_sync.py"), (True, "_async.py")):
        out = OUT_DIR / fname
        text = render(is_async)
        if "--check" in sys.argv:
            if not out.exists() or out.read_text(encoding="utf-8") != text:
                print(f"{out.relative_to(ROOT)} is out of date: run scripts/generate_resources.py", file=sys.stderr)
                status = 1
            continue
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")
    return status


if __name__ == "__main__":
    sys.exit(main())
