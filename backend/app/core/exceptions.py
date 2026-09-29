"""UMOA Banking Intelligence — Exception Handlers

Global exception handlers for structured JSON error responses.
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": _status_to_code(exc.status_code), "message": exc.detail, "details": {}}},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        encoded_errors = jsonable_encoder(exc.errors())
        logger.warning("validation_error", errors=encoded_errors, path=str(request.url))
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
        logger.error("unhandled_exception", exc_info=exc, path=str(request.url))
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "details": {}}},
        )


def _status_to_code(status: int) -> str:
    codes = {400: "BAD_REQUEST", 404: "RESOURCE_NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR"}
    return codes.get(status, f"HTTP_{status}")
