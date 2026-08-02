"""Filesystem storage — the compose default. No presigned URLs; returns file:// paths."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator


class FsStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("key escapes storage root")
        return p

    async def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return f"file://{p}"

    async def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    async def get_stream(self, key: str) -> AsyncIterator[bytes]:
        # ponytail: whole-file read is fine for now; switch to chunks when it hurts
        yield self._path(key).read_bytes()

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()

    async def presign_get(self, key: str, ttl_seconds: int = 3600) -> str:
        return f"file://{self._path(key)}"

    async def list(self, prefix: str) -> AsyncIterator[str]:
        base = self.root / prefix
        for p in base.rglob("*") if base.is_dir() else []:
            if p.is_file():
                yield str(p.relative_to(self.root))
