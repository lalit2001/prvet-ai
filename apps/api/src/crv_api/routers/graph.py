"""Code-graph read API: files, symbols, references, blast radius. Feeds the
Explorer and dashboard. All reads on indexed columns; nothing here writes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from crv_api.routers.auth import get_current_user, verify_repo_access
from crv_core.db import session_factory
from crv_worker.context.blast_radius import blast_radius

router = APIRouter()


@router.get("/repos/{repo_id}/graph/summary")
async def graph_summary(repo_id: str, user: dict = Depends(get_current_user)) -> dict:
    async with session_factory()() as db:
        await verify_repo_access(repo_id, user, db)
        counts = (await db.execute(text("""
            SELECT (SELECT count(*) FROM files WHERE repo_id = :rid) AS files,
                   (SELECT count(*) FROM symbols WHERE repo_id = :rid) AS symbols,
                   (SELECT count(*) FROM symbol_references WHERE repo_id = :rid) AS references,
                   (SELECT count(*) FROM file_imports WHERE repo_id = :rid) AS file_imports,
                   (SELECT sum(resolved_refs) FROM files WHERE repo_id = :rid) AS resolved,
                   (SELECT sum(unresolved_refs) FROM files WHERE repo_id = :rid) AS unresolved,
                   (SELECT max(updated_at)::text FROM files WHERE repo_id = :rid) AS indexed_at
        """), {"rid": repo_id})).mappings().one()
        by_lang = (await db.execute(text("""
            SELECT language, count(*) AS files, coalesce(sum(loc), 0) AS loc
            FROM files WHERE repo_id = :rid GROUP BY language ORDER BY files DESC
        """), {"rid": repo_id})).mappings().all()
        top_files = (await db.execute(text("""
            SELECT f.path, f.language, f.loc, count(fi.id) AS fan_in
            FROM files f LEFT JOIN file_imports fi ON fi.to_file_id = f.id
            WHERE f.repo_id = :rid GROUP BY f.id ORDER BY fan_in DESC, f.loc DESC LIMIT 10
        """), {"rid": repo_id})).mappings().all()
        top_symbols = (await db.execute(text("""
            SELECT s.id::text, s.symbol_key, s.name, s.kind, f.path, s.start_line, count(r.id) AS callers
            FROM symbols s JOIN files f ON f.id = s.file_id
            JOIN symbol_references r ON r.to_symbol_id = s.id
            WHERE s.repo_id = :rid GROUP BY s.id, f.path ORDER BY callers DESC LIMIT 10
        """), {"rid": repo_id})).mappings().all()
        kinds = (await db.execute(text("""
            SELECT kind, count(*) AS n FROM symbols WHERE repo_id = :rid GROUP BY kind ORDER BY n DESC
        """), {"rid": repo_id})).mappings().all()
    resolved, unresolved = int(counts["resolved"] or 0), int(counts["unresolved"] or 0)
    return {
        **{k: (int(v) if isinstance(v, int) else v) for k, v in dict(counts).items() if k not in ("resolved", "unresolved")},
        "resolved": resolved, "unresolved": unresolved,
        "resolution_rate": round(resolved / (resolved + unresolved), 3) if resolved + unresolved else None,
        "by_language": [dict(r) for r in by_lang],
        "symbol_kinds": [dict(r) for r in kinds],
        "top_files": [dict(r) for r in top_files],
        "top_symbols": [dict(r) for r in top_symbols],
    }


@router.get("/repos/{repo_id}/graph/files")
async def graph_files(repo_id: str, user: dict = Depends(get_current_user)) -> dict:
    async with session_factory()() as db:
        await verify_repo_access(repo_id, user, db)
        nodes = (await db.execute(text("""
            SELECT f.id::text, f.path, f.language, f.loc,
                   (SELECT count(*) FROM symbols s WHERE s.file_id = f.id) AS symbols,
                   (SELECT count(*) FROM file_imports i WHERE i.to_file_id = f.id) AS fan_in,
                   (SELECT count(*) FROM file_imports i WHERE i.from_file_id = f.id) AS fan_out
            FROM files f WHERE f.repo_id = :rid ORDER BY f.path
        """), {"rid": repo_id})).mappings().all()
        edges = (await db.execute(text("""
            SELECT from_file_id::text AS source, to_file_id::text AS target, count(*) AS weight
            FROM file_imports WHERE repo_id = :rid GROUP BY from_file_id, to_file_id
        """), {"rid": repo_id})).mappings().all()
    return {"nodes": [dict(n) for n in nodes], "edges": [dict(e) for e in edges]}


@router.get("/repos/{repo_id}/graph/file")
async def graph_file(repo_id: str, path: str, user: dict = Depends(get_current_user)) -> dict:
    async with session_factory()() as db:
        await verify_repo_access(repo_id, user, db)
        f = (await db.execute(text("""
            SELECT id::text, path, language, loc, indexed_at_sha, resolved_refs, unresolved_refs, updated_at::text
            FROM files WHERE repo_id = :rid AND path = :path
        """), {"rid": repo_id, "path": path})).mappings().one_or_none()
        if f is None:
            raise HTTPException(404, "file not indexed — run a baseline")
        symbols = (await db.execute(text("""
            SELECT s.id::text, s.symbol_key, s.name, s.kind, s.visibility, s.signature, s.docstring,
                   s.start_line, s.end_line,
                   (SELECT count(*) FROM symbol_references r WHERE r.to_symbol_id = s.id) AS callers,
                   (SELECT count(*) FROM symbol_references r WHERE r.from_symbol_id = s.id) AS callees
            FROM symbols s WHERE s.file_id = :fid ORDER BY s.start_line
        """), {"fid": f["id"]})).mappings().all()
        imports = (await db.execute(text("""
            SELECT t.path, t.id::text AS file_id, i.line, i.specifier
            FROM file_imports i JOIN files t ON t.id = i.to_file_id
            WHERE i.from_file_id = :fid ORDER BY i.line
        """), {"fid": f["id"]})).mappings().all()
        importers = (await db.execute(text("""
            SELECT s.path, s.id::text AS file_id, i.line, i.specifier
            FROM file_imports i JOIN files s ON s.id = i.from_file_id
            WHERE i.to_file_id = :fid ORDER BY s.path
        """), {"fid": f["id"]})).mappings().all()
        # references leaving this file, grouped by target file
        outgoing = (await db.execute(text("""
            SELECT tf.path, count(*) AS refs
            FROM symbol_references r JOIN symbols t ON t.id = r.to_symbol_id JOIN files tf ON tf.id = t.file_id
            WHERE r.file_id = :fid AND tf.id <> :fid GROUP BY tf.path ORDER BY refs DESC
        """), {"fid": f["id"]})).mappings().all()
        incoming = (await db.execute(text("""
            SELECT sf.path, count(*) AS refs
            FROM symbol_references r JOIN symbols t ON t.id = r.to_symbol_id JOIN files sf ON sf.id = r.file_id
            WHERE t.file_id = :fid AND sf.id <> :fid GROUP BY sf.path ORDER BY refs DESC
        """), {"fid": f["id"]})).mappings().all()
    return {"file": dict(f), "symbols": [dict(s) for s in symbols],
            "imports": [dict(i) for i in imports], "importers": [dict(i) for i in importers],
            "outgoing": [dict(o) for o in outgoing], "incoming": [dict(o) for o in incoming]}


@router.get("/repos/{repo_id}/symbols/search")
async def symbol_search(repo_id: str, q: str, limit: int = 30, user: dict = Depends(get_current_user)) -> list[dict]:
    q = q.strip()
    if len(q) < 2:
        return []
    async with session_factory()() as db:
        await verify_repo_access(repo_id, user, db)
        rows = (await db.execute(text("""
            SELECT s.id::text, s.symbol_key, s.name, s.kind, s.visibility, f.path, s.start_line, s.end_line,
                   (SELECT count(*) FROM symbol_references r WHERE r.to_symbol_id = s.id) AS callers
            FROM symbols s JOIN files f ON f.id = s.file_id
            WHERE s.repo_id = :rid AND (s.name ILIKE :pre OR s.symbol_key ILIKE :any)
            ORDER BY (s.name ILIKE :exact) DESC, (s.name ILIKE :pre) DESC, callers DESC, s.name LIMIT :lim
        """), {"rid": repo_id, "pre": f"{q}%", "any": f"%{q}%", "exact": q, "lim": limit})).mappings().all()
    return [dict(r) for r in rows]


@router.get("/repos/{repo_id}/symbols/{symbol_id}")
async def symbol_detail(repo_id: str, symbol_id: str, user: dict = Depends(get_current_user)) -> dict:
    async with session_factory()() as db:
        await verify_repo_access(repo_id, user, db)
        sym = (await db.execute(text("""
            SELECT s.id::text, s.symbol_key, s.name, s.kind, s.visibility, s.signature, s.docstring,
                   s.start_line, s.end_line, f.path
            FROM symbols s JOIN files f ON f.id = s.file_id WHERE s.id = :id AND s.repo_id = :rid
        """), {"id": symbol_id, "rid": repo_id})).mappings().one_or_none()
        if sym is None:
            raise HTTPException(404, "symbol not found")
        callers = (await db.execute(text("""
            SELECT r.line AS ref_line, r.ref_kind, r.precision, rf.path AS ref_path,
                   s.id::text, s.symbol_key, s.name, s.kind, s.start_line, s.end_line, sf.path
            FROM symbol_references r
            JOIN files rf ON rf.id = r.file_id
            LEFT JOIN symbols s ON s.id = r.from_symbol_id
            LEFT JOIN files sf ON sf.id = s.file_id
            WHERE r.to_symbol_id = :id ORDER BY rf.path, r.line
        """), {"id": symbol_id})).mappings().all()
        callees = (await db.execute(text("""
            SELECT r.line AS ref_line, r.ref_kind, r.precision,
                   t.id::text, t.symbol_key, t.name, t.kind, t.start_line, t.end_line, tf.path
            FROM symbol_references r JOIN symbols t ON t.id = r.to_symbol_id JOIN files tf ON tf.id = t.file_id
            WHERE r.from_symbol_id = :id ORDER BY r.line
        """), {"id": symbol_id})).mappings().all()
    return {"symbol": dict(sym), "callers": [dict(c) for c in callers], "callees": [dict(c) for c in callees]}


@router.get("/repos/{repo_id}/symbols/{symbol_id}/blast")
async def symbol_blast(repo_id: str, symbol_id: str, depth: int = 2, cap: int = 60,
                       user: dict = Depends(get_current_user)) -> list[dict]:
    async with session_factory()() as db:
        await verify_repo_access(repo_id, user, db)
        return await blast_radius(db, repo_id, [symbol_id], depth=min(depth, 4), cap=min(cap, 200))
