"""Target-database guard and engine log target — pure functions and fakes (no database connection)."""
import sys

import pytest

from app.core.config import Settings, database_url_source
from app.db.engine import describe_database_target, engine_connect_args
from app.deals import db_guard
from app.deals.db_guard import (
    RUNNER_APPLICATION_NAME,
    URL_FROM_ENVIRONMENT,
    TargetDatabaseError,
    check_target,
    revision_number,
    verify_target_database,
)

E2E = "umoa_discovery_e2e"
HEAD = "0015_deal_validation_flags"


# --------------------------------------------------------------------------- check_target


def test_expected_database_is_accepted():
    verified = check_target(E2E, HEAD, expect_db=E2E, url_source=URL_FROM_ENVIRONMENT)
    assert verified.name == E2E
    assert verified.message() == f"Base vérifiée: {E2E} (alembic {HEAD})"


def test_other_database_than_expected_stops():
    with pytest.raises(TargetDatabaseError, match="attendu 'umoa_discovery_e2e'"):
        check_target("umoa_phase13_mig", HEAD, expect_db=E2E, url_source=URL_FROM_ENVIRONMENT)


@pytest.mark.parametrize("expect_db", [None, "umoa_banking", E2E])
@pytest.mark.parametrize("url_source", [URL_FROM_ENVIRONMENT, ".env:DATABASE_URL"])
def test_historical_database_always_stops(expect_db, url_source):
    with pytest.raises(TargetDatabaseError, match="base historique interdite"):
        check_target("umoa_banking", HEAD, expect_db=expect_db, url_source=url_source)


@pytest.mark.parametrize("url_source", [".env:DATABASE_URL", "POSTGRES_* (POSTGRES_DB from default)"])
def test_fallback_url_stops_unless_working_database(url_source):
    with pytest.raises(TargetDatabaseError, match="DATABASE_URL absent de l'environnement"):
        check_target("umoa_other", HEAD, expect_db=None, url_source=url_source)
    assert check_target(E2E, HEAD, expect_db=None, url_source=url_source).name == E2E


@pytest.mark.parametrize("version", ["0014_public_debt_instruments", "0013_institutional_discovery", None, "abc"])
def test_old_or_unknown_alembic_revision_stops(version):
    with pytest.raises(TargetDatabaseError, match="0015 minimum"):
        check_target(E2E, version, expect_db=E2E, url_source=URL_FROM_ENVIRONMENT)


def test_newer_revision_is_accepted():
    assert check_target(E2E, "0016_x", expect_db=E2E, url_source=URL_FROM_ENVIRONMENT).alembic_version == "0016_x"
    assert revision_number("0015_deal_validation_flags") == 15


# --------------------------------------------------------------------------- verify_target_database (fake session)


class _Result:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    """Answers the guard queries; never connects anywhere."""

    def __init__(self, database, version, application_name="umoa_titres_run"):
        self.database, self.version, self.statements, self.rolled_back = database, version, [], False
        self.application_name = application_name

    async def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "application_name" in sql:
            return _Result(self.application_name)
        if "current_database" in sql:
            return _Result(self.database)
        if "to_regclass" in sql:
            return _Result(self.version is not None)
        return _Result(self.version)

    async def rollback(self):
        self.rolled_back = True


async def test_verify_reads_real_values_read_only():
    session = FakeSession(E2E, HEAD)
    verified = await verify_target_database(session, expect_db=E2E, url_source=URL_FROM_ENVIRONMENT)
    assert verified.alembic_version == HEAD
    assert session.rolled_back
    assert all(s.lstrip().upper().startswith("SELECT") for s in session.statements)


async def test_verify_checks_the_announced_application_name():
    ok = await verify_target_database(FakeSession(E2E, HEAD), expect_db=E2E, url_source=URL_FROM_ENVIRONMENT,
                                      expect_application_name=RUNNER_APPLICATION_NAME)
    assert ok.name == E2E
    with pytest.raises(TargetDatabaseError, match="'umoa_backend' au lieu de 'umoa_titres_run'"):
        await verify_target_database(FakeSession(E2E, HEAD, "umoa_backend"), expect_db=E2E,
                                     url_source=URL_FROM_ENVIRONMENT, expect_application_name=RUNNER_APPLICATION_NAME)


