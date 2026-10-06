"""
UMOA Banking Intelligence — Test Configuration

Provides shared fixtures for all tests.
"""

import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure a deterministic test environment before importing app modules.
# POSTGRES_PASSWORD is normally provided via the shared .env (root). A placeholder is
# only applied when no .env defines it, so DB-free tests can import the settings.
# (A process variable would take priority over .env, hence the check.)
os.environ.setdefault("APP_ENV", "development")


def _env_file_defines(key: str) -> bool:
    here = Path(__file__).resolve()
    for env_file in (here.parents[1] / ".env", here.parents[2] / ".env"):
        if env_file.is_file():
            lines = env_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if any(line.split("=", 1)[0].strip() == key for line in lines):
                return True
    return False


if not _env_file_defines("POSTGRES_PASSWORD"):
    os.environ.setdefault("POSTGRES_PASSWORD", "test-only-placeholder")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "umoa_banking")
os.environ.setdefault("POSTGRES_USER", "umoa_user")

from app.main import create_app  # noqa: E402  (after the environment defaults)


@pytest.fixture(scope="session")
def app():
    """Create test application instance."""
    return create_app()


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
