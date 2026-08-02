"""Admin utility endpoints — LLM connectivity test, recent runs, audit log."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from crv_adapters.llm import LlmError, client_from_org
from crv_core.db import session_factory

router = APIRouter()


class LlmTestOut(BaseModel):
    ok: bool
    model: str
    latency_ms: int | None
    error: str | None


@router.post("/admin/llm/test", response_model=LlmTestOut)
async def llm_test() -> LlmTestOut:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(settings->'providers', '[]'::jsonb) AS ps FROM organizations WHERE slug='default'"
        ))).mappings().one()
    providers = list(row["ps"] or [])
    try:
        client = client_from_org(providers, timeout_s=15)
        resp = await client.chat(
            "fast",  # resolves via role_map
            [{"role": "user", "content": "Reply with the single word: pong."}],
            temperature=0.0,
        )
        return LlmTestOut(ok=True, model=resp.model, latency_ms=resp.latency_ms, error=None)
    except LlmError as e:
        return LlmTestOut(ok=False, model="?", latency_ms=None, error=str(e))


@router.get("/runs")
async def recent_runs(limit: int = 25) -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT r.id::text, r.repo_id::text, repo.full_name AS repo,
                   r.run_type, r.status, r.commit_sha, r.duration_ms, r.stats,
                   r.created_at, r.finished_at
            FROM runs r JOIN repositories repo ON repo.id = r.repo_id
            ORDER BY r.created_at DESC LIMIT :limit
        """), {"limit": limit})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/audit")
async def recent_audit(limit: int = 100) -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT id, actor_type, actor_id, action, resource_type, resource_id,
                   metadata, ip_address, created_at
            FROM audit_log ORDER BY created_at DESC LIMIT :limit
        """), {"limit": limit})).mappings().all()
    return [dict(r) for r in rows]
