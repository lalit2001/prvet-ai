# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder
RUN pip install --no-cache-dir uv==0.4.15
WORKDIR /build
COPY pyproject.toml ./
COPY packages/core     packages/core
COPY packages/adapters packages/adapters
COPY apps/worker       apps/worker
RUN uv pip install --system --no-cache -e packages/core -e packages/adapters -e "apps/worker[sast]"

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -u 10001 -M -s /usr/sbin/nologin crv \
 && mkdir -p /var/lib/crv/objects && chown -R crv /var/lib/crv
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
USER 10001:10001
CMD ["python", "-m", "crv_worker.main"]
