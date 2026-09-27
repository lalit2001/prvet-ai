"""GitHub App: register via the manifest flow, receive app-level webhooks, keep
installations in sync. An installation is a forge_connections row so the rest of
the pipeline (webhook_events → handle_forge_event → pr_review) is untouched."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text

from crv_adapters.forge.github_app import convert_manifest_code, installation_token
from crv_api.routers.auth import get_current_user
from crv_core.db import session_factory
from crv_core.queue import pool
from crv_core.settings import get_settings
from fastapi import Depends

router = APIRouter()

PERMISSIONS = {"contents": "read", "metadata": "read", "pull_requests": "write", "checks": "write",
               "statuses": "write", "issues": "write"}
EVENTS = ["pull_request", "pull_request_review_comment", "issue_comment", "push", "check_suite"]


class ManifestOut(BaseModel):
    post_url: str
    manifest: dict
    app_uuid: str


@router.get("/forges/github-app/manifest", response_model=ManifestOut)
async def manifest(org: str | None = None, name: str | None = None, user: dict = Depends(get_current_user)) -> ManifestOut:
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    s = get_settings()
    host = (s.public_url.split("//", 1)[-1].split("/")[0].split(":")[0]).lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.endswith((".local", ".internal")) or "." not in host:
        raise HTTPException(400, f"PUBLIC_URL is '{s.public_url}' — GitHub cannot reach it. Expose the API with a tunnel "
                                 "(e.g. `ngrok http 8080` or `cloudflared tunnel --url http://localhost:8080`), set PUBLIC_URL "
                                 "to that https URL in .env, restart the API, then register again.")
    app_uuid = str(uuid.uuid4())
    async with session_factory()() as db:
        org_id = (await db.execute(text("SELECT id FROM organizations WHERE slug='default'"))).scalar_one()
        await db.execute(text("""
            INSERT INTO forge_apps (id, org_id, name, status) VALUES (:id, :org, :name, 'pending')
        """), {"id": app_uuid, "org": str(org_id), "name": name or "PRVet"})
        await db.commit()
    public, web = s.public_url.rstrip("/"), s.web_url.rstrip("/")
    m = {
        "name": name or f"PRVet ({app_uuid[:6]})",
        "url": web,
        "description": "Self-hosted AI code review with blast-radius analysis.",
        "hook_attributes": {"url": f"{public}/api/v1/webhooks/github-app/{app_uuid}", "active": True},
        "redirect_url": f"{public}/api/v1/forges/github-app/callback",
        "callback_urls": [web],
        "setup_url": f"{web}/admin/forges?setup=github-app",
        "setup_on_update": True,
        "public": False,
        "default_permissions": PERMISSIONS,
        "default_events": EVENTS,
    }
    base = f"https://github.com/organizations/{org}/settings/apps/new" if org else "https://github.com/settings/apps/new"
    return ManifestOut(post_url=f"{base}?state={app_uuid}", manifest=m, app_uuid=app_uuid)


@router.get("/forges/github-app/callback")
async def callback(code: str, state: str):
    s = get_settings()
    async with session_factory()() as db:
        done = (await db.execute(text("SELECT slug FROM forge_apps WHERE id = :id AND status = 'active'"), {"id": state})).scalar_one_or_none()
    if done:  # callback reloaded — the one-time code is spent, but the app already exists
        return RedirectResponse(f"{s.web_url.rstrip('/')}/admin/forges?app=created&slug={done}", status_code=302)
    try:
        data = await convert_manifest_code(code)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    async with session_factory()() as db:
        r = await db.execute(text("""
            UPDATE forge_apps SET app_id = :app_id, slug = :slug, name = :name, html_url = :html, client_id = :cid,
                   credentials = CAST(:creds AS jsonb), status = 'active'
            WHERE id = :id
        """), {"id": state, "app_id": str(data["id"]), "slug": data["slug"], "name": data["name"],
                "html": data.get("html_url"), "cid": data.get("client_id"),
                "creds": json.dumps({"pem": data["pem"], "webhook_secret": data["webhook_secret"],
                                     "client_secret": data.get("client_secret")})})
        if r.rowcount == 0:
            raise HTTPException(404, "unknown registration state")
        await db.commit()
    return RedirectResponse(f"{s.web_url.rstrip('/')}/admin/forges?app=created&slug={data['slug']}", status_code=302)


@router.get("/forges/github-apps")
async def list_apps(user: dict = Depends(get_current_user)) -> list[dict]:
    async with session_factory()() as db:
        rows = (await db.execute(text("""
            SELECT a.id::text, a.app_id, a.slug, a.name, a.html_url, a.status, a.created_at::text,
                   (SELECT count(*) FROM forge_connections c WHERE c.capabilities->>'app_uuid' = a.id::text AND c.status = 'active') AS installations
            FROM forge_apps a WHERE a.status <> 'pending' ORDER BY a.created_at DESC
        """))).mappings().all()
    return [{**dict(r), "install_url": f"https://github.com/apps/{r['slug']}/installations/new" if r["slug"] else None} for r in rows]


@router.delete("/forges/github-apps/{app_uuid}", status_code=204)
async def delete_app(app_uuid: str, user: dict = Depends(get_current_user)) -> None:
    if user["role"] != "admin":
        raise HTTPException(403, "admin only")
    async with session_factory()() as db:
        await db.execute(text("UPDATE forge_connections SET status = 'revoked' WHERE capabilities->>'app_uuid' = :id"), {"id": app_uuid})
        await db.execute(text("DELETE FROM forge_apps WHERE id = :id"), {"id": app_uuid})
        await db.commit()


# ── webhooks ───────────────────────────────────────────────────────────────

@router.post("/webhooks/github-app/{app_uuid}", status_code=status.HTTP_202_ACCEPTED)
async def app_webhook(app_uuid: str, request: Request):
    body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}
    async with session_factory()() as db:
        app = (await db.execute(text("SELECT id::text, org_id::text, app_id, base_url, credentials FROM forge_apps WHERE id = :id AND status = 'active'"),
                                {"id": app_uuid})).mappings().first()
    if app is None:
        raise HTTPException(404, "unknown app")
    secret = (app["credentials"] or {}).get("webhook_secret", "")
    sig = headers.get("x-hub-signature-256", "")
    if not sig or not hmac.compare_digest(sig, "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()):
        raise HTTPException(401, "invalid signature")

    event = headers.get("x-github-event", "")
    payload = await request.json() if body else {}
    delivery = headers.get("x-github-delivery") or uuid.uuid4().hex
    inst = payload.get("installation") or {}
    inst_id = str(inst.get("id") or "")

    if event == "installation":
        action = payload.get("action")
        if action == "created" or action == "unsuspend":
            await _sync_installation(app, inst, payload.get("repositories") or [])
        elif action in ("deleted", "suspend"):
            await _set_installation_status(app_uuid, inst_id, "revoked" if action == "deleted" else "suspended")
        return {"status": "accepted", "handled": True}
    if event == "installation_repositories":
        await _sync_installation(app, inst, payload.get("repositories_added") or [],
                                 removed=payload.get("repositories_removed") or [])
        return {"status": "accepted", "handled": True}
    if not inst_id:
        return {"status": "accepted", "handled": False}

    async with session_factory()() as db:
        conn = (await db.execute(text("""
            SELECT id::text FROM forge_connections
            WHERE capabilities->>'app_uuid' = :app AND capabilities->>'installation_id' = :inst AND status = 'active'
        """), {"app": app_uuid, "inst": inst_id})).scalar_one_or_none()
        if conn is None:
            return {"status": "accepted", "handled": False, "reason": "installation unknown"}
        if event not in ("pull_request", "issue_comment", "pull_request_review_comment", "check_suite"):
            return {"status": "accepted", "handled": False}
        row = (await db.execute(text("""
            INSERT INTO webhook_events (id, connection_id, external_event_id, event_type, payload, signature_valid)
            VALUES (:id, :cid, :eid, :et, CAST(:payload AS jsonb), true)
            ON CONFLICT (connection_id, external_event_id) DO NOTHING RETURNING id
        """), {"id": str(uuid.uuid4()), "cid": conn, "eid": delivery, "et": event,
                "payload": json.dumps(payload, separators=(",", ":"))})).first()
        await db.commit()
    if row is None:
        return {"status": "accepted", "duplicate": True}
    if event == "check_suite" and payload.get("action") != "rerequested":
        return {"status": "accepted", "handled": False}
    p = await pool()
    job = await p.enqueue_job("handle_forge_event", conn, delivery, event)
    return {"status": "accepted", "job_id": job.job_id if job else None}


async def _sync_installation(app: dict, inst: dict, repos: list[dict], removed: list[dict] = ()) -> None:
    inst_id = str(inst.get("id"))
    account = (inst.get("account") or {}).get("login", "")
    acct_type = (inst.get("account") or {}).get("type", "")
    api_base = app["base_url"] or "https://api.github.com"
    async with session_factory()() as db:
        conn_id = (await db.execute(text("""
            SELECT id::text FROM forge_connections
            WHERE capabilities->>'app_uuid' = :app AND capabilities->>'installation_id' = :inst
        """), {"app": app["id"], "inst": inst_id})).scalar_one_or_none()
        if conn_id is None:
            conn_id = str(uuid.uuid4())
            await db.execute(text("""
                INSERT INTO forge_connections (id, org_id, forge_type, base_url, display_name, credential_ref,
                                               webhook_secret_ref, capabilities, status, last_verified_at)
                VALUES (:id, :org, 'github', :base, :name, :cref, :sref, CAST(:caps AS jsonb), 'active', now())
            """), {"id": conn_id, "org": app["org_id"], "base": api_base, "name": f"GitHub App · {account}",
                    "cref": f"gh:app:{app['id']}:installation:{inst_id}", "sref": f"gh:app:{app['id']}:secret",
                    "caps": json.dumps({"installation_id": inst_id, "app_uuid": app["id"], "account": account,
                                        "account_type": acct_type, "github_user": account, "installed_via": "app"})})
        else:
            await db.execute(text("UPDATE forge_connections SET status = 'active', last_verified_at = now() WHERE id = :id"), {"id": conn_id})
        try:
            token = await installation_token(str(app["app_id"]), app["credentials"]["pem"], inst_id, api_base=api_base)
        except Exception as e:  # noqa: BLE001
            print(f"[github_app] could not mint installation token: {e}")
            token = None
        for r in repos:
            full = r.get("full_name") or ""
            meta = await _repo_meta(token, api_base, full) if token else {}
            await db.execute(text("""
                INSERT INTO repositories (id, org_id, connection_id, external_id, full_name, clone_url, default_branch,
                                          primary_language, is_enabled, config, onboarded_at)
                VALUES (:id, :org, :cid, :ext, :name, :url, :branch, :lang, true, '{}', now())
                ON CONFLICT (connection_id, external_id) DO UPDATE
                  SET full_name = EXCLUDED.full_name, is_enabled = true, default_branch = EXCLUDED.default_branch
            """), {"id": str(uuid.uuid4()), "org": app["org_id"], "cid": conn_id, "ext": str(r.get("id")), "name": full,
                    "url": meta.get("clone_url") or f"https://github.com/{full}.git",
                    "branch": meta.get("default_branch") or "main", "lang": (meta.get("language") or "").lower() or None})
        for r in removed:
            await db.execute(text("UPDATE repositories SET is_enabled = false WHERE connection_id = :cid AND external_id = :ext"),
                             {"cid": conn_id, "ext": str(r.get("id"))})
        await db.commit()


async def _set_installation_status(app_uuid: str, inst_id: str, new_status: str) -> None:
    async with session_factory()() as db:
        await db.execute(text("""
            UPDATE forge_connections SET status = :st
            WHERE capabilities->>'app_uuid' = :app AND capabilities->>'installation_id' = :inst
        """), {"st": new_status, "app": app_uuid, "inst": inst_id})
        await db.execute(text("""
            UPDATE repositories SET is_enabled = false WHERE connection_id IN (
                SELECT id FROM forge_connections WHERE capabilities->>'app_uuid' = :app AND capabilities->>'installation_id' = :inst)
        """), {"app": app_uuid, "inst": inst_id})
        await db.commit()


async def _repo_meta(token: str, api_base: str, full_name: str) -> dict:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10) as h:
            r = await h.get(f"{api_base}/repos/{full_name}", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        return r.json() if r.status_code == 200 else {}
    except Exception:  # noqa: BLE001
        return {}
