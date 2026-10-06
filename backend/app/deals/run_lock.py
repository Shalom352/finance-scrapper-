"""
Single-run lock for deal ingestion runners (PostgreSQL advisory lock).

A runner takes a session-level advisory lock on a DEDICATED connection that stays open for the
whole run, so the lock is never lost when the ingestion session returns its connections to the
pool. A second runner on the same database gets ``pg_try_advisory_lock = false`` and must refuse
to start. The lock disappears with the connection if the process dies (no stale lock).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.logging import get_logger

logger = get_logger(__name__)

UMOA_TITRES_LOCK = "umoa_titres_run"
# application_name of the dedicated lock connection (pg_stat_activity), distinct from the run's own.
LOCK_APPLICATION_NAME_SUFFIX = ":lock"

_NAME = text("SELECT set_config('application_name', :app, false)")
_RESET_NAME = text("RESET application_name")  # back to the process name before the connection is pooled

_TRY = text("SELECT pg_try_advisory_lock(hashtext(:name))")
_UNLOCK = text("SELECT pg_advisory_unlock(hashtext(:name))")
# PIDs holding the lock. A bigint advisory key is stored as classid = high 32 bits, objid = low 32
# bits, objsubid = 1; hashtext() may be negative, so its sign-extended high half is 0xFFFFFFFF.
_HOLDERS = text(
    "SELECT l.pid FROM pg_locks l "
    "WHERE l.locktype = 'advisory' AND l.granted AND l.objsubid = 1 AND l.database = "
    "(SELECT oid FROM pg_database WHERE datname = current_database()) "
    "AND l.classid::text::bigint = ((hashtext(:name)::bigint >> 32) & 4294967295) "
    "AND l.objid::text::bigint = (hashtext(:name)::bigint & 4294967295) "
    "ORDER BY l.pid"
)


@dataclass
class RunLock:
    acquired: bool
    holders: list[int] = field(default_factory=list)  # PIDs holding the lock when refused

    def refusal(self, database: str) -> str:
        who = ", ".join(str(p) for p in self.holders) or "inconnu"
        return (f"ABANDON: un autre {UMOA_TITRES_LOCK} est déjà actif sur {database!r} "
                f"(verrou consultatif détenu par le PID PostgreSQL {who}).")


@asynccontextmanager
async def single_run_lock(engine: AsyncEngine, name: str = UMOA_TITRES_LOCK) -> AsyncIterator[RunLock]:
    """Yield RunLock(acquired=True) while holding the lock, or RunLock(acquired=False, holders)."""
    async with engine.connect() as conn:
        await conn.execute(_NAME, {"app": f"{name}{LOCK_APPLICATION_NAME_SUFFIX}"})
        acquired = bool((await conn.execute(_TRY, {"name": name})).scalar_one())
        await conn.commit()  # no transaction left open on the lock connection
        if not acquired:
            holders = list((await conn.execute(_HOLDERS, {"name": name})).scalars())
            await conn.execute(_RESET_NAME)
            await conn.commit()
            yield RunLock(False, holders)
            return
        try:
            yield RunLock(True)
        finally:
            await _release(conn, name)


async def _release(conn, name: str) -> None:
    """Unlock; if that fails (broken connection), close the connection instead of pooling it.

    Never raises: an error of the run itself keeps propagating unmasked, and a closed session
    releases a session-level advisory lock on the server side anyway.
    """
    try:
        await conn.execute(_UNLOCK, {"name": name})
        await conn.execute(_RESET_NAME)
        await conn.commit()
    except Exception as err:  # noqa: BLE001 — the lock connection must not survive a failed unlock
        logger.warning("run_lock_release_failed", lock=name, error=f"{type(err).__name__}: {err}")
        try:
            await conn.invalidate()
        except Exception as inv_err:  # noqa: BLE001
            logger.warning("run_lock_invalidate_failed", lock=name, error=f"{type(inv_err).__name__}: {inv_err}")
