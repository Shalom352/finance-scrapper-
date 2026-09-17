"""
UMOA Banking Intelligence — Alembic Migration Environment

This file is loaded by Alembic on every migration command.
It configures the migration context with:
- The database URL from environment variables
- The SQLAlchemy metadata from all models
- Async engine support (asyncpg)
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Add backend directory to sys.path so we can import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import get_settings
from app.db.base import Base

# ============================================================
# Import all models here so Alembic can detect them
# Models will be added as phases progress
# ============================================================
# from app.models.institution import Institution  # Phase 1
# from app.models.document import Document        # Phase 2
# ============================================================

# Alembic Config object (gives access to alembic.ini values)
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url() -> str:
    """
    Load database URL from environment variables.
    Never reads from alembic.ini — always from env.
    """
    settings = get_settings()
    # Alembic needs a synchronous URL for configuration
    # but we use an async engine for running migrations
    url = settings.async_database_url
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    Configures context with a URL only (no engine connection).
    Used when generating SQL scripts without a live DB.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with an active connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations with an async engine."""
    url = get_database_url()

    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live DB connection."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
