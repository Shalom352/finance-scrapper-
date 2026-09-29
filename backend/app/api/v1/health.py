"""
UMOA Banking Intelligence — Health Check Endpoint

Provides:
  GET /health        → Application liveness
  GET /api/v1/health → Database connectivity
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session

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


@router.get("/api/v1/health", summary="Full health check including database")
async def full_health_check(
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Returns full application health including database connectivity.
    Suitable for readiness probes.
    """
    settings = get_settings()
    db_status = "unknown"
    db_error: str | None = None

    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
        db_status = "ok"
    except Exception as exc:
        db_status = "error"
        db_error = str(exc)

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "app": "UMOA Banking Intelligence",
        "version": "0.1.0",
        "env": settings.app_env,
        "database": {
            "status": db_status,
            "host": settings.postgres_host,
            "port": settings.postgres_port,
            "db": settings.postgres_db,
            **({"error": db_error} if db_error else {}),
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }
