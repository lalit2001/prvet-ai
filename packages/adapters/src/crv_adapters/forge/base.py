"""ForgeAdapter Protocol — PRD §10.1. Implement exactly."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class DiffHunk:
    file_path: str
    old_path: str | None
    change_type: Literal["added", "modified", "deleted", "renamed"]
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    content: str


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    description: str
    author_external_id: str
    source_branch: str
    target_branch: str
    head_sha: str
    base_sha: str
    is_draft: bool
    labels: list[str]


@dataclass(frozen=True)
class ReviewComment:
    file_path: str
    line: int
    body: str
    suggestion: str | None = None


@dataclass(frozen=True)
class ForgeEvent:
    kind: Literal["pr_opened", "pr_synchronize", "pr_reopened", "push", "comment", "ignored"]
    repo_full_name: str
    payload: dict


@runtime_checkable
class ForgeAdapter(Protocol):
    forge_type: str

    async def verify_webhook(self, headers: dict[str, str], body: bytes, secret: str) -> bool: ...
    def parse_event(self, headers: dict[str, str], payload: dict) -> ForgeEvent | None: ...
    async def get_pull_request(self, repo: str, number: int) -> PullRequest: ...
    async def get_diff(self, repo: str, base_sha: str, head_sha: str) -> list[DiffHunk]: ...
    async def get_file_content(self, repo: str, path: str, ref: str) -> bytes | None: ...
    async def post_review(
        self, repo: str, pr: int, commit_sha: str,
        summary: str, comments: list[ReviewComment],
    ) -> dict[str, str]: ...
    async def update_comment(self, repo: str, comment_id: str, body: str) -> None: ...
    async def resolve_thread(self, repo: str, comment_id: str) -> None: ...
    async def set_status(
        self, repo: str, commit_sha: str,
        state: Literal["pending", "success", "failure", "neutral"],
        title: str, summary: str, details_url: str,
    ) -> None: ...
    async def get_user_permission(self, repo: str, external_user_id: str) -> str: ...
    async def supports(self, capability: str) -> bool: ...
    async def get_clone_credentials(self, repo: str) -> tuple[str, str]: ...
    async def create_commit(self, repo: str, branch: str, file_path: str, content: str, commit_message: str) -> str: ...
    async def get_comment_thread(self, repo: str, pr_number: int, comment_id: str) -> list[ReviewComment]: ...

