"""Blast radius: who is affected when these symbols change. PRD §741.

BFS over symbol_references following to_symbol → from_symbol (reverse refs),
depth-limited and capped, scored so the review packs the most relevant callers first."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def symbols_touching(db: AsyncSession, repo_id: str, path: str, lines: set[int]) -> list[dict]:
    if not lines:
        return []
    rows = (await db.execute(text("""
        SELECT s.id::text, s.symbol_key, s.name, s.kind, s.visibility, s.signature,
               s.start_line, s.end_line, f.path
        FROM symbols s JOIN files f ON f.id = s.file_id
        WHERE s.repo_id = :rid AND f.path = :path
          AND s.start_line <= :hi AND s.end_line >= :lo
    """), {"rid": repo_id, "path": path, "lo": min(lines), "hi": max(lines)})).mappings().all()
    # innermost symbol per touched line wins; a class only counts if a line hits outside its methods
    out: dict[str, dict] = {}
    for line in lines:
        hits = [r for r in rows if r["start_line"] <= line <= r["end_line"]]
        if hits:
            best = min(hits, key=lambda r: r["end_line"] - r["start_line"])
            out[best["id"]] = dict(best)
    return list(out.values())


async def blast_radius(db: AsyncSession, repo_id: str, symbol_ids: list[str], depth: int = 2,
                       cap: int = 40, signature_changed: set[str] = frozenset()) -> list[dict]:
    if not symbol_ids:
        return []
    seen = set(symbol_ids)
    frontier = list(symbol_ids)
    out: list[dict] = []
    for d in range(1, depth + 1):
        if not frontier:
            break
        rows = (await db.execute(text("""
            SELECT DISTINCT ON (r.from_symbol_id, r.to_symbol_id)
                   r.from_symbol_id::text AS id, r.to_symbol_id::text AS target_id, r.line AS ref_line,
                   r.ref_kind, r.precision,
                   s.symbol_key, s.name, s.kind, s.visibility, s.signature, s.start_line, s.end_line,
                   f.path, t.name AS target_name, t.symbol_key AS target_key
            FROM symbol_references r
            JOIN symbols s ON s.id = r.from_symbol_id
            JOIN symbols t ON t.id = r.to_symbol_id
            JOIN files f ON f.id = s.file_id
            WHERE r.repo_id = :rid AND r.to_symbol_id = ANY(CAST(:ids AS uuid[]))
              AND r.from_symbol_id IS NOT NULL
        """), {"rid": repo_id, "ids": frontier})).mappings().all()
        frontier = []
        for r in rows:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            frontier.append(r["id"])
            score = (3 - d) * 2 + (2 if r["visibility"] == "public" else 0) \
                + (2 if r["target_id"] in signature_changed else 0) + (1 if r["precision"] != "heuristic" else 0)
            out.append({**dict(r), "depth": d, "score": score})
    out.sort(key=lambda r: (-r["score"], r["depth"], r["path"], r["start_line"]))
    return out[:cap]


async def callers_of(db: AsyncSession, repo_id: str, symbol_id: str) -> list[dict]:
    return await blast_radius(db, repo_id, [symbol_id], depth=1, cap=200)
