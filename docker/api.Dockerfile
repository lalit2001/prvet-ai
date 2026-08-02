# syntax=docker/dockerfile:1.7
# --- builder ---
FROM python:3.12-slim AS builder
ENV UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --no-cache-dir uv==0.4.15
WORKDIR /build
COPY pyproject.toml ./
COPY packages/core     packages/core
COPY packages/adapters packages/adapters
COPY apps/api          apps/api
RUN uv pip install --system --no-cache -e packages/core -e packages/adapters -e "apps/api[dev]"

# --- runtime ---
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1
RUN useradd -u 10001 -M -s /usr/sbin/nologin crv \
 && mkdir -p /var/lib/crv && chown crv /var/lib/crv
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY migrations /app/migrations
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "crv_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
