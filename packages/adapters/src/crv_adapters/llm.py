"""OpenAI-compatible LLM client. This is the ONLY module that talks to model APIs.

All providers reach us through an OpenAI-compatible base URL (LiteLLM proxy,
Ollama, vLLM, OpenAI, Azure OpenAI, Bedrock-via-LiteLLM, Anthropic-via-LiteLLM).

Real client wiring lands in M3 when llm_review.py first calls it — ponytail.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LlmResponse:
    model: str
    content: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cache_hit: bool = False


class LlmClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: int = 120) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.timeout_s = timeout_s

    async def chat(self, model: str, messages: list[dict], response_format: dict | None = None) -> LlmResponse:
        raise NotImplementedError  # M3

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError  # M2
