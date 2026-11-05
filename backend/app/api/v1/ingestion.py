"""
UMOA Banking Intelligence — Ingestion API Router

Endpoints:
  - GET  /api/v1/ingestion/runs: Paginated list of past ingestion runs.
  - GET  /api/v1/ingestion/runs/latest: Latest run summary & status.
  - GET  /api/v1/ingestion/runs/{run_id}: Run details by ID.
  - POST /api/v1/ingestion/runs/{run_id}/abort: Mark a run left "running" by a dead process as failed.
  - POST /api/v1/ingestion/trigger: Manually trigger an ingestion run, for all sources or one
    (bank statements: bceao, cb-umoa, brvm, umoa-titres; deals: umoa-titres, brvm, amf-umoa, ifc,
    boad, proparco). ``scope`` = all | financial | deals; ``since`` / ``until`` bound the deal window.
"""

import asyncio
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.internal_auth import write_access
from app.db.session import AsyncSessionLocal, get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.ingestion import IngestionRunRead, IngestionTriggerResponse
from app.services.ingestion import (
    IngestionService,
    abort_run,
    expire_stale_run,
    expire_stale_runs,
    get_ingestion_run_by_id,
    get_latest_ingestion_run,
    list_ingestion_runs,
)

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])

# Track manual workers so an abort request cancels the actual search task as well as its row.
_ACTIVE_INGESTION_TASKS: dict[str, asyncio.Task[None]] = {}


def _forget_ingestion_task(run_id: str, task: asyncio.Task[None]) -> None:
    if _ACTIVE_INGESTION_TASKS.get(run_id) is task:
        _ACTIVE_INGESTION_TASKS.pop(run_id, None)


@router.get("/runs", response_model=PaginatedResponse[IngestionRunRead], summary="List ingestion runs")
async def get_runs(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[IngestionRunRead]:
    """Retrieve paginated history of automated and manual ingestion executions."""
    await expire_stale_runs(db)
    items, total = await list_ingestion_runs(db, page=page, page_size=page_size)
    return PaginatedResponse(
        items=[IngestionRunRead.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
        has_prev=page > 1,
    )


@router.get("/runs/latest", response_model=IngestionRunRead | None, summary="Get latest ingestion run")
async def get_latest_run(
    db: AsyncSession = Depends(get_db_session),
) -> IngestionRunRead | None:
    """Retrieve the most recent ingestion execution."""
    await expire_stale_runs(db)
    run = await get_latest_ingestion_run(db)
    if run is None:
        return None
    return IngestionRunRead.model_validate(run)


@router.get("/runs/{run_id}", response_model=IngestionRunRead, summary="Get ingestion run by ID")
async def get_run_by_id(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> IngestionRunRead:
    """Retrieve detailed information about a specific ingestion run."""
    await expire_stale_run(db, run_id)
    run = await get_ingestion_run_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return IngestionRunRead.model_validate(run)


@router.post("/runs/{run_id}/abort", response_model=IngestionRunRead, summary="Mark a stuck run as failed")
async def abort_ingestion_run(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
    user: str | None = Depends(write_access),
) -> IngestionRunRead:
    """Close a run recorded as "running" whose process is gone, so new runs can start. 409 if it is not running."""
    run = await get_ingestion_run_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    if run.status != "running":
        raise HTTPException(status_code=409, detail=f"run is '{run.status}', not running")
    task = _ACTIVE_INGESTION_TASKS.get(run_id)
    if task is not None and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    run = await abort_run(db, run_id, actor=user)
    return IngestionRunRead.model_validate(run)


IngestionSource = Literal["all", "bceao", "cb-umoa", "brvm", "umoa-titres", "amf-umoa", "ifc", "boad", "proparco", "bidc", "press"]
IngestionScope = Literal["all", "financial", "deals"]


async def _run_in_background(
    run_id: str,
    target_years: list[int] | None,
    source: str | None,
    limit: int | None,
    force: bool = False,
    scope: str = "all",
    since: date | None = None,
    until: date | None = None,
) -> None:
    service = IngestionService()
    sources_list = [source] if source and source != "all" else None
    async with AsyncSessionLocal() as session:
        await service.execute_run(
            db=session,
            trigger_type="manual",
            target_years=target_years,
            sources=sources_list,
            limit_per_source=limit,
            force=force,
            run_id=run_id,
            scope=scope,
            deal_since=since,
            deal_until=until,
        )


async def _run_tracked(
    run_id: str,
    target_years: list[int] | None,
    source: str | None,
    limit: int | None,
    force: bool = False,
    scope: str = "all",
    since: date | None = None,
    until: date | None = None,
) -> None:
    task = asyncio.current_task()
    if task is not None:
        _ACTIVE_INGESTION_TASKS[run_id] = task
    try:
        await _run_in_background(run_id, target_years, source, limit, force, scope, since, until)
    finally:
        if task is not None and _ACTIVE_INGESTION_TASKS.get(run_id) is task:
            _ACTIVE_INGESTION_TASKS.pop(run_id, None)


@router.post("/trigger", response_model=IngestionTriggerResponse, summary="Trigger manual ingestion run")
async def trigger_ingestion(
    source: IngestionSource = Query("all"),
    scope: IngestionScope = Query("all", description="all | financial (bank statements) | deals"),
    year: int | None = Query(None, ge=1900, le=2100),
    limit: int | None = Query(None, ge=1, le=100),
    since: date | None = Query(None, description="Deals: first publication / modification date"),
    until: date | None = Query(None, description="Deals: last publication / modification date"),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db_session),
    _user: str | None = Depends(write_access),
) -> IngestionTriggerResponse:
    """
    Trigger an on-demand ingestion run in the background.
    Uses the exact same unified pipeline as the scheduled 2x/day runs (bank statements + deals).
    """
    from app.services.deal_collection import DEAL_SOURCES, FINANCIAL_SOURCES

    if since and until and since > until:
        raise HTTPException(status_code=422, detail="since must not be after until")
    if source != "all":
        if scope == "financial" and source not in FINANCIAL_SOURCES:
            raise HTTPException(status_code=422, detail=f"'{source}' has no bank-statement collection")
        if scope == "deals" and source not in DEAL_SOURCES:
            raise HTTPException(status_code=422, detail=f"'{source}' has no deal collection")
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.models.ingestion_run import IngestionRun
    from app.services.ingestion import expire_stale_runs, get_target_years

    await expire_stale_runs(db)
    active = (await db.execute(
        select(IngestionRun.id).where(IngestionRun.status == "running").limit(1))).scalar_one_or_none()
    if active and not force:
        raise HTTPException(status_code=409, detail=f"an ingestion run is already in progress ({active})")

    target_years = [year] if year else get_target_years()
    years_str = ", ".join(str(y) for y in target_years)

    run = IngestionRun(
        trigger_type="manual",
        status="running",
        started_at=datetime.now(UTC),
        target_years=years_str,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    task = asyncio.create_task(
        _run_tracked(
            run.id,
            [year] if year else None,
            source,
            limit,
            force,
            scope,
            since,
            until,
        ),
        name=f"ingestion:{run.id}",
    )
    _ACTIVE_INGESTION_TASKS[run.id] = task
    task.add_done_callback(lambda finished, run_id=run.id: _forget_ingestion_task(run_id, finished))

    return IngestionTriggerResponse(
        message="Ingestion run successfully initiated",
        run_id=run.id,
        status="running",
    )

