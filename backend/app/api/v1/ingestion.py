"""
UMOA Banking Intelligence — Ingestion API Router

Endpoints:
  - GET  /api/v1/ingestion/runs: Paginated list of past ingestion runs.
  - GET  /api/v1/ingestion/runs/latest: Latest run summary & status.
  - GET  /api/v1/ingestion/runs/{run_id}: Run details by ID.
  - POST /api/v1/ingestion/trigger: Manually trigger an ingestion run.
"""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.ingestion import IngestionRunRead, IngestionTriggerResponse
from app.services.ingestion import (
    IngestionService,
    get_ingestion_run_by_id,
    get_latest_ingestion_run,
    list_ingestion_runs,
)

router = APIRouter(prefix="/api/v1/ingestion", tags=["ingestion"])


@router.get("/runs", response_model=PaginatedResponse[IngestionRunRead], summary="List ingestion runs")
async def get_runs(
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[IngestionRunRead]:
    """Retrieve paginated history of automated and manual ingestion executions."""
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
    run = await get_ingestion_run_by_id(db, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return IngestionRunRead.model_validate(run)


async def _run_in_background(
    run_id: str,
    target_years: list[int] | None,
    source: str | None,
    limit: int | None,
    force: bool = False,
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
        )


@router.post("/trigger", response_model=IngestionTriggerResponse, summary="Trigger manual ingestion run")
async def trigger_ingestion(
    background_tasks: BackgroundTasks,
    source: Literal["all", "bceao", "cb-umoa"] = Query("all"),
    year: int | None = Query(None, ge=1900, le=2100),
    limit: int | None = Query(None, ge=1, le=100),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db_session),
) -> IngestionTriggerResponse:
    """
    Trigger an on-demand ingestion run in the background.
    Uses the exact same unified pipeline as the scheduled 2x/day runs.
    """
    from datetime import UTC, datetime

    from app.models.ingestion_run import IngestionRun
    from app.services.ingestion import get_target_years

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

    background_tasks.add_task(
        _run_in_background,
        run.id,
        [year] if year else None,
        source,
        limit,
        force,
    )

    return IngestionTriggerResponse(
        message="Ingestion run successfully initiated",
        run_id=run.id,
        status="running",
    )

