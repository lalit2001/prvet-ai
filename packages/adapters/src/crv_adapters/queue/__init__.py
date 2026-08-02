from crv_adapters.queue.base import QueueAdapter, QueueMessage

__all__ = ["QueueAdapter", "QueueMessage", "get_adapter"]


def get_adapter(backend: str, url: str) -> QueueAdapter:
    if backend == "redis":
        from crv_adapters.queue.redis import RedisQueue
        return RedisQueue(url)
    if backend == "pg":
        from crv_adapters.queue.pg import PgQueue
        return PgQueue(url)
    if backend == "sqs":
        from crv_adapters.queue.sqs import SqsQueue
        return SqsQueue(url)
    if backend == "servicebus":
        from crv_adapters.queue.servicebus import ServiceBusQueue
        return ServiceBusQueue(url)
    if backend == "pubsub":
        from crv_adapters.queue.pubsub import PubSubQueue
        return PubSubQueue(url)
    raise ValueError(f"unknown queue backend: {backend}")
