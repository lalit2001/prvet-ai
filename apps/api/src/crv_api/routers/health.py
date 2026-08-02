"""Liveness + readiness. PRD F10."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from crv_adapters.storage import get_adapter as get_storage
from crv_core.db import ping as db_ping
from crv_core.queue import pool as queue_pool
from crv_core.settings import get_settings

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness — must not touch dependencies (PRD F10)."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz() -> dict[str, dict[str, str]]:
    """Readiness — DB + queue + storage. 503 if any fail."""
    s = get_settings()
    checks: dict[str, dict[str, str]] = {}

    try:
        await db_ping()
        checks["db"] = {"status": "ok"}
    except Exception as e:
        checks["db"] = {"status": "fail", "error": str(e)[:200]}

    try:
        p = await queue_pool()
        await p.ping()
        checks["queue"] = {"status": "ok"}
    except Exception as e:
        checks["queue"] = {"status": "fail", "error": str(e)[:200]}

    try:
        store = get_storage(s.storage_backend, s.storage_uri)
        canary = ".crv-readyz-canary"
        await store.put(canary, b"ok")
        assert await store.exists(canary)
        await store.delete(canary)
        checks["storage"] = {"status": "ok"}
    except Exception as e:
        checks["storage"] = {"status": "fail", "error": str(e)[:200]}

    if any(v["status"] != "ok" for v in checks.values()):
        raise HTTPException(status_code=503, detail=checks)
    return checks
