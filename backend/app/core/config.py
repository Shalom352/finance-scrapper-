"""
UMOA Banking Intelligence — Core Configuration

All configuration is loaded from environment variables.
Never hardcode secrets or environment-specific values here.
"""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    See .env.example for the full list of available variables.
    """

    model_config = SettingsConfigDict(
        # Search for the env file in the backend directory first, then at the
        # repository root (docker-compose reads the root .env). This makes the
        # same credentials available whether commands run from ``backend/``
        # (pytest, alembic) or the repository root.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------
    app_env: Literal["development", "staging", "production"] = "development"
    default_locale: Literal["fr", "en"] = "fr"

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "umoa_banking"
    postgres_user: str = "umoa_user"
    postgres_password: str = Field(..., description="PostgreSQL password (required)")

    # Optional: override the full DSN directly
    database_url: str | None = None

    # application_name of every connection of this process (pg_stat_activity). Runners set their own.
    db_application_name: str = "umoa_backend"

    @computed_field  # type: ignore[misc]
    @property
    def async_database_url(self) -> str:
        """Build async database URL from components or use override."""
        if self.database_url:
            # Ensure asyncpg driver is used
            url = self.database_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            elif url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql+asyncpg://", 1)
            return url

        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ------------------------------------------------------------------
    # FastAPI / Backend
    # ------------------------------------------------------------------
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    backend_debug: bool = False
    backend_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # CORS origins (comma-separated)
    cors_origins: str = "http://localhost:3000"

    @computed_field  # type: ignore[misc]
    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------
    scraper_concurrency: int = 3
    scraper_timeout: int = 60
    documents_storage_path: str = "./data/downloads"

    # ------------------------------------------------------------------
    # Automated Ingestion & Scheduling
    # ------------------------------------------------------------------
    ingestion_enabled: bool = False
    ingestion_schedule: str = "0 8,20 * * *"
    ingestion_timezone: str = "Africa/Abidjan"
    ingestion_historical_years: int = 5
    ingestion_concurrency_limit: int = 1

    # ------------------------------------------------------------------
    # Entity & Source Discovery Engine (Phase 15) — disabled by default
    # ------------------------------------------------------------------
    discovery_enabled: bool = False
    discovery_schedule: str = "0 3 * * *"
    discovery_universe: str = "UMOA.BANKING"
    discovery_historical_years: int = 5
    discovery_fascicle_editions: int = 1

    # ------------------------------------------------------------------
    # Computed helpers
    # ------------------------------------------------------------------
    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def production_guards(self) -> "Settings":
        """Refuse an unsafe production configuration instead of starting with it."""
        if self.is_production:
            if not self.cors_origins_list or "*" in self.cors_origins_list:
                raise ValueError("CORS_ORIGINS must list explicit origins in production (no '*')")
            if self.backend_debug:
                raise ValueError("BACKEND_DEBUG must be false in production")
        return self


def _dotenv_defines(key: str) -> bool:
    """True when one of the configured env files sets ``key`` to a non-empty value."""
    from dotenv import dotenv_values

    env_files = Settings.model_config.get("env_file") or ()
    if isinstance(env_files, str | bytes):
        env_files = (env_files,)
    for env_file in env_files:
        values = {k.upper(): v for k, v in dotenv_values(env_file, encoding="utf-8").items()}
        if values.get(key.upper()):
            return True
    return False


def _origin(key: str) -> str:
    if os.environ.get(key):
        return "environment"
    if key not in os.environ and _dotenv_defines(key):
        return ".env"
    return "default"


def database_url_source(settings: Settings) -> str:
    """Where the effective database URL comes from (environment, .env, or POSTGRES_* values).

    A process variable has priority over the env files; an empty process variable
    (docker-compose sets DATABASE_URL="") disables DATABASE_URL in favour of POSTGRES_*.
    """
    if settings.database_url:
        return "environment:DATABASE_URL" if os.environ.get("DATABASE_URL") else ".env:DATABASE_URL"
    return f"POSTGRES_* (POSTGRES_DB from {_origin('POSTGRES_DB')})"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached application settings.
    Uses lru_cache so the .env file is read only once.
    """
    return Settings()  # type: ignore[call-arg]
