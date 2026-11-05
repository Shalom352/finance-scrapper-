"""
UMOA Financial Intelligence — Recurring Entity & Source Discovery (Phase 15).

Configuration (environment, see app.core.config):
  - DISCOVERY_ENABLED   : false by default — nothing runs unless explicitly enabled;
  - DISCOVERY_SCHEDULE  : 5-field cron expression (default "0 3 * * *"), evaluated in
                          INGESTION_TIMEZONE with the existing CronSchedule.

Every scheduled run re-checks the official reference lists (new list? new licence?), then walks
the gap queue: gaps whose retry date has passed are searched again, so a source that is empty
today is retried later instead of being considered useless.
"""

import asyncio
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.services.scheduler import CronSchedule

logger = get_logger(__name__)


class DiscoveryScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task[Any] | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        settings = get_settings()
        if not settings.discovery_enabled:
            logger.info("discovery_scheduler_disabled_by_config")
            return
        if self.is_running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="umoa_discovery_scheduler")
        logger.info("discovery_scheduler_started", schedule=settings.discovery_schedule)

    async def stop(self) -> None:
        self._running = False
        task = self._task
        if task is None:
            return
        if not task.done():
            task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            if self._task is task:
                self._task = None
        logger.info("discovery_scheduler_stopped")

    async def _run_loop(self) -> None:
        from datetime import UTC, datetime

        from app.db.engine import engine
        from app.deals.run_lock import DISCOVERY_LOCK, single_run_lock
        from scraping.universe.engine import DiscoveryEngine

        settings = get_settings()
        try:
            schedule = CronSchedule(settings.discovery_schedule, settings.ingestion_timezone)
        except Exception as err:
            logger.error("invalid_discovery_schedule_config", error=str(err))
            self._running = False
            return
        while self._running:
            try:
                await asyncio.sleep(schedule.seconds_until_next_run())
                if not self._running:
                    break
                year = datetime.now(UTC).year
                async with single_run_lock(engine, DISCOVERY_LOCK) as lock:
                    if not lock.acquired:  # a CLI run is active: this occurrence is skipped, not doubled
                        logger.warning("discovery_scheduled_run_skipped_lock", holders=lock.holders)
                        continue
                    async with AsyncSessionLocal() as session:
                        await DiscoveryEngine(max_rounds=settings.discovery_max_rounds).run(
                            session,
                            universe_code=settings.discovery_universe,
                            trigger_type="scheduled",
                            target_years=[year - i for i in range(settings.discovery_historical_years + 1)],
                            options={"fascicle_editions": settings.discovery_fascicle_editions,
                                     "reference_editions": settings.discovery_reference_editions},
                        )
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("discovery_scheduler_loop_error", error=str(err))
                await asyncio.sleep(60)


_GLOBAL_DISCOVERY_SCHEDULER = DiscoveryScheduler()


def get_discovery_scheduler() -> DiscoveryScheduler:
    return _GLOBAL_DISCOVERY_SCHEDULER
