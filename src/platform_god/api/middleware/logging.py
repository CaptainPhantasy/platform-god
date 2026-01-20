"""
Request logging middleware.

Logs all incoming HTTP requests with timing information.
"""

import logging
import time
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all HTTP requests with timing information.

    Logs:
    - Request method and path
    - Client IP address
    - Request ID if present
    - Response status code
    - Request processing time
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        logger_instance: logging.Logger | None = None,
        skip_paths: set[str] | None = None,
        skip_health_check: bool = True,
    ) -> None:
        """
        Initialize the logging middleware.

        Args:
            app: ASGI application
            logger_instance: Custom logger instance
            skip_paths: Paths to skip logging for
            skip_health_check: Skip logging for /health endpoint
        """
        super().__init__(app)
        self._logger = logger_instance or logger
        self._skip_paths = skip_paths or set()
        if skip_health_check:
            self._skip_paths.add("/health")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Process request and log details.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response from downstream handlers
        """
        # Skip logging for configured paths
        if request.url.path in self._skip_paths:
            return await call_next(request)

        # Start timing
        start_time = time.time()

        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = self._get_client_ip(request)
        request_id = request.headers.get("x-request-id", "unknown")

        # Log request
        self._logger.info(
            "Request started",
            extra={
                "event": "request_started",
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "request_id": request_id,
            },
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            self._logger.info(
                "Request completed",
                extra={
                    "event": "request_completed",
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )

            # Add timing header
            response.headers["X-Process-Time"] = f"{duration_ms:.2f}"
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Calculate duration for failed requests
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            self._logger.error(
                "Request failed",
                extra={
                    "event": "request_failed",
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "request_id": request_id,
                    "error": str(e),
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True,
            )
            raise

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
