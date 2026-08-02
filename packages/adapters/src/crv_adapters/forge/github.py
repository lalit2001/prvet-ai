"""GitHub adapter. Only the M1-critical methods are implemented — verify_webhook + parse_event.
The rest raise NotImplementedError so callers surface the gap loudly. Fill in as jobs need them."""
from __future__ import annotations

import hashlib
import hmac
from typing import Literal

from crv_adapters.forge.base import (
    DiffHunk, ForgeEvent, PullRequest, ReviewComment,
)


class GitHubAdapter:
    forge_type = "github"

    async def verify_webhook(self, headers: dict[str, str], body: bytes, secret: str) -> bool:
        sig = headers.get("x-hub-signature-256") or headers.get("X-Hub-Signature-256")
        if not sig or not sig.startswith("sha256="):
            return False
        mac = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(f"sha256={mac}", sig)

    def parse_event(self, headers: dict[str, str], payload: dict) -> ForgeEvent | None:
        event = headers.get("x-github-event") or headers.get("X-GitHub-Event")
        action = payload.get("action")
        repo = (payload.get("repository") or {}).get("full_name", "")
        if event == "pull_request" and action in ("opened", "reopened", "synchronize"):
            kind = {"opened": "pr_opened", "reopened": "pr_reopened", "synchronize": "pr_synchronize"}[action]
            return ForgeEvent(kind=kind, repo_full_name=repo, payload=payload)  # type: ignore[arg-type]
        if event == "issue_comment" and action == "created":
            return ForgeEvent(kind="comment", repo_full_name=repo, payload=payload)
        return None  # unknown events are ignored, not errors — AC1.4

    async def get_pull_request(self, repo: str, number: int) -> PullRequest:
        raise NotImplementedError  # M1

    async def get_diff(self, repo: str, base_sha: str, head_sha: str) -> list[DiffHunk]:
        raise NotImplementedError  # M2

    async def get_file_content(self, repo: str, path: str, ref: str) -> bytes | None:
        raise NotImplementedError  # M2

    async def post_review(self, repo: str, pr: int, commit_sha: str, summary: str, comments: list[ReviewComment]) -> dict[str, str]:
        raise NotImplementedError  # M1

    async def update_comment(self, repo: str, comment_id: str, body: str) -> None:
        raise NotImplementedError

    async def resolve_thread(self, repo: str, comment_id: str) -> None:
        raise NotImplementedError

    async def set_status(self, repo: str, commit_sha: str, state: Literal["pending", "success", "failure", "neutral"], title: str, summary: str, details_url: str) -> None:
        raise NotImplementedError  # M3

    async def get_user_permission(self, repo: str, external_user_id: str) -> str:
        raise NotImplementedError  # M3

    async def supports(self, capability: str) -> bool:
        # GitHub capabilities are known-fixed for github.com; enterprise probes at connect time
        return capability in {"external_status_check", "suggestion_blocks", "resolve_thread", "batch_review", "draft_pr_events"}

    async def get_clone_credentials(self, repo: str) -> tuple[str, str]:
        raise NotImplementedError  # M2 — App installation token
