"""LocalRunner — shells to subprocess. Compose default."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Literal

from crv_adapters.runner.base import JobSpec, RunnerCapabilities

_procs: dict[str, asyncio.subprocess.Process] = {}


class LocalRunner:
    async def submit(self, job_spec: JobSpec) -> str:
        proc = await asyncio.create_subprocess_exec(
            *job_spec.command,
            env={**job_spec.env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        handle = str(proc.pid)
        _procs[handle] = proc
        return handle

    async def status(self, handle: str) -> Literal["pending", "running", "succeeded", "failed"]:
        proc = _procs.get(handle)
        if proc is None:
            return "failed"
        if proc.returncode is None:
            return "running"
        return "succeeded" if proc.returncode == 0 else "failed"

    async def logs(self, handle: str, follow: bool = False) -> AsyncIterator[str]:
        proc = _procs.get(handle)
        if proc is None or proc.stdout is None:
            return
        async for line in proc.stdout:
            yield line.decode(errors="replace")

    async def cancel(self, handle: str) -> None:
        proc = _procs.get(handle)
        if proc and proc.returncode is None:
            proc.terminate()

    def capabilities(self) -> RunnerCapabilities:
        # Whatever this host has; the orchestrator only uses this to reject GPU jobs.
        return RunnerCapabilities(max_duration_s=86400, max_memory_mb=32768, max_disk_mb=100_000)
