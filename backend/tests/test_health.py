"""
UMOA Banking Intelligence — Health Endpoint Tests

Tests for GET /health (liveness check).
The full health check (GET /api/v1/health) requires a database
and is tested separately in integration tests.
"""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    """Health endpoint should return HTTP 200."""
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_structure(client):
    """Health response should contain required fields."""
    response = await client.get("/health")
    data = response.json()

    assert data["status"] == "ok"
    assert data["app"] == "UMOA Banking Intelligence"
    assert "version" in data
    assert "env" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_version_format(client):
    """Version should follow semver format."""
    response = await client.get("/health")
    version = response.json()["version"]
    parts = version.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
