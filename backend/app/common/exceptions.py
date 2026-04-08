"""
Custom exception classes and FastAPI exception handlers.

All API error responses conform to the shared error model from api_contracts.md:

    {
        "request_id": "req_...",
        "error": {
            "code": "ERROR_CODE",
            "message": "Human-readable message.",
            "details": {}
        }
    }
"""

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.common.logging_config import request_id_ctx_var

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception hierarchy
# ---------------------------------------------------------------------------

class AppError(Exception):
    """
    Base class for all RetailMind application errors.
    Subclass this to create domain-specific errors.
    """

    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    """Resource not found."""
    http_status = status.HTTP_404_NOT_FOUND
    error_code = "NOT_FOUND"


class ValidationError(AppError):
    """Invalid request payload or query parameters."""
    http_status = status.HTTP_400_BAD_REQUEST
    error_code = "INVALID_REQUEST"


class UnauthorizedError(AppError):
    """Authentication required or token invalid."""
    http_status = status.HTTP_401_UNAUTHORIZED
    error_code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    """Authenticated but not permitted."""
    http_status = status.HTTP_403_FORBIDDEN
    error_code = "FORBIDDEN"


class ConflictError(AppError):
    """State conflict, e.g. duplicate resource or idempotency key conflict."""
    http_status = status.HTTP_409_CONFLICT
    error_code = "CONFLICT"


class ServiceUnavailableError(AppError):
    """Downstream dependency unavailable."""
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "SERVICE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------

def _build_error_response(
    request_id: str,
    http_status: int,
    error_code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Construct the standard error JSON response body."""
    return JSONResponse(
        status_code=http_status,
        content={
            "request_id": request_id,
            "error": {
                "code": error_code,
                "message": message,
                "details": details or {},
            },
        },
    )


# ---------------------------------------------------------------------------
# Exception handlers – register these onto the FastAPI app in main.py
# ---------------------------------------------------------------------------

async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle all AppError subclasses."""
    request_id = request_id_ctx_var.get("-")
    logger.error(
        "Application error: %s",
        exc.message,
        extra={
            "error_code": exc.error_code,
            "http_status": exc.http_status,
            "error_message": exc.message,
            "details": exc.details,
        },
    )
    return _build_error_response(
        request_id=request_id,
        http_status=exc.http_status,
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Handle Pydantic / FastAPI validation errors and return the shared error format."""
    request_id = request_id_ctx_var.get("-")
    # Flatten Pydantic error list into a readable details dict
    field_errors: dict[str, list[str]] = {}
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        field_errors.setdefault(field, []).append(error["msg"])

    logger.warning(
        "Request validation failed",
        extra={"validation_errors": field_errors},
    )
    return _build_error_response(
        request_id=request_id,
        http_status=status.HTTP_400_BAD_REQUEST,
        error_code="INVALID_REQUEST",
        message="Request validation failed.",
        details={"field_errors": field_errors},
    )


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all handler for unexpected exceptions so we never leak a stack trace."""
    request_id = request_id_ctx_var.get("-")
    logger.exception("Unhandled exception", exc_info=exc)
    return _build_error_response(
        request_id=request_id,
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code="INTERNAL_ERROR",
        message="An unexpected error occurred. Please try again later.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers onto the FastAPI application.
    Call this once in main.py during app initialisation.
    """
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
