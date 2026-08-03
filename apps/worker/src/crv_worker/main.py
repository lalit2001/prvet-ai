"""Worker entrypoint. arq-based consumer.

Run:  python -m crv_worker.main            (dev)
      arq crv_worker.main.WorkerSettings   (prod — same file, arq CLI)
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

from arq.connections import RedisSettings

from crv_core.settings import get_settings
from crv_worker.jobs import baseline, pr_review, pr_reply
from crv_worker.jobs.webhook import handle_forge_event


def _redis_settings() -> RedisSettings:
    u = urlparse(get_settings().queue_url)
    return RedisSettings(host=u.hostname or "localhost", port=u.port or 6379, database=int((u.path or "/0").lstrip("/") or 0))


class WorkerSettings:
    """arq's config-class contract."""
    functions = [handle_forge_event, baseline.run, pr_review.run, pr_reply.run]
    redis_settings = _redis_settings()
    max_jobs = 4
    job_timeout = 900


async def _run_forever() -> None:
    from arq.worker import Worker
    w = Worker(functions=WorkerSettings.functions, redis_settings=WorkerSettings.redis_settings,
               max_jobs=WorkerSettings.max_jobs, job_timeout=WorkerSettings.job_timeout)
    await w.async_run()


if __name__ == "__main__":
    asyncio.run(_run_forever())
