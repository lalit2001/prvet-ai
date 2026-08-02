"""QueueAdapter Protocol — PRD §10.2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class QueueMessage:
    id: str
    body: dict
    receipt: object  # opaque per backend


@runtime_checkable
class QueueAdapter(Protocol):
    async def publish(self, topic: str, message: dict, dedup_key: str | None = None) -> str: ...
    async def consume(self, topic: str, max_messages: int = 1, visibility_s: int = 900) -> list[QueueMessage]: ...
    async def ack(self, message: QueueMessage) -> None: ...
    async def nack(self, message: QueueMessage, requeue_after_s: int = 0) -> None: ...
    async def extend_visibility(self, message: QueueMessage, seconds: int) -> None: ...
