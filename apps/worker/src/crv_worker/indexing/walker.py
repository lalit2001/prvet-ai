"""Repo file walker. See PRD F3.

Yields absolute paths to files worth indexing. Inside a git checkout the file
list comes from `git ls-files` so .gitignore is honoured (vendored clones,
build output, secrets never get indexed); elsewhere a hardcoded skip list."""
from __future__ import annotations

import os
import subprocess
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
    for p in (_git_files(root) or _os_walk(root)):
        if p.name.endswith(_SKIP_SUFFIX) or any(part in _SKIP_DIRS for part in p.relative_to(root).parts[:-1]):
            continue
        try:
            if not p.is_file() or p.stat().st_size > max_bytes or _looks_binary(p):
                continue
        except OSError:
            continue
        yield p


def _git_files(root: Path) -> list[Path] | None:
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             check=True, capture_output=True, timeout=60).stdout
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    return [root / f.decode(errors="replace") for f in out.split(b"\0") if f]


def _os_walk(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


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
