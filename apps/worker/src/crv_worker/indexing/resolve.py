"""Turn per-file FileFacts into a repo-wide graph: symbol_references edges and
file→file import edges. Pure functions, no DB.

Resolution order for a reference `head[.attr]`:
  self/this.attr → enclosing class · local symbol · imported binding →
  target file's symbol · unique-name fallback across the repo (precision=heuristic).
External libraries never resolve and are not counted against the resolution rate."""
from __future__ import annotations

import json
import posixpath
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from crv_worker.indexing.pyast import ExtractedSymbol, FileFacts

_JS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_SELF = {"self", "cls", "this"}


@dataclass
class IndexedFile:
    rel_path: str
    lang: str
    module_key: str
    facts: FileFacts


@dataclass(frozen=True)
class Edge:
    from_key: str | None
    to_key: str
    file: str
    line: int
    kind: str
    precision: str


@dataclass
class Resolution:
    edges: list[Edge] = field(default_factory=list)
    file_imports: list[tuple[str, str, int, str]] = field(default_factory=list)  # from, to, line, specifier
    resolved: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    unresolved: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def resolve(files: list[IndexedFile], root: Path | None = None) -> Resolution:
    by_path = {f.rel_path: f for f in files}
    aliases = _tsconfig_aliases(root) if root else []
    py_modules = {f.module_key: f.rel_path for f in files if f.lang == "python"}
    syms: dict[str, dict[str, str]] = {}          # rel → qname → key
    name_index: dict[str, list[tuple[str, str]]] = defaultdict(list)   # name → [(key, kind)]
    for f in files:
        prefix = f"{f.module_key}."
        table: dict[str, str] = {}
        for s in f.facts.symbols:
            qname = s.symbol_key.split("::", 1)[1]
            qname = qname[len(prefix):] if qname.startswith(prefix) else qname
            table[qname] = s.symbol_key
            name_index[s.name].append((s.symbol_key, s.kind))
        syms[f.rel_path] = table

    res = Resolution()
    seen: set[tuple] = set()

    for f in files:
        bindings: dict[str, tuple[str, str | None]] = {}   # alias → (target_rel, name|None)
        import_targets: set[tuple[str, int, str]] = set()
        for imp in f.facts.imports:
            # `from pkg import submodule` binds the module itself, not a symbol inside pkg/__init__
            if f.lang == "python" and imp.name and f"{imp.module}.{imp.name}" in py_modules:
                sub_rel = py_modules[f"{imp.module}.{imp.name}"]
                import_targets.add((sub_rel, imp.line, f"{imp.module}.{imp.name}"))
                bindings[imp.alias] = (sub_rel, None)
                continue
            target = _import_target(imp.module, f, by_path, py_modules, aliases)
            if target is None:
                continue
            target_rel, sub = target
            import_targets.add((target_rel, imp.line, imp.module))
            if imp.alias != "*":
                bindings[imp.alias] = (target_rel, imp.name if sub is None else sub)
            else:
                for qname, key in syms[target_rel].items():          # star import / re-export
                    if "." not in qname:
                        bindings.setdefault(qname, (target_rel, qname))
        for target_rel, line, spec in sorted(import_targets):
            res.file_imports.append((f.rel_path, target_rel, line, spec))

        local = syms[f.rel_path]
        ranges = sorted(f.facts.symbols, key=lambda s: s.end_line - s.start_line)

        for ref in f.facts.refs:
            head, _, attr = ref.name.partition(".")
            enclosing = _enclosing(ranges, ref.line)
            from_key = enclosing.symbol_key if enclosing else None
            to_key, precision = _resolve_ref(head, attr, enclosing, local, bindings, syms, name_index, f.module_key)
            if to_key is None:
                if head in bindings or head in local or head in _SELF:
                    res.unresolved[f.rel_path] += 1
                continue
            if to_key == from_key:
                continue
            res.resolved[f.rel_path] += 1
            e = Edge(from_key, to_key, f.rel_path, ref.line, ref.kind, precision)
            k = (e.from_key, e.to_key, e.line, e.kind)
            if k not in seen:
                seen.add(k)
                res.edges.append(e)
    return res


def _resolve_ref(head: str, attr: str, enclosing: ExtractedSymbol | None, local: dict[str, str],
                 bindings: dict[str, tuple[str, str | None]], syms: dict[str, dict[str, str]],
                 name_index: dict[str, list[tuple[str, str]]], module_key: str) -> tuple[str | None, str]:
    if head in _SELF and attr and enclosing is not None:
        qname = enclosing.symbol_key.split("::", 1)[1][len(module_key) + 1:]
        cls = qname.rsplit(".", 1)[0] if enclosing.kind == "method" else qname
        return local.get(f"{cls}.{attr}"), "import-resolved"

    if not attr:
        if head in local:
            return local[head], "import-resolved"
        if head in bindings:
            target_rel, name = bindings[head]
            t = syms.get(target_rel, {})
            if name == "default":
                cand = t.get(head) or next((k for q, k in t.items() if "." not in q and k.endswith(f".{head}")), None)
                if cand is None:
                    tops = [k for q, k in t.items() if "." not in q]
                    cand = tops[0] if len(tops) == 1 else None
                return cand, "import-resolved"
            if name is not None:
                return t.get(name), "import-resolved"
            return None, ""
        return _unique(name_index, head), "heuristic"

    if head in local:
        return local.get(f"{head}.{attr}"), "import-resolved"
    if head in bindings:
        target_rel, name = bindings[head]
        t = syms.get(target_rel, {})
        if name is None or name == "default":
            hit = t.get(attr)
            if hit is None and name == "default":
                hit = next((k for q, k in t.items() if q.endswith(f".{attr}")), None)
            return hit, "import-resolved"
        return t.get(f"{name}.{attr}"), "import-resolved"
    return _unique(name_index, attr, methods_only=True), "heuristic"


