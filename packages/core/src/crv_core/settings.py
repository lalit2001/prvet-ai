from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv

# Search up to 5 parent directories to locate and load the root .env file
_cur = Path(__file__).resolve().parent
for _ in range(6):
    _env = _cur / ".env"
    if _env.is_file():
        load_dotenv(dotenv_path=_env)
        break
    _cur = _cur.parent

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Deployment mode
    deployment_mode: Literal["standard", "airgap"] = "standard"
    public_url: str = "http://localhost:8080"   # where forges reach the API (webhooks, manifest callback)
    web_url: str = "http://localhost:3737"      # where humans reach the UI (setup redirects, check-run links)

    # Datastores
    database_url: str = "postgresql+asyncpg://crv:crv@localhost:5432/crv"

    queue_backend: Literal["redis", "sqs", "servicebus", "pubsub", "pg"] = "redis"
    queue_url: str = "redis://localhost:6379/0"

    storage_backend: Literal["fs", "s3", "azure_blob", "gcs"] = "fs"
    storage_uri: str = "/var/lib/crv/objects"

    secrets_backend: Literal["env", "aws_sm", "keyvault", "vault"] = "env"

    runner_backend: Literal["local", "docker", "ecs", "aci", "k8s", "lambda"] = "local"

    # Auth
    auth_mode: Literal["local", "oidc"] = "local"
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret_ref: str | None = None

    # LLM
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key_ref: str = "openai-key"
    llm_model_fast: str = "gpt-4o-mini"
    llm_model_deep: str = "claude-sonnet-4-6"
    llm_embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1024
    llm_timeout_s: int = 120
    llm_max_tokens_per_pr: int = 120_000
    llm_monthly_budget_usd: float = 500.0

    prompt_cache_backend: Literal["redis", "fs", "off"] = "redis"

    # Gate
    gate_mode: Literal["fail_open", "fail_closed"] = "fail_open"
    gate_block_severity: Literal["critical", "high", "medium", "low", "info"] = "high"

    # Indexing / review limits
    max_file_kb: int = 1024
    max_diff_files: int = 500
    max_diff_lines: int = 20_000
    scip_timeout_s: int = 300
    indexer_max_memory_mb: int = 2048
    baseline_hotspot_count: int = 150
    baseline_max_cost_usd: float = 25.0
    review_debounce_s: int = 20
    min_confidence: float = 0.6
    max_comments_per_pr: int = 25

    # Retention
    retention_days: int = 365

    # Observability
    otel_exporter_otlp_endpoint: str | None = None
    log_level: Literal["debug", "info", "warn", "error"] = "info"
    tz: str = "UTC"

    def validate_startup(self) -> None:
        """Hard-fail if config that must line up doesn't. Ran once on API boot."""
        if self.deployment_mode == "airgap" and self.llm_base_url.startswith("https://api.openai.com"):
            raise ValueError("airgap mode: LLM_BASE_URL must be an internal endpoint")


def get_settings() -> Settings:
    return Settings()  # cached at import time by callers via functools.lru_cache if needed
