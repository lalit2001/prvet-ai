"""JS/TS/TSX symbol extractor via tree-sitter. See PRD F3.

Same ExtractedSymbol shape as pyast so persist.py doesn't care which parser produced it."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

from crv_worker.indexing.pyast import ExtractedSymbol


_EXT_LANG = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
}


@lru_cache(maxsize=None)
def _parser(lang: str) -> Parser:
    if lang == "javascript":
        return Parser(Language(tsjs.language()))
    if lang == "typescript":
        return Parser(Language(tsts.language_typescript()))
    if lang == "tsx":
        return Parser(Language(tsts.language_tsx()))
    raise ValueError(f"no ts parser for {lang}")


def lang_for(path: Path) -> str | None:
    return _EXT_LANG.get(path.suffix.lower())


def extract_symbols(path: Path, module_key: str) -> list[ExtractedSymbol]:
    lang = lang_for(path)
    if lang is None:
        return []
    try:
        src = path.read_bytes()
    except OSError:
        return []
    tree = _parser(lang).parse(src)
    out: list[ExtractedSymbol] = []
    _walk(tree.root_node, module_key, parent_class=None, out=out, lang=lang)
    return out


_FN_TYPES = {
    "function_declaration", "generator_function_declaration",
    "method_definition", "function_signature",
    "arrow_function", "function_expression",
}


def _walk(node: Node, module: str, parent_class: str | None,
          out: list[ExtractedSymbol], lang: str) -> None:
    for child in node.children:
        t = child.type

        if t in ("class_declaration", "abstract_class_declaration"):
            name = _name(child)
            if name:
                qname = f"{parent_class}.{name}" if parent_class else name
                out.append(_sym(qname, name, "class", child, module, lang, exported=_is_exported(child)))
                _walk(child, module, parent_class=qname, out=out, lang=lang)
            continue

        if t == "interface_declaration":
            name = _name(child)
            if name:
                qname = f"{parent_class}.{name}" if parent_class else name
                out.append(_sym(qname, name, "interface", child, module, lang, exported=_is_exported(child)))
            continue

        if t == "type_alias_declaration":
            name = _name(child)
            if name:
                qname = f"{parent_class}.{name}" if parent_class else name
                out.append(_sym(qname, name, "type", child, module, lang, exported=_is_exported(child)))
            continue

        if t in _FN_TYPES:
            # method inside a class
            if t == "method_definition":
                name = _method_name(child)
                if name and parent_class:
                    qname = f"{parent_class}.{name}"
                    out.append(_sym(qname, name, "method", child, module, lang, exported=False))
            else:
                name = _name(child)
                if name:
                    qname = f"{parent_class}.{name}" if parent_class else name
                    out.append(_sym(qname, name, "function", child, module, lang, exported=_is_exported(child)))
            # do not recurse into function bodies for now — nested defs are rare
            continue

        # variable declaration that assigns a fn / arrow → still a function
        if t in ("lexical_declaration", "variable_declaration"):
            for decl in child.children:
                if decl.type == "variable_declarator":
                    name_node = decl.child_by_field_name("name")
                    val = decl.child_by_field_name("value")
                    if name_node and val and val.type in ("arrow_function", "function_expression"):
                        name = name_node.text.decode(errors="replace")
                        qname = f"{parent_class}.{name}" if parent_class else name
                        out.append(_sym(qname, name, "function", decl, module, lang, exported=_is_exported(child)))
            continue

        # export statements re-wrap their child; recurse into them
        if t in ("export_statement", "export_default_declaration"):
            _walk(child, module, parent_class, out, lang)
            continue

        # descend into blocks so we find top-level defs inside if/try/etc.
        if child.child_count:
            _walk(child, module, parent_class, out, lang)


def _name(node: Node) -> str | None:
    n = node.child_by_field_name("name")
    if n is not None:
        return n.text.decode(errors="replace")
    return None


def _method_name(node: Node) -> str | None:
    n = node.child_by_field_name("name")
    if n is None:
        return None
    txt = n.text.decode(errors="replace")
    # strip quotes for computed / string-keyed methods
    return txt.strip("'\"")


def _is_exported(node: Node) -> bool:
    p = node.parent
    while p is not None and p.type not in ("program", "statement_block", "class_body"):
        if p.type in ("export_statement", "export_default_declaration"):
            return True
        p = p.parent
    return False


def _sym(qname: str, name: str, kind: str, node: Node, module: str, lang: str, exported: bool) -> ExtractedSymbol:
    prefix = {"javascript": "js", "typescript": "ts", "tsx": "tsx"}[lang]
    return ExtractedSymbol(
        symbol_key=f"{prefix}::{module}.{qname}",
        name=name,
        kind=kind,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        signature=_signature(node),
        docstring=None,
        visibility="public" if exported else "private",
    )


def _signature(node: Node) -> str | None:
    # Only take the header (up to the body brace) so we don't return the whole body.
    txt = node.text.decode(errors="replace")
    for stop in ("{", "=>"):
        i = txt.find(stop)
        if i >= 0:
            return txt[:i].strip()
    return txt.strip()[:200] or None


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("apps/web/lib/api.ts")
    syms = extract_symbols(p, "sample")
    for s in syms:
        print(f"  {s.kind:10} {s.symbol_key} L{s.start_line}-{s.end_line}")
    print(f"{len(syms)} symbols in {p}")
