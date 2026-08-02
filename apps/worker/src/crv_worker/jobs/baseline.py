"""Baseline job — PRD F4.

M2 slice: walk → parse Python → persist files + symbols → insert baseline row.
Deferred to M3: git clone (currently takes a local path), snapshot archive to
object store, metrics computation, hotspot ranking + LLM review, embeddings."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from crv_core.db import session_factory
from crv_worker.indexing.persist import replace_symbols, upsert_file
from crv_worker.indexing.pyast import content_hash, extract_symbols, module_key_for
from crv_worker.indexing.walker import walk


async def run(ctx, repo_id: str, local_path: str, commit_sha: str) -> dict:
    root = Path(local_path).resolve()
    if not root.is_dir():
        return {"status": "failed", "error": f"not a directory: {root}"}

    run_id = str(uuid.uuid4())
    stats = {"files_seen": 0, "files_indexed": 0, "symbols": 0}
    started = datetime.now(timezone.utc)

    async with session_factory()() as db:
        # Idempotency: same repo+commit → return the existing baseline. PRD F4.
        existing = (await db.execute(text("""
            SELECT r.id::text AS run_id, r.stats, b.id::text AS baseline_id
            FROM runs r LEFT JOIN baselines b ON b.run_id = r.id
            WHERE r.idempotency_key = :key AND r.status = 'succeeded'
        """), {"key": f"baseline:{repo_id}:{commit_sha}"})).mappings().one_or_none()
        if existing:
            s = existing["stats"] or {}
            return {"status": "succeeded", "cached": True,
                    "run_id": existing["run_id"], "baseline_id": existing["baseline_id"],
                    "files_indexed": s.get("files_indexed", 0), "symbols": s.get("symbols", 0)}

        await db.execute(text("""
            INSERT INTO runs (id, repo_id, run_type, trigger, status, commit_sha,
                              idempotency_key, started_at, stats)
            VALUES (:id, :rid, 'baseline', 'api', 'running', :sha, :key, now(), '{}')
        """), {"id": run_id, "rid": repo_id, "sha": commit_sha,
               "key": f"baseline:{repo_id}:{commit_sha}"})
        await db.commit()

        for path in walk(root):
            stats["files_seen"] += 1
            if path.suffix != ".py":
                continue  # M3 extends to .ts/.tsx/.js/.java/.go via tree-sitter
            rel = str(path.relative_to(root))
            try:
                text_body = path.read_text(errors="replace")
                loc = text_body.count("\n") + 1
                mkey = module_key_for(path, root)
                syms = extract_symbols(path, mkey)
                file_id = await upsert_file(db, repo_id, rel, "python", content_hash(path), loc, commit_sha)
                await replace_symbols(db, repo_id, file_id, syms)
                stats["files_indexed"] += 1
                stats["symbols"] += len(syms)
            except Exception as e:  # single file failure never fails the run — AC3.6
                print(f"[baseline] skipped {rel}: {e}")
        await db.commit()

        baseline_id = str(uuid.uuid4())
        await db.execute(text("""
            UPDATE baselines SET is_current = false WHERE repo_id = :rid AND is_current = true
        """), {"rid": repo_id})
        await db.execute(text("""
            INSERT INTO baselines (id, repo_id, run_id, commit_sha, storage_uri, metrics,
                                   finding_count, is_current)
            VALUES (:id, :rid, :run_id, :sha, :uri, :metrics, 0, true)
        """), {"id": baseline_id, "rid": repo_id, "run_id": run_id,
               "sha": commit_sha, "uri": f"baselines/{repo_id}/{commit_sha}/",
               "metrics": _dumps({"loc_total": sum(1 for _ in walk(root)), **stats})})
        finished = datetime.now(timezone.utc)
        await db.execute(text("""
            UPDATE runs SET status='succeeded', finished_at=:fin,
                            duration_ms=:dur, stats=:stats
            WHERE id=:id
        """), {"id": run_id, "fin": finished,
               "dur": int((finished - started).total_seconds() * 1000),
               "stats": _dumps(stats)})
        await db.commit()

    return {"status": "succeeded", "run_id": run_id, "baseline_id": baseline_id, **stats}


def _dumps(o) -> str:
    import json
    return json.dumps(o, separators=(",", ":"))
