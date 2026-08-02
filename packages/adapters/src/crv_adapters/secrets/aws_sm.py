"""AWS Secrets Manager — M5."""


class AwsSecretsManager:
    async def get(self, ref: str) -> str: raise NotImplementedError
    async def put(self, ref: str, value: str) -> None: raise NotImplementedError
    async def delete(self, ref: str) -> None: raise NotImplementedError
    async def rotate(self, ref: str) -> str: raise NotImplementedError
