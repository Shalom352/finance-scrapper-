"""Single-run advisory lock against a REAL PostgreSQL (scratch database, never the dev bases)."""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.deals.run_lock import single_run_lock
from tests.test_migration_postgres_phase2 import _dsn
from tests.test_phase15_discovery_postgres import _drop, _fresh_db


@pytest.fixture(scope="module")
def url():
    params, name = _fresh_db("lot0_run_lock_pytest")
    yield _dsn(params, name).replace("postgresql://", "postgresql+asyncpg://")
    _drop(params, name)


def test_second_run_is_refused_while_the_first_holds_the_lock(url):
    async def scenario():
        first_engine, second_engine = create_async_engine(url), create_async_engine(url)
        try:
            async with single_run_lock(first_engine) as first:
                assert first.acquired
                async with first_engine.connect() as c:  # the lock connection is the only other one
                    pids = (await c.execute(text(
                        "SELECT pid FROM pg_stat_activity WHERE datname = current_database() "
                        "AND pid <> pg_backend_pid()"))).scalars().all()
                async with single_run_lock(second_engine) as second:
                    assert not second.acquired
                    assert second.holders == pids and len(pids) == 1
                    assert "déjà actif" in second.refusal("scratch")
            # Released at the end of the first run: a new run may start.
            async with single_run_lock(second_engine) as third:
                assert third.acquired
            # No transaction is left open on the lock connection while a run is active.
            async with single_run_lock(first_engine) as held:
                assert held.acquired
                async with second_engine.connect() as c:
                    idle_in_tx = (await c.execute(text(
                        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                        "AND state = 'idle in transaction'"))).scalar_one()
                assert idle_in_tx == 0
        finally:
            await first_engine.dispose()
            await second_engine.dispose()

    asyncio.run(scenario())


def test_lock_is_released_when_the_holder_disappears(url):
    async def scenario():
        holder, other = create_async_engine(url), create_async_engine(url)
        try:
            cm = single_run_lock(holder)
            lock = await cm.__aenter__()
            assert lock.acquired
            async with single_run_lock(other) as refused:
                assert not refused.acquired
                (pid,) = refused.holders
            # The holding process "dies" (scratch database only): its connection ends without unlock.
            async with other.connect() as c:
                await c.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
                await c.commit()
            await asyncio.sleep(0.3)
            async with single_run_lock(other) as again:
                assert again.acquired  # no stale lock
        finally:
            await other.dispose()
            await holder.dispose()

    asyncio.run(scenario())
