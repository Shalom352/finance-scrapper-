"""
UMOA Banking Intelligence — FastAPI Application Entry Point

This is the main application factory. It:
- Configures structured logging
- Creates the FastAPI application instance
- Registers routers
- Adds middleware (CORS)
- Handles application lifecycle (startup/shutdown)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

# Initialize logging before anything else
configure_logging()
logger = get_logger(__name__)


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
    yield
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
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

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
    from app.api.v1.countries import router as countries_router
    from app.api.v1.documents import router as documents_router
    from app.api.v1.financial_data import router as financial_data_router
    from app.api.v1.institutions import router as institutions_router
    from app.api.v1.metrics import router as metrics_router
    from app.api.v1.rankings import router as rankings_router
    from app.api.v1.search import router as search_router
    from app.api.v1.sources import router as sources_router

    app.include_router(countries_router)
    app.include_router(sources_router)
    app.include_router(banking_groups_router)
    app.include_router(institutions_router)
    app.include_router(metrics_router)
    app.include_router(documents_router)
    app.include_router(financial_data_router)
    app.include_router(rankings_router)
    app.include_router(search_router)
    app.include_router(analytics_router)

    from app.core.exceptions import register_exception_handlers
    register_exception_handlers(app)

    return app


# Application instance — used by uvicorn
app = create_app()
