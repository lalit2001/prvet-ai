"""Webhook fan-out job — routes pull_request events to pr_review."""
from __future__ import annotations

from sqlalchemy import text

from crv_core.db import session_factory


async def handle_forge_event(ctx, connection_id: str, external_event_id: str, event_type: str) -> dict:
    async with session_factory()() as db:
        row = (await db.execute(
            text("""UPDATE webhook_events SET processed_at = now()
                    WHERE connection_id = :cid AND external_event_id = :eid
                    RETURNING payload"""),
            {"cid": connection_id, "eid": external_event_id},
        )).mappings().one_or_none()
        await db.commit()
    if row is None:
        return {"connection_id": connection_id, "event_type": event_type, "status": "no_payload"}

    payload = row["payload"] or {}

    # GitHub pull_request event → enqueue pr_review
    if event_type == "pull_request":
        action = payload.get("action")
        if action in ("opened", "reopened", "synchronize"):
            pr = payload.get("pull_request", {})
            repo = payload.get("repository", {})
            pr_number = pr.get("number")
            repo_full_name = repo.get("full_name")
            if pr_number and repo_full_name:
                from crv_worker.jobs.pr_review import run as pr_run
                return await pr_run(ctx, connection_id=connection_id, pr_number=pr_number,
                                     repo_full_name=repo_full_name)

    # GitHub issue_comment event → enqueue pr_reply
    if event_type == "issue_comment":
        action = payload.get("action")
        if action == "created":
            comment = payload.get("comment", {})
            body = comment.get("body", "")
            if "@prvet" in body.lower() or "@pr-analyzer" in body.lower() or "@prvet-ai" in body.lower():
                repo = payload.get("repository", {})
                issue = payload.get("issue", {})
                pr_number = issue.get("number")
                repo_full_name = repo.get("full_name")
                comment_id = str(comment.get("id"))
                if pr_number and repo_full_name:
                    from crv_worker.jobs.pr_reply import run as reply_run
                    return await reply_run(ctx, connection_id=connection_id, pr_number=pr_number,
                                            repo_full_name=repo_full_name, comment_id=comment_id, body=body)

    print(f"[handle_forge_event] connection={connection_id} event={event_type} — no dispatch")
    return {"connection_id": connection_id, "event_type": event_type, "status": "no_dispatch"}
