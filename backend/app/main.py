"""
UMOA Banking Intelligence — FastAPI Application Entry Point

This is the main application factory. It:
- Configures structured logging
- Creates the FastAPI application instance
- Registers routers
- Adds middleware (CORS, security headers, access log)
- Handles application lifecycle (startup/shutdown)
"""

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

# Initialize logging before anything else
configure_logging()
logger = get_logger(__name__)
access_logger = get_logger("app.access")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown logic."""
    settings = get_settings()
    logger.info(
        "application_starting",
        app="UMOA Banking Intelligence",
        version="0.1.0",
        env=settings.app_env,
        host=settings.backend_host,
        port=settings.backend_port,
    )

    # Start background ingestion scheduler if enabled
    from app.services.scheduler import get_ingestion_scheduler
    scheduler = get_ingestion_scheduler()
    scheduler.start()

    # Start the recurring discovery engine if enabled (DISCOVERY_ENABLED, off by default)
    from app.services.discovery_scheduler import get_discovery_scheduler
    discovery_scheduler = get_discovery_scheduler()
    discovery_scheduler.start()

    yield

    discovery_scheduler.stop()
    scheduler.stop()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns a fully configured application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="UMOA Banking Intelligence API",
        description=(
            "Plateforme de données financières pour les banques et établissements "
            "financiers de l'Union Monétaire Ouest-Africaine (UMOA).\n\n"
            "Financial data platform for banks and financial institutions "
            "of the West African Monetary Union (UMOA)."
        ),
        version="0.1.0",
        # Interactive API docs are not exposed in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Security headers + minimal access log (route, status, duration).
    # Never logged: bodies, headers, query strings, credentials.
    # ------------------------------------------------------------------
    @app.middleware("http")
    async def security_headers_and_access_log(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path not in ("/health", "/api/v1/health"):
            access_logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
        return response

    # ------------------------------------------------------------------
    # CORS — allow configured origins
    # ------------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------
    # Routers
    # ------------------------------------------------------------------
    app.include_router(health_router)

    from app.api.v1.analytics import router as analytics_router
    from app.api.v1.banking_groups import router as banking_groups_router
    from app.api.v1.comparisons import router as comparisons_router
    from app.api.v1.countries import router as countries_router
    from app.api.v1.data_quality import router as data_quality_router
    from app.api.v1.deals import router as deals_router
    from app.api.v1.documents import router as documents_router
    from app.api.v1.financial_data import router as financial_data_router
    from app.api.v1.ingestion import router as ingestion_router
    from app.api.v1.institutions import router as institutions_router
    from app.api.v1.metrics import router as metrics_router
    from app.api.v1.rankings import router as rankings_router
    from app.api.v1.search import router as search_router
    from app.api.v1.sources import router as sources_router
    from app.api.v1.targeting import router as targeting_router

    app.include_router(countries_router)
    app.include_router(sources_router)
    app.include_router(banking_groups_router)
    app.include_router(institutions_router)
    app.include_router(metrics_router)
    app.include_router(documents_router)
    app.include_router(financial_data_router)
    app.include_router(rankings_router)
    app.include_router(comparisons_router)
    app.include_router(search_router)
    app.include_router(analytics_router)
    app.include_router(data_quality_router)
    app.include_router(deals_router)
    app.include_router(ingestion_router)
    app.include_router(targeting_router)

    from app.core.exceptions import register_exception_handlers
    register_exception_handlers(app)

    return app


# Application instance — used by uvicorn
app = create_app()
