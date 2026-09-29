"""
UMOA Banking Intelligence — Phase 2 PostgreSQL integration tests.

These tests exercise the Alembic migrations against a REAL PostgreSQL server.
They are SKIPPED automatically when no server is reachable, so the DB-free
suite still passes in environments without a database.

When a server is available the test:
  1. creates a dedicated scratch database (never touches the dev database);
  2. runs ``alembic upgrade head`` from an empty database;
  3. asserts the metric catalogue contains exactly the 26 canonical metrics;
  4. asserts the documented CHECK / UNIQUE constraints actually reject
     invalid rows at the database level;
  5. runs ``alembic downgrade base`` and drops the scratch database.

The scratch database name is ``<POSTGRES_DB>_pytest`` (override with the
``UMOA_POSTGRES_TEST_DB`` env var). The server coordinates come from the
regular settings (POSTGRES_HOST/PORT/USER/PASSWORD).

Reference: docs/specification-v1.md sections 7, 12, 13, 14, 15, 22, 23.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

from app.constants.metrics import V1_METRIC_CODES

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _server_params() -> dict[str, Any]:
    from app.core.config import get_settings

    s = get_settings()
    return {
        "host": s.postgres_host,
        "port": s.postgres_port,
        "user": s.postgres_user,
        "password": s.postgres_password,
        "base_db": s.postgres_db,
    }


async def _server_reachable(params: dict[str, Any]) -> bool:
    import asyncpg

    try:
        conn = await asyncpg.connect(
            host=params["host"],
            port=params["port"],
            user=params["user"],
            password=params["password"],
            database="postgres",
            timeout=3,
        )
    except Exception:
        return False
    await conn.close()
    return True


def _reachable(params: dict[str, Any]) -> bool:
    try:
        return asyncio.run(_server_reachable(params))
    except Exception:
        return False


async def _exec_admin(params: dict[str, Any], *statements: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(
        host=params["host"],
        port=params["port"],
        user=params["user"],
        password=params["password"],
        database="postgres",
    )
    try:
        for stmt in statements:
            await conn.execute(stmt)
    finally:
        await conn.close()


async def _fetchval(dsn: str, query: str, *args: Any) -> Any:
    import asyncpg

    conn = await asyncpg.connect(dsn=dsn)
    try:
        return await conn.fetchval(query, *args)
    finally:
        await conn.close()


async def _execute(dsn: str, query: str, *args: Any) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn=dsn)
    try:
        await conn.execute(query, *args)
    finally:
        await conn.close()


async def _expect_failure(dsn: str, query: str, *args: Any) -> None:
    """Assert that executing the statement raises a DB error."""
    import asyncpg

    conn = await asyncpg.connect(dsn=dsn)
    try:
        with pytest.raises(asyncpg.PostgresError):
            await conn.execute(query, *args)
    finally:
        await conn.close()


def _dsn(params: dict[str, Any], database: str) -> str:
    return (
        f"postgresql://{params['user']}:{params['password']}"
        f"@{params['host']}:{params['port']}/{database}"
    )


def _async_dsn(params: dict[str, Any], database: str) -> str:
    return (
        f"postgresql+asyncpg://{params['user']}:{params['password']}"
        f"@{params['host']}:{params['port']}/{database}"
    )


@pytest.fixture(scope="module")
def scratch_db() -> Generator[str, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = os.environ.get("UMOA_POSTGRES_TEST_DB", f"{params['base_db']}_pytest")

    # Drop & recreate a clean scratch database.
    asyncio.run(
        _exec_admin(
            params,
            f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)',
            f'CREATE DATABASE "{test_db}"',
        )
    )

    # Point Alembic (via settings) at the scratch database.
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()

    yield test_db

    # Cleanup: drop the scratch database.
    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(
        _exec_admin(
            params,
            f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)',
        )
    )


def _run_alembic(direction: str) -> None:
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if direction == "upgrade":
        command.upgrade(cfg, "head")
    else:
        command.downgrade(cfg, "base")


def test_migration_upgrade_creates_catalogue_and_constraints(scratch_db: str) -> None:
    params = _server_params()
    dsn = _dsn(params, scratch_db)

    # 1. Run the full migration chain from an empty database.
    _run_alembic("upgrade")

    # 2. Catalogue integrity: exactly the 26 canonical metrics.
    count = asyncio.run(
        _fetchval(dsn, "SELECT COUNT(*) FROM metric_definitions")
    )
    assert count == 26, f"expected 26 metrics, found {count}"

    codes = asyncio.run(
        _fetchval(
            dsn,
            "SELECT array_agg(code ORDER BY code) FROM metric_definitions",
        )
    )
    assert set(codes) == set(V1_METRIC_CODES)

    calculated = asyncio.run(
        _fetchval(
            dsn,
            "SELECT COUNT(*) FROM metric_definitions WHERE is_calculated",
        )
    )
    assert calculated == 0, "no V1 metric may be flagged as calculated"

    # 3. Seed idempotency: re-running upgrade must not duplicate rows.
    _run_alembic("upgrade")
    count_again = asyncio.run(
        _fetchval(dsn, "SELECT COUNT(*) FROM metric_definitions")
    )
    assert count_again == 26

    # 4. Constraint enforcement (real PostgreSQL).
    cid = str(uuid.uuid4())
    sid = str(uuid.uuid4())
    iid = str(uuid.uuid4())
    did = str(uuid.uuid4())

    # Migration 0003 seeds the 8 UMOA countries: reuse the seeded CI row.
    cid = asyncio.run(_fetchval(dsn, "SELECT id FROM countries WHERE code = 'CI'"))
    assert cid is not None
    asyncio.run(
        _execute(
            dsn,
            "INSERT INTO sources (id, name, source_type, priority, is_active, "
            "created_at, updated_at) VALUES ($1, 'Test source', 'bank', 1, "
            "true, now(), now())",
            sid,
        )
    )
    asyncio.run(
        _execute(
            dsn,
            "INSERT INTO institutions (id, name_official, institution_type, "
            "country_id, status, created_at, updated_at) VALUES ($1, 'Test "
            "Bank', 'bank', $2, 'active', now(), now())",
            iid,
            cid,
        )
    )
    asyncio.run(
        _execute(
            dsn,
            "INSERT INTO documents (id, title, document_type, source_id, "
            "download_status, extraction_status, file_hash, created_at, "
            "updated_at) VALUES ($1, 'Doc', 'annual_report', $2, 'downloaded', "
            "'pending', $3, now(), now())",
            did,
            sid,
            "a" * 64,
        )
    )

    base_cols = (
        "institution_id, source_id, document_id, metric_code, period_type, "
        "period_year, value_original, extraction_method, status, created_at, "
        "updated_at"
    )
    base_vals = (iid, sid, did, "total_actifs", "annual", 2024, "100", "manual")

    # Valid baseline row (status=extracted) must succeed.
    asyncio.run(
        _execute(
            dsn,
            f"INSERT INTO financial_data (id, scope, {base_cols}) "
            "VALUES ($1, 'individual', $2, $3, $4, $5, $6, $7, $8, $9, "
            "'extracted', now(), now())",
            str(uuid.uuid4()),
            *base_vals,
        )
    )

    # Invalid scope.
    asyncio.run(
        _expect_failure(
            dsn,
            f"INSERT INTO financial_data (id, scope, {base_cols}) "
            "VALUES ($1, 'sector', $2, $3, $4, $5, $6, $7, $8, $9, "
            "'extracted', now(), now())",
            str(uuid.uuid4()),
            *base_vals,
        )
    )

    # reviewed without value_normalized.
    asyncio.run(
        _expect_failure(
            dsn,
            f"INSERT INTO financial_data (id, scope, {base_cols}) "
            "VALUES ($1, 'individual', $2, $3, $4, $5, $6, $7, $8, $9, "
            "'reviewed', now(), now())",
            str(uuid.uuid4()),
            *base_vals,
        )
    )

    # verified without verified_by / verified_at.
    asyncio.run(
        _expect_failure(
            dsn,
            f"INSERT INTO financial_data (id, scope, value_normalized, {base_cols}) "
            "VALUES ($1, 'individual', 100, $2, $3, $4, $5, $6, $7, $8, $9, "
            "'verified', now(), now())",
            str(uuid.uuid4()),
            *base_vals,
        )
    )

    # confidence_score out of range.
    asyncio.run(
        _expect_failure(
            dsn,
            f"INSERT INTO financial_data (id, scope, confidence_score, {base_cols}) "
            "VALUES ($1, 'individual', 1.5, $2, $3, $4, $5, $6, $7, $8, $9, "
            "'extracted', now(), now())",
            str(uuid.uuid4()),
            *base_vals,
        )
    )

    # page_number not positive.
    asyncio.run(
        _expect_failure(
            dsn,
            f"INSERT INTO financial_data (id, scope, page_number, {base_cols}) "
            "VALUES ($1, 'individual', 0, $2, $3, $4, $5, $6, $7, $8, $9, "
            "'extracted', now(), now())",
            str(uuid.uuid4()),
            *base_vals,
        )
    )

    # Duplicate file_hash must be rejected.
    asyncio.run(
        _expect_failure(
            dsn,
            "INSERT INTO documents (id, title, document_type, source_id, "
            "download_status, extraction_status, file_hash, created_at, "
            "updated_at) VALUES ($1, 'Doc2', 'annual_report', $2, 'downloaded', "
            "'pending', $3, now(), now())",
            str(uuid.uuid4()),
            sid,
            "a" * 64,
        )
    )

    # 5. Downgrade back to base (schema fully reversible). The seed downgrades (0003/0004)
    #    refuse to delete referenced rows (FK RESTRICT), so remove this test's own rows first.
    for stmt in (
        "DELETE FROM financial_data",
        "DELETE FROM documents",
        "DELETE FROM institutions",
        "DELETE FROM sources WHERE name = 'Test source'",
    ):
        asyncio.run(_execute(dsn, stmt))
    _run_alembic("downgrade")

    gone = asyncio.run(
        _fetchval(
            dsn,
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name IN "
            "('financial_data', 'documents', 'metric_definitions', "
            "'institutions', 'sources', 'countries', 'banking_groups')",
        )
    )
    assert gone == 0, "downgrade must drop all application tables"
