"""Single-run lock of umoa_titres_run — runner behaviour and lock release with fakes (no database connection)."""
import sys
from contextlib import asynccontextmanager

import pytest

from app.core.config import get_settings
from app.deals import db_guard, run_lock
from app.deals.db_guard import VerifiedDatabase
from app.deals.run_lock import RunLock, single_run_lock

E2E = "umoa_discovery_e2e"


@pytest.fixture(autouse=True)
def _fresh_settings_cache():
    """The runner sets DB_APPLICATION_NAME and clears the settings cache: never leak it to other tests."""
    yield
    get_settings.cache_clear()


def test_refusal_message_names_the_database_and_the_holder():
    assert RunLock(False, [4242]).refusal(E2E) == (
        "ABANDON: un autre umoa_titres_run est déjà actif sur 'umoa_discovery_e2e' "
        "(verrou consultatif détenu par le PID PostgreSQL 4242)."
    )
    assert "PID PostgreSQL inconnu" in RunLock(False, []).refusal(E2E)


async def test_runner_refuses_to_start_when_another_run_holds_the_lock(monkeypatch, capsys):
    import scraping.universe.http as http
    from app.deals import umoa_titres_run

    async def accept(db, *, expect_db, url_source, expect_application_name=None):
        return VerifiedDatabase(name=E2E, alembic_version="0015_deal_validation_flags")

    @asynccontextmanager
    async def busy(engine, name=run_lock.UMOA_TITRES_LOCK):
        yield RunLock(False, [4242])

    class NoFetcher:
        def __init__(self, *a, **k):
            raise AssertionError("no HTTP request may be made while another run is active")

    monkeypatch.setenv("DB_APPLICATION_NAME", "umoa_backend")  # restored after the test (the runner overrides it)
    monkeypatch.setattr(db_guard, "verify_target_database", accept)
    monkeypatch.setattr(run_lock, "single_run_lock", busy)
    monkeypatch.setattr(http, "OfficialFetcher", NoFetcher)
    monkeypatch.setattr(sys, "argv", ["umoa_titres_run", "--since", "2025-01-01", "--expect-db", E2E])
    assert await umoa_titres_run.main_async() == 3
    out = capsys.readouterr().out
    assert "un autre umoa_titres_run est déjà actif sur 'umoa_discovery_e2e'" in out and "4242" in out


# --------------------------------------------------------------------------- lock release (fake engine)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalars(self):
        return iter(self.value)


class FakeConnection:
    """Records the SQL of the lock connection; can be told to fail on unlock."""

    def __init__(self, *, acquired=True, fail_unlock=False, fail_invalidate=False):
        self.acquired, self.fail_unlock, self.fail_invalidate = acquired, fail_unlock, fail_invalidate
        self.sql: list[str] = []
        self.invalidated = False

    async def execute(self, statement, params=None):
        sql = str(statement)
        self.sql.append(sql)
        if "pg_advisory_unlock" in sql and self.fail_unlock:
            raise ConnectionError("connection lost")
        if "pg_try_advisory_lock" in sql:
            return _Result(self.acquired)
        if "pg_locks" in sql:
            return _Result([4242])
        return _Result(None)

    async def commit(self):
        pass

    async def invalidate(self):
        if self.fail_invalidate:
            raise OSError("socket already closed")
        self.invalidated = True


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    @asynccontextmanager
    async def connect(self):
        yield self.conn


def _ran(conn, fragment):
    return any(fragment in s for s in conn.sql)


async def test_lock_connection_announces_itself_and_is_released():
    conn = FakeConnection()
    async with single_run_lock(FakeEngine(conn)) as lock:
        assert lock.acquired
    assert "set_config('application_name'" in conn.sql[0]  # named before the lock is taken
    assert _ran(conn, "pg_advisory_unlock") and _ran(conn, "RESET application_name")
    assert not conn.invalidated


async def test_lock_is_released_when_the_run_fails_and_the_run_error_propagates():
    conn = FakeConnection()
    with pytest.raises(ValueError, match="run failed"):
        async with single_run_lock(FakeEngine(conn)):
            raise ValueError("run failed")
    assert _ran(conn, "pg_advisory_unlock")
    assert not conn.invalidated


async def test_failed_unlock_invalidates_the_connection_without_masking_the_run_error():
    conn = FakeConnection(fail_unlock=True)
    with pytest.raises(ValueError, match="run failed"):  # not the ConnectionError of the unlock
        async with single_run_lock(FakeEngine(conn)):
            raise ValueError("run failed")
    assert conn.invalidated  # never returned to the pool while possibly holding the lock


async def test_failed_unlock_after_a_successful_run_does_not_raise():
    conn = FakeConnection(fail_unlock=True, fail_invalidate=True)
    async with single_run_lock(FakeEngine(conn)) as lock:
        assert lock.acquired
    assert not conn.invalidated  # invalidate itself failed: logged, the session ends with the process


async def test_refused_lock_reports_holders_and_resets_the_connection_name():
    conn = FakeConnection(acquired=False)
    async with single_run_lock(FakeEngine(conn)) as lock:
        assert not lock.acquired and lock.holders == [4242]
    assert _ran(conn, "RESET application_name")
    assert not _ran(conn, "pg_advisory_unlock")  # nothing to release
