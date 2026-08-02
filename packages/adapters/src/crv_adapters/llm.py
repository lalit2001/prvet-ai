"""LLM client — routes every provider through LiteLLM.

LiteLLM handles the provider-specific translation (Bedrock, Azure OpenAI,
Azure AI Foundry, Vertex AI, Anthropic — including Anthropic-on-Azure, OpenAI,
Ollama, vLLM, any OpenAI-compatible endpoint) so the rest of the app only
knows one call: `LlmClient.chat(model, messages)`.

Provider config comes from the UI, stored in org.settings.providers.
Each provider entry has a `type` and provider-specific fields, which this
module expands into the env vars / kwargs LiteLLM expects at call time.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import litellm

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


def _apply_provider_env(provider: dict) -> tuple[str, str | None]:
    """Set the env vars LiteLLM reads and return (model_prefix, api_base override).

    Env vars are set on the current process at call time — safe because the
    server is single-config per boot; multi-tenant would need per-call kwargs
    instead."""
    t = provider["type"]

    if t == "openai":
        os.environ["OPENAI_API_KEY"] = provider.get("api_key") or ""
        return "", None

    if t == "anthropic":
        # Anthropic can be either anthropic.com or an Anthropic-compat endpoint
        # (e.g. Azure AI Foundry's /anthropic route). If a base_url is set, we
        # pass it as api_base.
        os.environ["ANTHROPIC_API_KEY"] = provider.get("api_key") or ""
        base = provider.get("base_url") or None
        return "anthropic/", base

    if t == "azure_openai":
        # Azure OpenAI hosts OpenAI models (GPT, embeddings). The "model" field
        # in role_map must be your Azure DEPLOYMENT name, not the underlying id.
        os.environ["AZURE_API_KEY"] = provider.get("api_key") or ""
        os.environ["AZURE_API_BASE"] = provider.get("endpoint") or ""
        os.environ["AZURE_API_VERSION"] = provider.get("api_version") or "2024-06-01"
        return "azure/", None

    if t == "azure_ai":
        # Azure AI Foundry — hosts non-OpenAI models (Claude, Llama, Mistral,
        # DeepSeek…) via the Azure AI Inference API. Endpoint usually looks like
        # https://<resource>.services.ai.azure.com/models.  We normalize so
        # both '/models' and no-suffix work.
        endpoint = (provider.get("endpoint") or "").rstrip("/")
        if endpoint and not endpoint.endswith("/models"):
            endpoint = f"{endpoint}/models"
        os.environ["AZURE_AI_API_KEY"] = provider.get("api_key") or ""
        os.environ["AZURE_AI_API_BASE"] = endpoint
        return "azure_ai/", endpoint

    if t == "bedrock":
        os.environ["AWS_ACCESS_KEY_ID"] = provider.get("access_key_id") or ""
        os.environ["AWS_SECRET_ACCESS_KEY"] = provider.get("secret_access_key") or ""
        os.environ["AWS_REGION_NAME"] = provider.get("region") or "us-east-1"
        return "bedrock/", None

    if t == "vertex_ai":
        os.environ["VERTEXAI_PROJECT"] = provider.get("project") or ""
        os.environ["VERTEXAI_LOCATION"] = provider.get("location") or "us-central1"
        if provider.get("credentials_json"):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = provider["credentials_json"]
        return "vertex_ai/", None

    if t == "ollama":
        base = provider.get("base_url") or "http://localhost:11434"
        return "ollama/", base

    if t in ("vllm", "openai_compatible", "litellm"):
        base = provider.get("base_url") or ""
        if provider.get("api_key"):
            os.environ["OPENAI_API_KEY"] = provider["api_key"]
        return "openai/", base

    raise LlmError(f"unknown provider type: {t}")


class LlmClient:
    def __init__(self, providers: list[dict], timeout_s: int = 120) -> None:
        if not providers:
            raise LlmError("no providers configured — add one at /admin/providers")
        self.providers = providers
        self.timeout_s = timeout_s

    def _resolve(self, model: str) -> tuple[dict, str, str | None]:
        """Returns (provider, qualified_model_id, api_base_override)."""
        # 1. Exact model in any provider.role_map values
        for p in self.providers:
            role_map = p.get("role_map") or {}
            if model in role_map.values():
                prefix, base = _apply_provider_env(p)
                return p, f"{prefix}{model}", base
        # 2. Role alias (fast / deep / embed)
        for p in self.providers:
            role_map = p.get("role_map") or {}
            if model in role_map:
                actual = role_map[model]
                prefix, base = _apply_provider_env(p)
                return p, f"{prefix}{actual}", base
        # 3. Fallback to first provider
        p = self.providers[0]
        prefix, base = _apply_provider_env(p)
        return p, f"{prefix}{model}", base

    async def chat(
        self, model: str, messages: list[dict],
        response_format: dict | None = None, temperature: float = 0.2,
    ) -> LlmResponse:
        provider, qualified_model, api_base = self._resolve(model)
        kwargs: dict[str, Any] = {
            "model": qualified_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": self.timeout_s,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if provider["type"] == "azure_openai":
            kwargs["api_version"] = provider.get("api_version") or "2024-06-01"
        if response_format is not None:
            kwargs["response_format"] = response_format
        started = time.monotonic()
        try:
            resp = await litellm.acompletion(**kwargs)
        except Exception as e:
            raise LlmError(_hint_error(provider, e)) from e
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
        provider, qualified_model, api_base = self._resolve(model)
        kwargs: dict[str, Any] = {"model": qualified_model, "input": texts, "timeout": self.timeout_s}
        if api_base:
            kwargs["api_base"] = api_base
        try:
            resp = await litellm.aembedding(**kwargs)
        except Exception as e:
            raise LlmError(_hint_error(provider, e)) from e
        return [row["embedding"] for row in resp["data"]]


def _hint_error(provider: dict, exc: Exception) -> str:
    """Turn LiteLLM's 404/auth errors into something actionable."""
    msg = str(exc)
    t = provider.get("type", "?")
    lower = msg.lower()
    # Azure OpenAI + Claude in role_map is a classic mistake
    if t == "azure_openai" and ("resource not found" in lower or "404" in lower):
        role_map = provider.get("role_map") or {}
        model_val = " / ".join(role_map.values())
        return (
            f"Azure OpenAI returned 'Resource not found'. Two things to check:\n"
            f"  1) The role-map model must be your Azure DEPLOYMENT name (as created "
            f"in Azure Portal), not the underlying model id. You have: {model_val or 'nothing set'}.\n"
            f"  2) If you're trying to use Claude/Llama/Mistral, use provider type "
            f"'Azure AI Foundry' (azure_ai) — Azure OpenAI only hosts OpenAI models.\n"
            f"Underlying error: {msg[:300]}"
        )
    if t == "azure_ai" and ("404" in lower or "not found" in lower):
        return (
            f"Azure AI Foundry 404. Check: endpoint should be "
            f"https://<resource>.services.ai.azure.com/models (or just /), and the "
            f"model id in role_map must match the Foundry catalog exactly (case-sensitive, "
            f"e.g. 'Claude-Sonnet-4-6'). Underlying: {msg[:300]}"
        )
    if t == "anthropic" and provider.get("base_url") and "404" in lower:
        return (
            f"Anthropic-compat call to {provider['base_url']} returned 404. If this is "
            f"Azure AI Foundry, the URL should end with '/anthropic'. Model id should be "
            f"a plain Anthropic id (e.g. 'claude-sonnet-4-6'). Underlying: {msg[:300]}"
        )
    return f"llm request failed: {msg[:400]}"


def client_from_org(providers: list[dict], timeout_s: int = 120) -> LlmClient:
    active = [p for p in providers if p.get("enabled", True)]
    return LlmClient(active, timeout_s=timeout_s)
