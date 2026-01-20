"""
FastAPI Application Setup.

Main application factory for Platform God REST API.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from platform_god.api.auth import create_access_token, hash_api_key
from platform_god.api.middleware.auth import AuthMiddleware
from platform_god.api.middleware.cors import add_cors_middleware
from platform_god.api.middleware.logging import RequestLoggingMiddleware
from platform_god.api.middleware.rate_limit import add_rate_limit_middleware
from platform_god.api.middleware.size_limit import SizeLimitMiddleware
from platform_god.api.middleware.validation import ValidationMiddleware
from platform_god.api.routes import (
    agents,
    auth,
    chains,
    health,
    metrics,
    registry,
    runs,
)
from platform_god.api.schemas.exceptions import APIException, ValidationError
from platform_god.version import __version__

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifespan context manager for startup and shutdown events.

    Initializes registry connections and state managers on startup.
    Performs graceful cleanup on shutdown.
    """
    # Startup
    logger.info("Platform God API starting up...")
    logger.info(f"Version: {__version__}")

    # Ensure var directories exist
    var_dirs = ["var/registry", "var/state", "var/audit", "var/cache"]
    for dir_path in var_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        logger.debug(f"Ensured directory exists: {dir_path}")

    # Initialize registry (lazy loading in actual usage)
    logger.info("Registry storage initialized")

    # Initialize state manager (lazy loading in actual usage)
    logger.info("State manager initialized")

    yield

    # Shutdown
    logger.info("Platform God API shutting down...")


def create_app(title: str = "Platform God API") -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        title: Application title for OpenAPI docs

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title=title,
        description="REST API for agent-driven repository governance",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Add custom middleware
    app.add_middleware(RequestLoggingMiddleware)
    add_cors_middleware(app)

    # Add rate limiting middleware
    # Configure via PG_RATE_LIMIT environment variable (default: "10/second")
    rate_limit = os.getenv("PG_RATE_LIMIT", "10/second")
    exempt_paths = {"/health", "/metrics", "/", "/docs", "/redoc", "/openapi.json"}
    add_rate_limit_middleware(app, rate_limit=rate_limit, exempt_paths=exempt_paths)

    # Add authentication middleware (enabled by default)
    # Configure via PG_REQUIRE_AUTH environment variable (default: true)
    require_auth = os.getenv("PG_REQUIRE_AUTH", "true").lower() == "true"
    public_paths = {"/health", "/metrics", "/docs", "/redoc", "/openapi.json"}
    if require_auth:
        app.add_middleware(AuthMiddleware, require_auth=True, public_paths=public_paths)
        logger.info("Authentication middleware enabled (PG_REQUIRE_AUTH=true)")
    else:
        # Still add middleware for optional user ID extraction, but don't require auth
        app.add_middleware(AuthMiddleware, require_auth=False, public_paths=public_paths)
        logger.warning("Authentication DISABLED (PG_REQUIRE_AUTH=false)")

    # Add size limit middleware to prevent DoS attacks
    # Configure via PG_MAX_REQUEST_SIZE and PG_MAX_RESPONSE_SIZE environment variables
    max_request_size = os.getenv("PG_MAX_REQUEST_SIZE")
    if max_request_size:
        logger.info(f"Size limit middleware configured with max request size: {max_request_size}")
    app.add_middleware(SizeLimitMiddleware)

    # Add input validation middleware
    # Configure via PG_VALIDATION_STRICT and PG_MAX_QUERY_STRING_LENGTH environment variables
    validation_strict = os.getenv("PG_VALIDATION_STRICT", "true").lower() == "true"
    max_query_length = os.getenv("PG_MAX_QUERY_STRING_LENGTH")
    if max_query_length:
        try:
            max_query_length_int = int(max_query_length)
        except ValueError:
            logger.warning(f"Invalid PG_MAX_QUERY_STRING_LENGTH: {max_query_length}, using default")
            max_query_length_int = None
    else:
        max_query_length_int = None

    skip_validation_paths = {"/health", "/metrics", "/", "/docs", "/redoc", "/openapi.json"}
    app.add_middleware(
        ValidationMiddleware,
        strict_mode=validation_strict,
        max_query_length=max_query_length_int,
        skip_paths=skip_validation_paths,
    )
    logger.info(f"Input validation middleware enabled (strict={validation_strict})")

    # Include routers
    app.include_router(
        health.router,
        prefix="/health",
        tags=["Health"],
    )
    app.include_router(
        agents.router,
        prefix="/api/v1/agents",
        tags=["Agents"],
    )
    app.include_router(
        chains.router,
        prefix="/api/v1/chains",
        tags=["Chains"],
    )
    app.include_router(
        runs.router,
        prefix="/api/v1/runs",
        tags=["Runs"],
    )
    app.include_router(
        registry.router,
        prefix="/api/v1/registry",
        tags=["Registry"],
    )
    app.include_router(
        metrics.router,
        prefix="/metrics",
        tags=["Metrics"],
    )

    # Auth router (must come after middleware so auth state is available)
    app.include_router(
        auth.router,
        prefix="/api/v1/auth",
        tags=["Authentication"],
    )

    # Exception handlers
    @app.exception_handler(APIException)
    async def api_exception_handler(request, exc: APIException) -> JSONResponse:
        """Handle API exceptions with proper error responses."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": exc.error_type,
                    "message": exc.message,
                    "detail": exc.detail,
                }
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_exception_handler(request, exc: ValidationError) -> JSONResponse:
        """Handle validation errors with detailed field information."""
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "type": "validation_error",
                    "message": "Request validation failed",
                    "fields": exc.fields,
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        logger.exception(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": "An unexpected error occurred",
                    "detail": str(exc) if logger.isEnabledFor(logging.DEBUG) else None,
                }
            },
        )

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root() -> dict[str, object]:
        """Root endpoint with API information."""
        return {
            "name": "Platform God API",
            "version": __version__,
            "status": "operational",
            "docs": "/docs",
            "health": "/health",
            "metrics": "/metrics",
        }

    return app


# Create default app instance for direct imports
app = create_app()
