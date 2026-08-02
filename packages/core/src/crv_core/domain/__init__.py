"""Plain dataclasses that flow between adapters and workers.
No ORM leaks past this boundary. Add types here as consumers appear — ponytail."""
from crv_core.domain.finding import Finding, Severity, Category
from crv_core.domain.symbol import Symbol, SymbolReference

__all__ = ["Finding", "Severity", "Category", "Symbol", "SymbolReference"]
