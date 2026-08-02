"""Domain errors. Keep the hierarchy shallow."""


class CrvError(Exception):
    """Base for all app-defined errors."""


class ConfigError(CrvError):
    """Boot-time or runtime configuration is invalid."""


class ForgeError(CrvError):
    """Forge API returned an unexpected result."""


class BudgetExceeded(CrvError):
    """LLM monthly budget hit."""


class GateFailed(CrvError):
    """Merge gate returned failure."""
