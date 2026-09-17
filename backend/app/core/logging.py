"""
UMOA Banking Intelligence — Structured Logging

Configures structlog for structured JSON logging in production
and human-readable logging in development.
"""

import logging
import sys
from typing import Any

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """
    Configure structlog and standard library logging.

    In development: colored, human-readable output.
    In production: JSON output for log aggregation.
    """
    settings = get_settings()
    log_level = getattr(logging, settings.backend_log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Shared processors for all environments
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if settings.is_development:
        # Human-readable output for development
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # JSON output for production / log aggregation
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get a named structured logger.

    Usage:
        logger = get_logger(__name__)
        logger.info("event", key="value")
    """
    return structlog.get_logger(name)
