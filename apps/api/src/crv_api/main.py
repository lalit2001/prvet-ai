"""FastAPI entrypoint. Component 1 — receives webhooks, returns 202 in <500ms.
No analysis work here. All work is enqueued and handled by the worker."""
from __future__ import annotations

import contextlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crv_api.middleware.request_id import RequestIdMiddleware
from crv_api.routers import admin, config, health, repos, reviews, webhooks
from crv_api.startup import ensure_default_org
from crv_core.settings import get_settings


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    await ensure_default_org()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_startup()

    app = FastAPI(title="Sentry Review API", version="0.1.0", lifespan=_lifespan)
    app.add_middleware(RequestIdMiddleware)
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
    return app


app = create_app()
