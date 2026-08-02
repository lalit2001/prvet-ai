from crv_adapters.secrets.base import SecretsAdapter

__all__ = ["SecretsAdapter", "get_adapter"]


def get_adapter(backend: str) -> SecretsAdapter:
    if backend == "env":
        from crv_adapters.secrets.env import EnvSecrets
        return EnvSecrets()
    if backend == "aws_sm":
        from crv_adapters.secrets.aws_sm import AwsSecretsManager
        return AwsSecretsManager()
    if backend == "keyvault":
        from crv_adapters.secrets.keyvault import KeyVaultSecrets
        return KeyVaultSecrets()
    if backend == "vault":
        from crv_adapters.secrets.vault import HashicorpVaultSecrets
        return HashicorpVaultSecrets()
    raise ValueError(f"unknown secrets backend: {backend}")
