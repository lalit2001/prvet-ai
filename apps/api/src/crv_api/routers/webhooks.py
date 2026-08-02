"""Forge webhook handler. PRD F1.

Contract: return 202 within 500ms. No analysis inline. All work enqueued."""
from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text

from crv_adapters.forge import get_adapter
from crv_adapters.secrets import get_adapter as get_secrets
from crv_core.db import session_factory
from crv_core.queue import pool
from crv_core.settings import get_settings

router = APIRouter()


@router.post("/webhooks/{connection_id}", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(connection_id: UUID, request: Request):
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    async with session_factory()() as db:
        conn = (await db.execute(
            text("SELECT forge_type, webhook_secret_ref FROM forge_connections WHERE id = :id AND status = 'active'"),
            {"id": str(connection_id)},
        )).mappings().first()
        if conn is None:
            raise HTTPException(status_code=404, detail="unknown connection")

        adapter = get_adapter(conn["forge_type"])
        secrets = get_secrets(get_settings().secrets_backend)
        secret = await secrets.get(conn["webhook_secret_ref"])
        if not await adapter.verify_webhook(headers, body, secret):
            # AC1.1 — audit + 401, nothing enqueued
            await db.execute(
                text("""INSERT INTO audit_log (org_id, actor_type, action, resource_type, resource_id, metadata)
                        SELECT org_id, 'forge', 'webhook.signature_invalid', 'forge_connection', :cid::text, '{}'::jsonb
                        FROM forge_connections WHERE id = :cid"""),
                {"cid": str(connection_id)},
            )
            await db.commit()
            raise HTTPException(status_code=401, detail="invalid signature")

        external_event_id = headers.get("x-github-delivery") or headers.get("x-gitlab-event-uuid") or headers.get("x-request-id") or uuid.uuid4().hex
        event_type = headers.get("x-github-event") or headers.get("x-gitlab-event") or "unknown"
        payload_json = await request.json() if body else {}

        parsed = adapter.parse_event(headers, payload_json)
        if parsed is None:
            # AC1.4 — unknown events accepted, not enqueued
            return {"status": "accepted", "handled": False}

        # AC1.2 — dedupe on (connection_id, external_event_id)
        row = (await db.execute(
            text("""INSERT INTO webhook_events (id, connection_id, external_event_id, event_type, payload, signature_valid)
                    VALUES (:id, :cid, :eid, :et, :payload, true)
                    ON CONFLICT (connection_id, external_event_id) DO NOTHING
                    RETURNING id"""),
            {"id": str(uuid.uuid4()), "cid": str(connection_id), "eid": external_event_id,
             "et": event_type, "payload": _dumps(payload_json)},
        )).first()
        await db.commit()
        if row is None:
            return {"status": "accepted", "duplicate": True}

    p = await pool()
    job = await p.enqueue_job("handle_forge_event", str(connection_id), external_event_id, event_type)
    return {"status": "accepted", "job_id": job.job_id if job else None}


def _dumps(o) -> str:
    import json
    return json.dumps(o, separators=(",", ":"))
