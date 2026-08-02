"""Upsert files + symbols. Raw SQL — no ORM class needed for this write path.

The M3 blast-radius query joins on symbol_references, which we start adding
when the JS/TS extractor lands with real cross-file references."""
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
