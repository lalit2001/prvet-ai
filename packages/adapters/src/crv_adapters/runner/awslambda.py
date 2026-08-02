"""AWS Lambda runner — short jobs only (<15 min). M5."""
from typing import AsyncIterator, Literal
from crv_adapters.runner.base import JobSpec, RunnerCapabilities


class LambdaRunner:
    async def submit(self, job_spec: JobSpec) -> str: raise NotImplementedError
    async def status(self, handle: str) -> Literal["pending", "running", "succeeded", "failed"]: raise NotImplementedError
    async def logs(self, handle: str, follow: bool = False) -> AsyncIterator[str]: raise NotImplementedError
    async def cancel(self, handle: str) -> None: raise NotImplementedError
    def capabilities(self) -> RunnerCapabilities:
        # AWS Lambda hard limits — used by orchestrator to reject long/big jobs.
        return RunnerCapabilities(max_duration_s=900, max_memory_mb=10240, max_disk_mb=10240)
