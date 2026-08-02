# syntax=docker/dockerfile:1.7
# Heavy image — includes SCIP toolchains for Tier-1 precise xrefs.
# Only pulled by the orchestrator for "heavy" runner-tier jobs (baselines, big reindexes).
FROM python:3.12 AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      git ca-certificates curl openjdk-21-jdk-headless nodejs npm \
      golang-1.23 cargo \
 && rm -rf /var/lib/apt/lists/*
# SCIP CLIs — pinned versions written in M6. For now, placeholders.
# RUN curl -sSL <scip-python>  -o /usr/local/bin/scip-python && chmod +x /usr/local/bin/scip-python
# RUN curl -sSL <scip-java>    -o /usr/local/bin/scip-java   && chmod +x /usr/local/bin/scip-java
RUN useradd -u 10001 -M -s /usr/sbin/nologin crv \
 && mkdir -p /var/lib/crv/objects && chown -R crv /var/lib/crv
# Reuse the worker's python packages by copying its site-packages tree via the build system in CI.
USER 10001:10001
CMD ["python", "-m", "crv_worker.main"]
