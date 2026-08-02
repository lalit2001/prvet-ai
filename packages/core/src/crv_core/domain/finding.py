from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

Severity = Literal["critical", "high", "medium", "low", "info"]
Category = Literal["security", "bug", "performance", "maintainability", "style", "dependency", "test"]
Source = Literal["semgrep", "gitleaks", "osv", "llm", "custom"]


@dataclass(frozen=True)
class Finding:
    repo_id: UUID
    run_id: UUID
    fingerprint: str
    source: Source
    category: Category
    severity: Severity
    title: str
    body: str
    file_path: str
    start_line: int | None = None
    end_line: int | None = None
    confidence: float = 0.8
    rule_id: str | None = None
    suggested_patch: str | None = None
    affected_symbols: list[str] = field(default_factory=list)
