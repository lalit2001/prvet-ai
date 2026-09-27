"""JS/TS/TSX extractor via tree-sitter → FileFacts. Same shape as pyast so
resolve.py / persist.py never care which parser produced it."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

from crv_worker.indexing.pyast import ExtractedImport, ExtractedRef, ExtractedSymbol, FileFacts

_EXT_LANG = {
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
}
_PREFIX = {"javascript": "js", "typescript": "ts", "tsx": "tsx"}


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


def extract(path: Path, module_key: str) -> FileFacts:
    lang = lang_for(path)
    if lang is None:
        return FileFacts()
    try:
        src = path.read_bytes()
    except OSError:
        return FileFacts()
    tree = _parser(lang).parse(src)
    facts = FileFacts()
    _walk(tree.root_node, module_key, parent_class=None, out=facts.symbols, lang=lang)
    _imports(tree.root_node, facts.imports)
    _refs(tree.root_node, facts.refs)
    return facts


def extract_symbols(path: Path, module_key: str) -> list[ExtractedSymbol]:
    return extract(path, module_key).symbols


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
            continue

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

        if t in ("export_statement", "export_default_declaration"):
            _walk(child, module, parent_class, out, lang)
            continue

        if child.child_count:
            _walk(child, module, parent_class, out, lang)


def _imports(root: Node, out: list[ExtractedImport]) -> None:
    def spec_of(node: Node) -> str | None:
        s = node.child_by_field_name("source")
        return s.text.decode(errors="replace").strip("'\"`") if s is not None else None

    def visit(node: Node) -> None:
        line = node.start_point[0] + 1
        if node.type == "import_statement":
            spec = spec_of(node)
            if spec:
                clause = next((c for c in node.children if c.type == "import_clause"), None)
                if clause is None:
                    out.append(ExtractedImport(spec, None, "*", line))  # side-effect import
                for c in (clause.children if clause else []):
                    if c.type == "identifier":
                        out.append(ExtractedImport(spec, "default", c.text.decode(), line))
                    elif c.type == "namespace_import":
                        ident = next((x for x in c.children if x.type == "identifier"), None)
                        if ident is not None:
                            out.append(ExtractedImport(spec, None, ident.text.decode(), line))
                    elif c.type == "named_imports":
                        for sp in c.children:
                            if sp.type == "import_specifier":
                                n = sp.child_by_field_name("name")
                                a = sp.child_by_field_name("alias")
                                if n is not None:
                                    out.append(ExtractedImport(spec, n.text.decode(), (a or n).text.decode(), line))
            return
        if node.type == "export_statement":
            spec = spec_of(node)
            if spec:
                for c in node.children:
                    if c.type == "export_clause":
                        for sp in c.children:
                            if sp.type == "export_specifier":
                                n = sp.child_by_field_name("name")
                                a = sp.child_by_field_name("alias")
                                if n is not None:
                                    out.append(ExtractedImport(spec, n.text.decode(), (a or n).text.decode(), line))
                    elif c.type == "namespace_export":
                        out.append(ExtractedImport(spec, None, "*", line))
                if not any(c.type in ("export_clause", "namespace_export") for c in node.children):
                    out.append(ExtractedImport(spec, None, "*", line))  # export * from
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if fn is not None and fn.text == b"require" and args is not None:
                s = next((a for a in args.children if a.type == "string"), None)
                decl = node.parent
                if s is not None and decl is not None and decl.type == "variable_declarator":
                    nm = decl.child_by_field_name("name")
                    if nm is not None and nm.type == "identifier":
                        out.append(ExtractedImport(s.text.decode().strip("'\"`"), None, nm.text.decode(), line))
        for c in node.children:
            visit(c)

    visit(root)


def _refs(root: Node, out: list[ExtractedRef]) -> None:
    def dotted(n: Node | None) -> str | None:
        if n is None:
            return None
        if n.type in ("identifier", "type_identifier", "property_identifier"):
            return n.text.decode(errors="replace")
        if n.type == "member_expression":
            obj = n.child_by_field_name("object")
            prop = n.child_by_field_name("property")
            head = obj.text.decode(errors="replace") if obj is not None and obj.type in ("identifier", "this") else (
                dotted(obj).rsplit(".", 1)[-1] if obj is not None and dotted(obj) else None)
            p = prop.text.decode(errors="replace") if prop is not None else None
            return f"{head}.{p}" if head and p else p
        if n.type == "nested_type_identifier":
            return ".".join(n.text.decode(errors="replace").split(".")[-2:])
        if n.type == "generic_type":
            return dotted(n.child_by_field_name("name"))
        return None

    def add(n: Node | None, kind: str) -> None:
        name = dotted(n)
        if name and name != "require":
            out.append(ExtractedRef(name, n.start_point[0] + 1, kind))

    def visit(node: Node) -> None:
        t = node.type
        if t == "call_expression":
            add(node.child_by_field_name("function"), "call")
        elif t == "new_expression":
            add(node.child_by_field_name("constructor"), "new")
        elif t == "class_heritage":
            for c in node.children:
                if c.type in ("identifier", "member_expression"):
                    add(c, "inherit")
                elif c.type in ("extends_clause", "implements_clause"):
                    for x in c.children:
                        if x.type in ("identifier", "member_expression", "type_identifier", "generic_type"):
                            add(x, "inherit")
        elif t == "extends_type_clause":
            for x in node.children:
                if x.type in ("type_identifier", "generic_type", "nested_type_identifier"):
                    add(x, "inherit")
        elif t == "decorator":
            expr = node.children[-1] if node.children else None
            add(expr.child_by_field_name("function") if expr is not None and expr.type == "call_expression" else expr, "decorator")
        elif t == "type_annotation":
            inner = node.children[-1] if node.children else None
            if inner is not None and inner.type in ("type_identifier", "generic_type", "nested_type_identifier"):
                add(inner, "type")
        elif t in ("jsx_opening_element", "jsx_self_closing_element"):
            nm = node.child_by_field_name("name")
            if nm is not None and nm.type in ("identifier", "member_expression") and nm.text[:1].isupper():
                add(nm, "call")
        for c in node.children:
            visit(c)

    visit(root)


def _name(node: Node) -> str | None:
    n = node.child_by_field_name("name")
    return n.text.decode(errors="replace") if n is not None else None


def _method_name(node: Node) -> str | None:
    n = node.child_by_field_name("name")
    return n.text.decode(errors="replace").strip("'\"") if n is not None else None


def _is_exported(node: Node) -> bool:
    p = node.parent
    while p is not None and p.type not in ("program", "statement_block", "class_body"):
        if p.type in ("export_statement", "export_default_declaration"):
            return True
        p = p.parent
    return False


def _sym(qname: str, name: str, kind: str, node: Node, module: str, lang: str, exported: bool) -> ExtractedSymbol:
    return ExtractedSymbol(
        symbol_key=f"{_PREFIX[lang]}::{module}.{qname}",
        name=name,
        kind=kind,
        start_line=node.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        signature=_signature(node),
        docstring=None,
        visibility="public" if exported else "private",
    )


def _signature(node: Node) -> str | None:
    txt = node.text.decode(errors="replace")
    for stop in ("{", "=>"):
        i = txt.find(stop)
        if i >= 0:
            return txt[:i].strip()
    return txt.strip()[:200] or None


if __name__ == "__main__":
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("apps/web/app/page.tsx")
    facts = extract(p, "sample")
    for s in facts.symbols:
        print(f"  {s.kind:10} {s.symbol_key} L{s.start_line}-{s.end_line}")
    print(f"{len(facts.symbols)} symbols, {len(facts.imports)} imports, {len(facts.refs)} refs in {p}")
    assert facts.imports and facts.refs
