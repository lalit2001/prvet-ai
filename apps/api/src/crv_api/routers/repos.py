"""Repos endpoints. UI calls these — CLI does not (see plan.md §C5)."""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from crv_core.db import session_factory
from crv_core.settings import get_settings

router = APIRouter()


class LocalRepoIn(BaseModel):
    name: str
    local_path: str


class RepoOut(BaseModel):
    id: str
    full_name: str
    clone_url: str
    default_branch: str
    is_enabled: bool


class TriggerOut(BaseModel):
    run_id: str
    baseline_id: str
    files_indexed: int
    symbols: int
    cached: bool = False


@router.get("/repos", response_model=list[RepoOut])
async def list_repos() -> list[RepoOut]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT id::text, full_name, clone_url, default_branch, is_enabled
            FROM repositories ORDER BY created_at DESC
        """))).mappings().all()
    return [RepoOut(**r) for r in rows]


@router.post("/repos/local", response_model=RepoOut, status_code=201)
async def create_local_repo(body: LocalRepoIn) -> RepoOut:
    root = Path(body.local_path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"not a directory: {root}")

    async with session_factory()() as db:
        org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
        # Reuse or create a local-fs pseudo connection so the FK holds.
        conn_id = (await db.execute(text("""
            SELECT id FROM forge_connections WHERE org_id = :org AND forge_type = 'local'
        """), {"org": str(org_id)})).scalar_one_or_none()
        if not conn_id:
            conn_id = uuid.uuid4()
            await db.execute(text("""
                INSERT INTO forge_connections (id, org_id, forge_type, base_url, display_name,
                                               credential_ref, webhook_secret_ref)
                VALUES (:id, :org, 'local', 'file://', 'Local filesystem', 'unused', 'unused')
            """), {"id": str(conn_id), "org": str(org_id)})

        repo_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO repositories (id, org_id, connection_id, external_id, full_name,
                                       clone_url, default_branch, primary_language)
            VALUES (:id, :org, :cid, :ext, :name, :url, 'main', 'python')
            ON CONFLICT (connection_id, external_id) DO UPDATE
              SET full_name = EXCLUDED.full_name
            RETURNING id::text, full_name, clone_url, default_branch, is_enabled
        """), {"id": repo_id, "org": str(org_id), "cid": str(conn_id),
               "ext": str(root), "name": body.name, "url": f"file://{root}"})
        await db.execute(text("UPDATE repositories SET config = jsonb_set(config, '{local_path}', to_jsonb(CAST(:p AS text))) WHERE id = :id"),
                         {"p": str(root), "id": repo_id})
        await db.commit()
        row = (await db.execute(text("""
            SELECT id::text, full_name, clone_url, default_branch, is_enabled
            FROM repositories WHERE id = :id
        """), {"id": repo_id})).mappings().one()
    return RepoOut(**row)


@router.delete("/repos/{repo_id}", status_code=204)
async def delete_repo(repo_id: str) -> None:
    async with session_factory()() as db:
        r = await db.execute(text("DELETE FROM repositories WHERE id = :id"), {"id": repo_id})
        if r.rowcount == 0:
            raise HTTPException(404, "repo not found")
        await db.commit()


@router.post("/repos/{repo_id}/baseline", response_model=TriggerOut)
async def trigger_baseline(repo_id: str) -> TriggerOut:
    """Local repos: use config.local_path.
    GitHub repos: shallow-clone into a working dir under STORAGE_URI, then baseline."""
    async with session_factory()() as db:
        row = (await db.execute(text("""
            SELECT r.full_name, r.clone_url, r.default_branch, r.config,
                   r.connection_id::text AS connection_id,
                   c.forge_type, c.capabilities
            FROM repositories r JOIN forge_connections c ON c.id = r.connection_id
            WHERE r.id = :id
        """), {"id": repo_id})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "repo not found")

    cfg = row["config"] or {}
    local_path = cfg.get("local_path")

    # GitHub → clone on demand (or reuse cached clone dir)
    if not local_path and row["forge_type"] == "github":
        caps = row["capabilities"] or {}
        token = caps.get("dev_token")
        if not token:
            raise HTTPException(400, "GitHub connection is missing a token — reconnect it")
        try:
            local_path = _clone_or_pull(repo_id, row["full_name"], row["default_branch"], token)
        except subprocess.CalledProcessError as e:
            raise HTTPException(500, f"git clone/pull failed: {e.stderr.decode(errors='replace')[:400] if isinstance(e.stderr, (bytes, bytearray)) else str(e)[:400]}")
        # Cache the path so re-runs skip the clone
        async with session_factory()() as db:
            await db.execute(text("""
                UPDATE repositories
                  SET config = jsonb_set(COALESCE(config, '{}'::jsonb),
                                          '{local_path}', to_jsonb(CAST(:p AS text)))
                  WHERE id = :id
            """), {"p": local_path, "id": repo_id})
            await db.commit()

    if not local_path:
        raise HTTPException(400, f"cannot baseline {row['forge_type']} repos yet — set a local_path")

    sha = _head_sha(local_path)
    from crv_worker.jobs.baseline import run as baseline_run
    result = await baseline_run(None, repo_id=repo_id, local_path=local_path, commit_sha=sha)
    if result["status"] != "succeeded":
        raise HTTPException(500, result)
    return TriggerOut(
        run_id=result["run_id"], baseline_id=result["baseline_id"],
        files_indexed=result["files_indexed"], symbols=result["symbols"],
        cached=bool(result.get("cached")),
    )


@router.get("/repos/{repo_id}/findings")
async def list_findings(repo_id: str, limit: int = 100) -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT id::text, source, category, severity, title, body, file_path,
                   start_line, end_line, confidence, status, created_at
            FROM findings WHERE repo_id = :id
            ORDER BY created_at DESC LIMIT :limit
        """), {"id": repo_id, "limit": limit})).mappings().all()
    return [dict(r) for r in rows]


def _clone_or_pull(repo_id: str, full_name: str, branch: str, token: str) -> str:
    """Shallow-clone into STORAGE_URI/clones/<repo_id>. If already present, pull.
    ponytail: dev-only; production should use the SCIP/indexer runner container."""
    root = Path(get_settings().storage_uri).expanduser().resolve() / "clones" / repo_id
    url = f"https://x-access-token:{token}@github.com/{full_name}.git"
    if (root / ".git").is_dir():
        subprocess.run(["git", "-C", str(root), "fetch", "--depth", "1", "origin", branch],
                        check=True, capture_output=True)
        subprocess.run(["git", "-C", str(root), "reset", "--hard", f"origin/{branch}"],
                        check=True, capture_output=True)
    else:
        root.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", "--branch", branch, url, str(root)],
                        check=True, capture_output=True)
    return str(root)


def _head_sha(local_path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", local_path, "rev-parse", "HEAD"], text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "HEAD-dev"