def test_application_name_is_not_checked_when_not_expected():
    assert check_target(E2E, HEAD, expect_db=E2E, url_source=URL_FROM_ENVIRONMENT, application_name="psql").name == E2E


async def test_verify_without_alembic_table_stops():
    with pytest.raises(TargetDatabaseError, match="0015 minimum"):
        await verify_target_database(FakeSession(E2E, None), expect_db=E2E, url_source=URL_FROM_ENVIRONMENT)


# --------------------------------------------------------------------------- URL source and engine log


def _settings(monkeypatch, **env):
    for key in ("DATABASE_URL", "POSTGRES_DB"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None, postgres_password="pw")  # type: ignore[call-arg]


def test_engine_log_uses_effective_url_from_environment(monkeypatch):
    s = _settings(monkeypatch, DATABASE_URL="postgresql+asyncpg://u:secret@db.local:5433/x_db", POSTGRES_DB="umoa_banking")
    target = describe_database_target(s)
    assert target["db"] == "x_db" and target["host"] == "db.local" and target["port"] == 5433
    assert "secret" not in str(target["url"])
    assert target["url_source"] == URL_FROM_ENVIRONMENT


def test_engine_connections_announce_the_process(monkeypatch):
    monkeypatch.delenv("DB_APPLICATION_NAME", raising=False)
    s = _settings(monkeypatch)
    assert engine_connect_args(s) == {"server_settings": {"application_name": "umoa_backend"}}
    assert describe_database_target(s)["application_name"] == "umoa_backend"
    monkeypatch.setenv("DB_APPLICATION_NAME", RUNNER_APPLICATION_NAME)
    s = Settings(_env_file=None, postgres_password="pw")  # type: ignore[call-arg]
    assert engine_connect_args(s)["server_settings"] == {"application_name": RUNNER_APPLICATION_NAME}


def test_empty_database_url_falls_back_on_postgres_values(monkeypatch):
    monkeypatch.setattr("app.core.config._dotenv_defines", lambda key: False)
    s = _settings(monkeypatch, DATABASE_URL="", POSTGRES_DB="umoa_discovery_e2e")
    assert describe_database_target(s)["db"] == "umoa_discovery_e2e"
    assert database_url_source(s) == "POSTGRES_* (POSTGRES_DB from environment)"


def test_default_values_are_reported_as_default(monkeypatch):
    monkeypatch.setattr("app.core.config._dotenv_defines", lambda key: False)
    s = _settings(monkeypatch)
    assert database_url_source(s) == "POSTGRES_* (POSTGRES_DB from default)"


def test_database_url_from_env_file_is_reported(monkeypatch):
    for key in ("DATABASE_URL", "POSTGRES_DB"):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None, postgres_password="pw", database_url="postgresql://u:p@h/f_db")  # type: ignore[call-arg]
    assert database_url_source(s) == ".env:DATABASE_URL"


# --------------------------------------------------------------------------- runner: guard before any request


async def test_runner_stops_before_any_http_request(monkeypatch, capsys):
    import scraping.universe.http as http
    from app.deals import run_lock, umoa_titres_run

    seen = {}

    async def refuse(db, *, expect_db, url_source, expect_application_name=None):
        seen["expect_application_name"] = expect_application_name
        raise TargetDatabaseError("ABANDON: test")

    def no_lock(*a, **k):
        raise AssertionError("the run lock was requested although the guard refused the database")

    class NoFetcher:
        def __init__(self, *a, **k):
            raise AssertionError("HTTP fetcher created before the database guard")

    monkeypatch.setenv("DB_APPLICATION_NAME", "umoa_backend")  # restored after the test (the runner overrides it)
    monkeypatch.setattr(db_guard, "verify_target_database", refuse)
    monkeypatch.setattr(run_lock, "single_run_lock", no_lock)
    monkeypatch.setattr(http, "OfficialFetcher", NoFetcher)
    monkeypatch.setattr(sys, "argv", ["umoa_titres_run", "--since", "2025-01-01", "--expect-db", E2E])
    assert await umoa_titres_run.main_async() == 2
    assert "ABANDON: test" in capsys.readouterr().out
    assert seen["expect_application_name"] == RUNNER_APPLICATION_NAME
    import os

    assert os.environ["DB_APPLICATION_NAME"] == RUNNER_APPLICATION_NAME  # set by the runner itself
