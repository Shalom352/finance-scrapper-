"""
UMOA Banking Intelligence — Async Database Engine

Creates the SQLAlchemy async engine from configuration.
"""

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import Settings, database_url_source, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def describe_database_target(settings: Settings) -> dict[str, object]:
    """Host, port and database taken from the URL the engine really uses (password masked)."""
    target = make_url(settings.async_database_url)
    return {
        "host": target.host,
        "port": target.port,
        "db": target.database,
        "url": target.render_as_string(hide_password=True),
        "url_source": database_url_source(settings),
        "application_name": settings.db_application_name,
    }


def engine_connect_args(settings: Settings) -> dict[str, object]:
    """asyncpg connection arguments: every connection announces the process in pg_stat_activity."""
    return {"server_settings": {"application_name": settings.db_application_name}}


def create_engine() -> AsyncEngine:
    """
    Create and return the async SQLAlchemy engine.

    Configuration is read from the application settings (env vars).
    """
    settings = get_settings()
    url = settings.async_database_url

    engine = create_async_engine(
        url,
        echo=settings.is_development,  # Log SQL queries in development only
        pool_pre_ping=True,             # Verify connections before use
        pool_size=10,
        max_overflow=20,
        connect_args=engine_connect_args(settings),
    )

    logger.info("database_engine_created", **describe_database_target(settings), env=settings.app_env)

    return engine


# Module-level engine instance
engine = create_engine()
