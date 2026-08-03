"""Findings & Pull Requests endpoints.

Provides detailed findings retrieval, manual resolution triggers, and Pull Requests aggregation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from crv_core.db import session_factory

router = APIRouter()


class ResolveIn(BaseModel):
    resolution: dict | None = None


@router.get("/findings/{finding_id}")
async def get_finding(finding_id: str):
    async with session_factory()() as db:
        row = (await db.execute(text("""
            SELECT f.id::text, f.source, f.category, f.severity, f.title, f.body, f.file_path,
                   f.start_line, f.end_line, f.confidence, f.status, f.created_at, f.suggested_patch, f.resolution,
                   repo.full_name AS repo_name, repo.id::text AS repo_id
            FROM findings f
            JOIN repositories repo ON repo.id = f.repo_id
            WHERE f.id = :id
        """), {"id": finding_id})).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "finding not found")
    return dict(row)


@router.post("/findings/{finding_id}/resolve")
async def resolve_finding(finding_id: str, body: ResolveIn = None):
    # 1. Fetch finding details and target branch information
    async with session_factory()() as db:
        row = (await db.execute(text("""
            SELECT f.id, f.file_path, f.suggested_patch, repo.full_name AS repo_name,
                   repo.default_branch, conn.capabilities, r.pr_number
            FROM findings f
            JOIN repositories repo ON repo.id = f.repo_id
            JOIN forge_connections conn ON conn.id = repo.connection_id
            LEFT JOIN runs r ON r.id = f.run_id
            WHERE f.id = :id
        """), {"id": finding_id})).mappings().one_or_none()
        
        if not row:
            raise HTTPException(404, "finding not found")
        
        # Determine target branch (PR source branch or default branch)
        branch = None
        if row["pr_number"] is not None:
            we_row = (await db.execute(text("""
                SELECT payload->'pull_request'->'head'->>'ref' AS source_branch
                FROM webhook_events
                WHERE event_type = 'pull_request'
                  AND payload->'pull_request'->>'number' = :pr_num
                ORDER BY created_at DESC LIMIT 1
            """), {"pr_num": str(row["pr_number"])})).mappings().one_or_none()
            if we_row:
                branch = we_row["source_branch"]
        
        if not branch:
            branch = row["default_branch"] or "main"
        
        token = (row["capabilities"] or {}).get("dev_token")
        patch_text = row["suggested_patch"]
        file_path = row["file_path"]
        repo_name = row["repo_name"]

    # 2. Apply and commit patch directly to GitHub
    is_pr_fix = body and body.resolution and body.resolution.get("method") == "pr_ui_fix"
    if is_pr_fix and token and patch_text and file_path and file_path != "adhoc":
        import os
        import base64
        import subprocess
        import tempfile
        import httpx
        
        # Fetch file metadata and current content from GitHub
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json"
        }
        url = f"https://api.github.com/repos/{repo_name}/contents/{file_path}?ref={branch}"
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                file_info = resp.json()
                current_sha = file_info.get("sha")
                current_b64 = file_info.get("content", "")
                
                # Decode base64
                current_bytes = base64.b64decode(current_b64.replace("\n", ""))
                
                with tempfile.TemporaryDirectory() as tmpdir:
                    file_path_local = os.path.join(tmpdir, "file_to_patch")
                    patch_path_local = os.path.join(tmpdir, "patch.diff")
                    
                    with open(file_path_local, "wb") as f_out:
                        f_out.write(current_bytes)
                    
                    # Ensure patch ends with a newline and write it
                    with open(patch_path_local, "w", encoding="utf-8") as p_out:
                        p_out.write(patch_text + "\n")
                    
                    # Apply the patch using the local patch utility
                    proc = subprocess.run(
                        ["patch", "-s", file_path_local, patch_path_local],
                        capture_output=True,
                        text=True
                    )
                    
                    if proc.returncode == 0:
                        with open(file_path_local, "rb") as f_in:
                            patched_bytes = f_in.read()
                        
                        patched_b64 = base64.b64encode(patched_bytes).decode("utf-8")
                        
                        # Commit the change back to GitHub
                        put_url = f"https://api.github.com/repos/{repo_name}/contents/{file_path}"
                        put_resp = await client.put(put_url, headers=headers, json={
                            "message": f"fix: resolve Sentry review finding in {file_path}",
                            "content": patched_b64,
                            "sha": current_sha,
                            "branch": branch
                        })
                        if put_resp.status_code not in (200, 201):
                            print(f"[resolve] Failed to commit patched file: {put_resp.text}")
                    else:
                        print(f"[resolve] patch failed: stdout={proc.stdout}, stderr={proc.stderr}")

    # 3. Update database status
    async with session_factory()() as db:
        await db.execute(text("""
            UPDATE findings
            SET status = 'resolved',
                resolution = CAST(:res AS jsonb)
            WHERE id = :id
        """), {
            "id": finding_id,
            "res": json.dumps(body.resolution if body and body.resolution else {
                "method": "manual_fix",
                "resolved_at": datetime.now(timezone.utc).isoformat()
            })
        })
        await db.commit()
        
    return {"status": "success", "finding_id": finding_id}


@router.get("/prs")
async def list_prs():
    async with session_factory()() as db:
        # Get all unique PRs based on repo_id + pr_number from runs
        pr_rows = (await db.execute(text("""
            SELECT DISTINCT ON (r.repo_id, r.pr_number)
                   r.id::text AS run_id,
                   r.repo_id::text,
                   repo.full_name AS repo_name,
                   r.pr_number,
                   r.commit_sha,
                   r.status AS run_status,
                   r.created_at
            FROM runs r
            JOIN repositories repo ON repo.id = r.repo_id
            WHERE r.pr_number IS NOT NULL
            ORDER BY r.repo_id, r.pr_number, r.created_at DESC
        """))).mappings().all()

        prs = []
        for pr in pr_rows:
            # Let's find PR metadata from webhook_events if possible
            we_row = (await db.execute(text("""
                SELECT payload->'pull_request'->>'title' AS title,
                       payload->'pull_request'->'head'->>'ref' AS source_branch,
                       payload->'pull_request'->'base'->>'ref' AS target_branch
                FROM webhook_events
                WHERE event_type = 'pull_request'
                  AND payload->'pull_request'->>'number' = :pr_num
                ORDER BY created_at DESC LIMIT 1
            """), {"pr_num": str(pr["pr_number"])})).mappings().one_or_none()

            title = we_row["title"] if we_row and we_row["title"] else f"Pull Request #{pr['pr_number']}"
            source_branch = we_row["source_branch"] if we_row and we_row["source_branch"] else "feature"
            target_branch = we_row["target_branch"] if we_row and we_row["target_branch"] else "main"

            # Get findings for this run
            findings = (await db.execute(text("""
                SELECT id::text, source, category, severity, title, body, file_path,
                       start_line, end_line, confidence, status, created_at, suggested_patch, resolution
                FROM findings
                WHERE run_id = :run_id
                ORDER BY severity = 'critical' DESC, severity = 'high' DESC, severity = 'medium' DESC, created_at DESC
            """), {"run_id": pr["run_id"]})).mappings().all()

            # Structure files/git structure for this PR
            # A dictionary mapping file_path to its findings list
            files_tree = {}
            for f in findings:
                fp = f["file_path"]
                if fp not in files_tree:
                    files_tree[fp] = []
                files_tree[fp].append(dict(f))

            prs.append({
                "run_id": pr["run_id"],
                "repo_id": pr["repo_id"],
                "repo_name": pr["repo_name"],
                "pr_number": pr["pr_number"],
                "commit_sha": pr["commit_sha"],
                "title": title,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "created_at": pr["created_at"],
                "findings": [dict(f) for f in findings],
                "files_tree": files_tree,
                "open_findings_count": sum(1 for f in findings if f["status"] == "open")
            })

        # Sort PRs by latest created_at
        prs.sort(key=lambda x: x["created_at"], reverse=True)
        return prs


@router.get("/repos/{repo_name:path}/prs/{pr_number}/gate")
async def get_pr_gate_status(repo_name: str, pr_number: int):
    async with session_factory()() as db:
        repo_row = (await db.execute(text("""
            SELECT id::text, config FROM repositories WHERE full_name = :repo
        """), {"repo": repo_name})).mappings().one_or_none()
        
        if not repo_row:
            raise HTTPException(404, "Repository not found")
            
        repo_id = repo_row["id"]
        repo_cfg = repo_row["config"] or {}
        
        review_cfg = repo_cfg.get("review", {})
        block_severity = review_cfg.get("block_severity", "high")
        gated_categories = review_cfg.get("categories", ["security", "bug", "performance"])
        
        run_row = (await db.execute(text("""
            SELECT id::text FROM runs
            WHERE repo_id = :repo_id AND pr_number = :pr_num
            ORDER BY created_at DESC LIMIT 1
        """), {"repo_id": repo_id, "pr_num": pr_number})).mappings().one_or_none()
        
        if not run_row:
            return {"passed": True, "reason": "No review run has been recorded for this PR yet."}
            
        run_id = run_row["id"]
        
        findings = (await db.execute(text("""
            SELECT category, severity, title, file_path, start_line
            FROM findings
            WHERE run_id = :run_id AND status = 'open'
        """), {"run_id": run_id})).mappings().all()
        
    SEV_MAP = {"critical": 5, "high": 4, "medium": 3, "low": 2, "info": 1}
    threshold_val = SEV_MAP.get(block_severity.lower(), 4)
    
    for f in findings:
        f_sev = f["severity"].lower()
        f_cat = f["category"].lower()
        f_val = SEV_MAP.get(f_sev, 2)
        
        if f_cat in [c.lower() for c in gated_categories] and f_val >= threshold_val:
            loc = f"{f['file_path']}:{f['start_line'] or '–'}"
            return {
                "passed": False,
                "reason": f"Gating violation: [{f_sev.upper()}] {f['title']} in {loc} ({f_cat})"
            }
            
    return {"passed": True, "reason": "All check gates passed successfully."}

