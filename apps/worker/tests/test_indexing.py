"""Self-index the repo: walk + pyast should find known symbols.
No DB, no arq. Just the pure indexing pipeline."""
from pathlib import Path

from crv_worker.indexing.pyast import extract_symbols, module_key_for
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
    assert ("parse_event", "method") in names
    verify = next(s for s in syms if s.name == "verify_webhook")
    assert verify.signature is not None
    assert "async def verify_webhook" in verify.signature


def test_pyast_extracts_settings_class():
    path = REPO / "packages/core/src/crv_core/settings.py"
    syms = extract_symbols(path, module_key_for(path, REPO))
    settings_cls = next((s for s in syms if s.name == "Settings"), None)
    assert settings_cls is not None
    assert settings_cls.kind == "class"
    # symbol_key strips apps/<app>/src/ and packages/<pkg>/src/ wrappers
    assert settings_cls.symbol_key == "py::crv_core.settings.Settings"


def test_pyast_ignores_syntax_error():
    """Syntax-error file → empty list, no crash. AC3.6."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write("def broken(:\n  pass\n")
        p = Path(f.name)
    try:
        assert extract_symbols(p, "broken") == []
    finally:
        p.unlink()
