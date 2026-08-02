"""LLM code review — ad-hoc first, blast-radius review lands with M3 in full.

Produces the PRD §13.2 finding schema. On any error, returns an empty list
and a message so the caller can surface the failure — never crashes the run."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from crv_adapters.llm import LlmError, client_from_org
from crv_core.db import session_factory
from sqlalchemy import text

_SYSTEM = """You are a senior code reviewer. Return STRICT JSON:
{
  "summary": "<one paragraph, markdown, ending with 'Risk: LOW|MEDIUM|HIGH.'>",
  "findings": [
    {
      "category": "security|bug|performance|maintainability|style|dependency|test",
      "severity": "critical|high|medium|low|info",
      "confidence": 0.0-1.0,
      "start_line": <int|null>,
      "end_line": <int|null>,
      "title": "<one sentence>",
      "body": "<markdown, cite specific lines/identifiers>",
      "suggested_patch": "<unified diff or replacement block, or null>"
    }
  ]
}
Only report real issues. Empty findings list is a valid response when the code is fine.
"""


@dataclass
class ReviewResult:
    summary: str
    findings: list[dict]
    error: str | None = None
    cost_usd: float | None = None
    stats: dict = field(default_factory=dict)


async def review(code: str, language: str | None = None, context: str | None = None,
                 run_id: str | None = None) -> ReviewResult:
    # Load providers from org.settings; if none, the UI tells the user to add one.
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(settings->'providers', '[]'::jsonb) AS ps FROM organizations WHERE slug='default'"
        ))).mappings().one()
    providers = list(row["ps"] or [])
    try:
        client = client_from_org(providers)
    except LlmError as e:
        return ReviewResult(summary="", findings=[], error=str(e))

    user_parts = []
    if context:
        user_parts.append(f"Context:\n{context}\n")
    if language:
        user_parts.append(f"Language: {language}")
    user_parts.append(f"Review this code:\n```\n{code}\n```")
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n".join(user_parts)},
    ]

    try:
        # 'deep' resolves via provider.role_map; falls back to a plain model name.
        resp = await client.chat("deep", messages,
                                 response_format={"type": "json_object"})
    except LlmError as e:
        return ReviewResult(summary="", findings=[], error=str(e))

    try:
        parsed = json.loads(resp.content)
        summary = parsed.get("summary", "")
        findings = parsed.get("findings", []) or []
    except json.JSONDecodeError:
        return ReviewResult(summary="", findings=[], error="llm returned non-JSON",
                            stats={"raw": resp.content[:2000]})

    if run_id:
        await _log_call(run_id, resp)

    return ReviewResult(
        summary=summary,
        findings=findings,
        stats={"model": resp.model, "prompt_tokens": resp.prompt_tokens,
               "completion_tokens": resp.completion_tokens, "latency_ms": resp.latency_ms},
    )


async def _log_call(run_id: str, resp) -> None:
    async with session_factory()() as db:
        await db.execute(text("""
            INSERT INTO llm_calls (id, run_id, model, purpose, prompt_tokens, completion_tokens,
                                   latency_ms, status)
            VALUES (:id, :rid, :model, 'review', :pt, :ct, :lat, 'ok')
        """), {"id": str(uuid.uuid4()), "rid": run_id, "model": resp.model,
               "pt": resp.prompt_tokens, "ct": resp.completion_tokens, "lat": resp.latency_ms})
        await db.commit()


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(review(
        code="def divide(a, b): return a / b",
        language="python",
    ))
    print("error:", result.error)
    print("summary:", result.summary)
    print("findings:", len(result.findings))
