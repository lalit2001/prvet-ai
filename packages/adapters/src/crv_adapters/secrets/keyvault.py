"""Azure Key Vault — M5."""


class KeyVaultSecrets:
    async def get(self, ref: str) -> str: raise NotImplementedError
    async def put(self, ref: str, value: str) -> None: raise NotImplementedError
    async def delete(self, ref: str) -> None: raise NotImplementedError
    async def rotate(self, ref: str) -> str: raise NotImplementedError
