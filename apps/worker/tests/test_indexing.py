"""Self-index the repo: walk + extractors + resolver should link known symbols.
No DB, no arq. Just the pure indexing pipeline."""
from pathlib import Path

from crv_worker.indexing import treesitter
from crv_worker.indexing.pyast import extract, extract_symbols, module_key_for
from crv_worker.indexing.resolve import IndexedFile, resolve
from crv_worker.indexing.walker import walk

REPO = Path(__file__).resolve().parents[3]


def test_walker_finds_py_files_and_skips_venv():
    files = list(walk(REPO))
    assert any(p.name == "settings.py" and "crv_core" in str(p) for p in files)
    assert not any(".venv" in p.parts for p in files)
    assert not any(p.name.endswith(".pyc") for p in files)


def test_pyast_extracts_github_adapter_methods():
    path = REPO / "packages/adapters/src/crv_adapters/forge/github.py"
    syms = extract_symbols(path, module_key_for(path, REPO))
    names = {(s.name, s.kind) for s in syms}
    assert ("GitHubAdapter", "class") in names
    assert ("verify_webhook", "method") in names
    verify = next(s for s in syms if s.name == "verify_webhook")
    assert "async def verify_webhook" in (verify.signature or "")


def test_pyast_extracts_settings_class():
    path = REPO / "packages/core/src/crv_core/settings.py"
    syms = extract_symbols(path, module_key_for(path, REPO))
    settings_cls = next(s for s in syms if s.name == "Settings")
    assert settings_cls.kind == "class"
    assert settings_cls.symbol_key == "py::crv_core.settings.Settings"


def test_pyast_ignores_syntax_error(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n  pass\n")
    assert extract_symbols(bad, "bad") == []


def test_pyast_imports_and_refs(tmp_path):
    pkg = tmp_path / "pkg"; pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("class Base:\n    def run(self): ...\n\ndef helper(): ...\n")
    (pkg / "b.py").write_text(
        "from .a import Base, helper\nfrom . import a\n\n"
        "class Child(Base):\n    def go(self):\n        helper()\n        a.helper()\n        self.go()\n"
    )
    facts = extract(pkg / "b.py", "pkg.b")
    imports = {(i.module, i.name, i.alias) for i in facts.imports}
    assert ("pkg.a", "Base", "Base") in imports and ("pkg", "a", "a") in imports
    refs = {(r.name, r.kind) for r in facts.refs}
    assert ("Base", "inherit") in refs and ("helper", "call") in refs and ("a.helper", "call") in refs


def test_resolve_links_python_across_files(tmp_path):
    pkg = tmp_path / "pkg"; pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("class Base:\n    def run(self): ...\n\ndef helper(): ...\n")
    (pkg / "b.py").write_text(
        "from .a import Base, helper\n\nclass Child(Base):\n    def go(self):\n        helper()\n        self.go()\n        Base.run(self)\n"
    )
    files = [IndexedFile(f"pkg/{n}", "python", f"pkg.{n[:-3]}" if n != "__init__.py" else "pkg",
                         extract(pkg / n, f"pkg.{n[:-3]}" if n != "__init__.py" else "pkg"))
             for n in ("__init__.py", "a.py", "b.py")]
    r = resolve(files)
    edges = {(e.from_key, e.to_key, e.kind) for e in r.edges}
    assert ("py::pkg.b.Child", "py::pkg.a.Base", "inherit") in edges
    assert ("py::pkg.b.Child.go", "py::pkg.a.helper", "call") in edges
    assert ("py::pkg.b.Child.go", "py::pkg.a.Base.run", "call") in edges
    assert ("pkg/b.py", "pkg/a.py") in {(f, t) for f, t, _, _ in r.file_imports}
    assert r.unresolved.get("pkg/b.py", 0) == 0  # self.go() is recursion → dropped, not unresolved


def test_resolve_links_typescript_imports(tmp_path):
    (tmp_path / "util.ts").write_text("export function add(a: number, b: number) { return a + b }\nexport class Box { open() {} }\n")
    (tmp_path / "main.ts").write_text("import { add, Box as B } from './util'\nexport const run = () => { const b = new B(); b.open(); return add(1, 2) }\n")
    files = [IndexedFile(n, "typescript", n[:-3], treesitter.extract(tmp_path / n, n[:-3])) for n in ("util.ts", "main.ts")]
    r = resolve(files)
    edges = {(e.from_key, e.to_key, e.kind) for e in r.edges}
    assert ("ts::main.run", "ts::util.add", "call") in edges
    assert ("ts::main.run", "ts::util.Box", "new") in edges
    assert ("main.ts", "util.ts") in {(f, t) for f, t, _, _ in r.file_imports}


def test_self_resolution_rate_is_high():
    files: list[IndexedFile] = []
    for p in walk(REPO / "apps/worker"):
        lang = "python" if p.suffix == ".py" else treesitter.lang_for(p)
        if not lang:
            continue
        mk = module_key_for(p, REPO)
        facts = extract(p, mk) if lang == "python" else treesitter.extract(p, mk)
        files.append(IndexedFile(p.relative_to(REPO).as_posix(), lang, mk, facts))
    r = resolve(files)
    res, unres = sum(r.resolved.values()), sum(r.unresolved.values())
    assert res / (res + unres) >= 0.85
    assert any(e.to_key == "py::crv_worker.indexing.resolve.resolve" for e in r.edges)


def test_resolve_honours_tsconfig_paths(tmp_path):
    (tmp_path / "tsconfig.json").write_text('{ "compilerOptions": { "paths": { "@app/*": ["src/*"] } } } // c\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "util.ts").write_text("export function add(a: number, b: number) { return a + b }\n")
    (tmp_path / "src" / "main.ts").write_text("import { add } from '@app/util'\nexport const run = () => add(1, 2)\n")
    files = [IndexedFile(f"src/{n}", "typescript", f"src.{n[:-3]}", treesitter.extract(tmp_path / "src" / n, f"src.{n[:-3]}")) for n in ("util.ts", "main.ts")]
    r = resolve(files, tmp_path)
    assert ("src/main.ts", "src/util.ts") in {(f, t) for f, t, _, _ in r.file_imports}
    assert ("ts::src.main.run", "ts::src.util.add", "call") in {(e.from_key, e.to_key, e.kind) for e in r.edges}
