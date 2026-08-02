"""FastAPI entrypoint. Component 1 — receives webhooks, returns 202 in <500ms.
No analysis work here. All work is enqueued and handled by the worker."""
from __future__ import annotations

from fastapi import FastAPI

from crv_api.middleware.request_id import RequestIdMiddleware
from crv_api.routers import health, webhooks
from crv_core.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_startup()

    app = FastAPI(title="Sentry Review API", version="0.1.0")
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(webhooks.router, prefix="/api/v1")
    return app


app = create_app()
