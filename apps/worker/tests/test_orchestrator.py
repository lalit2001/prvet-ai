from crv_adapters.runner.base import JobSpec, RunnerCapabilities
from crv_worker.orchestrator import decide_runner


class _Runner:
    def __init__(self, cap: RunnerCapabilities) -> None: self.cap = cap
    def capabilities(self) -> RunnerCapabilities: return self.cap
    async def submit(self, j): ...
    async def status(self, h): ...
    async def logs(self, h, follow=False): ...
    async def cancel(self, h): ...


def test_decide_runner_picks_first_that_fits():
    small = _Runner(RunnerCapabilities(max_duration_s=60, max_memory_mb=512, max_disk_mb=1024))
    big = _Runner(RunnerCapabilities(max_duration_s=3600, max_memory_mb=8192, max_disk_mb=100_000))
    job = JobSpec(image="x", command=["echo"], estimated_duration_s=1200, estimated_memory_mb=4096, estimated_disk_mb=2048)
    assert decide_runner(job, [small, big]) is big


def test_decide_runner_raises_when_nothing_fits():
    import pytest
    small = _Runner(RunnerCapabilities(max_duration_s=60, max_memory_mb=512, max_disk_mb=1024))
    job = JobSpec(image="x", command=["echo"], estimated_duration_s=3600, estimated_memory_mb=16384, estimated_disk_mb=50_000)
    with pytest.raises(RuntimeError):
        decide_runner(job, [small])
