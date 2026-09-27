"""LLM calls for review: triage (fast) → review (fast|deep) → verify (fast).

Produces the PRD §13.2 finding schema. On any error, returns an empty result
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


async def _client():
    async with session_factory()() as db:
        row = (await db.execute(text(
            "SELECT COALESCE(settings->'providers', '[]'::jsonb) AS ps FROM organizations WHERE slug='default'"
        ))).mappings().one()
    return client_from_org(list(row["ps"] or []))


async def summarize_project(prompt: str, run_id: str | None = None) -> str:
    try:
        client = await _client()
    except LlmError as e:
        return f"_summary skipped: {e}_"

    messages = [
        {"role": "system", "content": "You are a senior tech lead helping developers understand a codebase. Return a plain markdown paragraph (4-6 sentences) summarizing the codebase."},
        {"role": "user", "content": prompt}
    ]
    try:
        resp = await client.chat("deep", messages)
        if run_id:
            await _log_call(run_id, resp, "summary")
        return resp.content or ""
    except Exception as e:
        return f"_summary failed: {e}_"


async def review(code: str, full_file: str | None = None, language: str | None = None, context: str | None = None,
                 run_id: str | None = None, model_role: str = "deep") -> ReviewResult:
    try:
        client = await _client()
    except LlmError as e:
        return ReviewResult(summary="", findings=[], error=str(e))

    user_parts = []
    if context:
        user_parts.append(f"Context:\n{context}\n")
    if language:
        user_parts.append(f"Language: {language}")
    if full_file:
        user_parts.append(f"FULL SOURCE FILE (for data-flow/AST context):\n```\n{full_file}\n```\n")
    user_parts.append(f"Review these DIFF CHANGES (Patch):\n```diff\n{code}\n```")
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n".join(user_parts)},
    ]

    try:
        # role resolves via provider.role_map; falls back to a plain model name.
        resp = await client.chat(model_role, messages,
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
            resp_retry = await client.chat(model_role, repair_messages, response_format={"type": "json_object"})
            parsed = _clean_and_parse_json(resp_retry.content)
            summary = parsed.get("summary", "")
            findings = parsed.get("findings", []) or []
            resp = resp_retry
        except Exception as retry_err:
            return ReviewResult(summary="", findings=[], error=f"llm returned non-JSON: {first_err} (retry failed: {retry_err})",
                                stats={"raw": resp.content[:2000]})

    if run_id:
        await _log_call(run_id, resp, "review")

    return ReviewResult(
        summary=summary,
        findings=findings,
        stats={"model": resp.model, "prompt_tokens": resp.prompt_tokens,
               "completion_tokens": resp.completion_tokens, "latency_ms": resp.latency_ms},
    )


_TRIAGE = """You route pull-request files to the right review depth. Return STRICT JSON:
{"files": [{"path": "<path>", "verdict": "skip|fast|deep", "reason": "<short>"}]}

- skip: formatting/whitespace only, comments/docs only, generated code, lockfiles, pure renames.
- fast: routine changes with no security surface and no public-API change.
- deep: security-sensitive code (auth, secrets, crypto, SQL, file/network I/O, permissions, payments),
  public signature changes, changes to symbols with many callers, error-handling or concurrency changes.
When unsure, choose deep. Every input path must appear exactly once."""

_VERIFY = """You are a skeptical second reviewer. For each candidate finding decide whether it is REAL given the
code shown — not speculative, not already handled, not a style preference. Return STRICT JSON:
{"confirmed": [<index>, ...], "rejected": [{"index": <int>, "reason": "<short>"}]}"""


async def triage_files(items: list[dict], run_id: str | None = None) -> dict[str, str] | None:
    """items: [{path, excerpt, changed_symbols, callers, signature_changed}] → {path: verdict}.
    None when the model is unavailable/unparseable — caller falls back to deep for everything."""
    if not items:
        return {}
    try:
        client = await _client()
        resp = await client.chat("fast", [
            {"role": "system", "content": _TRIAGE},
            {"role": "user", "content": json.dumps({"files": items}, ensure_ascii=False)},
        ], response_format={"type": "json_object"}, temperature=0.0)
        if run_id:
            await _log_call(run_id, resp, "triage")
        out = {}
        for f in _clean_and_parse_json(resp.content).get("files", []):
            v = str(f.get("verdict", "deep")).lower()
            out[f.get("path", "")] = v if v in ("skip", "fast", "deep") else "deep"
        return out
    except Exception as e:  # noqa: BLE001 — triage is best-effort
        print(f"[llm_review] triage failed, reviewing everything deep: {e}")
        return None


async def verify_findings(items: list[dict], run_id: str | None = None) -> set[int] | None:
    """items: [{index, title, body, file, lines, code}] → confirmed indices; None if the pass failed."""
    if not items:
        return set()
    try:
        client = await _client()
        resp = await client.chat("fast", [
            {"role": "system", "content": _VERIFY},
            {"role": "user", "content": json.dumps({"findings": items}, ensure_ascii=False)},
        ], response_format={"type": "json_object"}, temperature=0.0)
        if run_id:
            await _log_call(run_id, resp, "verify")
        data = _clean_and_parse_json(resp.content)
        return {int(i) for i in data.get("confirmed", [])}
    except Exception as e:  # noqa: BLE001
        print(f"[llm_review] verify failed, keeping all findings: {e}")
        return None


async def _log_call(run_id: str, resp, purpose: str = "review") -> None:
    async with session_factory()() as db:
        await db.execute(text("""
            INSERT INTO llm_calls (id, run_id, model, purpose, prompt_tokens, completion_tokens,
                                   latency_ms, status)
            VALUES (:id, :rid, :model, :purpose, :pt, :ct, :lat, 'ok')
        """), {"id": str(uuid.uuid4()), "rid": run_id, "model": resp.model, "purpose": purpose,
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
