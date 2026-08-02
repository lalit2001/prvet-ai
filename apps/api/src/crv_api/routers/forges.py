"""Forge connections — start with GitHub PAT flow. GitHub App + OAuth land in M4.

Flow:
  1. UI POST /forges/github with a PAT → we verify (GET /user), store connection.
  2. UI GET  /forges/{id}/repos          → list user's GitHub repos via that token.
  3. UI POST /forges/{id}/repos/enable   → create a repositories row + register webhook.
"""
from __future__ import annotations

import json
import secrets as _secrets
import uuid

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from crv_core.db import session_factory

router = APIRouter()

_GH = "https://api.github.com"


class GitHubConnectIn(BaseModel):
    token: str
    name: str | None = None


class GitHubConnectOut(BaseModel):
    id: str
    forge_type: str
    display_name: str
    github_user: str


class RepoIn(BaseModel):
    full_name: str
    webhook_url: str   # user-provided public URL where GitHub will POST


class RepoEnableOut(BaseModel):
    id: str
    full_name: str
    webhook_id: int | None
    webhook_url: str


async def _gh(headers_token: str, path: str, method: str = "GET",
              json_body: dict | None = None) -> tuple[int, dict | list]:
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.request(method, f"{_GH}{path}",
            headers={"Authorization": f"Bearer {headers_token}",
                     "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"},
            json=json_body)
    return r.status_code, (r.json() if r.content else {})


@router.post("/forges/github", response_model=GitHubConnectOut, status_code=201)
async def connect_github(body: GitHubConnectIn) -> GitHubConnectOut:
    status, me = await _gh(body.token, "/user")
    if status != 200 or not isinstance(me, dict) or "login" not in me:
        raise HTTPException(400, f"github rejected token ({status})")
    user_login = me["login"]

    async with session_factory()() as db:
        org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
        webhook_secret = _secrets.token_urlsafe(32)
        conn_id = str(uuid.uuid4())
        # Store token + webhook secret in credential_ref/webhook_secret_ref refs;
        # ponytail: refs point at .env-style keys via a per-connection lookup table.
        # For dev, encode both directly in a small JSON blob in capabilities.
        await db.execute(text("""
            INSERT INTO forge_connections (id, org_id, forge_type, base_url, display_name,
                                            credential_ref, webhook_secret_ref, capabilities, status)
            VALUES (:id, :org, 'github', 'https://api.github.com', :name,
                    :cref, :sref, CAST(:caps AS jsonb), 'active')
        """), {"id": conn_id, "org": str(org_id),
                "name": body.name or f"GitHub · {user_login}",
                "cref": f"gh:conn:{conn_id}:token",
                "sref": f"gh:conn:{conn_id}:secret",
                "caps": json.dumps({
                    "github_user": user_login,
                    "dev_token": body.token,        # ponytail: dev-only stash
                    "dev_webhook_secret": webhook_secret,
                })})
        await db.commit()
    return GitHubConnectOut(id=conn_id, forge_type="github",
                            display_name=body.name or f"GitHub · {user_login}",
                            github_user=user_login)


@router.get("/forges")
async def list_forges() -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT id::text, forge_type, display_name, base_url,
                   capabilities->>'github_user' AS github_user, status, created_at
            FROM forge_connections ORDER BY created_at DESC
        """))).mappings().all()
    return [dict(r) for r in rows]


@router.delete("/forges/{cid}", status_code=204)
async def delete_forge(cid: str) -> None:
    async with session_factory()() as db:
        await db.execute(text("DELETE FROM forge_connections WHERE id = :id"), {"id": cid})
        await db.commit()


async def _conn_token(conn_id: str) -> tuple[str, str]:
    async with session_factory()() as db:
        row = (await db.execute(text("""
            SELECT capabilities FROM forge_connections WHERE id = :id AND forge_type = 'github'
        """), {"id": conn_id})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "github connection not found")
    caps = row["capabilities"] or {}
    token = caps.get("dev_token")
    secret = caps.get("dev_webhook_secret")
    if not token or not secret:
        raise HTTPException(400, "connection missing stored credentials")
    return token, secret


@router.get("/forges/{cid}/repos")
async def list_github_repos(cid: str, per_page: int = 50) -> list[dict]:
    token, _ = await _conn_token(cid)
    status, data = await _gh(token, f"/user/repos?per_page={per_page}&sort=updated")
    if status != 200 or not isinstance(data, list):
        raise HTTPException(status_code=status if status else 500, detail=str(data)[:400])
    return [{"full_name": r["full_name"], "private": r["private"], "default_branch": r["default_branch"],
             "language": r.get("language"), "updated_at": r["updated_at"]} for r in data]


@router.post("/forges/{cid}/repos/enable", response_model=RepoEnableOut, status_code=201)
async def enable_repo(cid: str, body: RepoIn) -> RepoEnableOut:
    token, secret = await _conn_token(cid)

    # Verify repo exists + create webhook via GitHub API
    status, repo_meta = await _gh(token, f"/repos/{body.full_name}")
    if status != 200 or not isinstance(repo_meta, dict):
        raise HTTPException(status, f"cannot access {body.full_name}: {str(repo_meta)[:200]}")

    async with session_factory()() as db:
        org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
        # Insert repositories row (idempotent per connection+external_id)
        repo_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO repositories (id, org_id, connection_id, external_id, full_name,
                                       clone_url, default_branch, primary_language, is_enabled, config)
            VALUES (:id, :org, :cid, :ext, :name, :url, :branch, :lang, true, '{}')
            ON CONFLICT (connection_id, external_id) DO UPDATE
              SET full_name = EXCLUDED.full_name, is_enabled = true
            RETURNING id::text
        """), {"id": repo_id, "org": str(org_id), "cid": cid,
                "ext": str(repo_meta["id"]), "name": repo_meta["full_name"],
                "url": repo_meta["clone_url"], "branch": repo_meta.get("default_branch") or "main",
                "lang": (repo_meta.get("language") or "").lower() or None})
        await db.commit()

    # Register webhook on GitHub → point at user's public URL
    hook_body = {
        "name": "web",
        "active": True,
        "events": ["pull_request", "issue_comment"],
        "config": {"url": body.webhook_url, "content_type": "json",
                    "secret": secret, "insecure_ssl": "0"},
    }
    status, resp = await _gh(token, f"/repos/{body.full_name}/hooks",
                              method="POST", json_body=hook_body)
    webhook_id = resp.get("id") if isinstance(resp, dict) and status in (200, 201) else None
    if webhook_id is None:
        # If a hook already exists w/ same URL, don't consider this fatal
        # ponytail: idempotence via check-then-create in M4
        pass
    return RepoEnableOut(id=repo_id, full_name=body.full_name,
                          webhook_id=webhook_id, webhook_url=body.webhook_url)
