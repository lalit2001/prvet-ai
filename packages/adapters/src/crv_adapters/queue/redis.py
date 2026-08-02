"""Redis queue — compose default. Implemented in M0-M1 via arq."""
from crv_adapters.queue.base import QueueMessage


class RedisQueue:
    def __init__(self, url: str) -> None:
        self.url = url
        # actual arq wiring lands with the first real job in M1

    async def publish(self, topic, message, dedup_key=None): raise NotImplementedError  # M1
    async def consume(self, topic, max_messages=1, visibility_s=900) -> list[QueueMessage]: raise NotImplementedError
    async def ack(self, message): raise NotImplementedError
    async def nack(self, message, requeue_after_s=0): raise NotImplementedError
    async def extend_visibility(self, message, seconds): raise NotImplementedError
