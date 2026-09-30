"""
UMOA Banking Intelligence — Automated Ingestion Scheduler

Provides background scheduling for automated 2x/day ingestion runs.
Configured via:
  - INGESTION_ENABLED: bool
  - INGESTION_SCHEDULE: standard cron expression (default: "0 8,20 * * *")
  - INGESTION_TIMEZONE: IANA timezone name (default: "Africa/Abidjan")
  - INGESTION_HISTORICAL_YEARS: number of historical years to search (default: 5)

No heavyweight dependencies (no Celery, no Redis).
Integrated cleanly with the FastAPI lifespan.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.services.ingestion import IngestionService

logger = get_logger(__name__)


def parse_cron_field(field_str: str, min_val: int, max_val: int) -> set[int]:
    """
    Parse a single cron field expression into a set of matching integers.
    Supports: '*', '*/N', 'A,B,C', 'A-B', and plain numbers.
    """
    field_str = field_str.strip()
    if field_str == "*":
        return set(range(min_val, max_val + 1))

    results: set[int] = set()
    for part in field_str.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("*/"):
            step = int(part[2:])
            results.update(val for val in range(min_val, max_val + 1) if (val - min_val) % step == 0)
        elif "-" in part:
            start_str, end_str = part.split("-", 1)
            results.update(range(int(start_str), int(end_str) + 1))
        else:
            results.add(int(part))

    return {v for v in results if min_val <= v <= max_val}


class CronSchedule:
    """Represents a standard 5-field cron schedule evaluated in a specific timezone."""

    def __init__(self, expr: str, tz_name: str = "Africa/Abidjan") -> None:
        self.expr = expr.strip()
        self.tz_name = tz_name
        try:
            self.tz = ZoneInfo(tz_name)
        except Exception:
            logger.warning("invalid_timezone_fallback_utc", requested_tz=tz_name)
            self.tz = UTC

        parts = self.expr.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression '{expr}': expected 5 fields, got {len(parts)}")

        self.minutes = parse_cron_field(parts[0], 0, 59)
        self.hours = parse_cron_field(parts[1], 0, 23)
        self.days = parse_cron_field(parts[2], 1, 31)
        self.months = parse_cron_field(parts[3], 1, 12)
        # Cron day of week: 0=Sunday, 6=Saturday (or 7=Sunday)
        self.weekdays = parse_cron_field(parts[4].replace("7", "0"), 0, 6)

    def matches(self, dt: datetime) -> bool:
        """Check if datetime (in target timezone) matches the cron schedule."""
        dt_tz = dt.astimezone(self.tz)
        # Python weekday: Monday is 0, Sunday is 6 -> convert to cron: Sunday is 0
        cron_weekday = (dt_tz.weekday() + 1) % 7
        return (
            dt_tz.minute in self.minutes
            and dt_tz.hour in self.hours
            and dt_tz.day in self.days
            and dt_tz.month in self.months
            and cron_weekday in self.weekdays
        )

    def seconds_until_next_run(self, now: datetime | None = None) -> float:
        """Calculate seconds until the next matching minute."""
        now_dt = (now or datetime.now(UTC)).astimezone(self.tz)
        # Check minute by minute up to 48 hours ahead
        check_dt = now_dt.replace(second=0, microsecond=0)
        for i in range(1, 48 * 60 + 1):
            cand = check_dt.fromtimestamp(check_dt.timestamp() + i * 60, tz=self.tz)
            if self.matches(cand):
                diff = (cand - now_dt).total_seconds()
                return max(1.0, diff)
        return 60.0


class IngestionScheduler:
    """Background task orchestrator for running IngestionService according to schedule."""

    def __init__(self) -> None:
        self._task: asyncio.Task[Any] | None = None
        self._running: bool = False
        self._service = IngestionService()

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    def start(self) -> None:
        """Start the background scheduler task if enabled."""
        settings = get_settings()
        if not settings.ingestion_enabled:
            logger.info("ingestion_scheduler_disabled_by_config")
            return

        if self.is_running:
            logger.info("ingestion_scheduler_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="umoa_ingestion_scheduler")
        logger.info(
            "ingestion_scheduler_started",
            schedule=settings.ingestion_schedule,
            timezone=settings.ingestion_timezone,
            historical_years=settings.ingestion_historical_years,
        )

    def stop(self) -> None:
        """Stop the background scheduler task."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("ingestion_scheduler_stopped")

    async def _run_loop(self) -> None:
        """Main evaluation loop."""
        settings = get_settings()
        try:
            schedule = CronSchedule(settings.ingestion_schedule, settings.ingestion_timezone)
        except Exception as err:
            logger.error("invalid_ingestion_schedule_config", error=str(err))
            self._running = False
            return

        while self._running:
            try:
                seconds_wait = schedule.seconds_until_next_run()
                logger.info("ingestion_scheduler_waiting", next_run_in_seconds=round(seconds_wait, 1))
                await asyncio.sleep(seconds_wait)

                if not self._running:
                    break

                logger.info("ingestion_scheduler_triggering_run")
                async with AsyncSessionLocal() as session:
                    await self._service.execute_run(
                        db=session,
                        trigger_type="scheduled",
                    )

            except asyncio.CancelledError:
                break
            except Exception as err:
                logger.error("ingestion_scheduler_loop_error", error=str(err))
                # Polite backoff before retrying loop
                await asyncio.sleep(60)


# Global scheduler instance
_GLOBAL_SCHEDULER = IngestionScheduler()


def get_ingestion_scheduler() -> IngestionScheduler:
    """Return the application scheduler singleton."""
    return _GLOBAL_SCHEDULER
