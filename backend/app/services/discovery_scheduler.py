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

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("discovery_scheduler_stopped")

    async def _run_loop(self) -> None:
        from datetime import UTC, datetime

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
                async with AsyncSessionLocal() as session:
                    await DiscoveryEngine().run(
                        session,
                        universe_code=settings.discovery_universe,
                        trigger_type="scheduled",
                        target_years=[year - i for i in range(settings.discovery_historical_years + 1)],
                        options={"fascicle_editions": settings.discovery_fascicle_editions},
                    )
            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("discovery_scheduler_loop_error", error=str(err))
                await asyncio.sleep(60)


_GLOBAL_DISCOVERY_SCHEDULER = DiscoveryScheduler()


def get_discovery_scheduler() -> DiscoveryScheduler:
    return _GLOBAL_DISCOVERY_SCHEDULER
