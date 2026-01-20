"""
Request/Response size limit middleware.

Protects against DoS attacks by limiting request body size and
monitoring response sizes for potential issues.
"""

import logging
import os
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Default maximum request size in bytes (10 MB)
DEFAULT_MAX_REQUEST_SIZE = 10 * 1024 * 1024

# Default maximum response size warning threshold in bytes (50 MB)
DEFAULT_MAX_RESPONSE_SIZE = 50 * 1024 * 1024


def get_max_request_size() -> int:
    """
    Get maximum request size from environment variable.

    Reads the PG_MAX_REQUEST_SIZE environment variable.
    Accepts values in bytes or with suffixes (K, M, G).

    Returns:
        Maximum request size in bytes
    """
    env_value = os.getenv("PG_MAX_REQUEST_SIZE", "")
    if not env_value:
        return DEFAULT_MAX_REQUEST_SIZE

    try:
        # Parse size with optional suffix
        env_value = env_value.strip().upper()
        multipliers = {
            "K": 1024,
            "M": 1024 * 1024,
            "G": 1024 * 1024 * 1024,
        }

        for suffix, multiplier in multipliers.items():
            if env_value.endswith(suffix):
                return int(env_value[:-1]) * multiplier

        # Plain number in bytes
        return int(env_value)
    except (ValueError, AttributeError) as e:
        logger.warning(
            f"Invalid PG_MAX_REQUEST_SIZE value: {env_value}, using default",
            extra={"error": str(e)},
        )
        return DEFAULT_MAX_REQUEST_SIZE


def get_max_response_size() -> int:
    """
    Get maximum response size warning threshold from environment variable.

    Reads the PG_MAX_RESPONSE_SIZE environment variable.
    Accepts values in bytes or with suffixes (K, M, G).

    Returns:
        Maximum response size in bytes for warning threshold
    """
    env_value = os.getenv("PG_MAX_RESPONSE_SIZE", "")
    if not env_value:
        return DEFAULT_MAX_RESPONSE_SIZE

    try:
        # Parse size with optional suffix
        env_value = env_value.strip().upper()
        multipliers = {
            "K": 1024,
            "M": 1024 * 1024,
            "G": 1024 * 1024 * 1024,
        }

        for suffix, multiplier in multipliers.items():
            if env_value.endswith(suffix):
                return int(env_value[:-1]) * multiplier

        # Plain number in bytes
        return int(env_value)
    except (ValueError, AttributeError) as e:
        logger.warning(
            f"Invalid PG_MAX_RESPONSE_SIZE value: {env_value}, using default",
            extra={"error": str(e)},
        )
        return DEFAULT_MAX_RESPONSE_SIZE


def format_size(size_bytes: int) -> str:
    """
    Format byte size as human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string (e.g., "10 MB")
    """
    for unit, divisor in [("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)]:
        if size_bytes >= divisor:
            return f"{size_bytes / divisor:.1f} {unit}"
    return f"{size_bytes} bytes"


class SizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce request size limits and monitor response sizes.

    Features:
    - Rejects requests exceeding max size with 413 status
    - Logs oversized requests for security monitoring
    - Warns on large responses
    - Configurable via environment variables

    Environment Variables:
    - PG_MAX_REQUEST_SIZE: Maximum request size (default: 10M)
    - PG_MAX_RESPONSE_SIZE: Response size warning threshold (default: 50M)
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_request_size: int | None = None,
        max_response_size: int | None = None,
        skip_paths: set[str] | None = None,
    ) -> None:
        """
        Initialize the size limit middleware.

        Args:
            app: ASGI application
            max_request_size: Maximum request size in bytes (default: from env or 10MB)
            max_response_size: Response size warning threshold in bytes
            skip_paths: Paths to skip size checking for
        """
        super().__init__(app)
        self._max_request_size = max_request_size or get_max_request_size()
        self._max_response_size = max_response_size or get_max_response_size()
        self._skip_paths = skip_paths or {
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

        logger.info(
            "SizeLimitMiddleware initialized",
            extra={
                "max_request_size": self._max_request_size,
                "max_request_size_formatted": format_size(self._max_request_size),
                "max_response_size": self._max_response_size,
                "max_response_size_formatted": format_size(self._max_response_size),
            },
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Process request and enforce size limits.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response from downstream handlers or 413 error
        """
        path = request.url.path

        # Skip size checking for configured paths
        if path in self._skip_paths:
            return await call_next(request)

        # Check request size before processing
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                request_size = int(content_length)
                if request_size > self._max_request_size:
                    # Log oversized request for security monitoring
                    client_ip = self._get_client_ip(request)
                    logger.warning(
                        "Request size limit exceeded",
                        extra={
                            "event": "request_size_exceeded",
                            "path": path,
                            "method": request.method,
                            "client_ip": client_ip,
                            "content_length": request_size,
                            "content_length_formatted": format_size(request_size),
                            "max_size": self._max_request_size,
                            "max_size_formatted": format_size(self._max_request_size),
                        },
                    )

                    return JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "type": "payload_too_large",
                                "message": "Request body exceeds maximum allowed size",
                                "detail": (
                                    f"Request size ({format_size(request_size)}) "
                                    f"exceeds maximum allowed ({format_size(self._max_request_size)})"
                                ),
                            }
                        },
                    )
            except ValueError:
                # Invalid content-length header, let the request proceed
                # and let FastAPI handle it
                pass

        # Process request
        response = await call_next(request)

        # Check response size for warning
        response_size = self._get_response_size(response)
        if response_size and response_size > self._max_response_size:
            logger.warning(
                "Large response detected",
                extra={
                    "event": "large_response",
                    "path": path,
                    "method": request.method,
                    "response_size": response_size,
                    "response_size_formatted": format_size(response_size),
                    "threshold": self._max_response_size,
                    "threshold_formatted": format_size(self._max_response_size),
                },
            )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.

        Checks forwarded headers for proxied requests.

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

    def _get_response_size(self, response: Response) -> int | None:
        """
        Get response size from response headers.

        Args:
            response: HTTP response

        Returns:
            Response size in bytes or None if not available
        """
        content_length = response.headers.get("content-length")
        if content_length:
            try:
                return int(content_length)
            except ValueError:
                pass
        return None


def add_size_limit_middleware(
    app: ASGIApp,
    *,
    max_request_size: int | None = None,
    max_response_size: int | None = None,
    skip_paths: set[str] | None = None,
) -> SizeLimitMiddleware:
    """
    Create and return a size limit middleware instance.

    This is a convenience function for creating the middleware
    with custom configuration.

    Args:
        app: ASGI application
        max_request_size: Maximum request size in bytes
        max_response_size: Response size warning threshold in bytes
        skip_paths: Paths to skip size checking for

    Returns:
        Configured SizeLimitMiddleware instance
    """
    return SizeLimitMiddleware(
        app,
        max_request_size=max_request_size,
        max_response_size=max_response_size,
        skip_paths=skip_paths,
    )
