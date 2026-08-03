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

_SYSTEM = """You are an elite senior security engineer and code reviewer. Your job is to thoroughly analyze the provided code changes for both obvious and subtle vulnerabilities, logic flaws, and architectural anti-patterns.

Return STRICT JSON:
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

CRITICAL INSTRUCTIONS FOR ANALYSIS:
1. Data-Flow & Taint Analysis: Trace all inputs (from APIs, parameters, users) to their sinks. Explicitly check for Path Traversal (e.g., untrusted strings entering fs operations) and SSRF (untrusted strings entering network request URLs/baseUrls).
2. Logic Validation: Check for "dead" or unused captured variables that indicate a logic error. If a parameter is passed but never utilized in the function's logic, flag it as a bug.
3. Input Boundary Checking: Ensure all inputs (like sizes, IDs) are strictly validated for type, negative/NaN values, and reasonable bounds before being processed.
4. Information Disclosure: Ensure raw errors from dependencies or upstream providers are NEVER leaked back to the user/UI. All errors should be sanitized.
5. Authorization & Permissions: Ensure window/shell operations (like shell.openExternal) strictly allowlist protocols/domains to prevent sandbox escapes.

Only report real, impactful issues. Empty findings list is a valid response when the code is fully secure and correct.
"""


@dataclass
class ReviewResult:
    summary: str
    findings: list[dict]
    error: str | None = None
    cost_usd: float | None = None
    stats: dict = field(default_factory=dict)


def _clean_and_parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1:
        text = text[first_brace:last_brace+1]
    return json.loads(text)


async def summarize_project(prompt: str, run_id: str | None = None) -> str:
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(settings->'providers', '[]'::jsonb) AS ps FROM organizations WHERE slug='default'"
        ))).mappings().one()
    providers = list(row["ps"] or [])
    try:
        client = client_from_org(providers)
    except LlmError as e:
        return f"_summary skipped: {e}_"

    messages = [
        {"role": "system", "content": "You are a senior tech lead helping developers understand a codebase. Return a plain markdown paragraph (4-6 sentences) summarizing the codebase."},
        {"role": "user", "content": prompt}
    ]
    try:
        resp = await client.chat("deep", messages)
        if run_id:
            await _log_call(run_id, resp)
        return resp.content or ""
    except Exception as e:
        return f"_summary failed: {e}_"


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
        parsed = _clean_and_parse_json(resp.content)
        summary = parsed.get("summary", "")
        findings = parsed.get("findings", []) or []
    except (json.JSONDecodeError, ValueError) as first_err:
        # One-time repair retry on malformed JSON
        repair_messages = messages + [
            {"role": "assistant", "content": resp.content},
            {"role": "user", "content": f"Your response was not valid JSON ({first_err}). Please output ONLY the raw JSON document matching the requested schema. Do not wrap in markdown code blocks."}
        ]
        try:
            resp_retry = await client.chat("deep", repair_messages, response_format={"type": "json_object"})
            parsed = _clean_and_parse_json(resp_retry.content)
            summary = parsed.get("summary", "")
            findings = parsed.get("findings", []) or []
            resp = resp_retry
        except Exception as retry_err:
            return ReviewResult(summary="", findings=[], error=f"llm returned non-JSON: {first_err} (retry failed: {retry_err})",
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
