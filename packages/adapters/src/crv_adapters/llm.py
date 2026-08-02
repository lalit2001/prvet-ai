"""LLM client — routes every provider through LiteLLM.

LiteLLM handles the provider-specific translation (Bedrock, Azure OpenAI,
Vertex AI, Anthropic, OpenAI, Ollama, vLLM, any OpenAI-compatible endpoint)
so the rest of the app only knows one call: `LlmClient.chat(model, messages)`.

Provider config comes from the UI, stored in org.settings.providers.
Each provider entry has a `type` and provider-specific fields, which this
module expands into the env vars LiteLLM expects at call time.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import litellm

# Provider-agnostic setting so LiteLLM doesn't leak provider names into logs
litellm.suppress_debug_info = True


@dataclass(frozen=True)
class LlmResponse:
    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cache_hit: bool = False


class LlmError(RuntimeError):
    """Any LLM call failure — surfaced to callers, never crashes the app."""


# ────────── Provider config expansion ──────────

def _apply_provider_env(provider: dict) -> tuple[str | None, str | None]:
    """Set the env vars LiteLLM reads for this provider type.
    Returns (model_prefix, api_base) for building the fully-qualified model id.

    Never mutates a persistent state — env vars are set at call time,
    scoped to the current process."""
    t = provider["type"]

    if t == "openai":
        os.environ["OPENAI_API_KEY"] = provider["api_key"]
        return "", None  # models are plain, e.g. "gpt-4o-mini"

    if t == "anthropic":
        os.environ["ANTHROPIC_API_KEY"] = provider["api_key"]
        return "anthropic/", None  # e.g. "anthropic/claude-sonnet-4-6"

    if t == "azure_openai":
        # Azure uses deployment names as the "model" identifier
        os.environ["AZURE_API_KEY"] = provider["api_key"]
        os.environ["AZURE_API_BASE"] = provider["endpoint"]
        os.environ["AZURE_API_VERSION"] = provider.get("api_version", "2024-06-01")
        return "azure/", None  # e.g. "azure/<deployment-name>"

    if t == "bedrock":
        os.environ["AWS_ACCESS_KEY_ID"] = provider["access_key_id"]
        os.environ["AWS_SECRET_ACCESS_KEY"] = provider["secret_access_key"]
        os.environ["AWS_REGION_NAME"] = provider.get("region", "us-east-1")
        return "bedrock/", None  # e.g. "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"

    if t == "vertex_ai":
        os.environ["VERTEXAI_PROJECT"] = provider["project"]
        os.environ["VERTEXAI_LOCATION"] = provider.get("location", "us-central1")
        if provider.get("credentials_json"):
            # LiteLLM reads this env var for JSON creds
            os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = provider["credentials_json"]
        return "vertex_ai/", None  # e.g. "vertex_ai/gemini-1.5-pro"

    if t == "ollama":
        # Ollama uses the openai-compat prefix + api_base override
        base = provider.get("base_url", "http://localhost:11434")
        return "ollama/", base  # e.g. "ollama/llama3.1:70b"

    if t in ("vllm", "openai_compatible", "litellm"):
        # OpenAI-compatible endpoint — no provider prefix, just base_url + key
        base = provider["base_url"]
        if provider.get("api_key"):
            os.environ["OPENAI_API_KEY"] = provider["api_key"]
        return "openai/", base  # LiteLLM's "openai/" routes to any openai-compat endpoint

    raise LlmError(f"unknown provider type: {t}")


# ────────── Client ──────────

class LlmClient:
    """Model routing lives inside chat/embed; caller passes a model name.
    Provider selection is deterministic: pick the provider whose role_map maps to this model."""

    def __init__(self, providers: list[dict], timeout_s: int = 120) -> None:
        if not providers:
            raise LlmError("no providers configured — add one at /admin/providers")
        self.providers = providers
        self.timeout_s = timeout_s

    def _resolve(self, model: str) -> tuple[dict, str]:
        """Given a model name (or a role alias like 'fast'/'deep'), find the
        provider that owns it and return the LiteLLM-qualified model id."""
        # First: exact model match in any provider.role_map
        for p in self.providers:
            role_map = p.get("role_map", {})
            if model in role_map.values():
                prefix, _ = _apply_provider_env(p)
                return p, f"{prefix}{model}"
        # Second: role alias
        for p in self.providers:
            role_map = p.get("role_map", {})
            if model in role_map:  # model == "fast" | "deep" | "embed"
                actual = role_map[model]
                prefix, _ = _apply_provider_env(p)
                return p, f"{prefix}{actual}"
        # Third: use the default provider (first one) and pass model through
        p = self.providers[0]
        prefix, _ = _apply_provider_env(p)
        return p, f"{prefix}{model}"

    async def chat(
        self, model: str, messages: list[dict],
        response_format: dict | None = None, temperature: float = 0.2,
    ) -> LlmResponse:
        provider, qualified_model = self._resolve(model)
        _, api_base = _apply_provider_env(provider)
        kwargs: dict[str, Any] = {
            "model": qualified_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": self.timeout_s,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if response_format is not None:
            kwargs["response_format"] = response_format
        started = time.monotonic()
        try:
            resp = await litellm.acompletion(**kwargs)
        except Exception as e:  # LiteLLM raises many exception subclasses; funnel one
            raise LlmError(f"llm request failed: {e}") from e
        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            content = resp["choices"][0]["message"]["content"] or ""
            usage = resp.get("usage") or {}
        except (KeyError, IndexError, TypeError) as e:
            raise LlmError(f"unexpected llm response shape: {e}") from e
        return LlmResponse(
            model=resp.get("model", qualified_model),
            content=content,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            latency_ms=latency_ms,
        )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        provider, qualified_model = self._resolve(model)
        _, api_base = _apply_provider_env(provider)
        kwargs: dict[str, Any] = {"model": qualified_model, "input": texts, "timeout": self.timeout_s}
        if api_base:
            kwargs["api_base"] = api_base
        try:
            resp = await litellm.aembedding(**kwargs)
        except Exception as e:
            raise LlmError(f"embedding call failed: {e}") from e
        return [row["embedding"] for row in resp["data"]]


# ────────── Convenience: build from stored org config ──────────

def client_from_org(providers: list[dict], timeout_s: int = 120) -> LlmClient:
    """Filter enabled providers and instantiate."""
    active = [p for p in providers if p.get("enabled", True)]
    return LlmClient(active, timeout_s=timeout_s)
