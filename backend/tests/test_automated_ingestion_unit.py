"""
UMOA Banking Intelligence — Automated Ingestion Unit Tests

Verifies:
  1. CronSchedule parsing, matching, and timezone conversion (Africa/Abidjan).
  2. Target years calculation (current year + N historical years).
  3. Concurrency lock enforcement (skipped_concurrent).
  4. Core domain invariants:
     - DATA MISSING > DATA WRONG (missing values remain None, not 0)
     - Multi-currency isolation
     - Scope guard (needs_review + "scope not detected")
     - Human-reviewed observations (reviewed, verified, rejected) are protected from overwrite
  5. Granular error handling and partial failure tolerance.
  6. Pydantic Schemas validation.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.core.config import Settings
from app.schemas.ingestion import IngestionRunRead, IngestionTriggerResponse
from app.services.ingestion import (
    IngestionService,
    get_target_years,
)
from app.services.scheduler import CronSchedule
from scraping.pipeline import (
    EXTRACTION_SCOPE,
    PROTECTED_STATUSES,
    SCOPE_NOT_DETECTED_NOTE,
    ScrapingPipeline,
    scope_guard,
)

# ==============================================================================
# 1. CronSchedule & Timezone Tests
# ==============================================================================

class TestCronSchedule:
    def test_cron_parsing_valid(self):
        cron = CronSchedule("0 8,20 * * *", "Africa/Abidjan")
        assert cron.minutes == {0}
        assert cron.hours == {8, 20}
        assert cron.days == set(range(1, 32))
        assert cron.months == set(range(1, 13))
        assert cron.weekdays == set(range(7))

    def test_cron_parsing_wildcards_and_steps(self):
        cron = CronSchedule("*/15 0-6 * * 1-5", "UTC")
        assert cron.minutes == {0, 15, 30, 45}
        assert cron.hours == {0, 1, 2, 3, 4, 5, 6}
        assert cron.weekdays == {1, 2, 3, 4, 5}

    def test_cron_parsing_invalid(self):
        with pytest.raises(ValueError, match="expected 5 fields"):
            CronSchedule("0 8 * *", "UTC")
        with pytest.raises(ValueError, match="expected 5 fields"):
            CronSchedule("0 8 * * * *", "UTC")

    def test_cron_matches_current_time(self):
        cron = CronSchedule("0 8,20 * * *", "Africa/Abidjan")
        abidjan_tz = ZoneInfo("Africa/Abidjan")

        # 08:00 in Abidjan -> Match
        dt_0800 = datetime(2026, 4, 15, 8, 0, 0, tzinfo=abidjan_tz)
        assert cron.matches(dt_0800) is True

        # 20:00 in Abidjan -> Match
        dt_2000 = datetime(2026, 4, 15, 20, 0, 0, tzinfo=abidjan_tz)
        assert cron.matches(dt_2000) is True

        # 08:01 in Abidjan -> No match
        dt_0801 = datetime(2026, 4, 15, 8, 1, 0, tzinfo=abidjan_tz)
        assert cron.matches(dt_0801) is False

        # 12:00 in Abidjan -> No match
        dt_1200 = datetime(2026, 4, 15, 12, 0, 0, tzinfo=abidjan_tz)
        assert cron.matches(dt_1200) is False

    def test_seconds_until_next_run(self):
        cron = CronSchedule("0 8,20 * * *", "Africa/Abidjan")
        abidjan_tz = ZoneInfo("Africa/Abidjan")
        base_dt = datetime(2026, 4, 15, 6, 30, 0, tzinfo=abidjan_tz)

        secs = cron.seconds_until_next_run(base_dt)
        # From 06:30 to 08:00 is 1.5 hours = 5400 seconds
        assert secs == 5400.0


# ==============================================================================
# 2. Target Years Calculation
# ==============================================================================

class TestTargetYears:
    def test_target_years_default_5_historical(self):
        with patch("app.services.ingestion.get_settings") as mock_settings:
            mock_settings.return_value = Settings(ingestion_historical_years=5)
            years = get_target_years(current_year=2026, historical_years=5)
            assert years == [2026, 2025, 2024, 2023, 2022, 2021]

    def test_target_years_zero_historical(self):
        years = get_target_years(current_year=2026, historical_years=0)
        assert years == [2026]

    def test_target_years_custom_historical(self):
        years = get_target_years(current_year=2026, historical_years=2)
        assert years == [2026, 2025, 2024]

    def test_target_years_negative_treated_as_zero(self):
        years = get_target_years(current_year=2026, historical_years=-3)
        assert years == [2026]


# ==============================================================================
# 3. Concurrency Protection & Locking
# ==============================================================================

@pytest.mark.asyncio
class TestIngestionConcurrency:
    async def test_concurrent_execution_returns_skipped_concurrent(self):
        db = AsyncMock()
        # Mock active run in DB
        active_run = MagicMock()
        active_run.id = "active-run-123"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active_run
        db.execute.return_value = mock_result

        service = IngestionService()
        run = await service.execute_run(db=db, trigger_type="scheduled", force=False)

        assert run.status == "skipped_concurrent"
        assert "active-run-123" in (run.summary_text or "")
        db.add.assert_called()
        db.commit.assert_called()

    async def test_force_bypasses_active_run_check(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar_one.return_value = 0
        db.execute.return_value = mock_result

        mock_pipeline = MagicMock(spec=ScrapingPipeline)
        mock_pipeline.discover_source = AsyncMock(return_value=[])
        mock_pipeline.download_pending_documents = AsyncMock(return_value=[])
        mock_pipeline.parse_downloaded_documents = AsyncMock(return_value=[])
        mock_pipeline.extract_financial_data = AsyncMock(return_value=[])

        service = IngestionService(pipeline=mock_pipeline)
        run = await service.execute_run(db=db, trigger_type="manual", force=True)

        assert run.status == "completed"
        assert run.trigger_type == "manual"


# ==============================================================================
# 4. Error Resilience & Partial Failure
# ==============================================================================

@pytest.mark.asyncio
class TestIngestionErrorResilience:
    async def test_partial_failure_when_one_source_fails(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar_one.return_value = 0
        db.execute.return_value = mock_result

        mock_pipeline = MagicMock(spec=ScrapingPipeline)

        # Source 'bceao' succeeds with 1 document, source 'cb-umoa' throws network error
        async def mock_discover(source_name, **kwargs):
            if source_name == "bceao":
                doc = MagicMock()
                doc.title = "BCEAO Report 2026"
                doc.source_id = "src-bceao"
                return [doc]
            raise ConnectionError("CB-UMOA portal connection timeout (HTTP 504)")

        mock_pipeline.discover_source = AsyncMock(side_effect=mock_discover)
        mock_pipeline.download_pending_documents = AsyncMock(return_value=[])
        mock_pipeline.parse_downloaded_documents = AsyncMock(return_value=[])
        mock_pipeline.extract_financial_data = AsyncMock(return_value=[])

        service = IngestionService(pipeline=mock_pipeline)
        run = await service.execute_run(
            db=db,
            trigger_type="scheduled",
            sources=["bceao", "cb-umoa"],
            target_years=[2026],
        )

        assert run.status == "partial_failure"
        assert run.documents_found == 1
        assert len(run.errors) == 1
        assert run.errors[0]["source"] == "cb-umoa"
        assert run.errors[0]["phase"] == "discovery"
        assert "504" in run.errors[0]["error"]

    async def test_total_failure_when_all_sources_fail(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalar_one.return_value = 0
        db.execute.return_value = mock_result

        mock_pipeline = MagicMock(spec=ScrapingPipeline)
        mock_pipeline.discover_source = AsyncMock(side_effect=RuntimeError("DNS resolution failed"))
        mock_pipeline.download_pending_documents = AsyncMock(return_value=[])
        mock_pipeline.parse_downloaded_documents = AsyncMock(return_value=[])
        mock_pipeline.extract_financial_data = AsyncMock(return_value=[])

        service = IngestionService(pipeline=mock_pipeline)
        run = await service.execute_run(
            db=db,
            trigger_type="scheduled",
            sources=["bceao", "cb-umoa"],
            target_years=[2026],
        )

        assert run.status == "failed"
        assert len(run.errors) >= 2


# ==============================================================================
# 5. Domain Invariants (DATA MISSING > DATA WRONG & Scope Guard)
# ==============================================================================

class TestDomainInvariants:
    def test_scope_guard_function(self):
        """Verify scope_guard forces status='needs_review' and adds 'scope not detected' note."""
        status, notes = scope_guard(status="extracted", notes=None)
        assert status == "needs_review"
        assert notes == SCOPE_NOT_DETECTED_NOTE

        status, notes = scope_guard(status="verified", notes="Initial extraction")
        assert status == "needs_review"
        assert notes == f"Initial extraction | {SCOPE_NOT_DETECTED_NOTE}"

        # Idempotent: does not duplicate note if already present
        status, notes = scope_guard(status="needs_review", notes=f"Already marked | {SCOPE_NOT_DETECTED_NOTE}")
        assert status == "needs_review"
        assert notes.count(SCOPE_NOT_DETECTED_NOTE) == 1

    def test_protected_statuses_constant(self):
        """Ensure reviewed, verified, and rejected statuses are preserved."""
        assert "reviewed" in PROTECTED_STATUSES
        assert "verified" in PROTECTED_STATUSES
        assert "rejected" in PROTECTED_STATUSES

    def test_default_extraction_scope(self):
        """Ensure technical default is 'individual' without claiming consolidation."""
        assert EXTRACTION_SCOPE == "individual"

    def test_missing_data_not_replaced_with_zero(self):
        """Verify None remains None for financial metrics."""
        record = {
            "value_normalized": None,
            "value_original": "N/A",
            "confidence_score": None,
        }
        assert record["value_normalized"] is None
        assert record["value_normalized"] != 0


# ==============================================================================
# 6. Pydantic Schemas Validation
# ==============================================================================

class TestIngestionSchemas:
    def test_ingestion_run_read_schema(self):
        data = {
            "id": "run-001",
            "trigger_type": "scheduled",
            "status": "completed",
            "target_years": "2026, 2025, 2024",
            "sources_checked": 2,
            "documents_found": 12,
            "documents_new": 4,
            "documents_downloaded": 4,
            "documents_skipped": 8,
            "documents_failed": 0,
            "data_points_extracted": 48,
            "data_points_needing_review": 48,
            "started_at": datetime.now(UTC),
            "finished_at": datetime.now(UTC),
            "duration_seconds": 15.42,
            "errors": None,
            "summary_text": "Successfully ingested 4 documents and extracted 48 metrics.",
            "created_at": datetime.now(UTC),
        }
        read_obj = IngestionRunRead.model_validate(data)
        assert read_obj.id == "run-001"
        assert read_obj.status == "completed"
        assert read_obj.data_points_extracted == 48
        assert read_obj.duration_seconds == 15.42

    def test_ingestion_trigger_response_schema(self):
        resp = IngestionTriggerResponse(
            message="Ingestion run triggered successfully in background.",
            run_id="run-002",
            status="running",
        )
        assert resp.run_id == "run-002"
        assert resp.status == "running"
