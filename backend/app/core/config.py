"""
UMOA Banking Intelligence — Core Configuration

All configuration is loaded from environment variables.
Never hardcode secrets or environment-specific values here.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables.
    See .env.example for the full list of available variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
    # Computed helpers
    # ------------------------------------------------------------------
    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return cached application settings.
    Uses lru_cache so the .env file is read only once.
    """
    return Settings()  # type: ignore[call-arg]
