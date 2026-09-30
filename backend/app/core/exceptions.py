"""UMOA Banking Intelligence — Exception Handlers

Global exception handlers for structured JSON error responses.
"""
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    # Starlette's HTTPException is the base class: this also covers FastAPI's HTTPException and
    # the router-level 404 (unknown path) / 405 (method not allowed), all in the same envelope.
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": _status_to_code(exc.status_code), "message": exc.detail, "details": {}}},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        encoded_errors = jsonable_encoder(exc.errors())
        # Path only: never the query string.
        logger.warning("validation_error", error_count=len(encoded_errors), path=request.url.path)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": encoded_errors},
                }
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback server-side only; the client never receives a stack trace.
        logger.error("unhandled_exception", exc_info=exc, path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "details": {}}},
        )


def _status_to_code(status: int) -> str:
    codes = {
        400: "BAD_REQUEST",
        404: "RESOURCE_NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        422: "VALIDATION_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    return codes.get(status, f"HTTP_{status}")
