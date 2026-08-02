"""Repos endpoints. UI calls these — CLI does not (see plan.md §C5)."""
from __future__ import annotations

import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from crv_core.db import session_factory

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
        # Store the local_path in config for the baseline trigger to find later.
        await db.execute(text("UPDATE repositories SET config = jsonb_set(config, '{local_path}', to_jsonb(CAST(:p AS text))) WHERE id = :id"),
                         {"p": str(root), "id": repo_id})
        await db.commit()
        row = (await db.execute(text("""
            SELECT id::text, full_name, clone_url, default_branch, is_enabled
            FROM repositories WHERE id = :id
        """), {"id": repo_id})).mappings().one()
    return RepoOut(**row)


@router.post("/repos/{repo_id}/baseline", response_model=TriggerOut)
async def trigger_baseline(repo_id: str) -> TriggerOut:
    # ponytail: sync execution for the compose/local target — no queue round-trip needed
    # since the API and worker share a Python process at dev-time. Enqueue via arq
    # when the UI needs to fire-and-forget on big repos.
    async with session_factory()() as db:
        row = (await db.execute(text("""
            SELECT config->>'local_path' AS lp FROM repositories WHERE id = :id
        """), {"id": repo_id})).mappings().one_or_none()
    if row is None or not row["lp"]:
        raise HTTPException(status_code=404, detail="repo not found or missing local_path")
    local_path = row["lp"]
    sha = _head_sha(local_path)

    from crv_worker.jobs.baseline import run as baseline_run
    result = await baseline_run(None, repo_id=repo_id, local_path=local_path, commit_sha=sha)
    if result["status"] != "succeeded":
        raise HTTPException(status_code=500, detail=result)
    return TriggerOut(run_id=result["run_id"], baseline_id=result["baseline_id"],
                      files_indexed=result["files_indexed"], symbols=result["symbols"])


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


def _head_sha(local_path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", local_path, "rev-parse", "HEAD"], text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "HEAD-dev"
