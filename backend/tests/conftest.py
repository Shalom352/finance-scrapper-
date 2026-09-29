"""
UMOA Banking Intelligence — Test Configuration

Provides shared fixtures for all tests.
"""

import os

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure a deterministic test environment before importing app modules.
# POSTGRES_PASSWORD is normally provided via the shared .env (root). A fallback
# is only applied so DB-free tests can import the settings without a real DB.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("POSTGRES_PASSWORD", "umoa_dev_2024!")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_DB", "umoa_banking")
os.environ.setdefault("POSTGRES_USER", "umoa_user")

from app.main import create_app


@pytest.fixture(scope="session")
def app():
    """Create test application instance."""
    return create_app()


@pytest.fixture
async def client(app):
    """Async HTTP test client."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
