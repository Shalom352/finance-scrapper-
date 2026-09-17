"""
UMOA Banking Intelligence — Async Database Engine

Creates the SQLAlchemy async engine from configuration.
"""

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


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
    )

    logger.info(
        "database_engine_created",
        host=settings.postgres_host,
        port=settings.postgres_port,
        db=settings.postgres_db,
        env=settings.app_env,
    )

    return engine


# Module-level engine instance
engine = create_engine()
