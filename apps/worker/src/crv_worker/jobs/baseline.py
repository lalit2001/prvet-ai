"""Baseline job — PRD F4.

Two phases:
  1. INDEXING  — walk files, extract symbols (Python via ast; JS/TS via
                 tree-sitter), persist files + symbols.
  2. REVIEWING — pick top-K non-test files by LOC, LLM-review each,
                 persist findings. Respects BASELINE_MAX_COST_USD.

Progress is written back into runs.stats after each file so the UI can poll.
Deferred: git clone from URL (caller supplies local_path), snapshot archive,
metrics (complexity, coupling), embeddings.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from crv_core.db import session_factory
from crv_core.settings import get_settings
from crv_worker.analysis.llm_review import review as llm_review, summarize_project
from crv_worker.indexing import pyast, treesitter
from crv_worker.indexing.persist import replace_symbols, upsert_file
from crv_worker.indexing.walker import walk

# Rough per-call cost estimate (USD) — used for the budget cap before we have
# real token accounting for the deep model wired in. Update when the pricing
# table in llm_review lands.
_COST_PER_HOTSPOT_USD = 0.05


def _lang_for(path: Path) -> str | None:
    if path.suffix == ".py":
        return "python"
    return treesitter.lang_for(path)


def _extract(path: Path, mkey: str, lang: str):
    if lang == "python":
        return pyast.extract_symbols(path, mkey)
    return treesitter.extract_symbols(path, mkey)


def _is_testy(rel_path: str) -> bool:
    p = rel_path.lower()
    return any(seg in p for seg in ("/test", "test/", "/tests/", "/spec/", ".test.", ".spec.", "__tests__"))


async def _write_stats(run_id: str, stats: dict) -> None:
    async with session_factory()() as db:
        await db.execute(text("""
            UPDATE runs SET stats = CAST(:s AS jsonb) WHERE id = :id
        """), {"id": run_id, "s": json.dumps(stats, default=str)})
        await db.commit()


async def run(ctx, repo_id: str, local_path: str, commit_sha: str,
              force: bool = False) -> dict:
    root = Path(local_path).resolve()
    if not root.is_dir():
        return {"status": "failed", "error": f"not a directory: {root}"}

    settings = get_settings()
    key = f"baseline:v2:{repo_id}:{commit_sha}"

    if force:
        async with session_factory()() as db:
            await db.execute(text("DELETE FROM runs WHERE idempotency_key = :key"), {"key": key})
            await db.commit()

    async with session_factory()() as db:
        existing = (await db.execute(text("""
            SELECT r.id::text AS run_id, r.stats, b.id::text AS baseline_id
            FROM runs r LEFT JOIN baselines b ON b.run_id = r.id
            WHERE r.idempotency_key = :key AND r.status = 'succeeded'
        """), {"key": key})).mappings().one_or_none()
        if existing:
            s = existing["stats"] or {}
            return {"status": "succeeded", "cached": True,
                    "run_id": existing["run_id"], "baseline_id": existing["baseline_id"],
                    "files_seen": s.get("files_seen", 0),
                    "files_indexed": s.get("files_indexed", 0),
                    "symbols": s.get("symbols", 0),
                    "by_language": s.get("by_language", {}),
                    "findings": s.get("findings", 0)}

    run_id = str(uuid.uuid4())
    stats: dict = {
        "phase": "indexing",
        "files_seen": 0, "files_indexed": 0, "files_skipped": 0,
        "symbols": 0, "by_language": {},
        "hotspots_total": 0, "hotspots_done": 0,
        "findings": 0, "cost_usd": 0.0,
    }
    started = datetime.now(timezone.utc)

    async with session_factory()() as db:
        await db.execute(text("""
            INSERT INTO runs (id, repo_id, run_type, trigger, status, commit_sha,
                              idempotency_key, started_at, stats)
            VALUES (:id, :rid, 'baseline', 'api', 'running', :sha, :key, now(), CAST(:s AS jsonb))
        """), {"id": run_id, "rid": repo_id, "sha": commit_sha, "key": key,
                "s": json.dumps(stats, default=str)})
        await db.commit()

    try:
        return await _do_baseline(run_id, repo_id, commit_sha, root, stats, started, settings)
    except asyncio.CancelledError:
        await _mark_failed(run_id, "task cancelled — process restart? see plan.md dev notes")
        raise
    except Exception as e:
        import traceback
        await _mark_failed(run_id, f"{type(e).__name__}: {e}\n" + traceback.format_exc()[:1500])
        return {"status": "failed", "run_id": run_id, "error": str(e), **stats}


async def _mark_failed(run_id: str, err_msg: str) -> None:
    try:
        async with session_factory()() as db:
            await db.execute(text("""
                UPDATE runs SET status='failed', finished_at=now(),
                                error=CAST(:e AS jsonb)
                  WHERE id=:id
            """), {"id": run_id, "e": json.dumps({"message": err_msg})})
            await db.commit()
    except Exception as inner:
        print(f"[baseline] failed to mark run {run_id} as failed: {inner}")


async def _do_baseline(run_id: str, repo_id: str, commit_sha: str,
                        root: Path, stats: dict, started: datetime, settings) -> dict:
    # ── Phase 1: index ─────────────────────────────────────────────────────
    indexed: list[dict] = []  # for hotspot ranking
    async with session_factory()() as db:
        write_every = 20
        i = 0
        for path in walk(root):
            stats["files_seen"] += 1
            lang = _lang_for(path)
            if lang is None:
                stats["files_skipped"] += 1
                continue
            rel = str(path.relative_to(root))
            try:
                body = path.read_text(errors="replace")
                loc = body.count("\n") + 1
                mkey = pyast.module_key_for(path, root)
                syms = _extract(path, mkey, lang)
                file_id = await upsert_file(db, repo_id, rel, lang, pyast.content_hash(path), loc, commit_sha)
                await replace_symbols(db, repo_id, file_id, syms)
                stats["files_indexed"] += 1
                stats["symbols"] += len(syms)
                stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
                indexed.append({"path": rel, "loc": loc, "lang": lang})
                i += 1
                if i % write_every == 0:
                    await db.commit()
                    await _write_stats(run_id, stats)
            except Exception as e:
                print(f"[baseline] skipped {rel}: {e}")
        await db.commit()

    # ── Phase 2: hotspot LLM review ────────────────────────────────────────
    stats["phase"] = "reviewing"
    hotspot_count = _hotspot_count(indexed)
    hotspots = _pick_hotspots(indexed, hotspot_count)
    stats["hotspots_total"] = len(hotspots)
    await _write_stats(run_id, stats)

    max_cost = float(settings.baseline_max_cost_usd)
    for hs in hotspots:
        if stats["cost_usd"] + _COST_PER_HOTSPOT_USD > max_cost:
            print(f"[baseline] budget hit ({stats['cost_usd']:.2f}/{max_cost} USD); stopping hotspot review")
            break
        p = root / hs["path"]
        try:
            body = p.read_text(errors="replace")
            if len(body) > 60_000:  # skip huge single files
                stats["hotspots_done"] += 1
                await _write_stats(run_id, stats)
                continue
            result = await llm_review(
                code=body,
                language=hs["lang"],
                context=f"Baseline hotspot: {hs['path']} ({hs['loc']} LOC)",
                run_id=run_id,
            )
            if result.error:
                print(f"[baseline] hotspot {hs['path']}: {result.error}")
            else:
                await _persist_findings(repo_id, run_id, hs["path"], result.findings)
                stats["findings"] += len(result.findings)
                # Bump cost estimate; token-based math lands with cost accounting M3
                stats["cost_usd"] += _COST_PER_HOTSPOT_USD
        except Exception as e:
            print(f"[baseline] hotspot review of {hs['path']} failed: {e}")
        stats["hotspots_done"] += 1
        await _write_stats(run_id, stats)

    # ── Phase 3: LLM project summary ───────────────────────────────────────
    stats["phase"] = "summarizing"
    await _write_stats(run_id, stats)
    stats["summary"] = await _project_summary(root, indexed, stats, run_id)

    # ── Finalize ───────────────────────────────────────────────────────────
    stats["phase"] = "done"
    baseline_id = str(uuid.uuid4())
    finished = datetime.now(timezone.utc)
    async with session_factory()() as db:
        await db.execute(text("""
            UPDATE baselines SET is_current = false WHERE repo_id = :rid AND is_current = true
        """), {"rid": repo_id})
        await db.execute(text("""
            INSERT INTO baselines (id, repo_id, run_id, commit_sha, storage_uri, metrics,
                                   finding_count, is_current)
            VALUES (:id, :rid, :run_id, :sha, :uri, CAST(:m AS jsonb), :fc, true)
        """), {"id": baseline_id, "rid": repo_id, "run_id": run_id,
                "sha": commit_sha, "uri": f"baselines/{repo_id}/{commit_sha}/",
                "m": json.dumps(stats, default=str), "fc": stats["findings"]})
        await db.execute(text("""
            UPDATE runs SET status='succeeded', finished_at=:fin,
                            duration_ms=:dur, stats=CAST(:s AS jsonb)
            WHERE id=:id
        """), {"id": run_id, "fin": finished,
                "dur": int((finished - started).total_seconds() * 1000),
                "s": json.dumps(stats, default=str)})
        await db.commit()

    return {"status": "succeeded", "run_id": run_id, "baseline_id": baseline_id, **stats}


def _hotspot_count(indexed: list[dict]) -> int:
    # Small default for dev; can be raised in repo config later.
    # ponytail: 5 is enough to prove the loop works without burning $$.
    if not indexed:
        return 0
    return min(5, len(indexed))


def _pick_hotspots(indexed: list[dict], k: int) -> list[dict]:
    # Filter out test-y files and prefer larger, non-trivial files.
    # LOC as a proxy for hotspot importance until we have churn + fan-in.
    candidates = [f for f in indexed if not _is_testy(f["path"]) and f["loc"] >= 40]
    candidates.sort(key=lambda f: (-f["loc"], f["path"]))
    return candidates[:k]


async def _project_summary(root: Path, indexed: list[dict], stats: dict, run_id: str) -> str:
    """Ask the LLM for a short project overview. Fails gracefully → empty string."""
    if not indexed:
        return ""
    total_loc = sum(f["loc"] for f in indexed)
    by_lang = stats.get("by_language", {})
    top = sorted(indexed, key=lambda f: -f["loc"])[:20]
    # Read the README if present for context
    readme_body = ""
    for name in ("README.md", "README.rst", "README.txt", "readme.md"):
        p = root / name
        if p.exists():
            try:
                readme_body = p.read_text(errors="replace")[:4000]
                break
            except OSError:
                pass

    prompt = (
        "You are summarising a codebase for its owner. Return 4-6 sentences of "
        "markdown covering: what the project appears to be, primary language(s), "
        "notable modules, and one or two concrete improvement suggestions. "
        "No headings, no bullet lists, plain prose.\n\n"
        f"Repo root: {root.name}\n"
        f"Languages: {by_lang}\n"
        f"Total files indexed: {stats.get('files_indexed', 0)} · LOC: {total_loc}\n"
        f"Top files by size:\n" +
        "\n".join(f"  - {f['path']} ({f['loc']} LOC, {f['lang']})" for f in top) +
        (f"\n\nREADME excerpt:\n---\n{readme_body}\n---" if readme_body else "")
    )
    try:
        return await summarize_project(prompt, run_id=run_id)
    except Exception as e:
        return f"_summary failed: {e}_"


async def _persist_findings(repo_id: str, run_id: str, file_path: str, findings: list[dict]) -> None:
    if not findings:
        return
    import hashlib
    async with session_factory()() as db:
        for f in findings:
            fp = hashlib.sha256(f"{file_path}:{f.get('title','')}:{f.get('category','')}".encode()).hexdigest()[:16]
            await db.execute(text("""
                INSERT INTO findings (id, repo_id, run_id, fingerprint, source, category,
                                      severity, confidence, title, body, file_path,
                                      start_line, end_line, suggested_patch, status)
                VALUES (:id, :rid, :run, :fp, 'llm', :cat, :sev, :conf, :title, :body,
                        :file, :sl, :el, :patch, 'open')
            """), {"id": str(uuid.uuid4()), "rid": repo_id, "run": run_id, "fp": fp,
                    "cat": f.get("category", "maintainability"), "sev": f.get("severity", "low"),
                    "conf": float(f.get("confidence", 0.6)), "title": f.get("title", "Untitled"),
                    "body": f.get("body", ""), "file": file_path,
                    "sl": f.get("start_line"), "el": f.get("end_line"),
                    "patch": f.get("suggested_patch")})
        await db.commit()
