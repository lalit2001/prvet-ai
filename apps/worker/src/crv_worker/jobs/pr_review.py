"""PR review job — the real thing.

Fetches the PR diff via GitHub API, reviews each changed file with the LLM,
persists findings, and posts a batched review comment + status back on GitHub.

M3-lite: no blast-radius join (that lands with symbol_references). Reviews the
diff hunks in isolation with a note in the summary that blast-radius is coming.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

import httpx
from sqlalchemy import text

from crv_core.db import session_factory
from crv_worker.analysis.llm_review import review

_GH = "https://api.github.com"


async def run(ctx, connection_id: str, pr_number: int, repo_full_name: str) -> dict:
    print(f"[pr_review] Starting PR review for {repo_full_name} PR #{pr_number}")
    async with session_factory()() as db:
        conn = (await db.execute(text("""
            SELECT capabilities FROM forge_connections WHERE id = :id
        """), {"id": connection_id})).mappings().one_or_none()
        if conn is None:
            print(f"[pr_review] Error: connection {connection_id} not found")
            return {"status": "failed", "error": "connection not found"}
        token = (conn["capabilities"] or {}).get("dev_token")
        if not token:
            print("[pr_review] Error: no dev_token found for connection")
            return {"status": "failed", "error": "no token stored"}

        repo_row = (await db.execute(text("""
            SELECT id::text FROM repositories
            WHERE connection_id = :cid AND full_name = :fn
        """), {"cid": connection_id, "fn": repo_full_name})).mappings().one_or_none()
        if repo_row is None:
            print(f"[pr_review] Error: repository {repo_full_name} is not enabled")
            return {"status": "failed", "error": f"repo {repo_full_name} not enabled"}
        repo_id = repo_row["id"]

    # Fetch PR metadata + files
    print(f"[pr_review] Fetching PR #{pr_number} metadata and file list from GitHub...")
    async with httpx.AsyncClient(timeout=30) as h:
        headers = {"Authorization": f"Bearer {token}",
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28"}
        pr = (await h.get(f"{_GH}/repos/{repo_full_name}/pulls/{pr_number}", headers=headers)).json()
        files = (await h.get(f"{_GH}/repos/{repo_full_name}/pulls/{pr_number}/files?per_page=100",
                              headers=headers)).json()

    if not isinstance(pr, dict) or not isinstance(files, list):
        print(f"[pr_review] Error: unexpected API response from GitHub. PR: {type(pr)}, Files: {type(files)}")
        return {"status": "failed", "error": "unexpected github response"}

    head_sha = pr.get("head", {}).get("sha", "")
    print(f"[pr_review] PR metadata loaded. Head commit SHA: {head_sha}. Total files: {len(files)}")

    run_id = str(uuid.uuid4())
    async with session_factory()() as db:
        key = f"pr:{repo_id}:{pr_number}:{head_sha}"
        existing = (await db.execute(text("""
            SELECT id FROM runs WHERE idempotency_key = :key
        """), {"key": key})).first()

        if existing:
            run_id = str(existing[0])
            print(f"[pr_review] Found existing run matching commit SHA. Resetting status of run {run_id} to running.")
            await db.execute(text("""
                UPDATE runs 
                SET status = 'running', started_at = now(), finished_at = NULL, error = NULL, stats = '{}'
                WHERE id = :id
            """), {"id": run_id})
        else:
            print(f"[pr_review] Creating new review run: {run_id}")
            await db.execute(text("""
                INSERT INTO runs (id, repo_id, run_type, trigger, status, commit_sha, pr_number,
                                  idempotency_key, started_at, stats)
                VALUES (:id, :rid, 'pr_review', 'webhook', 'running', :sha, :pr, :key, now(), '{}')
            """), {"id": run_id, "rid": repo_id, "sha": head_sha, "pr": pr_number, "key": key})
        await db.commit()

    all_findings: list[dict] = []
    per_file_summaries: list[str] = []
    
    files_to_review = [f for f in files if f.get("status") != "removed" and (f.get("patch") or "")]
    print(f"[pr_review] Reviewing {len(files_to_review)} modified files...")

    for idx, f in enumerate(files_to_review, 1):
        filename = f["filename"]
        patch = f.get("patch") or ""
        print(f"[pr_review] [{idx}/{len(files_to_review)}] Reviewing '{filename}' ({len(patch.splitlines())} lines in diff)...")
        
        result = await review(
            code=patch,
            language=_lang_from_path(filename),
            context=f"File: {filename}\nPR #{pr_number}: {pr.get('title','')}\n{pr.get('body','') or ''}",
            run_id=run_id,
        )
        if result.error:
            print(f"[pr_review] [{idx}/{len(files_to_review)}] File review failed: {result.error}")
            per_file_summaries.append(f"- **{filename}**: review failed — {result.error}")
            continue
            
        print(f"[pr_review] [{idx}/{len(files_to_review)}] File review complete. Found {len(result.findings)} issues.")
        per_file_summaries.append(
            f"- **{filename}**: {len(result.findings)} finding(s)"
        )
        for finding in result.findings:
            finding["_file_path"] = filename
            finding["_patch"] = patch
        all_findings.extend(result.findings)

    print(f"[pr_review] All file reviews complete. Total findings: {len(all_findings)}")

    # Persist findings
    print(f"[pr_review] Saving findings to database...")
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
    print(f"[pr_review] Database records updated successfully.")

    # Prepare inline comments
    review_comments = []
    for f in all_findings:
        filepath = f.get("_file_path")
        patch = f.get("_patch") or ""
        line = f.get("start_line") or f.get("end_line")
        try:
            line_val = int(line) if line else None
        except (ValueError, TypeError):
            line_val = None
        
        # Verify the line is part of the PR diff changes
        modified_lines = _get_modified_lines(patch)
        
        if filepath and line_val and line_val in modified_lines:
            comment_body = (
                f"### **[{f.get('severity', 'low').upper()}] {f.get('title', 'Untitled')}**\n"
                f"**Category:** `{f.get('category', 'maintainability')}` · **Confidence:** `{float(f.get('confidence', 0.6)):.2f}`\n\n"
                f"{f.get('body', '')}"
            )
            if f.get("suggested_patch"):
                comment_body += f"\n\n**Suggested Fix:**\n```diff\n{f['suggested_patch']}\n```"
            
            review_comments.append({
                "path": filepath,
                "line": line_val,
                "body": comment_body
            })
        else:
            print(f"[pr_review] Warning: Line {line_val} in '{filepath}' is not part of the modified PR diff. Skipping inline comment to avoid GitHub API errors.")

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

    # Append list of exact findings to summary body so they are always visible
    if all_findings:
        body_lines.append("### Detailed Findings\n")
        for idx, f in enumerate(all_findings, 1):
            loc = f"{f.get('_file_path', 'unknown')}:{f.get('start_line') or '–'}"
            body_lines.append(
                f"#### {idx}. [{f.get('severity', 'low').upper()}] {f.get('title', 'Untitled')}\n"
                f"- **Location:** `{loc}`\n"
                f"- **Category:** `{f.get('category', 'maintainability')}`\n"
                f"- **Description:** {f.get('body', '')}\n"
            )
            if f.get("suggested_patch"):
                body_lines.append(f"```diff\n{f['suggested_patch']}\n```\n")

    body_lines.extend(per_file_summaries)
    body_lines.append("")
    body_lines.append("_Blast-radius review (cross-file callers) lands with the M3 finish. This review is diff-scoped only._")
    body = "\n".join(body_lines)

    print(f"[pr_review] Attempting to post review and inline comments ({len(review_comments)} inline comments) to GitHub...")
    async with httpx.AsyncClient(timeout=15) as h:
        headers = {"Authorization": f"Bearer {token}",
                   "Accept": "application/vnd.github+json"}
        
        posted = False
        if review_comments:
            try:
                review_url = f"{_GH}/repos/{repo_full_name}/pulls/{pr_number}/reviews"
                resp = await h.post(review_url, headers=headers, json={
                    "body": body,
                    "event": "COMMENT",
                    "comments": review_comments
                })
                if resp.status_code in (200, 201):
                    posted = True
                    print(f"[pr_review] Batched PR review and inline comments posted successfully.")
                else:
                    print(f"[pr_review] Batched PR review returned status {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"[pr_review] Exception posting batched PR review: {e}")
        
        if not posted:
            print(f"[pr_review] Falling back to posting a single summary issue comment...")
            resp = await h.post(f"{_GH}/repos/{repo_full_name}/issues/{pr_number}/comments",
                                 headers=headers, json={"body": body})
            if resp.status_code in (200, 201):
                print(f"[pr_review] Summary comment posted successfully.")
            else:
                print(f"[pr_review] Summary comment posting returned status {resp.status_code}: {resp.text}")

    print(f"[pr_review] Completed review for {repo_full_name} PR #{pr_number}.")
    return {"status": "succeeded", "run_id": run_id, "findings": len(all_findings)}


def _get_modified_lines(patch: str) -> set[int]:
    modified = set()
    if not patch:
        return modified
    
    current_line = 0
    hunk_header_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    
    for line in patch.splitlines():
        m = hunk_header_re.match(line)
        if m:
            current_line = int(m.group(1))
            continue
        
        if line.startswith("+"):
            modified.add(current_line)
            current_line += 1
        elif line.startswith("-"):
            continue
        else:
            current_line += 1
            
    return modified


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
