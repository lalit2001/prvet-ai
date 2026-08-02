"""Webhook fan-out job.

M1: log-only. Marks webhook_events.processed_at.
M3: dispatch to pr_review / baseline / weekly per event_type.
"""
from __future__ import annotations

from sqlalchemy import text

from crv_core.db import session_factory


async def handle_forge_event(ctx, connection_id: str, external_event_id: str, event_type: str) -> dict:
    async with session_factory()() as db:
        await db.execute(
            text("""UPDATE webhook_events SET processed_at = now()
                    WHERE connection_id = :cid AND external_event_id = :eid"""),
            {"cid": connection_id, "eid": external_event_id},
        )
        await db.commit()
    # ponytail: real dispatch (pr_review vs baseline vs weekly) lands with M2/M3
    print(f"[handle_forge_event] connection={connection_id} event={event_type} id={external_event_id}")
    return {"connection_id": connection_id, "event_type": event_type, "external_event_id": external_event_id}
