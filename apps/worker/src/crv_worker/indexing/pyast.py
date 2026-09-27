"""Python extractor via stdlib ast → FileFacts (symbols, imports, references).

Stdlib beats tree-sitter for Python: no dep, precise line ranges. Same FileFacts
shape comes out of treesitter.py so resolve.py / persist.py never care which
parser produced it."""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ExtractedSymbol:
    symbol_key: str                     # stable: "py::pkg.mod.Class.method"
    name: str
    kind: str                           # function|method|class|interface|type
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None
    visibility: str                     # public|private


@dataclass(frozen=True)
class ExtractedImport:
    module: str                         # py: absolute dotted module · js: raw specifier
    name: str | None                    # imported member; None = whole module / namespace
    alias: str                          # local binding name
    line: int


@dataclass(frozen=True)
class ExtractedRef:
    name: str                           # "foo" or "obj.foo" (head.attr, at most one dot)
    line: int
    kind: str                           # call|new|inherit|decorator|type


@dataclass
class FileFacts:
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    refs: list[ExtractedRef] = field(default_factory=list)


def extract(path: Path, module_key: str) -> FileFacts:
    try:
        tree = ast.parse(path.read_text(errors="replace"), filename=str(path))
    except SyntaxError:
        return FileFacts()
    facts = FileFacts()
    _walk(tree, module_key, parent_kind=None, parent_name=None, out=facts.symbols)
    is_pkg = path.name == "__init__.py"
    package = module_key if is_pkg else module_key.rpartition(".")[0]
    _imports(tree, package, facts.imports)
    _refs(tree, facts.refs)
    return facts


def extract_symbols(path: Path, module_key: str) -> list[ExtractedSymbol]:
    return extract(path, module_key).symbols


def _walk(node: ast.AST, module: str, parent_kind: str | None, parent_name: str | None, out: list[ExtractedSymbol]) -> None:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "method" if parent_kind == "class" else "function"
            qname = f"{parent_name}.{child.name}" if parent_name else child.name
            out.append(ExtractedSymbol(
                symbol_key=f"py::{module}.{qname}",
                name=child.name,
                kind=kind,
                start_line=child.lineno,
                end_line=child.end_lineno or child.lineno,
                signature=_signature(child),
                docstring=ast.get_docstring(child),
                visibility="private" if child.name.startswith("_") else "public",
            ))
        elif isinstance(child, ast.ClassDef):
            qname = f"{parent_name}.{child.name}" if parent_name else child.name
            out.append(ExtractedSymbol(
                symbol_key=f"py::{module}.{qname}",
                name=child.name,
                kind="class",
                start_line=child.lineno,
                end_line=child.end_lineno or child.lineno,
                signature=None,
                docstring=ast.get_docstring(child),
                visibility="private" if child.name.startswith("_") else "public",
            ))
            _walk(child, module, parent_kind="class", parent_name=qname, out=out)


def _imports(tree: ast.AST, package: str, out: list[ExtractedImport]) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append(ExtractedImport(a.name, None, a.asname or a.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            mod = _resolve_relative(node.module or "", node.level, package)
            if mod is None:
                continue
            for a in node.names:
                if a.name == "*":
                    out.append(ExtractedImport(mod, None, "*", node.lineno))
                else:
                    out.append(ExtractedImport(mod, a.name, a.asname or a.name, node.lineno))


def _resolve_relative(module: str, level: int, package: str) -> str | None:
    if level == 0:
        return module
    parts = package.split(".") if package else []
    if level - 1 > len(parts):
        return None
    base = parts[: len(parts) - (level - 1)]
    return ".".join([*base, module] if module else base) or None


def _refs(tree: ast.AST, out: list[ExtractedRef]) -> None:
    def add(expr: ast.AST | None, kind: str) -> None:
        name = _dotted(expr)
        if name:
            out.append(ExtractedRef(name, getattr(expr, "lineno", 0), kind))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            add(node.func, "call")
        elif isinstance(node, ast.ClassDef):
            for b in node.bases:
                add(b, "inherit")
            for d in node.decorator_list:
                add(d.func if isinstance(d, ast.Call) else d, "decorator")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                add(d.func if isinstance(d, ast.Call) else d, "decorator")
            for a in [*node.args.args, *node.args.posonlyargs, *node.args.kwonlyargs]:
                add(_strip_subscript(a.annotation), "type")
            add(_strip_subscript(node.returns), "type")
        elif isinstance(node, ast.AnnAssign):
            add(_strip_subscript(node.annotation), "type")


def _strip_subscript(e: ast.AST | None) -> ast.AST | None:
    while isinstance(e, ast.Subscript):
        e = e.value
    return e


def _dotted(e: ast.AST | None) -> str | None:
    """Name → 'x'; Attribute(Name x, y) → 'x.y'; deeper chains keep the last two hops."""
    if isinstance(e, ast.Name):
        return e.id
    if isinstance(e, ast.Attribute):
        base = e.value
        while isinstance(base, (ast.Attribute, ast.Call, ast.Subscript)):
            base = base.func if isinstance(base, ast.Call) else base.value
        if isinstance(base, ast.Name):
            head = e.value
            head_name = head.id if isinstance(head, ast.Name) else (head.attr if isinstance(head, ast.Attribute) else None)
            return f"{head_name}.{e.attr}" if head_name else e.attr
        return e.attr
    return None


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = ast.unparse(fn.args)
    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    prefix = "async def " if isinstance(fn, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{fn.name}({args}){ret}"


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_key_for(path: Path, repo_root: Path) -> str:
    """apps/api/src/crv_api/main.py under repo_root → 'crv_api.main'.
    ponytail: only strips known src-layout prefixes; refine when a real repo breaks it."""
    rel = path.relative_to(repo_root).with_suffix("")
    parts = list(rel.parts)
    for wrapper in ("src", "lib"):
        while wrapper in parts[:-1]:
            parts.remove(wrapper)
    if len(parts) >= 2 and parts[0] in ("apps", "packages"):
        parts = parts[2:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else path.stem


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "apps/worker/src/crv_worker/jobs/baseline.py").resolve()
    facts = extract(root, module_key_for(root, Path.cwd()))
    for s in facts.symbols:
        print(f"  {s.kind:8} {s.symbol_key} L{s.start_line}-{s.end_line}")
    print(f"{len(facts.symbols)} symbols, {len(facts.imports)} imports, {len(facts.refs)} refs")
    assert facts.imports and facts.refs
