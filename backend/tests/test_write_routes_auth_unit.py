"""
Audit 22/10/2026 (S1/S2): every backend write route requires the internal token, and the actor of a
decision is the authenticated user named by the proxy, never a name chosen by the client.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core import internal_auth
from app.core.config import Settings
from app.core.internal_auth import actor_of, write_access
from app.main import app


class _Req:
    client = None


REQ = _Req()
WRITE_PREFIXES = ("/api/v1/financial-data", "/api/v1/data-quality", "/api/v1/ingestion", "/api/v1/syndication",
                  "/api/v1/deals")


def test_every_write_route_is_guarded():
    from tests.route_inventory import dependency_calls, iter_routes

    writes = [r for r in iter_routes(app)
              if r.methods & {"POST", "PATCH", "PUT", "DELETE"} and r.path.startswith(WRITE_PREFIXES)]
    assert len(writes) >= 20  # 20 on 22/10/2026: never a test that passes on zero routes
    unguarded = [f"{sorted(r.methods)} {r.path}" for r in writes
                 if not dependency_calls(r.dependant) & {write_access, internal_auth.require_internal}]
    assert unguarded == []


def test_internal_reads_are_guarded():
    """Contacts, mandates and the tracker are internal even when only read."""
    from tests.route_inventory import dependency_calls, iter_routes

    internal = [r for r in iter_routes(app) if r.path.startswith(("/api/v1/syndication", "/api/v1/mandates"))]
    assert internal
    assert [r.path for r in internal if internal_auth.require_internal not in dependency_calls(r.dependant)] == []


@pytest.mark.asyncio
async def test_token_is_required_once_configured(monkeypatch):
    monkeypatch.setattr(internal_auth, "get_settings",
                        lambda: Settings(app_env="production", backend_debug=False, internal_api_token="s3cret-token", postgres_password="x"))
    with pytest.raises(HTTPException) as err:
        await write_access(REQ, x_internal_token=None, x_authenticated_user="ana")
    assert err.value.status_code == 401
    with pytest.raises(HTTPException):
        await write_access(REQ, x_internal_token="wrong", x_authenticated_user="ana")
    assert await write_access(REQ, x_internal_token="s3cret-token", x_authenticated_user=" ana ") == "ana"


@pytest.mark.asyncio
async def test_production_without_token_is_closed(monkeypatch):
    monkeypatch.setattr(internal_auth, "get_settings",
                        lambda: Settings(app_env="production", backend_debug=False, internal_api_token=None, postgres_password="x"))
    with pytest.raises(HTTPException) as err:
        await write_access(REQ, x_internal_token=None, x_authenticated_user=None)
    assert err.value.status_code == 503


def test_authenticated_user_wins_over_the_declared_actor():
    assert actor_of("someone-else", "ana") == "ana"
    assert actor_of("cli-operator", None) == "cli-operator"


def test_writes_are_rate_limited():
    from app.core.internal_auth import WRITES_PER_MINUTE, _rate_limit, _recent_writes

    _recent_writes.pop("bot", None)
    for _ in range(WRITES_PER_MINUTE):
        _rate_limit("bot")
    with pytest.raises(HTTPException) as err:
        _rate_limit("bot")
    assert err.value.status_code == 429
    _rate_limit("ana")  # another user is not affected


def test_nul_character_is_a_clean_422_not_a_500():
    """Security tests of 22/10/2026: a NUL character in a search reached PostgreSQL and gave a 500."""
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)
    for path in ("/api/v1/search?q=a%00b", "/api/v1/deals?borrower=a%00b", "/api/v1/institutions?search=%00"):
        res = client.get(path)
        assert res.status_code == 422 and "NUL" in res.text, path
