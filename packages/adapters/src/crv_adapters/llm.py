"""OpenAI-compatible LLM client. This is the ONLY module that talks to model APIs.

All providers reach us through an OpenAI-compatible base URL — LiteLLM proxy,
Ollama, vLLM, OpenAI, Azure OpenAI, Anthropic. One code path, config-swapped.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


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


class LlmClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: int = 120) -> None:
        if not api_key:
            raise LlmError("no api key configured — set LLM_API_KEY_REF and the referenced secret")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def chat(
        self, model: str, messages: list[dict], response_format: dict | None = None,
        temperature: float = 0.2,
    ) -> LlmResponse:
        payload: dict = {"model": model, "messages": messages, "temperature": temperature}
        if response_format is not None:
            payload["response_format"] = response_format
        started = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as h:
            try:
                r = await h.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                )
            except httpx.HTTPError as e:
                raise LlmError(f"llm request failed: {e}") from e
        if r.status_code >= 400:
            raise LlmError(f"llm returned {r.status_code}: {r.text[:400]}")
        data = r.json()
        try:
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
        except (KeyError, IndexError) as e:
            raise LlmError(f"unexpected llm response shape: {e}: {str(data)[:400]}") from e
        return LlmResponse(
            model=data.get("model", model),
            content=content,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=self.timeout_s) as h:
            r = await h.post(
                f"{self.base_url}/embeddings",
                json={"model": model, "input": texts},
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            )
        if r.status_code >= 400:
            raise LlmError(f"embedding call returned {r.status_code}: {r.text[:400]}")
        return [row["embedding"] for row in r.json()["data"]]
