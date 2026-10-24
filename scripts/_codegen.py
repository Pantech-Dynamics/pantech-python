"""Shared code generation: OpenAPI schemas to TypedDicts, and operations to method specs.

``generate_types.py`` writes the TypedDicts and ``generate_resources.py`` the
resource classes. Both build the same ``TypeRegistry``, so an inline schema
gets the same name in both files.
"""

from __future__ import annotations

import json
import keyword
import re
import subprocess
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from _spec import ROOT, iter_operations

TYPING_NAMES = {"Any", "Dict", "List", "Literal", "Optional", "TypedDict", "Union"}


def pascal(name: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", name)
    out = "".join(p[:1].upper() + p[1:] for p in parts if p)
    return out or "X"


def snake(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower().strip("_")
    if keyword.iskeyword(s) or not s.isidentifier():
        s += "_"
    return s


def first_sentence(text: Optional[str]) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    # Sentence ends: a stop followed by a space and a capital, or the end. Not
    # "e.g." or "i.e.". A very short first sentence ("Optional.") takes the next.
    ends = [
        m.end(1)
        for m in re.finditer(r"([.!?])(?=\s+[A-Z`(]|$)", text)
        if not re.search(r"\b(e\.g|i\.e|etc|vs)\.$", text[: m.end(1)])
    ]
    if not ends:
        return text.strip()
    cut = ends[0]
    if cut < 20 and len(ends) > 1:
        cut = ends[1]
    return text[:cut].strip()


def ruff_format(text: str, filename: str) -> str:
    """Formats generated code with the project's ruff settings, so output is stable."""
    for args in (["check", "--select", "I", "--fix", "--quiet", "--exit-zero"], ["format"]):
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", *args, "--stdin-filename", filename, "-"],
            input=text,
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(f"ruff {args[0]} failed on {filename}:\n{proc.stderr}")
        text = proc.stdout
    return text


def docstring_text(text: str) -> str:
    """Escapes text for a plain triple-quoted docstring."""
    return text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')


def comment_lines(text: str, indent: str, width: int = 96) -> List[str]:
    if not text:
        return []
    # The spec writes console menu paths with U+203A; comments use ">".
    text = text.replace("\u203a", ">")
    return [indent + "# " + line for line in textwrap.wrap(text, width - len(indent) - 2)]


@dataclass
class TypedDictDef:
    name: str
    bases: List[str]
    fields: List[Tuple[str, str, bool, str]]  # (name, type, required, doc)
    doc: str = ""


@dataclass
class TypeRegistry:
    spec: Dict[str, Any]
    defs: Dict[str, TypedDictDef] = field(default_factory=dict)
    order: List[str] = field(default_factory=list)

    @property
    def schemas(self) -> Dict[str, Any]:
        return self.spec["components"]["schemas"]  # type: ignore[no-any-return]

    def resolve(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        while "$ref" in schema:
            schema = self.schemas[schema["$ref"].split("/")[-1]]
        return schema

    # -- type expressions ---------------------------------------------------

    def py_type(self, schema: Optional[Dict[str, Any]], ctx: str) -> str:
        if not schema:
            return "Any"
        if "$ref" in schema:
            return schema["$ref"].split("/")[-1]
        if "allOf" in schema:
            parts = schema["allOf"]
            if len(parts) == 1:
                return self.py_type(parts[0], ctx)
            return self.object_def(schema, ctx)
        types = schema.get("type")
        nullable = False
        if isinstance(types, list):
            nullable = "null" in types
            non_null = [t for t in types if t != "null"]
            types = non_null[0] if len(non_null) == 1 else None
        expr = self._base_type(schema, types, ctx)
        if nullable and expr != "Any":
            return f"Optional[{expr}]"
        return expr

    def _base_type(self, schema: Dict[str, Any], kind: Optional[str], ctx: str) -> str:
        enum = schema.get("enum")
        if enum and all(isinstance(v, str) for v in enum):
            return "Literal[" + ", ".join(json.dumps(v) for v in enum) + "]"
        if kind == "string":
            return "str"
        if kind == "integer":
            return "int"
        if kind == "number":
            return "float"
        if kind == "boolean":
            return "bool"
        if kind == "array":
            return f"List[{self.py_type(schema.get('items'), ctx + 'Item')}]"
        if kind == "object" or "properties" in schema:
            if schema.get("properties"):
                return self.object_def(schema, ctx)
            extra = schema.get("additionalProperties")
            if isinstance(extra, dict):
                return f"Dict[str, {self.py_type(extra, ctx + 'Value')}]"
            return "Dict[str, Any]"
        return "Any"

    # -- TypedDicts ---------------------------------------------------------

    def object_def(self, schema: Dict[str, Any], name: str) -> str:
        if name in self.defs:
            return name
        if name in TYPING_NAMES:
            raise SystemExit(f"schema name {name!r} collides with a typing name")
        bases: List[str] = []
        props: Dict[str, Any] = {}
        required: List[str] = []
        for part in schema.get("allOf", [schema]):
            if "$ref" in part and part is not schema:
                bases.append(part["$ref"].split("/")[-1])
                continue
            props.update(part.get("properties", {}))
            required.extend(part.get("required", []))
        td = TypedDictDef(name=name, bases=bases, fields=[], doc=first_sentence(schema.get("description")))
        self.defs[name] = td  # registered before fields, so recursive schemas terminate
        for prop, sub in props.items():
            if not prop.isidentifier() or keyword.iskeyword(prop):
                raise SystemExit(f"{name}.{prop}: not a Python identifier; add functional TypedDict support")
            ptype = self.py_type(sub, name + pascal(prop))
            doc = first_sentence(sub.get("description") if isinstance(sub, dict) else None)
            td.fields.append((prop, ptype, prop in required, doc))
        self.order.append(name)
        return name

    def build_components(self) -> None:
        for name, schema in self.schemas.items():
            s = schema
            if "allOf" in s or s.get("type") == "object" or "properties" in s:
                self.object_def(s, name)

    # -- rendering ----------------------------------------------------------

    def render(self) -> str:
        # A TypedDict base is a runtime class, so bases are written before subclasses.
        out: List[str] = []
        done: set = set()  # type: ignore[type-arg]

        def emit(name: str) -> None:
            if name in done:
                return
            done.add(name)
            for base in self.defs[name].bases:
                emit(base)
            out.extend(self._render_def(self.defs[name]))

        for name in self.order:
            emit(name)
        return "\n".join(out)

    def _render_def(self, td: TypedDictDef) -> List[str]:
        req = [f for f in td.fields if f[2]]
        opt = [f for f in td.fields if not f[2]]
        bases = td.bases or ["TypedDict"]
        lines: List[str] = ["", ""]
        if req and opt:
            base_name = f"_{td.name}Required"
            lines += self._class(base_name, bases, "", req, total=True)
            lines += ["", ""]
            lines += self._class(td.name, [base_name], td.doc, opt, total=False)
        elif req or (not opt and td.bases):
            lines += self._class(td.name, bases, td.doc, req, total=True)
        else:
            lines += self._class(td.name, bases, td.doc, opt, total=False)
        return lines

    def _class(
        self, name: str, bases: List[str], doc: str, fields: List[Tuple[str, str, bool, str]], total: bool
    ) -> List[str]:
        head = ", ".join(bases) + ("" if total else ", total=False")
        lines = [f"class {name}({head}):"]
        if doc:
            lines.append(f'    """{docstring_text(doc)}"""')
            if fields:
                lines.append("")
        for fname, ftype, _req, fdoc in fields:
            lines += comment_lines(fdoc, "    ")
            lines.append(f"    {fname}: {ftype}")
        if not doc and not fields:
            lines.append("    pass")
        return lines


# -- operations --------------------------------------------------------------


@dataclass
class Param:
    name: str  # Python name
    wire: str  # name on the wire
    type: str
    required: bool
    doc: str


@dataclass
class OperationSpec:
    operation_id: str
    method: str
    path: str
    summary: str
    path_params: List[Param]
    query_params: List[Param]
    body_params: List[Param]
    has_body: bool
    body_extra_allowed: bool
    returns: str  # a type expression, "None", "bytes" or "stream"
    page_item: Optional[str]  # the item type when the response is a cursor page


def _param_schema(reg: TypeRegistry, p: Dict[str, Any]) -> Dict[str, Any]:
    if "$ref" in p:
        name = p["$ref"].split("/")[-1]
        return reg.spec["components"]["parameters"][name]  # type: ignore[no-any-return]
    return p


def build_operations(reg: TypeRegistry) -> Dict[str, OperationSpec]:
    ops: Dict[str, OperationSpec] = {}
    for op_id, method, path, op, item in iter_operations(reg.spec):
        ctx = pascal(op_id)
        path_params: List[Param] = []
        query_params: List[Param] = []
        for raw in list(item.get("parameters", [])) + list(op.get("parameters", [])):
            p = _param_schema(reg, raw)
            if p["in"] == "header":
                continue
            param = Param(
                name=snake(p["name"]),
                wire=p["name"],
                type=reg.py_type(p.get("schema"), ctx + pascal(p["name"])),
                required=bool(p.get("required")) or p["in"] == "path",
                doc=first_sentence(p.get("description")),
            )
            (path_params if p["in"] == "path" else query_params).append(param)
        # Path params in the order they appear in the path.
        order = re.findall(r"{([^}]+)}", path)
        path_params.sort(key=lambda prm: order.index(prm.wire))

        body_params: List[Param] = []
        has_body = False
        extra_allowed = True
        rb = op.get("requestBody")
        if rb:
            has_body = True
            content = rb.get("content", {}).get("application/json", {})
            body_schema = content.get("schema", {})
            type_name = reg.py_type(body_schema, ctx + "Body")
            resolved = reg.resolve(body_schema)
            extra_allowed = resolved.get("additionalProperties") is not False
            td = reg.defs.get(type_name)
            if td is None:
                raise SystemExit(f"{op_id}: request body is not an object")
            for fname, ftype, req, fdoc in _all_fields(reg, td):
                body_params.append(Param(name=fname, wire=fname, type=ftype, required=req, doc=fdoc))

        returns, page_item = _response_type(reg, op, ctx)
        ops[op_id] = OperationSpec(
            operation_id=op_id,
            method=method,
            path=path,
            summary=first_sentence(op.get("summary")) or op_id,
            path_params=path_params,
            query_params=query_params,
            body_params=body_params,
            has_body=has_body,
            body_extra_allowed=extra_allowed,
            returns=returns,
            page_item=page_item,
        )
    return ops


def _all_fields(reg: TypeRegistry, td: TypedDictDef) -> List[Tuple[str, str, bool, str]]:
    fields: List[Tuple[str, str, bool, str]] = []
    for base in td.bases:
        fields.extend(_all_fields(reg, reg.defs[base]))
    fields.extend(td.fields)
    return fields


def _response_type(reg: TypeRegistry, op: Dict[str, Any], ctx: str) -> Tuple[str, Optional[str]]:
    for code, resp in sorted(op.get("responses", {}).items(), key=lambda kv: str(kv[0])):
        if not str(code).startswith("2"):
            continue
        content = resp.get("content") or {}
        if not content:
            return "None", None
        if "text/event-stream" in content:
            return "stream", None
        if "application/json" not in content:
            return "bytes", None
        schema = content["application/json"].get("schema", {})
        expr = reg.py_type(schema, ctx + "Response")
        page_item = None
        resolved = reg.resolve(schema)
        props = resolved.get("properties", {})
        if "data" in props and "next_cursor" in props and props["data"].get("type") == "array":
            page_item = reg.py_type(props["data"].get("items"), expr + "DataItem")
        return expr, page_item
    return "None", None
