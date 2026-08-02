"""Repo file walker. See PRD F3.

Yields absolute paths to files worth indexing. Hardcoded ignore list —
`.crvignore` and per-repo `exclude_paths` land when a real caller needs them."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

_SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "node_modules", ".venv", "venv", "__pycache__",
    "vendor", "third_party", "dist", "build", "out", ".next",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
})

_SKIP_SUFFIX = (
    ".min.js", ".min.css",
    ".lock", ".log",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".bz2",
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
)


def walk(root: Path, max_file_kb: int = 1024) -> Iterator[Path]:
    root = root.resolve()
    max_bytes = max_file_kb * 1024
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn.endswith(_SKIP_SUFFIX):
                continue
            p = Path(dirpath) / fn
            try:
                if p.stat().st_size > max_bytes:
                    continue
                if _looks_binary(p):
                    continue
            except OSError:
                continue
            yield p


def _looks_binary(p: Path) -> bool:
    """NUL byte in first 4KB = binary. Cheap and close enough."""
    try:
        with p.open("rb") as f:
            return b"\x00" in f.read(4096)
    except OSError:
        return True


if __name__ == "__main__":
    import sys
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    files = list(walk(root))
    print(f"{len(files)} files indexable under {root}")
    assert files, "walker returned nothing on a non-empty tree"
