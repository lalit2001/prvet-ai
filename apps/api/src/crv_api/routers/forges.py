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
from crv_worker.forge_token import connection_auth

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


class GitLabConnectIn(BaseModel):
    token: str
    base_url: str | None = None
    name: str | None = None


class AzureConnectIn(BaseModel):
    token: str
    base_url: str
    name: str | None = None


class RepoIn(BaseModel):
    full_name: str
    webhook_url: str


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


async def _gl(token: str, base_url: str, path: str, method: str = "GET",
              json_body: dict | None = None) -> tuple[int, dict | list]:
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.request(method, f"{base_url}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=json_body)
    return r.status_code, (r.json() if r.content else {})


async def _az(token: str, base_url: str, path: str, method: str = "GET",
              json_body: dict | None = None) -> tuple[int, dict | list]:
    import base64
    basic_auth = base64.b64encode(f":{token}".encode()).decode()
    async with httpx.AsyncClient(timeout=15) as h:
        url = f"{base_url.rstrip('/')}{path}"
        r = await h.request(method, url,
            headers={"Authorization": f"Basic {basic_auth}"},
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
                    "dev_token": body.token,
                    "dev_webhook_secret": webhook_secret,
                })})
        await db.commit()
    return GitHubConnectOut(id=conn_id, forge_type="github",
                            display_name=body.name or f"GitHub · {user_login}",
                            github_user=user_login)


@router.post("/forges/gitlab", status_code=201)
async def connect_gitlab(body: GitLabConnectIn):
    base_url = (body.base_url or "https://gitlab.com").rstrip("/")
    status, me = await _gl(body.token, base_url, "/api/v4/user")
    if status != 200 or not isinstance(me, dict) or "username" not in me:
        raise HTTPException(400, f"GitLab rejected token ({status})")
    username = me["username"]
    
    async with session_factory()() as db:
        org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
        webhook_secret = _secrets.token_urlsafe(32)
        conn_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO forge_connections (id, org_id, forge_type, base_url, display_name,
                                            credential_ref, webhook_secret_ref, capabilities, status)
            VALUES (:id, :org, 'gitlab', :base, :name,
                    :cref, :sref, CAST(:caps AS jsonb), 'active')
        """), {"id": conn_id, "org": str(org_id), "base": base_url,
                "name": body.name or f"GitLab · {username}",
                "cref": f"gl:conn:{conn_id}:token",
                "sref": f"gl:conn:{conn_id}:secret",
                "caps": json.dumps({
                    "gitlab_user": username,
                    "dev_token": body.token,
                    "dev_webhook_secret": webhook_secret,
                })})
        await db.commit()
    return {"id": conn_id, "forge_type": "gitlab", "display_name": body.name or f"GitLab · {username}"}


@router.post("/forges/azure", status_code=201)
async def connect_azure(body: AzureConnectIn):
    base_url = body.base_url.rstrip("/")
    status, res = await _az(body.token, base_url, "/_apis/projects?api-version=6.0")
    if status != 200:
        raise HTTPException(400, f"Azure DevOps verification failed (status {status})")
        
    async with session_factory()() as db:
        org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
        webhook_secret = _secrets.token_urlsafe(32)
        conn_id = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO forge_connections (id, org_id, forge_type, base_url, display_name,
                                            credential_ref, webhook_secret_ref, capabilities, status)
            VALUES (:id, :org, 'azure', :base, :name,
                    :cref, :sref, CAST(:caps AS jsonb), 'active')
        """), {"id": conn_id, "org": str(org_id), "base": base_url,
                "name": body.name or f"Azure DevOps · {base_url.split('/')[-1]}",
                "cref": f"az:conn:{conn_id}:token",
                "sref": f"az:conn:{conn_id}:secret",
                "caps": json.dumps({
                    "dev_token": body.token,
                    "dev_webhook_secret": webhook_secret,
                })})
        await db.commit()
    return {"id": conn_id, "forge_type": "azure", "display_name": body.name or f"Azure DevOps · {base_url.split('/')[-1]}"}


