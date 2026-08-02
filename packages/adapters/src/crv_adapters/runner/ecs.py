"""ECS Fargate runner — M5."""
from typing import AsyncIterator, Literal
from crv_adapters.runner.base import JobSpec, RunnerCapabilities


class EcsRunner:
    async def submit(self, job_spec: JobSpec) -> str: raise NotImplementedError
    async def status(self, handle: str) -> Literal["pending", "running", "succeeded", "failed"]: raise NotImplementedError
    async def logs(self, handle: str, follow: bool = False) -> AsyncIterator[str]: raise NotImplementedError
    async def cancel(self, handle: str) -> None: raise NotImplementedError
    def capabilities(self) -> RunnerCapabilities: return RunnerCapabilities(max_duration_s=86400, max_memory_mb=32768, max_disk_mb=200_000)
