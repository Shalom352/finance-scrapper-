"""
UMOA Banking Intelligence — Health Check Endpoint

Provides:
  GET /health        → Application liveness
  GET /api/v1/health → Database connectivity
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_db_session

logger = get_logger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health", summary="Application liveness check")
async def health_check() -> dict:
    """
    Returns basic application health status.
    Does not check database connectivity.
    Use GET /api/v1/health for a full check.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "app": "UMOA Banking Intelligence",
        "version": "0.1.0",
        "env": settings.app_env,
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/api/v1/health", summary="Readiness check including database (503 when unavailable)")
async def full_health_check(
    db: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Returns full application health including database connectivity.
    Suitable for readiness probes: HTTP 503 when the database is not reachable,
    never "ok" without a successful query. Connection details and driver errors
    are logged server-side (without credentials) and never returned.
    """
    settings = get_settings()
    db_status = "ok"
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
    except Exception as exc:
        db_status = "unavailable"
        logger.error("health_database_unavailable", error_type=type(exc).__name__)

    return JSONResponse(
        status_code=200 if db_status == "ok" else 503,
        content={
            "status": "ok" if db_status == "ok" else "unavailable",
            "app": "UMOA Banking Intelligence",
            "version": "0.1.0",
            "env": settings.app_env,
            "database": {"status": db_status},
            "timestamp": datetime.now(UTC).isoformat(),
        },
    )