def _unique(name_index: dict[str, list[tuple[str, str]]], name: str, methods_only: bool = False) -> str | None:
    """Repo-wide unique-name fallback. `foo()` may only hit a non-method; `x.foo()` only a method."""
    if len(name) < 3:
        return None
    hits = [k for k, kind in name_index.get(name, []) if (kind == "method") == methods_only]
    return hits[0] if len(hits) == 1 else None


def _enclosing(ranges: list[ExtractedSymbol], line: int) -> ExtractedSymbol | None:
    for s in ranges:  # sorted smallest range first → innermost wins
        if s.start_line <= line <= s.end_line:
            return s
    return None


def _tsconfig_aliases(root: Path) -> list[tuple[str, list[str]]]:
    """[(prefix, [target_dir_rel, ...])] from every tsconfig*.json / jsconfig.json at repo root.
    ponytail: root-level configs only; nested packages get aliases when a real monorepo needs them."""
    out: list[tuple[str, list[str]]] = []
    for cfg in sorted(root.glob("tsconfig*.json")) + sorted(root.glob("jsconfig.json")):
        try:
            raw = re.sub(r"//[^\n]*|/\*.*?\*/", "", cfg.read_text(errors="replace"), flags=re.S)
            data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw))
        except (OSError, ValueError):
            continue
        co = data.get("compilerOptions") or {}
        base = posixpath.normpath(posixpath.join(cfg.parent.relative_to(root).as_posix(), co.get("baseUrl") or "."))
        for pat, targets in (co.get("paths") or {}).items():
            prefix = pat[:-1] if pat.endswith("*") else pat
            dirs = [posixpath.normpath(posixpath.join(base, t[:-1] if t.endswith("*") else t)) for t in targets]
            out.append((prefix, dirs))
    out.sort(key=lambda a: -len(a[0]))  # longest prefix wins
    return out


def _import_target(spec: str, f: IndexedFile, by_path: dict[str, IndexedFile],
                   py_modules: dict[str, str], aliases: list[tuple[str, list[str]]] = ()) -> tuple[str, str | None] | None:
    """→ (target_rel_path, submodule_name_if_spec_pointed_at_a_package) or None (external)."""
    if f.lang == "python":
        if spec in py_modules:
            return py_modules[spec], None
        return None
    if spec.startswith("."):
        base = posixpath.normpath(posixpath.join(posixpath.dirname(f.rel_path), spec))
        return _js_candidate(base, by_path)
    for prefix, dirs in aliases:
        if spec.startswith(prefix):
            for d in dirs:
                hit = _js_candidate(posixpath.normpath(posixpath.join(d, spec[len(prefix):])).lstrip("./"), by_path)
                if hit:
                    return hit
    if spec[:2] in ("@/", "~/"):
        tail = spec[2:]
        hits = {p for p in by_path if p == tail or p.endswith("/" + tail) or
                any(p == tail + e or p.endswith("/" + tail + e) or p.endswith("/" + tail + "/index" + e) for e in _JS_EXTS)}
        return (min(hits, key=len), None) if hits else None
    return None


def _js_candidate(base: str, by_path: dict[str, IndexedFile]) -> tuple[str, None] | None:
    if base in by_path:
        return base, None
    for e in _JS_EXTS:
        if base + e in by_path:
            return base + e, None
    for e in _JS_EXTS:
        if f"{base}/index{e}" in by_path:
            return f"{base}/index{e}", None
    return None


if __name__ == "__main__":
    from pathlib import Path
    from crv_worker.indexing import pyast, treesitter
    from crv_worker.indexing.walker import walk
    root = Path.cwd()
    files: list[IndexedFile] = []
    for p in walk(root):
        lang = "python" if p.suffix == ".py" else treesitter.lang_for(p)
        if not lang:
            continue
        mk = pyast.module_key_for(p, root)
        facts = pyast.extract(p, mk) if lang == "python" else treesitter.extract(p, mk)
        files.append(IndexedFile(str(p.relative_to(root)), lang, mk, facts))
    r = resolve(files)
    tot_r, tot_u = sum(r.resolved.values()), sum(r.unresolved.values())
    print(f"{len(files)} files · {len(r.edges)} edges · {len(r.file_imports)} file imports · "
          f"resolution {tot_r}/{tot_r + tot_u} = {tot_r / max(1, tot_r + tot_u):.0%}")
    assert r.edges and r.file_imports
