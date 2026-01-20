"""
Rate limiting middleware for Platform God API.

Implements IP-based rate limiting using in-memory storage with sliding window algorithm.
Configurable via PG_RATE_LIMIT environment variable.

Features:
- Automatic rate limiting on all API routes via middleware
- Per-IP address rate limiting with proxy support (X-Forwarded-For, X-Real-IP)
- Configurable rate limit via environment variable
- Exempt paths for health checks, metrics, and documentation
- Standard rate limit headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset)

Environment Variables:
    PG_RATE_LIMIT: Rate limit string (default: "10/second")
                  Format: "<number>/<period>" where period is
                  "second", "minute", "hour", or "day"

Example:
    # Set to 100 requests per minute
    export PG_RATE_LIMIT="100/minute"
"""

import asyncio
import logging
import os
import time
from collections import defaultdict
from typing import Awaitable, Callable

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Default rate limit: 10 requests per second per IP
DEFAULT_RATE_LIMIT = "10/second"
RATE_LIMIT = os.getenv("PG_RATE_LIMIT", DEFAULT_RATE_LIMIT)


def _parse_rate_limit(limit_str: str) -> tuple[int, str]:
    """
    Parse rate limit string into (count, period) tuple.

    Args:
        limit_str: Rate limit string like "10/second" or "100/minute"

    Returns:
        Tuple of (max_requests, period)
    """
    try:
        parts = limit_str.split("/")
        count = int(parts[0])
        period = parts[1].lower() if len(parts) > 1 else "second"
        return count, period
    except (ValueError, IndexError):
        logger.warning(f"Invalid rate limit format: {limit_str}, using default")
        return 10, "second"


