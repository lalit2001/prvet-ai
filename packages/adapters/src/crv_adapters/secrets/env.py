"""Env-backed secrets — compose default. `ref` is treated as an env var name."""
from __future__ import annotations

import os


class EnvSecrets:
    async def get(self, ref: str) -> str:
        v = os.environ.get(ref)
        if v is None:
            raise KeyError(f"secret {ref!r} not found in environment")
        return v

    async def put(self, ref: str, value: str) -> None:
        # env-backed secrets are read-only from the app's perspective; writes must go via deploy
        raise NotImplementedError("EnvSecrets is read-only; write via .env or the deploy pipeline")

    async def delete(self, ref: str) -> None:
        raise NotImplementedError

    async def rotate(self, ref: str) -> str:
        raise NotImplementedError
