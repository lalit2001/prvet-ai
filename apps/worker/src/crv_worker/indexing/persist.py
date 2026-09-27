"""Upsert files, symbols, symbol_references, file_imports. Raw SQL — no ORM
class needed for this write path. Per-file delete+insert keeps reindexing simple."""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from crv_worker.indexing.pyast import ExtractedSymbol


async def upsert_file(
    db: AsyncSession, repo_id: str, rel_path: str, language: str | None,
    content_sha: str, loc: int, at_sha: str,
) -> str:
    row = (await db.execute(text("""
        INSERT INTO files (id, repo_id, path, language, content_hash, loc, indexed_at_sha, updated_at)
        VALUES (:id, :rid, :path, :lang, :sha, :loc, :at, now())
        ON CONFLICT (repo_id, path) DO UPDATE
          SET language=EXCLUDED.language, content_hash=EXCLUDED.content_hash,
              loc=EXCLUDED.loc, indexed_at_sha=EXCLUDED.indexed_at_sha, updated_at=now()
        RETURNING id
    """), {"id": str(uuid.uuid4()), "rid": repo_id, "path": rel_path,
           "lang": language, "sha": content_sha, "loc": loc, "at": at_sha})).scalar_one()
    return str(row)


async def replace_symbols(
    db: AsyncSession, repo_id: str, file_id: str, symbols: list[ExtractedSymbol],
) -> None:
    # Files can gain/lose symbols across runs; simplest correct thing is delete + insert.
    # ponytail: ok up to ~1k symbols/file; upgrade to per-symbol diff if that ever hurts.
    await db.execute(text("DELETE FROM symbols WHERE file_id = :fid"), {"fid": file_id})
    if not symbols:
        return
    await db.execute(text("""
        INSERT INTO symbols (id, repo_id, file_id, symbol_key, name, kind, signature,
                             visibility, start_line, end_line, docstring, precision)
        VALUES (:id, :rid, :fid, :key, :name, :kind, :sig, :vis, :sl, :el, :doc, 'heuristic')
        ON CONFLICT (repo_id, symbol_key) DO UPDATE
          SET file_id=EXCLUDED.file_id, kind=EXCLUDED.kind, signature=EXCLUDED.signature,
              visibility=EXCLUDED.visibility, start_line=EXCLUDED.start_line,
              end_line=EXCLUDED.end_line, docstring=EXCLUDED.docstring
    """), [{"id": str(uuid.uuid4()), "rid": repo_id, "fid": file_id,
            "key": s.symbol_key, "name": s.name, "kind": s.kind,
            "sig": s.signature, "vis": s.visibility,
            "sl": s.start_line, "el": s.end_line, "doc": s.docstring}
           for s in symbols])


async def load_symbol_ids(db: AsyncSession, repo_id: str) -> dict[str, str]:
    rows = await db.execute(text("SELECT symbol_key, id::text FROM symbols WHERE repo_id = :rid"), {"rid": repo_id})
    return {k: i for k, i in rows.all()}


async def replace_references(db: AsyncSession, repo_id: str, file_id: str,
                             edges: list, key_to_id: dict[str, str]) -> int:
    await db.execute(text("DELETE FROM symbol_references WHERE file_id = :fid"), {"fid": file_id})
    rows = [{"id": str(uuid.uuid4()), "rid": repo_id, "fid": file_id,
             "frm": key_to_id.get(e.from_key) if e.from_key else None,
             "to": key_to_id.get(e.to_key), "line": e.line, "kind": e.kind, "prec": e.precision}
            for e in edges]
    rows = [r for r in rows if r["to"]]
    if rows:
        await db.execute(text("""
            INSERT INTO symbol_references (id, repo_id, from_symbol_id, to_symbol_id, file_id, line, ref_kind, precision)
            VALUES (:id, :rid, :frm, :to, :fid, :line, :kind, :prec)
        """), rows)
    return len(rows)


async def replace_file_imports(db: AsyncSession, repo_id: str, file_id: str,
                               targets: list[tuple[str, int, str]], path_to_file_id: dict[str, str]) -> int:
    await db.execute(text("DELETE FROM file_imports WHERE from_file_id = :fid"), {"fid": file_id})
    rows = [{"id": str(uuid.uuid4()), "rid": repo_id, "frm": file_id, "to": path_to_file_id.get(rel),
             "line": line, "spec": spec} for rel, line, spec in targets]
    rows = [r for r in rows if r["to"]]
    if rows:
        await db.execute(text("""
            INSERT INTO file_imports (id, repo_id, from_file_id, to_file_id, line, specifier)
            VALUES (:id, :rid, :frm, :to, :line, :spec)
        """), rows)
    return len(rows)


async def update_ref_stats(db: AsyncSession, file_id: str, resolved: int, unresolved: int) -> None:
    await db.execute(text("UPDATE files SET resolved_refs = :r, unresolved_refs = :u WHERE id = :fid"),
                     {"r": resolved, "u": unresolved, "fid": file_id})
