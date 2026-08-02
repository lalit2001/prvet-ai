"""Baseline job — PRD F4.

Multi-language via dispatch: pyast for Python, tree-sitter for JS/TS/TSX.
Deferred: git clone (caller supplies local_path), snapshot archive, metrics,
hotspot ranking + LLM review, embeddings."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from crv_core.db import session_factory
from crv_worker.indexing import pyast, treesitter
from crv_worker.indexing.persist import replace_symbols, upsert_file
from crv_worker.indexing.walker import walk


def _lang_for(path: Path) -> str | None:
    if path.suffix == ".py":
        return "python"
    return treesitter.lang_for(path)


def _extract(path: Path, mkey: str, lang: str):
    if lang == "python":
        return pyast.extract_symbols(path, mkey)
    return treesitter.extract_symbols(path, mkey)


async def run(ctx, repo_id: str, local_path: str, commit_sha: str) -> dict:
    root = Path(local_path).resolve()
    if not root.is_dir():
        return {"status": "failed", "error": f"not a directory: {root}"}

    run_id = str(uuid.uuid4())
    stats: dict = {"files_seen": 0, "files_indexed": 0, "files_skipped": 0,
                   "symbols": 0, "by_language": {}}
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
                    "files_seen": s.get("files_seen", 0),
                    "files_indexed": s.get("files_indexed", 0),
                    "symbols": s.get("symbols", 0),
                    "by_language": s.get("by_language", {})}

        await db.execute(text("""
            INSERT INTO runs (id, repo_id, run_type, trigger, status, commit_sha,
                              idempotency_key, started_at, stats)
            VALUES (:id, :rid, 'baseline', 'api', 'running', :sha, :key, now(), '{}')
        """), {"id": run_id, "rid": repo_id, "sha": commit_sha,
               "key": f"baseline:{repo_id}:{commit_sha}"})
        await db.commit()

        for path in walk(root):
            stats["files_seen"] += 1
            lang = _lang_for(path)
            if lang is None:
                stats["files_skipped"] += 1
                continue
            rel = str(path.relative_to(root))
            try:
                text_body = path.read_text(errors="replace")
                loc = text_body.count("\n") + 1
                mkey = pyast.module_key_for(path, root)
                syms = _extract(path, mkey, lang)
                file_id = await upsert_file(db, repo_id, rel, lang, pyast.content_hash(path), loc, commit_sha)
                await replace_symbols(db, repo_id, file_id, syms)
                stats["files_indexed"] += 1
                stats["symbols"] += len(syms)
                stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
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
               "metrics": _dumps(stats)})
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
