"""Dependency-injection helpers. Kept intentionally small — add functions when a
route needs them, not before."""
from __future__ import annotations

from functools import lru_cache

from crv_core.settings import Settings, get_settings as _get


@lru_cache
def settings() -> Settings:
    return _get()
