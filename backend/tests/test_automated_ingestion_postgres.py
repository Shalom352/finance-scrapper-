"""
UMOA Banking Intelligence — Automated Ingestion PostgreSQL Integration Tests

Tests against a REAL scratch PostgreSQL database (consistent with Phase 8C-13).
Verifies:
  1. Database persistence of IngestionRun records in PostgreSQL.
  2. IngestionService execution lifecycle and DB updates against PostgreSQL.
  3. API endpoints:
     - GET /api/v1/ingestion/runs
     - GET /api/v1/ingestion/runs/latest
     - GET /api/v1/ingestion/runs/{run_id}
     - POST /api/v1/ingestion/trigger
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

BASE_URL = "/api/v1/ingestion"


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_ingestion_pytest"
    asyncio.run(
        _exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"')
    )
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")
    yield {"url": _async_dsn(params, test_db)}

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


@pytest_asyncio.fixture
async def db_session(pg_db: dict):
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def api(pg_db: dict) -> AsyncGenerator[AsyncClient, None]:
    from app.db.session import get_db_session
    from app.main import create_app

    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override() -> AsyncGenerator:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest.mark.asyncio
class TestAutomatedIngestionPostgres:
    async def test_create_and_retrieve_ingestion_run(self, db_session):
        """Verify inserting and querying IngestionRun records from PostgreSQL."""
        from app.models.ingestion_run import IngestionRun
        from app.services.ingestion import (
            get_ingestion_run_by_id,
            list_ingestion_runs,
        )

        now = datetime.now(UTC)
        run = IngestionRun(
            trigger_type="scheduled",
            status="completed",
            target_years="2026, 2025, 2024, 2023, 2022, 2021",
            sources_checked=2,
            documents_found=5,
            documents_new=2,
            documents_downloaded=2,
            documents_skipped=3,
            documents_failed=0,
            data_points_extracted=24,
            data_points_needing_review=24,
            started_at=now,
            finished_at=now,
            summary_text="Integration test run completed.",
        )
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)

        assert run.id is not None

        # Query via service helpers
        fetched = await get_ingestion_run_by_id(db_session, run.id)
        assert fetched is not None
        assert fetched.id == run.id
        assert fetched.status == "completed"
        assert fetched.documents_found == 5
        assert fetched.data_points_extracted == 24
        assert fetched.target_years == "2026, 2025, 2024, 2023, 2022, 2021"

        # List runs
        runs, total = await list_ingestion_runs(db_session, page=1, page_size=10)
        assert total >= 1
        assert any(r.id == run.id for r in runs)

    async def test_get_latest_ingestion_run(self, db_session):
        """Verify retrieving the most recent run."""
        from app.models.ingestion_run import IngestionRun
        from app.services.ingestion import get_latest_ingestion_run

        now = datetime.now(UTC)
        run = IngestionRun(
            trigger_type="manual",
            status="completed",
            target_years="2026",
            sources_checked=1,
            documents_found=3,
            started_at=now,
            finished_at=now,
        )
        db_session.add(run)
        await db_session.commit()

        latest = await get_latest_ingestion_run(db_session)
        assert latest is not None
        assert latest.id == run.id

    async def test_execute_run_service_integration(self, db_session):
        """Verify IngestionService.execute_run() runs through and commits to DB."""
        from app.services.ingestion import IngestionService
        from scraping.pipeline import ScrapingPipeline

        mock_pipeline = MagicMock(spec=ScrapingPipeline)
        mock_pipeline.discover_source = AsyncMock(return_value=[])
        mock_pipeline.download_pending_documents = AsyncMock(return_value=[])
        mock_pipeline.parse_downloaded_documents = AsyncMock(return_value=[])
        mock_pipeline.extract_financial_data = AsyncMock(return_value=[])

        service = IngestionService(pipeline=mock_pipeline)
        run = await service.execute_run(
            db=db_session,
            trigger_type="manual",
            target_years=[2026],
            sources=["bceao"],
            limit_per_source=1,
            force=True,
        )

        assert run.id is not None
        assert run.trigger_type == "manual"
        assert run.status in ("completed", "partial_failure", "failed")
        assert run.finished_at is not None
        assert run.duration_seconds is not None

    async def test_api_ingestion_endpoints(self, api: AsyncClient):
        """Verify FastAPI endpoints for ingestion status and triggering."""
        from unittest.mock import patch

        with patch("app.api.v1.ingestion._run_in_background"):
            # 1. GET /api/v1/ingestion/runs
            res_list = await api.get(f"{BASE_URL}/runs?page=1&page_size=5")
            assert res_list.status_code == 200
            data_list = res_list.json()
            assert "items" in data_list
            assert "total" in data_list
            assert isinstance(data_list["items"], list)

            # 2. GET /api/v1/ingestion/runs/latest
            res_latest = await api.get(f"{BASE_URL}/runs/latest")
            assert res_latest.status_code == 200
            latest_data = res_latest.json()
            assert latest_data is None or "id" in latest_data

            # 3. POST /api/v1/ingestion/trigger
            res_trigger = await api.post(f"{BASE_URL}/trigger?source=bceao&force=true")
            assert res_trigger.status_code in (200, 202)
            trigger_data = res_trigger.json()
            assert "run_id" in trigger_data
            assert "status" in trigger_data

            # 4. GET /api/v1/ingestion/runs/{run_id}
            run_id = trigger_data["run_id"]
            res_run = await api.get(f"{BASE_URL}/runs/{run_id}")
            assert res_run.status_code == 200
            assert res_run.json()["id"] == run_id
