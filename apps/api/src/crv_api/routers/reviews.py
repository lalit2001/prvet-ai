"""Ad-hoc code review. Fastest path to 'point an LLM at some code and see findings'.

Full PR-review with blast radius lands in M3."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from crv_core.db import session_factory
from crv_worker.analysis.llm_review import review

router = APIRouter()


class ReviewIn(BaseModel):
    code: str
    language: str | None = None
    context: str | None = None
    repo_id: str | None = None  # if set, findings are persisted; if not, just returned


class ReviewOut(BaseModel):
    summary: str
    findings: list[dict]
    error: str | None
    stats: dict


@router.post("/reviews/adhoc", response_model=ReviewOut)
async def adhoc_review(body: ReviewIn) -> ReviewOut:
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="code cannot be empty")

    run_id: str | None = None
    if body.repo_id:
        run_id = str(uuid.uuid4())
        async with session_factory()() as db:
            exists = (await db.execute(text("SELECT 1 FROM repositories WHERE id = :id"),
                                       {"id": body.repo_id})).scalar_one_or_none()
            if not exists:
                raise HTTPException(status_code=404, detail="repo not found")
            await db.execute(text("""
                INSERT INTO runs (id, repo_id, run_type, trigger, status, commit_sha,
                                  idempotency_key, started_at)
                VALUES (:id, :rid, 'manual', 'api', 'running', 'adhoc', :key, now())
            """), {"id": run_id, "rid": body.repo_id, "key": f"adhoc:{run_id}"})
            await db.commit()

    result = await review(body.code, body.language, body.context, run_id=run_id)

    if run_id and body.repo_id and not result.error:
        await _persist(body.repo_id, run_id, result.findings)
        await _close_run(run_id, "succeeded", result.stats)
    elif run_id:
        await _close_run(run_id, "failed", {"error": result.error, **result.stats})

    return ReviewOut(
        summary=result.summary,
        findings=result.findings,
        error=result.error,
        stats=result.stats,
    )


async def _persist(repo_id: str, run_id: str, findings: list[dict]) -> None:
    if not findings:
        return
    async with session_factory()() as db:
        for f in findings:
            fp = _fingerprint(f)
            await db.execute(text("""
                INSERT INTO findings (id, repo_id, run_id, fingerprint, source, category,
                                      severity, confidence, title, body, file_path,
                                      start_line, end_line, suggested_patch, status)
                VALUES (:id, :rid, :run, :fp, 'llm', :cat, :sev, :conf, :title, :body,
                        'adhoc', :sl, :el, :patch, 'open')
            """), {"id": str(uuid.uuid4()), "rid": repo_id, "run": run_id, "fp": fp,
                   "cat": f.get("category", "maintainability"), "sev": f.get("severity", "low"),
                   "conf": float(f.get("confidence", 0.6)), "title": f.get("title", "Untitled"),
                   "body": f.get("body", ""),
                   "sl": f.get("start_line"), "el": f.get("end_line"),
                   "patch": f.get("suggested_patch")})
        await db.commit()


async def _close_run(run_id: str, status: str, stats: dict) -> None:
    import json
    async with session_factory()() as db:
        await db.execute(text("""
            UPDATE runs SET status=:s, finished_at=now(),
                            stats=CAST(:stats AS jsonb) WHERE id=:id
        """), {"id": run_id, "s": status, "stats": json.dumps(stats, default=str)})
        await db.commit()


def _fingerprint(f: dict) -> str:
    import hashlib
    key = f"{f.get('title','')}:{f.get('category','')}:{f.get('body','')[:200]}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]
