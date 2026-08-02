from crv_adapters.storage.base import StorageAdapter

__all__ = ["StorageAdapter", "get_adapter"]


def get_adapter(backend: str, uri: str) -> StorageAdapter:
    if backend == "fs":
        from crv_adapters.storage.fs import FsStorage
        return FsStorage(uri)
    if backend == "s3":
        from crv_adapters.storage.s3 import S3Storage
        return S3Storage(uri)
    if backend == "azure_blob":
        from crv_adapters.storage.azure_blob import AzureBlobStorage
        return AzureBlobStorage(uri)
    if backend == "gcs":
        from crv_adapters.storage.gcs import GcsStorage
        return GcsStorage(uri)
    raise ValueError(f"unknown storage backend: {backend}")
