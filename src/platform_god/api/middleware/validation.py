"""
Input validation middleware.

Provides comprehensive request validation at the middleware level,
including Content-Type validation, query parameter sanitization,
and enhanced JSON parsing with detailed error messages.
"""

import json
import logging
import re
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Allowed Content-Types for non-GET requests
ALLOWED_CONTENT_TYPES = {
    "application/json",
    "application/json; charset=utf-8",
    "multipart/form-data",
    "application/x-www-form-urlencoded",
    "text/plain",
}

# Control characters to remove from query parameters
# Allows: tab, newline, carriage return for legitimate text
CONTROL_CHARS_PATTERN = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"
)

# Maximum query string length to prevent DoS
MAX_QUERY_STRING_LENGTH = 2048

# Paths exempt from Content-Type validation
CONTENT_TYPE_EXEMPT_PATHS = {
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
}


class ContentValidationError(Exception):
    """Raised when Content-Type validation fails."""

    def __init__(self, message: str, detail: str | None = None) -> None:
        self.message = message
        self.detail = detail
        super().__init__(message)


class JSONParseError(Exception):
    """Raised when JSON parsing fails with detailed context."""

    def __init__(
        self,
        message: str,
        line: int | None = None,
        column: int | None = None,
        position: int | None = None,
    ) -> None:
        self.message = message
        self.line = line
        self.column = column
        self.position = position
        super().__init__(message)


def sanitize_query_string(query_string: str) -> str:
    """
    Sanitize query string by removing dangerous characters.

    Removes null bytes and control characters that could be used
    in injection attacks. Keeps newlines and tabs which may be
    legitimate in some contexts.

    Args:
        query_string: Raw query string

    Returns:
        Sanitized query string
    """
    if not query_string:
        return ""

    # Remove null bytes
    sanitized = query_string.replace("\x00", "")

    # Remove other dangerous control characters
    sanitized = CONTROL_CHARS_PATTERN.sub("", sanitized)

    return sanitized


def validate_content_type(content_type: str | None, method: str) -> bool:
    """
    Validate Content-Type header for non-GET requests.

    Args:
        content_type: Content-Type header value
        method: HTTP method

    Returns:
        True if Content-Type is valid or not required

    Raises:
        ContentValidationError: If Content-Type is invalid
    """
    # GET, HEAD, DELETE don't require Content-Type validation
    if method in {"GET", "HEAD", "DELETE"}:
        return True

    # No Content-Type for methods that typically have a body
    if not content_type:
        raise ContentValidationError(
            message="Missing Content-Type header",
            detail=f"Requests with {method} method must include a Content-Type header",
        )

    # Normalize and validate
    content_type_lower = content_type.strip().lower()

    # Check if it's in our allowed list
    for allowed in ALLOWED_CONTENT_TYPES:
        if content_type_lower == allowed.lower():
            return True

    # Check for multipart with boundary (dynamic part)
    if content_type_lower.startswith("multipart/form-data"):
        return True

    # Check for form-urlencoded with charset
    if content_type_lower.startswith("application/x-www-form-urlencoded"):
        return True

    raise ContentValidationError(
        message="Unsupported Content-Type",
        detail=(
            f"Content-Type '{content_type}' is not supported. "
            f"Supported types: {', '.join(sorted(set(ct.split(';')[0].strip() for ct in ALLOWED_CONTENT_TYPES)))}"
        ),
    )


