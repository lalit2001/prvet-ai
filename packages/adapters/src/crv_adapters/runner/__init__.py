from crv_adapters.runner.base import JobRunner, JobSpec, RunnerCapabilities

__all__ = ["JobRunner", "JobSpec", "RunnerCapabilities", "get_runner"]


def get_runner(backend: str) -> JobRunner:
    if backend == "local":
        from crv_adapters.runner.local import LocalRunner
        return LocalRunner()
    if backend == "docker":
        from crv_adapters.runner.docker import DockerRunner
        return DockerRunner()
    if backend == "ecs":
        from crv_adapters.runner.ecs import EcsRunner
        return EcsRunner()
    if backend == "aci":
        from crv_adapters.runner.aci import AciRunner
        return AciRunner()
    if backend == "k8s":
        from crv_adapters.runner.k8s import K8sRunner
        return K8sRunner()
    if backend == "lambda":
        from crv_adapters.runner.awslambda import LambdaRunner
        return LambdaRunner()
    raise ValueError(f"unknown runner backend: {backend}")
