"""GitHub App auth: app JWT → installation access token (cached), plus Check Runs.

Installation tokens live 1h; we refresh at 50min. Cache is per-process — good
enough for one worker/API process each; move to Redis if we shard workers."""
from __future__ import annotations

import time
from typing import Any

import httpx
import jwt

_cache: dict[tuple[str, str], tuple[str, float]] = {}


def app_jwt(app_id: str, private_key_pem: str) -> str:
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(app_id)}, private_key_pem, algorithm="RS256")


async def installation_token(app_id: str, private_key_pem: str, installation_id: str,
                             api_base: str = "https://api.github.com") -> str:
    key = (str(app_id), str(installation_id))
    tok = _cache.get(key)
    if tok and tok[1] > time.time():
        return tok[0]
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post(f"{api_base}/app/installations/{installation_id}/access_tokens",
                         headers={"Authorization": f"Bearer {app_jwt(app_id, private_key_pem)}",
                                  "Accept": "application/vnd.github+json"})
    if r.status_code != 201:
        raise RuntimeError(f"installation token failed ({r.status_code}): {r.text[:200]}")
    token = r.json()["token"]
    _cache[key] = (token, time.time() + 50 * 60)
    return token


async def convert_manifest_code(code: str, api_base: str = "https://api.github.com") -> dict[str, Any]:
    """Manifest flow: exchange the one-time code for the app's credentials."""
    async with httpx.AsyncClient(timeout=15) as h:
        r = await h.post(f"{api_base}/app-manifests/{code}/conversions",
                         headers={"Accept": "application/vnd.github+json"})
    if r.status_code != 201:
        raise RuntimeError(f"manifest conversion failed ({r.status_code}): {r.text[:200]}")
    return r.json()


async def list_installation_repos(token: str, api_base: str = "https://api.github.com") -> list[dict]:
    out: list[dict] = []
    page = 1
    async with httpx.AsyncClient(timeout=20) as h:
        while True:
            r = await h.get(f"{api_base}/installation/repositories?per_page=100&page={page}",
                            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                break
            batch = r.json().get("repositories", [])
            out.extend(batch)
            if len(batch) < 100:
                break
            page += 1
    return out


async def create_check_run(token: str, repo: str, head_sha: str, *, name: str, conclusion: str,
                           title: str, summary: str, annotations: list[dict] | None = None,
                           details_url: str | None = None, api_base: str = "https://api.github.com") -> int | None:
    body: dict[str, Any] = {
        "name": name, "head_sha": head_sha, "status": "completed", "conclusion": conclusion,
        "output": {"title": title[:255], "summary": summary[:65000], "annotations": (annotations or [])[:50]},
    }
    if details_url:
        body["details_url"] = details_url
    async with httpx.AsyncClient(timeout=20) as h:
        r = await h.post(f"{api_base}/repos/{repo}/check-runs", json=body,
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    return r.json().get("id") if r.status_code == 201 else None
