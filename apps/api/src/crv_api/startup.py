"""One-time startup wiring. Idempotent — runs on every API boot."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text

from crv_core.db import session_factory


async def ensure_default_org() -> str:
    """Ensure a single 'default' org exists so the UI has something to hang off."""
    async with session_factory()() as db:
        existing = (await db.execute(
            text("SELECT id FROM organizations WHERE slug = 'default'")
        )).scalar_one_or_none()
        if existing:
            return str(existing)
        oid = str(uuid.uuid4())
        await db.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, 'Default', 'default')"),
            {"id": oid},
        )
        await db.commit()
        return oid


async def clean_stale_runs() -> int:
    """Mark any 'running' rows as failed — the process holding them is gone.

    Runs in-process asyncio tasks (baseline, ad-hoc review) get killed when
    uvicorn --reload restarts, when we crash, or when the pod is rescheduled.
    Their DB rows would otherwise sit at 'running' forever, blocking retries
    and lying to the UI. Wipe on boot."""
    err = json.dumps({"reason": "server_restarted",
                       "hint": "Task was interrupted (uvicorn reload, crash, or pod restart). Click Re-run."})
    async with session_factory()() as db:
        r = await db.execute(text("""
            UPDATE runs
               SET status = 'failed',
                   finished_at = COALESCE(finished_at, now()),
                   error = CAST(:e AS jsonb)
             WHERE status IN ('running', 'queued')
        """), {"e": err})
        await db.commit()
        return r.rowcount or 0
