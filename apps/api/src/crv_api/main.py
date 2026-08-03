"""FastAPI entrypoint. Component 1 — receives webhooks, returns 202 in <500ms.
No analysis work here. All work is enqueued and handled by the worker."""
from __future__ import annotations

import contextlib
import json
import httpx
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from crv_api.middleware.request_id import RequestIdMiddleware
from crv_api.routers import admin, config, findings, forges, health, providers, repos, reviews, webhooks
from crv_api.startup import clean_stale_runs, ensure_default_org
from crv_core.settings import get_settings
from crv_core.queue import pool as queue_pool


def patch_httpx_airgap():
    settings = get_settings()
    if getattr(settings, "deployment_mode", "standard") != "airgap":
        return
        
    allowed_domains = {"localhost", "127.0.0.1", "testserver"}
    if settings.llm_base_url:
        parsed = urlparse(settings.llm_base_url)
        if parsed.hostname:
            allowed_domains.add(parsed.hostname)
            
    original_async_send = httpx.AsyncClient.send
    original_sync_send = httpx.Client.send
    
    def _verify_url(url: httpx.URL):
        if url.host not in allowed_domains:
            raise RuntimeError(f"Airgap block: Outbound request to {url.host} is denied in airgap mode.")
            
    async def async_send_wrapper(self, request, *args, **kwargs):
        _verify_url(request.url)
        return await original_async_send(self, request, *args, **kwargs)
        
    def sync_send_wrapper(self, request, *args, **kwargs):
        _verify_url(request.url)
        return original_sync_send(self, request, *args, **kwargs)
        
    httpx.AsyncClient.send = async_send_wrapper
    httpx.Client.send = sync_send_wrapper
    print("[startup] patched HTTP clients for airgap mode constraints")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(("/healthz", "/readyz", "/docs", "/openapi.json")):
            return await call_next(request)
            
        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_ip}:{path}"
        
        try:
            p = await queue_pool()
            current = await p.incr(key)
            if current == 1:
                await p.expire(key, 60)
            if current > 60:
                return Response(
                    content=json.dumps({"detail": "Rate limit exceeded. Try again in a minute."}),
                    status_code=429,
                    media_type="application/json"
                )
        except Exception as e:
            # Fail open if Redis is down
            print(f"[rate_limit] Redis error: {e}")
            
        return await call_next(request)


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    patch_httpx_airgap()
    await ensure_default_org()
    n = await clean_stale_runs()
    if n:
        print(f"[startup] marked {n} stale running/queued runs as failed")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_startup()

    app = FastAPI(title="Sentry Review API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        # ponytail: dev origins hardcoded; wire to settings.cors_origins when a real domain shows up
        allow_origins=["http://localhost:3737", "http://localhost:3000", "http://127.0.0.1:3737"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.include_router(health.router)
    app.include_router(webhooks.router, prefix="/api/v1")
    app.include_router(repos.router, prefix="/api/v1")
    app.include_router(reviews.router, prefix="/api/v1")
    app.include_router(config.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")
    app.include_router(providers.router, prefix="/api/v1")
    app.include_router(forges.router, prefix="/api/v1")
    app.include_router(findings.router, prefix="/api/v1")
    return app


app = create_app()
