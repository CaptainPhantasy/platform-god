"""
CORS (Cross-Origin Resource Sharing) middleware configuration.

Configures CORS headers for the FastAPI application to allow
cross-origin requests from web browsers.
"""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Default CORS origins - configure via environment for production
DEFAULT_ALLOW_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

DEFAULT_ALLOW_METHODS: list[str] = [
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "OPTIONS",
]

DEFAULT_ALLOW_HEADERS: list[str] = [
    "accept",
    "accept-language",
    "content-language",
    "content-type",
    "authorization",
    "x-request-id",
    "x-client-version",
]


def add_cors_middleware(
    app: FastAPI,
    *,
    allow_origins: list[str] | Literal["*"] | None = None,
    allow_credentials: bool = False,
    allow_methods: list[str] | None = None,
    allow_headers: list[str] | None = None,
    expose_headers: list[str] | None = None,
    max_age: int = 600,
) -> None:
    """
    Add CORS middleware to the FastAPI application.

    Args:
        app: FastAPI application instance
        allow_origins: List of allowed origins or "*" for all
        allow_credentials: Allow credentials in requests
        allow_methods: List of allowed HTTP methods
        allow_headers: List of allowed headers
        expose_headers: Headers to expose to browsers
        max_age: Cache time for preflight requests (seconds)
    """
    if allow_origins is None:
        allow_origins = DEFAULT_ALLOW_ORIGINS
    if allow_methods is None:
        allow_methods = DEFAULT_ALLOW_METHODS
    if allow_headers is None:
        allow_headers = DEFAULT_ALLOW_HEADERS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=allow_credentials,
        allow_methods=allow_methods,
        allow_headers=allow_headers,
        expose_headers=expose_headers or [],
        max_age=max_age,
    )


async def cors_preflight_handler(request: Request) -> dict[str, str]:
    """
    Handle CORS preflight OPTIONS requests.

    This is an alternative to using CORSMiddleware for more control.
    Most use cases should use add_cors_middleware() instead.
    """
    origin = request.headers.get("origin", "*")
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Access-Control-Max-Age": "600",
    }
