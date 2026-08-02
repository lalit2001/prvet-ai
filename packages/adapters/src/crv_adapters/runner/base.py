"""JobRunner Protocol — PRD §10.2. Where escalation lives."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class RunnerCapabilities:
    max_duration_s: int
    max_memory_mb: int
    max_disk_mb: int
    supports_gpu: bool = False


@dataclass(frozen=True)
class JobSpec:
    image: str
    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    estimated_duration_s: int = 300
    estimated_memory_mb: int = 1024
    estimated_disk_mb: int = 2048


@runtime_checkable
class JobRunner(Protocol):
    async def submit(self, job_spec: JobSpec) -> str: ...
    async def status(self, handle: str) -> Literal["pending", "running", "succeeded", "failed"]: ...
    async def logs(self, handle: str, follow: bool = False) -> AsyncIterator[str]: ...
    async def cancel(self, handle: str) -> None: ...
    def capabilities(self) -> RunnerCapabilities: ...
