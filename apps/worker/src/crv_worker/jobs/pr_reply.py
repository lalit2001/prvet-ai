"""PR reply job — replies to @mentions on pull requests."""
from __future__ import annotations

import httpx
from sqlalchemy import text

from crv_core.db import session_factory
from crv_worker.analysis.llm_review import _client
from crv_worker.forge_token import connection_auth

_GH = "https://api.github.com"


async def run(ctx, connection_id: str, pr_number: int, repo_full_name: str, comment_id: str, body: str) -> dict:
    print(f"[pr_reply] Replying to comment {comment_id} on {repo_full_name} PR #{pr_number}")
    try:
        auth = await connection_auth(connection_id)
    except LookupError as e:
        return {"status": "failed", "error": str(e)}
    token = auth.token

    try:
        llm = await _client()
    except Exception as e:  # noqa: BLE001
        return {"status": "failed", "error": f"no llm client: {e}"}

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