# Convert period names to seconds
_PERIOD_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter using sliding window algorithm.

    Thread-safe implementation tracking request counts per IP address.
    Uses asyncio.Lock for concurrent access protection.
    """

    def __init__(self, max_requests: int, window_seconds: int):
        """
        Initialize the rate limiter.

        Args:
            max_requests: Maximum requests allowed per window
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str) -> tuple[bool, dict[str, str]]:
        """
        Check if a request is allowed under the rate limit.

        Uses sliding window algorithm - only counts requests within
        the current time window.

        Args:
            key: Unique identifier (typically IP address)

        Returns:
            Tuple of (is_allowed, headers_dict)
            - is_allowed: True if request should be allowed
            - headers_dict: Dictionary with rate limit headers
        """
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds

            # Get existing timestamps for this key
            timestamps = self._requests[key]

            # Remove timestamps outside the current window (sliding window)
            self._requests[key] = [ts for ts in timestamps if ts > window_start]
            current_count = len(self._requests[key])

            # Calculate remaining requests and reset time
            remaining = max(0, self.max_requests - current_count)
            reset_time = int(now + self.window_seconds)

            if current_count >= self.max_requests:
                # Rate limit exceeded
                return False, {
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(self.window_seconds),
                }

            # Add current request timestamp
            self._requests[key].append(now)

            return True, {
                "X-RateLimit-Limit": str(self.max_requests),
                "X-RateLimit-Remaining": str(remaining - 1),
                "X-RateLimit-Reset": str(reset_time),
            }

    def is_allowed_sync(self, key: str) -> tuple[bool, dict[str, str]]:
        """
        Synchronous version of is_allowed for use in sync contexts.

        Args:
            key: Unique identifier (typically IP address)

        Returns:
            Tuple of (is_allowed, headers_dict)
        """
        now = time.time()
        window_start = now - self.window_seconds

        # Get existing timestamps for this key
        timestamps = self._requests[key]

        # Remove timestamps outside the current window
        self._requests[key] = [ts for ts in timestamps if ts > window_start]
        current_count = len(self._requests[key])

        # Calculate remaining requests and reset time
        remaining = max(0, self.max_requests - current_count)
        reset_time = int(now + self.window_seconds)

        if current_count >= self.max_requests:
            # Rate limit exceeded
            return False, {
                "X-RateLimit-Limit": str(self.max_requests),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
                "Retry-After": str(self.window_seconds),
            }

        # Add current request timestamp
        self._requests[key].append(now)

        return True, {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(remaining - 1),
            "X-RateLimit-Reset": str(reset_time),
        }


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.

    Checks forwarded headers for proxied requests before falling back
    to the direct client address. This ensures correct rate limiting
    when behind a proxy or load balancer.

    Args:
        request: Incoming FastAPI request

    Returns:
        Client IP address as string
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

    # Fallback for testing/development
    return "127.0.0.1"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for applying rate limiting to all API requests.

    This middleware intercepts all requests and applies rate limiting
    based on client IP address. Requests exceeding the rate limit
    receive a 429 Too Many Requests response.

    Rate limit headers are added to all responses:
        X-RateLimit-Limit: Maximum requests per window
        X-RateLimit-Remaining: Remaining requests in current window
        X-RateLimit-Reset: Unix timestamp when window resets
        Retry-After: Seconds until client can retry (when limited)

    Environment Variables:
        PG_RATE_LIMIT: Rate limit string (default: "10/second")

    Example:
        # Apply to FastAPI app
        app.add_middleware(
            RateLimitMiddleware,
            rate_limit="100/minute",
            exempt_paths={"/health", "/metrics"}
        )
    """

    # Class-level shared limiter (shared across all instances for consistency)
    _shared_limiter: InMemoryRateLimiter | None = None
    _shared_limiter_lock = asyncio.Lock()

    def __init__(
        self,
        app: ASGIApp,
        *,
        rate_limit: str | None = None,
        exempt_paths: set[str] | None = None,
    ) -> None:
        """
        Initialize the rate limit middleware.

        Args:
            app: ASGI application
            rate_limit: Optional rate limit string override
            exempt_paths: Set of paths to exempt from rate limiting
        """
        super().__init__(app)
        self._rate_limit_str = rate_limit or RATE_LIMIT
        self._exempt_paths = exempt_paths or {
            "/health",
            "/metrics",
            "/",
            "/docs",
            "/redoc",
            "/openapi.json",
        }

        # Parse rate limit
        count, period = _parse_rate_limit(self._rate_limit_str)
        window_seconds = _PERIOD_SECONDS.get(period, 1)

        # Create or reuse shared limiter
        self._limiter = InMemoryRateLimiter(count, window_seconds)

        logger.info(
            "Rate limit middleware initialized",
            extra={
                "rate_limit": self._rate_limit_str,
                "max_requests": count,
                "window_seconds": window_seconds,
                "exempt_paths": list(self._exempt_paths),
            },
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """
        Process request with rate limiting.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response from downstream handlers or 429 if rate limited
        """
        # Skip rate limiting for exempt paths
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        # Get client IP
        client_ip = get_client_ip(request)

        # Check rate limit
        allowed, headers = await self._limiter.is_allowed(client_ip)

        if not allowed:
            from fastapi.responses import JSONResponse

            logger.debug(
                "Rate limit exceeded",
                extra={
                    "client_ip": client_ip,
                    "path": request.url.path,
                    "rate_limit": self._rate_limit_str,
                },
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "type": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded: {self._rate_limit_str}",
                        "detail": "Too many requests. Please try again later.",
                    }
                },
                headers=headers,
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response


def add_rate_limit_middleware(
    app,
    *,
    rate_limit: str | None = None,
    exempt_paths: set[str] | None = None,
) -> None:
    """
    Add rate limiting to a FastAPI application.

    Convenience function to add the RateLimitMiddleware to a FastAPI app.

    Args:
        app: FastAPI application instance
        rate_limit: Optional rate limit string (default: from env or "10/second")
        exempt_paths: Set of path patterns to exempt from rate limiting

    Example:
        add_rate_limit_middleware(
            app,
            rate_limit="100/minute",
            exempt_paths={"/health", "/metrics"}
        )
    """
    app.add_middleware(
        RateLimitMiddleware,
        rate_limit=rate_limit,
        exempt_paths=exempt_paths,
    )
    logger.info(
        "Rate limiting added to application",
        extra={
            "rate_limit": rate_limit or RATE_LIMIT,
            "exempt_paths": list(exempt_paths) if exempt_paths else [],
        },
    )


def check_rate_limit(request: Request) -> tuple[bool, dict[str, str]]:
    """
    Check if a request would be rate limited.

    Utility function for custom rate limit checking
    outside of the standard middleware flow.

    Args:
        request: FastAPI request

    Returns:
        Tuple of (is_allowed, headers_dict)
    """
    client_ip = get_client_ip(request)
    count, period = _parse_rate_limit(RATE_LIMIT)
    window_seconds = _PERIOD_SECONDS.get(period, 1)
    limiter = InMemoryRateLimiter(count, window_seconds)
    return limiter.is_allowed_sync(client_ip)


def get_rate_limit_info() -> dict[str, int | str]:
    """
    Get the current rate limit configuration.

    Returns:
        Dictionary with rate limit configuration
    """
    count, period = _parse_rate_limit(RATE_LIMIT)
    window_seconds = _PERIOD_SECONDS.get(period, 1)
    return {
        "limit": RATE_LIMIT,
        "max_requests": count,
        "period": period,
        "window_seconds": window_seconds,
    }