@router.get("/forges")
async def list_forges() -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT id::text, forge_type, display_name, base_url,
                   capabilities->>'github_user' AS github_user,
                   capabilities->>'installation_id' AS installation_id,
                   capabilities->>'app_uuid' AS app_uuid,
                   capabilities->>'account' AS account,
                   (SELECT count(*) FROM repositories r WHERE r.connection_id = forge_connections.id AND r.is_enabled) AS repo_count,
                   capabilities->>'gitlab_user' AS gitlab_user,
                   capabilities->>'webhook_base_url' AS webhook_base_url,
                   status, created_at
            FROM forge_connections ORDER BY created_at DESC
        """))).mappings().all()
    return [dict(r) for r in rows]


class WebhookBaseIn(BaseModel):
    webhook_base_url: str


@router.put("/forges/{cid}/webhook-base")
async def set_webhook_base(cid: str, body: WebhookBaseIn) -> dict:
    base = body.webhook_base_url.rstrip("/")
    async with session_factory()() as db:
        r = await db.execute(text("""
            UPDATE forge_connections
              SET capabilities = jsonb_set(COALESCE(capabilities, '{}'::jsonb),
                                            '{webhook_base_url}', to_jsonb(CAST(:b AS text)))
              WHERE id = :id
        """), {"b": base, "id": cid})
        if r.rowcount == 0:
            raise HTTPException(404, "connection not found")
        await db.commit()
    return {"webhook_base_url": base}


@router.delete("/forges/{cid}", status_code=204)
async def delete_forge(cid: str) -> None:
    async with session_factory()() as db:
        await db.execute(text("DELETE FROM forge_connections WHERE id = :id"), {"id": cid})
        await db.commit()


async def _conn_token(conn_id: str) -> tuple[str, str, str, str]:
    try:
        a = await connection_auth(conn_id)
    except LookupError as e:
        raise HTTPException(404, str(e))
    if not a.webhook_secret:
        raise HTTPException(400, "Connection missing stored credentials")
    return a.token, a.webhook_secret, a.forge_type, a.base_url


async def _is_installation(conn_id: str) -> bool:
    async with session_factory()() as db:
        v = (await db.execute(text("SELECT capabilities->>'installation_id' FROM forge_connections WHERE id = :id"),
                              {"id": conn_id})).scalar_one_or_none()
    return bool(v)


@router.get("/forges/{cid}/repos")
async def list_forge_repos(cid: str) -> list[dict]:
    token, _, forge_type, base_url = await _conn_token(cid)
    
    if forge_type == "github":
        if await _is_installation(cid):
            from crv_adapters.forge.github_app import list_installation_repos
            data = await list_installation_repos(token, api_base=base_url or _GH)
        else:
            status, data = await _gh(token, "/user/repos?per_page=50&sort=updated")
            if status != 200 or not isinstance(data, list):
                raise HTTPException(status_code=status if status else 500, detail=str(data)[:400])
        return [{"full_name": r["full_name"], "private": r["private"], "default_branch": r["default_branch"],
                 "language": r.get("language"), "updated_at": r["updated_at"]} for r in data]
                 
    elif forge_type == "gitlab":
        status, data = await _gl(token, base_url, "/api/v4/projects?membership=true&simple=true&per_page=50")
        if status != 200 or not isinstance(data, list):
            raise HTTPException(status_code=status if status else 500, detail=str(data)[:400])
        return [{"full_name": p["path_with_namespace"], "private": p["visibility"] != "public", "default_branch": p["default_branch"],
                 "language": None, "updated_at": p["last_activity_at"]} for p in data]
                 
    elif forge_type == "azure":
        status, data = await _az(token, base_url, "/_apis/projects?api-version=6.0")
        if status != 200 or not isinstance(data, dict):
            raise HTTPException(status_code=status if status else 500, detail=str(data)[:400])
        
        projects = data.get("value", [])
        repos = []
        for proj in projects:
            p_name = proj["name"]
            r_status, r_data = await _az(token, base_url, f"/{p_name}/_apis/git/repositories?api-version=6.0")
            if r_status == 200 and isinstance(r_data, dict):
                for r in r_data.get("value", []):
                    ref_branch = r.get("defaultBranch", "refs/heads/main")
                    branch = ref_branch.replace("refs/heads/", "")
                    repos.append({
                        "full_name": f"{p_name}/{r['name']}",
                        "private": True,
                        "default_branch": branch,
                        "language": None,
                        "updated_at": None
                    })
        return repos
    else:
        raise HTTPException(400, f"Unsupported forge type: {forge_type}")


@router.post("/forges/{cid}/repos/enable", response_model=RepoEnableOut, status_code=201)
async def enable_repo(cid: str, body: RepoIn) -> RepoEnableOut:
    token, secret, forge_type, base_url = await _conn_token(cid)
    
    base = body.webhook_url.split("/api/v1/webhooks/")[0].rstrip("/") if "/api/v1/webhooks/" in body.webhook_url else body.webhook_url.rstrip("/")
    
    if forge_type == "github":
        status, repo_meta = await _gh(token, f"/repos/{body.full_name}")
        if status != 200 or not isinstance(repo_meta, dict):
            raise HTTPException(status, f"cannot access {body.full_name}: {str(repo_meta)[:200]}")
            
        async with session_factory()() as db:
            org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
            await db.execute(text("""
                UPDATE forge_connections
                  SET capabilities = jsonb_set(COALESCE(capabilities, '{}'::jsonb),
                                                '{webhook_base_url}', to_jsonb(CAST(:b AS text)))
                  WHERE id = :id
            """), {"b": base, "id": cid})
            
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

        if await _is_installation(cid):
            # App installations deliver every event to the app-level hook — nothing to register per repo
            return RepoEnableOut(id=repo_id, full_name=body.full_name, webhook_id=None, webhook_url="(GitHub App)")
        hook_body = {
            "name": "web",
            "active": True,
            "events": ["pull_request", "issue_comment"],
            "config": {"url": body.webhook_url, "content_type": "json",
                        "secret": secret, "insecure_ssl": "0"},
        }
        h_status, resp = await _gh(token, f"/repos/{body.full_name}/hooks",
                                  method="POST", json_body=hook_body)
        webhook_id = resp.get("id") if isinstance(resp, dict) and h_status in (200, 201) else None
        return RepoEnableOut(id=repo_id, full_name=body.full_name,
                              webhook_id=webhook_id, webhook_url=body.webhook_url)
                              
    elif forge_type == "gitlab":
        import urllib.parse
        encoded_path = urllib.parse.quote(body.full_name, safe="")
        
        status, project_meta = await _gl(token, base_url, f"/api/v4/projects/{encoded_path}")
        if status != 200 or not isinstance(project_meta, dict):
            raise HTTPException(status, f"cannot access project {body.full_name}: {str(project_meta)[:200]}")
            
        async with session_factory()() as db:
            org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
            await db.execute(text("""
                UPDATE forge_connections
                  SET capabilities = jsonb_set(COALESCE(capabilities, '{}'::jsonb),
                                                '{webhook_base_url}', to_jsonb(CAST(:b AS text)))
                  WHERE id = :id
            """), {"b": base, "id": cid})
            
            repo_id = str(uuid.uuid4())
            await db.execute(text("""
                INSERT INTO repositories (id, org_id, connection_id, external_id, full_name,
                                           clone_url, default_branch, primary_language, is_enabled, config)
                VALUES (:id, :org, :cid, :ext, :name, :url, :branch, :lang, true, '{}')
                ON CONFLICT (connection_id, external_id) DO UPDATE
                  SET full_name = EXCLUDED.full_name, is_enabled = true
                RETURNING id::text
            """), {"id": repo_id, "org": str(org_id), "cid": cid,
                    "ext": str(project_meta["id"]), "name": project_meta["path_with_namespace"],
                    "url": project_meta["http_url_to_repo"], "branch": project_meta.get("default_branch") or "main",
                    "lang": None})
            await db.commit()
            
        hook_body = {
            "url": body.webhook_url,
            "push_events": False,
            "merge_requests_events": True,
            "note_events": True,
            "token": secret
        }
        h_status, resp = await _gl(token, base_url, f"/api/v4/projects/{project_meta['id']}/hooks",
                                  method="POST", json_body=hook_body)
        webhook_id = resp.get("id") if isinstance(resp, dict) and h_status in (200, 201) else None
        return RepoEnableOut(id=repo_id, full_name=body.full_name,
                              webhook_id=webhook_id, webhook_url=body.webhook_url)
                              
    elif forge_type == "azure":
        parts = body.full_name.split("/")
        project_name = parts[0]
        repo_name = parts[1]
        
        status, repo_meta = await _az(token, base_url, f"/{project_name}/_apis/git/repositories/{repo_name}?api-version=6.0")
        if status != 200 or not isinstance(repo_meta, dict):
            raise HTTPException(status, f"cannot access {body.full_name}: {str(repo_meta)[:200]}")
            
        async with session_factory()() as db:
            org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
            await db.execute(text("""
                UPDATE forge_connections
                  SET capabilities = jsonb_set(COALESCE(capabilities, '{}'::jsonb),
                                                '{webhook_base_url}', to_jsonb(CAST(:b AS text)))
                  WHERE id = :id
            """), {"b": base, "id": cid})
            
            repo_id = str(uuid.uuid4())
            await db.execute(text("""
                INSERT INTO repositories (id, org_id, connection_id, external_id, full_name,
                                           clone_url, default_branch, primary_language, is_enabled, config)
                VALUES (:id, :org, :cid, :ext, :name, :url, :branch, :lang, true, '{}')
                ON CONFLICT (connection_id, external_id) DO UPDATE
                  SET full_name = EXCLUDED.full_name, is_enabled = true
                RETURNING id::text
            """), {"id": repo_id, "org": str(org_id), "cid": cid,
                    "ext": str(repo_meta["id"]), "name": body.full_name,
                    "url": repo_meta["webUrl"], "branch": repo_meta.get("defaultBranch", "refs/heads/main").replace("refs/heads/", ""),
                    "lang": None})
            await db.commit()
            
        return RepoEnableOut(id=repo_id, full_name=body.full_name,
                              webhook_id=None, webhook_url=body.webhook_url)
    else:
        raise HTTPException(400, f"Unsupported forge type: {forge_type}")
