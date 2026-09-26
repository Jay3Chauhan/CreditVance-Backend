"""
Centralized Application Exceptions and Custom Error Handlers.
"""

from typing import Any, Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse
from loguru import logger


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        code: str = "INTERNAL_ERROR",
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            details=details,
        )


class ConflictError(AppException):
    def __init__(self, message: str = "Resource conflict", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            code="CONFLICT",
            details=details,
        )


class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            details=details,
        )


class ForbiddenError(AppException):
    def __init__(self, message: str = "Access forbidden", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            details=details,
        )


class ValidationError(AppException):
    def __init__(self, message: str = "Validation failed", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            details=details,
        )


class ExternalServiceError(AppException):
    def __init__(self, message: str = "Upstream service error", details: Optional[Any] = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="EXTERNAL_SERVICE_ERROR",
            details=details,
        )


from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning(
        f"Handled application exception [{exc.code}] at {request.url.path}: {exc.message}"
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.message,
            "detail": exc.message,
            "data": None,
            "error": {
                "code": exc.code,
                "details": exc.details,
            },
        },
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Flattens FastAPI validation errors into a single, clean 'detail' string."""
    error_messages = []
    for err in exc.errors():
        loc = ".".join(str(l) for l in err.get("loc", []) if l != "body")
        msg = err.get("msg", "Invalid value")
        if loc:
            error_messages.append(f"{loc}: {msg}")
        else:
            error_messages.append(msg)

    detail_str = "; ".join(error_messages) if error_messages else "Request validation failed"
    logger.warning(f"Validation error at {request.url.path}: {detail_str}")

    return JSONResponse(
        status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
        content={
            "success": False,
            "message": detail_str,
            "detail": detail_str,
            "data": None,
            "error": {
                "code": "VALIDATION_ERROR",
                "details": exc.errors(),
            },
        },
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Wraps standard Starlette HTTPExceptions with standard envelope and 'detail' string."""
    detail_msg = str(exc.detail) if isinstance(exc.detail, str) else "HTTP error"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": detail_msg,
            "detail": detail_msg,
            "data": None,
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "details": exc.detail,
            },
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled system exception at {request.url.path}: {str(exc)}")
    error_msg = "An unexpected internal server error occurred."
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": error_msg,
            "detail": error_msg,
            "data": None,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "details": str(exc) if not request.app.state.settings.is_production else None,
            },
        },
    )

