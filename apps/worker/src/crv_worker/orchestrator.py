"""DAG expansion + escalation logic. PRD §6, F5.

`decide_runner(job)` compares JobSpec against each configured runner's capabilities
and picks the smallest one that fits — same logic in every deployment topology."""
from __future__ import annotations

from crv_adapters.runner.base import JobRunner, JobSpec


def decide_runner(job: JobSpec, runners: list[JobRunner]) -> JobRunner:
    for r in runners:
        c = r.capabilities()
        if (job.estimated_duration_s <= c.max_duration_s
                and job.estimated_memory_mb <= c.max_memory_mb
                and job.estimated_disk_mb <= c.max_disk_mb):
            return r
    raise RuntimeError(f"no runner can handle job: {job}")
