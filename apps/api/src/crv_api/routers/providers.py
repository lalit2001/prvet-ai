"""Multi-provider LLM configuration.

Providers live in org.settings.providers = [ { id, type, ...fields, role_map }, ... ].
UI adds/edits; runtime resolves models via LlmClient(...).
"""
from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from crv_adapters.llm import LlmClient, LlmError, client_from_org
from crv_core.db import session_factory

router = APIRouter()


class Provider(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: str                              # openai | anthropic | azure_openai | bedrock | vertex_ai | ollama | vllm | litellm | openai_compatible
    name: str                              # display name, user-picked
    enabled: bool = True

    # Provider-specific fields — all optional at the schema level; validated per type client-side
    api_key: str | None = None
    endpoint: str | None = None            # azure
    api_version: str | None = None         # azure
    region: str | None = None              # bedrock
    access_key_id: str | None = None       # bedrock
    secret_access_key: str | None = None   # bedrock
    project: str | None = None             # vertex
    location: str | None = None            # vertex
    credentials_json: str | None = None    # vertex
    base_url: str | None = None            # ollama / vllm / litellm / openai_compatible

    # Which model this provider serves for each role. e.g. {"fast": "gpt-4o-mini", "deep": "gpt-4o"}
    role_map: dict[str, str] = Field(default_factory=dict)


class TestOut(BaseModel):
    ok: bool
    provider_id: str
    latency_ms: int | None
    error: str | None


async def _load_providers() -> list[dict]:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(settings->'providers', '[]'::jsonb) AS ps FROM organizations WHERE slug='default'"
        ))).mappings().one()
    return list(row["ps"] or [])


async def _save_providers(providers: list[dict]) -> None:
    async with session_factory()() as db:
        await db.execute(text("""
            UPDATE organizations
              SET settings = jsonb_set(COALESCE(settings, '{}'::jsonb), '{providers}', CAST(:p AS jsonb))
              WHERE slug = 'default'
        """), {"p": json.dumps(providers)})
        await db.commit()


@router.get("/config/providers", response_model=list[Provider])
async def list_providers() -> list[Provider]:
    return [Provider(**p) for p in await _load_providers()]


@router.put("/config/providers", response_model=list[Provider])
async def put_providers(body: list[Provider]) -> list[Provider]:
    await _save_providers([p.model_dump(exclude_none=False) for p in body])
    return await list_providers()


@router.post("/config/providers", response_model=Provider, status_code=201)
async def add_provider(body: Provider) -> Provider:
    providers = await _load_providers()
    if any(p["id"] == body.id for p in providers):
        raise HTTPException(400, f"provider id {body.id} already exists")
    providers.append(body.model_dump(exclude_none=False))
    await _save_providers(providers)
    return body


@router.delete("/config/providers/{pid}", status_code=204)
async def delete_provider(pid: str) -> None:
    providers = await _load_providers()
    providers = [p for p in providers if p["id"] != pid]
    await _save_providers(providers)


@router.post("/admin/providers/{pid}/test", response_model=TestOut)
async def test_provider(pid: str) -> TestOut:
    providers = await _load_providers()
    provider = next((p for p in providers if p["id"] == pid), None)
    if provider is None:
        raise HTTPException(404, "provider not found")
    # Use only THIS provider — do not fall through to defaults
    try:
        client = LlmClient([provider], timeout_s=15)
        # Pick any model the provider serves — prefer 'fast' role
        role_map = provider.get("role_map", {})
        target = role_map.get("fast") or (list(role_map.values())[0] if role_map else "fast")
        started = time.monotonic()
        resp = await client.chat(target, [{"role": "user", "content": "Reply with the single word: pong."}], temperature=0.0)
        return TestOut(ok=True, provider_id=pid, latency_ms=resp.latency_ms, error=None)
    except LlmError as e:
        return TestOut(ok=False, provider_id=pid, latency_ms=None, error=str(e))
