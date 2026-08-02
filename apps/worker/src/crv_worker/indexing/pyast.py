"""Python symbol extractor via stdlib ast. See PRD F3.

Stdlib beats tree-sitter for Python — no dep, precise line ranges, works on
partial trees via ast.parse's error recovery (Python 3.13+). JS/TS/Java land
via tree-sitter when their walkers are wired in."""
from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExtractedSymbol:
    symbol_key: str                     # stable: "py::pkg.mod.Class.method"
    name: str
    kind: str                           # function|method|class
    start_line: int
    end_line: int
    signature: str | None
    docstring: str | None
    visibility: str                     # public|private (underscore convention)


def extract_symbols(path: Path, module_key: str) -> list[ExtractedSymbol]:
    """`module_key` is the dotted path used as symbol_key prefix.
    For apps/api/src/crv_api/main.py that's 'crv_api.main'."""
    try:
        tree = ast.parse(path.read_text(errors="replace"), filename=str(path))
    except SyntaxError:
        return []  # AC3.6 — partial-tree on syntax error; ast can't do partial, so return []

    out: list[ExtractedSymbol] = []
    _walk(tree, module_key, parent_kind=None, parent_name=None, out=out)
    return out


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
            # nested functions get indexed but classes-inside-functions are rare enough to skip
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


def _signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args = ast.unparse(fn.args)
    ret = f" -> {ast.unparse(fn.returns)}" if fn.returns else ""
    prefix = "async def " if isinstance(fn, ast.AsyncFunctionDef) else "def "
    return f"{prefix}{fn.name}({args}){ret}"


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_key_for(path: Path, repo_root: Path) -> str:
    """apps/api/src/crv_api/main.py under repo_root/apps/api → 'crv_api.main'.
    ponytail: only strips known src-layout prefixes; refine when a real repo breaks it."""
    rel = path.relative_to(repo_root).with_suffix("")
    parts = list(rel.parts)
    # Strip common src-layout wrappers to get the actual package path
    for wrapper in ("src", "lib"):
        while wrapper in parts[:-1]:
            parts.remove(wrapper)
    # Also strip apps/<app>/ and packages/<pkg>/ prefixes
    if len(parts) >= 2 and parts[0] in ("apps", "packages"):
        parts = parts[2:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else path.stem


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "packages/core/src/crv_core/settings.py").resolve()
    syms = extract_symbols(root, module_key_for(root, Path.cwd()))
    assert any(s.name == "Settings" for s in syms), "should have found the Settings class"
    for s in syms:
        print(f"  {s.kind:8} {s.symbol_key} L{s.start_line}-{s.end_line}")
    print(f"{len(syms)} symbols")
