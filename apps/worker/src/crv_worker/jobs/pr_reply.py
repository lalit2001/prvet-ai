"""PR reply job — replies to @mentions on pull requests."""
from __future__ import annotations

import httpx
from sqlalchemy import text

from crv_core.db import session_factory
from crv_adapters.llm import client_from_org

_GH = "https://api.github.com"


async def run(ctx, connection_id: str, pr_number: int, repo_full_name: str, comment_id: str, body: str) -> dict:
    print(f"[pr_reply] Replying to comment {comment_id} on {repo_full_name} PR #{pr_number}")
    async with session_factory()() as db:
        conn = (await db.execute(text("""
            SELECT capabilities, org_id FROM forge_connections WHERE id = :id
        """), {"id": connection_id})).mappings().one_or_none()
        if conn is None:
            return {"status": "failed", "error": "connection not found"}
            
        token = (conn["capabilities"] or {}).get("dev_token")
        org_id = conn["org_id"]
        
        if not token:
            return {"status": "failed", "error": "no dev_token"}

    # Initialize LLM client
    llm = await client_from_org(org_id)
    if not llm:
        return {"status": "failed", "error": "no llm client"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    async with httpx.AsyncClient(timeout=30) as h:
        # Fetch PR diff to give context
        diff_resp = await h.get(f"{_GH}/repos/{repo_full_name}/pulls/{pr_number}", headers={
            **headers, "Accept": "application/vnd.github.v3.diff"
        })
        diff_text = diff_resp.text[:5000] if diff_resp.status_code == 200 else ""

        system_prompt = """You are an AI code reviewer assistant (PRVet). A developer has mentioned you in a Pull Request comment.
You should read their question or clarification and answer it directly, concisely, and helpfully.
Refer to the PR diff if necessary, but keep your answer focused on their comment.
Return ONLY your reply text. No JSON."""
        
        user_prompt = f"PR Diff Context (truncated):\n```diff\n{diff_text}\n```\n\nDeveloper Comment:\n{body}\n\nPlease reply to the developer:"
        
        print("[pr_reply] Querying LLM...")
        try:
            res = await llm.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], fast=True)
            reply_text = res.content
        except Exception as e:
            print(f"[pr_reply] LLM Error: {e}")
            reply_text = "I encountered an error while trying to generate a reply. Please try again later."

        print("[pr_reply] Posting reply to GitHub...")
        post_resp = await h.post(f"{_GH}/repos/{repo_full_name}/issues/{pr_number}/comments", headers=headers, json={
            "body": reply_text
        })
        if post_resp.status_code not in (200, 201):
            print(f"[pr_reply] Failed to post reply: {post_resp.text}")
            return {"status": "failed", "error": "post failed"}

    return {"status": "success", "comment_id": comment_id}
