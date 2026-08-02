"""Config endpoints — the UI's admin surface."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from crv_core.db import session_factory
from crv_core.settings import get_settings

router = APIRouter()

# ─── Org-wide config (LLM + gate + budget) ──────────────────────────────────

_DEFAULT_ORG_CONFIG = {
    "llm": {
        "base_url": "",             # empty = fall back to env LLM_BASE_URL
        "api_key_ref": "",
        "model_fast": "",
        "model_deep": "",
        "monthly_budget_usd": 500,
    },
    "gate": {
        "mode": "fail_open",        # fail_open | fail_closed
        "block_severity": "high",   # critical|high|medium|low|info
        "min_confidence": 0.6,
        "max_comments_per_pr": 25,
    },
    "custom_rules": [],
}


class OrgConfig(BaseModel):
    llm: dict = Field(default_factory=dict)
    gate: dict = Field(default_factory=dict)
    custom_rules: list[dict] = Field(default_factory=list)


@router.get("/config/org", response_model=OrgConfig)
async def get_org_config() -> OrgConfig:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT settings FROM organizations WHERE slug='default'"
        ))).mappings().one_or_none()
    if row is None:
        raise HTTPException(500, "default org missing")
    stored = row["settings"] or {}
    merged = {**_DEFAULT_ORG_CONFIG, **stored}
    for k in ("llm", "gate"):
        merged[k] = {**_DEFAULT_ORG_CONFIG[k], **stored.get(k, {})}
    return OrgConfig(**merged)


@router.put("/config/org", response_model=OrgConfig)
async def put_org_config(body: OrgConfig) -> OrgConfig:
    async with session_factory()() as db:
        await db.execute(text("""
            UPDATE organizations SET settings = CAST(:s AS jsonb) WHERE slug = 'default'
        """), {"s": json.dumps(body.model_dump())})
        await db.commit()
    return await get_org_config()


@router.get("/config/env")
async def get_env_config() -> dict:
    """Read-only view of what the env is contributing. Never returns secrets."""
    s = get_settings()
    return {
        "llm_base_url": s.llm_base_url,
        "llm_api_key_ref": s.llm_api_key_ref,
        "llm_model_fast": s.llm_model_fast,
        "llm_model_deep": s.llm_model_deep,
        "llm_embedding_model": s.llm_embedding_model,
        "llm_monthly_budget_usd": s.llm_monthly_budget_usd,
        "gate_mode": s.gate_mode,
        "gate_block_severity": s.gate_block_severity,
        "min_confidence": s.min_confidence,
        "max_comments_per_pr": s.max_comments_per_pr,
        "deployment_mode": s.deployment_mode,
        "queue_backend": s.queue_backend,
        "storage_backend": s.storage_backend,
        "secrets_backend": s.secrets_backend,
    }


# ─── Per-repo config (.crv.yml equivalent) ──────────────────────────────────

_DEFAULT_REPO_CONFIG = {
    "review": {
        "block_severity": "high",
        "categories": ["security", "bug", "performance", "maintainability"],
        "min_confidence": 0.7,
        "drafts": False,
        "guidelines": "",
    },
    "bypass": {
        "roles": ["admin", "maintain"],
        "require_second_approver_for": ["critical"],
    },
    "exclude_paths": ["vendor/**", "**/*.generated.*"],
    "hotspots": {"count": 150, "extra": []},
    "weekly": {"schedule": "0 6 * * MON", "auto_promote_baseline": False},
}


class RepoConfig(BaseModel):
    review: dict = Field(default_factory=dict)
    bypass: dict = Field(default_factory=dict)
    exclude_paths: list[str] = Field(default_factory=list)
    hotspots: dict = Field(default_factory=dict)
    weekly: dict = Field(default_factory=dict)


@router.get("/repos/{repo_id}/config", response_model=RepoConfig)
async def get_repo_config(repo_id: str) -> RepoConfig:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT config FROM repositories WHERE id = :id"
        ), {"id": repo_id})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "repo not found")
    stored = row["config"] or {}
    # local_path lives here too; leave it alone, don't overwrite it in PUT
    merged = {k: {**v, **stored.get(k, {})} if isinstance(v, dict) else stored.get(k, v)
              for k, v in _DEFAULT_REPO_CONFIG.items()}
    return RepoConfig(**merged)


@router.put("/repos/{repo_id}/config", response_model=RepoConfig)
async def put_repo_config(repo_id: str, body: RepoConfig) -> RepoConfig:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT config FROM repositories WHERE id = :id"
        ), {"id": repo_id})).mappings().one_or_none()
        if row is None:
            raise HTTPException(404, "repo not found")
        current = row["config"] or {}
        merged = {**current, **body.model_dump()}
        await db.execute(text(
            "UPDATE repositories SET config = CAST(:c AS jsonb) WHERE id = :id"
        ), {"c": json.dumps(merged), "id": repo_id})
        await db.commit()
    return await get_repo_config(repo_id)
