"""S3 storage — implement in M5."""
from typing import AsyncIterator


class S3Storage:
    def __init__(self, uri: str) -> None:
        # uri: s3://bucket/prefix
        raise NotImplementedError  # M5

    async def put(self, key, data, content_type="application/octet-stream"): raise NotImplementedError
    async def get(self, key): raise NotImplementedError
    async def get_stream(self, key) -> AsyncIterator[bytes]: raise NotImplementedError
    async def delete(self, key): raise NotImplementedError
    async def exists(self, key): raise NotImplementedError
    async def presign_get(self, key, ttl_seconds=3600): raise NotImplementedError
    async def list(self, prefix) -> AsyncIterator[str]: raise NotImplementedError
