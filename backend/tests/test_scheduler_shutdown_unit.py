import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import ingestion as ingestion_module
from app.services.discovery_scheduler import DiscoveryScheduler
from app.services.ingestion import IngestionService
from app.services.scheduler import IngestionScheduler


@pytest.mark.parametrize("scheduler_type", [IngestionScheduler, DiscoveryScheduler])
@pytest.mark.asyncio
async def test_stop_waits_for_background_task_cleanup(scheduler_type):
    scheduler = scheduler_type()
    cleanup_finished = asyncio.Event()

    async def worker():
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleanup_finished.set()

    scheduler._running = True
    task = asyncio.create_task(worker())
    scheduler._task = task

    await scheduler.stop()

    assert task.done()
    assert cleanup_finished.is_set()
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_cancelled_run_is_marked_failed_and_reraises(monkeypatch):
    run = SimpleNamespace(
        id="run-1", status="running", errors=[], finished_at=None, summary_text=None
    )
    active_result = MagicMock()
    active_result.scalar_one_or_none.return_value = None
    run_result = MagicMock()
    run_result.scalar_one_or_none.return_value = run
    failed_result = MagicMock()
    failed_result.scalar_one.return_value = run

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[active_result, run_result, failed_result])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    monkeypatch.setattr(ingestion_module, "expire_stale_runs", AsyncMock(return_value=0))

    service = IngestionService(pipeline=MagicMock())

    async def cancel_phases(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(service, "_run_phases", cancel_phases)
    with pytest.raises(asyncio.CancelledError):
        await service.execute_run(db, target_years=[2026], run_id="run-1")

    assert run.status == "failed"
    assert run.finished_at is not None
    assert "Ingestion interrupted by task cancellation." in run.summary_text
    db.rollback.assert_awaited_once()
    db.commit.assert_awaited_once()