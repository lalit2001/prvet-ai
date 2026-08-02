"""One-time startup wiring. Idempotent — runs on every API boot."""
from __future__ import annotations

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
