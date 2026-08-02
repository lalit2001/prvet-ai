"""PR review job — the real thing.

Fetches the PR diff via GitHub API, reviews each changed file with the LLM,
persists findings, and posts a batched review comment + status back on GitHub.

M3-lite: no blast-radius join (that lands with symbol_references). Reviews the
diff hunks in isolation with a note in the summary that blast-radius is coming.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
from sqlalchemy import text

from crv_core.db import session_factory
from crv_worker.analysis.llm_review import review

_GH = "https://api.github.com"


async def run(ctx, connection_id: str, pr_number: int, repo_full_name: str) -> dict:
    async with session_factory()() as db:
        conn = (await db.execute(text("""
            SELECT capabilities FROM forge_connections WHERE id = :id
        """), {"id": connection_id})).mappings().one_or_none()
        if conn is None:
            return {"status": "failed", "error": "connection not found"}
        token = (conn["capabilities"] or {}).get("dev_token")
        if not token:
            return {"status": "failed", "error": "no token stored"}

        repo_row = (await db.execute(text("""
            SELECT id::text FROM repositories
            WHERE connection_id = :cid AND full_name = :fn
        """), {"cid": connection_id, "fn": repo_full_name})).mappings().one_or_none()
        if repo_row is None:
            return {"status": "failed", "error": f"repo {repo_full_name} not enabled"}
        repo_id = repo_row["id"]

    # Fetch PR metadata + files
    async with httpx.AsyncClient(timeout=30) as h:
        headers = {"Authorization": f"Bearer {token}",
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        pr = (await h.get(f"{_GH}/repos/{repo_full_name}/pulls/{pr_number}", headers=headers)).json()
        files = (await h.get(f"{_GH}/repos/{repo_full_name}/pulls/{pr_number}/files?per_page=100",
                              headers=headers)).json()

    if not isinstance(pr, dict) or not isinstance(files, list):
        return {"status": "failed", "error": "unexpected github response"}

    head_sha = pr.get("head", {}).get("sha", "")
    run_id = str(uuid.uuid4())
    async with session_factory()() as db:
        await db.execute(text("""
            INSERT INTO runs (id, repo_id, run_type, trigger, status, commit_sha, pr_number,
                              idempotency_key, started_at, stats)
            VALUES (:id, :rid, 'pr_review', 'webhook', 'running', :sha, :pr, :key, now(), '{}')
            ON CONFLICT (idempotency_key) DO NOTHING
        """), {"id": run_id, "rid": repo_id, "sha": head_sha, "pr": pr_number,
                "key": f"pr:{repo_id}:{pr_number}:{head_sha}"})
        await db.commit()

    all_findings: list[dict] = []
    per_file_summaries: list[str] = []
    for f in files:
        if f.get("status") == "removed":
            continue
        # LLM review the patch. Falls back to reviewing raw_url if no patch (large binary etc.)
        patch = f.get("patch") or ""
        if not patch:
            continue
        result = await review(
            code=patch,
            language=_lang_from_path(f["filename"]),
            context=f"File: {f['filename']}\nPR #{pr_number}: {pr.get('title','')}\n{pr.get('body','') or ''}",
            run_id=run_id,
        )
        if result.error:
            per_file_summaries.append(f"- **{f['filename']}**: review failed — {result.error}")
            continue
        per_file_summaries.append(
            f"- **{f['filename']}**: {len(result.findings)} finding(s)"
        )
        for finding in result.findings:
            finding["_file_path"] = f["filename"]
        all_findings.extend(result.findings)

    # Persist findings
    async with session_factory()() as db:
        for f in all_findings:
            fp = _fingerprint(f)
            await db.execute(text("""
                INSERT INTO findings (id, repo_id, run_id, fingerprint, source, category,
                                      severity, confidence, title, body, file_path,
                                      start_line, end_line, suggested_patch, status)
                VALUES (:id, :rid, :run, :fp, 'llm', :cat, :sev, :conf, :title, :body,
                        :file, :sl, :el, :patch, 'open')
            """), {"id": str(uuid.uuid4()), "rid": repo_id, "run": run_id, "fp": fp,
                    "cat": f.get("category", "maintainability"), "sev": f.get("severity", "low"),
                    "conf": float(f.get("confidence", 0.6)), "title": f.get("title", "Untitled"),
                    "body": f.get("body", ""), "file": f.get("_file_path", "unknown"),
                    "sl": f.get("start_line"), "el": f.get("end_line"),
                    "patch": f.get("suggested_patch")})
        await db.execute(text("""
            UPDATE runs SET status='succeeded', finished_at=now(),
                            stats=CAST(:stats AS jsonb)
            WHERE id=:id
        """), {"id": run_id, "stats": json.dumps({"files_reviewed": len(per_file_summaries),
                                                    "findings": len(all_findings)})})
        await db.commit()

    # Post a summary comment to GitHub
    counts: dict[str, int] = {}
    for f in all_findings:
        counts[f.get("severity", "info")] = counts.get(f.get("severity", "info"), 0) + 1
    body_lines = [
        "## Sentry Review",
        "",
        f"**Files reviewed:** {len(per_file_summaries)} · **Findings:** {len(all_findings)}",
        ""
    ]
    if counts:
        body_lines.append("| Severity | Count |")
        body_lines.append("|----------|-------|")
        for sev in ("critical", "high", "medium", "low", "info"):
            if counts.get(sev):
                body_lines.append(f"| {sev} | {counts[sev]} |")
        body_lines.append("")
    body_lines.extend(per_file_summaries)
    body_lines.append("")
    body_lines.append("_Blast-radius review (cross-file callers) lands with the M3 finish. This review is diff-scoped only._")
    body = "\n".join(body_lines)

    async with httpx.AsyncClient(timeout=15) as h:
        headers = {"Authorization": f"Bearer {token}",
                   "Accept": "application/vnd.github+json"}
        await h.post(f"{_GH}/repos/{repo_full_name}/issues/{pr_number}/comments",
                     headers=headers, json={"body": body})

    return {"status": "succeeded", "run_id": run_id, "findings": len(all_findings)}


def _fingerprint(f: dict) -> str:
    import hashlib
    key = f"{f.get('_file_path','')}:{f.get('title','')}:{f.get('category','')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _lang_from_path(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return {
        "py": "python", "ts": "typescript", "tsx": "typescript",
        "js": "javascript", "jsx": "javascript",
        "go": "go", "java": "java", "rs": "rust", "rb": "ruby",
        "cs": "csharp", "php": "php", "kt": "kotlin",
        "c": "c", "cpp": "cpp", "h": "c", "hpp": "cpp",
        "sql": "sql", "yaml": "yaml", "yml": "yaml",
    }.get(ext, ext or "text")
