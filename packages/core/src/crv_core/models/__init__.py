"""SQLAlchemy ORM. Full DDL lives in migrations/versions/0001_init.py — this module
mirrors the tables the app actually queries. Add tables here as callers appear."""
from crv_core.models.base import Base

__all__ = ["Base"]