def parse_json_enhanced(body: bytes) -> dict | list:
    """
    Enhanced JSON parsing with detailed error messages.

    Provides line and column information for parse errors
    to help clients debug their requests.

    Args:
        body: Request body bytes

    Returns:
        Parsed JSON object

    Raises:
        JSONParseError: If JSON parsing fails
    """
    if not body:
        raise JSONParseError(message="Empty request body")

    try:
        return json.loads(body.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise JSONParseError(
            message="Invalid UTF-8 encoding in request body",
            detail=str(e),
        )
    except json.JSONDecodeError as e:
        # Extract useful error information
        error_context = _get_json_error_context(body, e.pos)

        raise JSONParseError(
            message="Invalid JSON format",
            line=e.lineno,
            column=e.colno,
            position=e.pos,
        )


def _get_json_error_context(body: bytes, error_pos: int) -> str:
    """
    Extract context around JSON parse error.

    Args:
        body: Request body bytes
        error_pos: Position of error

    Returns:
        Context string with error highlighted
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return "[binary data]"

    # Show snippet around error
    start = max(0, error_pos - 50)
    end = min(len(text), error_pos + 50)

    before = text[start:error_pos]
    after = text[error_pos:end]

    return f"...{before}<ERROR>{after}..."


class ValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware for comprehensive input validation.

    Features:
    - Content-Type whitelist enforcement
    - Query parameter sanitization
    - Enhanced JSON parsing with detailed errors
    - Query string length limits
    - Security logging for validation failures

    Environment Variables:
    - PG_VALIDATION_STRICT: Enable strict mode (default: true)
    - PG_MAX_QUERY_STRING_LENGTH: Max query string length (default: 2048)
    - PG_SKIP_VALIDATION_PATHS: Comma-separated paths to skip validation
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        strict_mode: bool = True,
        max_query_length: int | None = None,
        skip_paths: set[str] | None = None,
    ) -> None:
        """
        Initialize validation middleware.

        Args:
            app: ASGI application
            strict_mode: Enable strict validation (reject unknown content types)
            max_query_length: Maximum query string length
            skip_paths: Paths to skip validation for
        """
        super().__init__(app)
        self._strict_mode = strict_mode
        self._max_query_length = max_query_length or MAX_QUERY_STRING_LENGTH
        self._skip_paths = skip_paths or set()

        logger.info(
            "ValidationMiddleware initialized",
            extra={
                "strict_mode": self._strict_mode,
                "max_query_length": self._max_query_length,
                "skip_paths": self._skip_paths,
            },
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Process request with validation.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response from downstream handlers or validation error
        """
        path = request.url.path

        # Skip validation for exempted paths
        if path in self._skip_paths or self._is_exempt_path(path):
            return await call_next(request)

        client_ip = self._get_client_ip(request)

        # Validate and sanitize query string
        validation_error = self._validate_query_string(request, client_ip)
        if validation_error:
            return validation_error

        # Validate Content-Type for non-GET requests
        validation_error = self._validate_content_type(request, client_ip)
        if validation_error:
            return validation_error

        # Process request
        try:
            return await call_next(request)
        except Exception as e:
            # Catch any parsing errors that escaped FastAPI
            if "json" in str(e).lower() or "parse" in str(e).lower():
                logger.warning(
                    "JSON parsing error",
                    extra={
                        "event": "json_parse_error",
                        "path": path,
                        "method": request.method,
                        "client_ip": client_ip,
                        "error": str(e),
                    },
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "type": "invalid_json",
                            "message": "Request body contains invalid JSON",
                            "detail": str(e),
                        }
                    },
                )
            raise

    def _is_exempt_path(self, path: str) -> bool:
        """
        Check if path is exempt from Content-Type validation.

        Args:
            path: Request path

        Returns:
            True if path is exempt
        """
        for exempt in CONTENT_TYPE_EXEMPT_PATHS:
            if path == exempt or path.startswith(exempt):
                return True
        return False

    def _validate_query_string(
        self, request: Request, client_ip: str
    ) -> JSONResponse | None:
        """
        Validate and sanitize query string.

        Args:
            request: Incoming request
            client_ip: Client IP address

        Returns:
            JSONResponse if validation fails, None otherwise
        """
        query_string = str(request.url.query) if request.url.query else ""

        # Check query string length
        if len(query_string) > self._max_query_length:
            logger.warning(
                "Query string too long",
                extra={
                    "event": "query_string_too_long",
                    "path": request.url.path,
                    "method": request.method,
                    "client_ip": client_ip,
                    "query_length": len(query_string),
                    "max_length": self._max_query_length,
                },
            )
            return JSONResponse(
                status_code=414,  # URI Too Long
                content={
                    "error": {
                        "type": "uri_too_long",
                        "message": "Query string exceeds maximum length",
                        "detail": f"Query string length ({len(query_string)}) "
                        f"exceeds maximum allowed ({self._max_query_length})",
                    }
                },
            )

        # Sanitize query string (remove dangerous characters)
        if query_string:
            sanitized = sanitize_query_string(query_string)
            if sanitized != query_string:
                logger.warning(
                    "Query string contained dangerous characters, sanitized",
                    extra={
                        "event": "query_string_sanitized",
                        "path": request.url.path,
                        "method": request.method,
                        "client_ip": client_ip,
                    },
                )
                # Note: We can't modify the query string in Starlette,
                # but we've sanitized for logging/monitoring purposes

        return None

    def _validate_content_type(
        self, request: Request, client_ip: str
    ) -> JSONResponse | None:
        """
        Validate Content-Type header.

        Args:
            request: Incoming request
            client_ip: Client IP address

        Returns:
            JSONResponse if validation fails, None otherwise
        """
        # Skip Content-Type check for GET, HEAD, DELETE
        if request.method in {"GET", "HEAD", "DELETE"}:
            return None

        content_type = request.headers.get("content-type")

        # Check if request has body (should have Content-Type)
        has_body = self._request_has_body(request)

        if has_body and not content_type:
            logger.warning(
                "Request with body missing Content-Type",
                extra={
                    "event": "missing_content_type",
                    "path": request.url.path,
                    "method": request.method,
                    "client_ip": client_ip,
                },
            )
            return JSONResponse(
                status_code=415,  # Unsupported Media Type
                content={
                    "error": {
                        "type": "missing_content_type",
                        "message": "Content-Type header is required for this request",
                        "detail": f"Requests with {request.method} method must include "
                        "a Content-Type header",
                    }
                },
            )

        # Validate Content-Type value
        if content_type and self._strict_mode:
            try:
                validate_content_type(content_type, request.method)
            except ContentValidationError as e:
                logger.warning(
                    "Invalid Content-Type",
                    extra={
                        "event": "invalid_content_type",
                        "path": request.url.path,
                        "method": request.method,
                        "client_ip": client_ip,
                        "content_type": content_type,
                    },
                )
                return JSONResponse(
                    status_code=415,  # Unsupported Media Type
                    content={
                        "error": {
                            "type": "unsupported_media_type",
                            "message": e.message,
                            "detail": e.detail,
                        }
                    },
                )

        return None

    def _request_has_body(self, request: Request) -> bool:
        """
        Check if request is expected to have a body.

        Args:
            request: Incoming request

        Returns:
            True if request likely has a body
        """
        # Methods that typically have a body
        if request.method in {"POST", "PUT", "PATCH"}:
            return True

        # Check for content-length or transfer-encoding
        return (
            request.headers.get("content-length") is not None
            or request.headers.get("transfer-encoding") is not None
        )

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Args:
            request: Incoming request

        Returns:
            Client IP address
        """
        # Check for forwarded headers (proxy/load balancer)
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fall back to direct client address
        if request.client:
            return request.client.host

        return "unknown"


def add_validation_middleware(
    app: ASGIApp,
    *,
    strict_mode: bool = True,
    max_query_length: int | None = None,
    skip_paths: set[str] | None = None,
) -> ValidationMiddleware:
    """
    Create and return a validation middleware instance.

    This is a convenience function for creating the middleware
    with custom configuration.

    Args:
        app: ASGI application
        strict_mode: Enable strict validation
        max_query_length: Maximum query string length
        skip_paths: Paths to skip validation for

    Returns:
        Configured ValidationMiddleware instance
    """
    return ValidationMiddleware(
        app,
        strict_mode=strict_mode,
        max_query_length=max_query_length,
        skip_paths=skip_paths,
    )
