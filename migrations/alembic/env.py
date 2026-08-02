"""Alembic env — driven by DATABASE_URL from crv_core.settings."""
from __future__ import annotations

import os

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

from crv_core.models.base import Base

load_dotenv()  # so `alembic upgrade head` works from PyCharm without extra config

config = context.config

# Convert the async DSN to a sync one for Alembic. Ponytail: only strip the +asyncpg driver.
db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
