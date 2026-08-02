"""Postgres queue via SKIP LOCKED — for deployments that don't want Redis. Post-v1."""
from crv_adapters.queue.base import QueueMessage


class PgQueue:
    def __init__(self, url: str) -> None:
        raise NotImplementedError

    async def publish(self, topic, message, dedup_key=None): raise NotImplementedError
    async def consume(self, topic, max_messages=1, visibility_s=900) -> list[QueueMessage]: raise NotImplementedError
    async def ack(self, message): raise NotImplementedError
    async def nack(self, message, requeue_after_s=0): raise NotImplementedError
    async def extend_visibility(self, message, seconds): raise NotImplementedError
