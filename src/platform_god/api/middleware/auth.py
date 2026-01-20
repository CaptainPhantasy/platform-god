"""
Authentication middleware.

Handles authentication and authorization for API requests.
Supports JWT tokens via Authorization header and API keys via x-api-key header.
"""

import logging
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from platform_god.api.auth import (
    TokenError,
    ExpiredTokenError,
    InvalidTokenError,
    validate_token,
    extract_token_from_header,
    hash_api_key,
)
from platform_god.api.schemas.exceptions import APIException

logger = logging.getLogger(__name__)


class AuthRequiredError(APIException):
    """Exception raised when authentication is required but missing."""

    status_code = 401
    error_type = "authentication_required"
    message = "Authentication required"


class InvalidCredentialsError(APIException):
    """Exception raised when provided credentials are invalid."""

    status_code = 401
    error_type = "invalid_credentials"
    message = "Invalid authentication credentials"


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware for request authentication.

    Supports multiple authentication methods:
    - JWT Bearer tokens via Authorization header
    - API keys via x-api-key header
    - Direct user ID via x-user-id header (for backwards compatibility)

    JWT tokens are validated using the PG_JWT_SECRET environment variable.
    API keys are validated against configured valid keys via PG_API_KEYS env var.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        require_auth: bool = True,
        user_id_header: str = "x-user-id",
        api_key_header: str = "x-api-key",
        public_paths: set[str] | None = None,
        valid_api_keys: set[str] | None = None,
        enable_jwt: bool = True,
    ) -> None:
        """
        Initialize authentication middleware.

        Args:
            app: ASGI application
            require_auth: Whether to require authentication for all requests
            user_id_header: Header containing user ID (fallback auth method)
            api_key_header: Header containing API key
            public_paths: Set of path prefixes that bypass auth (e.g., {"/health", "/metrics"})
            valid_api_keys: Set of valid API key hashes (reads from PG_API_KEYS env if None)
            enable_jwt: Whether to enable JWT authentication
        """
        super().__init__(app)
        self._require_auth = require_auth
        self._user_id_header = user_id_header.lower()
        self._api_key_header = api_key_header.lower()
        self._public_paths = public_paths or set()
        self._enable_jwt = enable_jwt

        # Initialize API keys from environment or provided set
        self._valid_api_keys = valid_api_keys
        if self._valid_api_keys is None:
            self._valid_api_keys = self._load_api_keys_from_env()

    def _load_api_keys_from_env(self) -> set[str]:
        """Load valid API keys from PG_API_KEYS environment variable."""
        import os

        api_keys_env = os.getenv("PG_API_KEYS", "")
        if not api_keys_env:
            return set()

        # API keys should be comma-separated pre-hashed values
        keys = {k.strip() for k in api_keys_env.split(",") if k.strip()}
        if keys:
            logger.info(f"Loaded {len(keys)} valid API keys from environment")
        return keys

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """
        Process request and authenticate.

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response from downstream handlers

        Raises:
            AuthRequiredError: If auth is required but missing
            InvalidCredentialsError: If provided credentials are invalid
        """
        # Check if path is public (bypasses auth)
        is_public = self._is_public_path(request.url.path)

        # Extract user ID and auth method from headers
        user_id, auth_method = self._authenticate(request)

        # Store in request state for downstream use
        request.state.user_id = user_id
        request.state.auth_method = auth_method

        # Check if auth is required (skip for public paths)
        if self._require_auth and not is_public and not user_id:
            raise AuthRequiredError(
                message="Authentication required",
                detail="Provide a valid JWT token (Authorization: Bearer <token>), API key (x-api-key), or user ID (x-user-id)",
            )

        # Log authenticated requests
        if user_id:
            logger.debug(f"Authenticated request from user: {user_id} ({auth_method}) on {request.url.path}")

        return await call_next(request)

    def _is_public_path(self, path: str) -> bool:
        """
        Check if a path should bypass authentication.

        Args:
            path: Request path

        Returns:
            True if path is public (bypasses auth)
        """
        for public_prefix in self._public_paths:
            if path.startswith(public_prefix):
                return True
        return False

    def _authenticate(self, request: Request) -> tuple[str | None, str | None]:
        """
        Authenticate request using multiple methods.

        Args:
            request: Incoming request

        Returns:
            Tuple of (user_id, auth_method) where auth_method indicates
            how authentication was performed ("jwt", "api_key", "user_id_header", or None)
        """
        # Try JWT Bearer token first (most secure)
        if self._enable_jwt:
            user_id = self._try_jwt_auth(request)
            if user_id:
                return user_id, "jwt"

        # Try API key validation
        user_id = self._try_api_key_auth(request)
        if user_id:
            return user_id, "api_key"

        # Fall back to user ID header (for backwards compatibility)
        user_id = self._try_user_id_header(request)
        if user_id:
            return user_id, "user_id_header"

        return None, None

    def _try_jwt_auth(self, request: Request) -> str | None:
        """
        Attempt JWT authentication via Authorization header.

        Args:
            request: Incoming request

        Returns:
            User ID from token or None
        """
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return None

        token = extract_token_from_header(auth_header)
        if not token:
            return None

        try:
            is_valid, payload, error = validate_token(token)
            if is_valid and payload:
                return payload.sub
            elif error:
                logger.debug(f"JWT validation failed: {error}")
        except (TokenError, InvalidTokenError, ExpiredTokenError) as e:
            logger.debug(f"JWT authentication failed: {e}")

        return None

    def _try_api_key_auth(self, request: Request) -> str | None:
        """
        Attempt API key authentication via x-api-key header.

        Args:
            request: Incoming request

        Returns:
            User ID or None
        """
        api_key = request.headers.get(self._api_key_header)
        if not api_key:
            return None

        if not self._valid_api_keys:
            # If no keys configured, accept any API key but log a warning
            # This allows development without pre-configured keys
            logger.warning("API key authentication attempted but no valid keys configured (PG_API_KEYS not set)")
            return f"api_key_user:{api_key[:8]}"

        # Hash the provided key and check against valid hashes
        key_hash = hash_api_key(api_key)
        if key_hash in self._valid_api_keys:
            return f"api_key:{key_hash[:8]}"

        logger.debug(f"Invalid API key provided (hash: {key_hash})")
        return None

    def _try_user_id_header(self, request: Request) -> str | None:
        """
        Extract user ID from x-user-id header (fallback method).

        Args:
            request: Incoming request

        Returns:
            User ID or None
        """
        user_id = request.headers.get(self._user_id_header)
        if user_id:
            logger.debug("Using x-user-id header for authentication (less secure, consider using JWT)")
        return user_id


async def get_optional_user_id(request: Request) -> str | None:
    """
    Get user ID from request state if present.

    Use this in route handlers to access the authenticated user ID.

    Args:
        request: Current request

    Returns:
        User ID or None
    """
    return getattr(request.state, "user_id", None)


async def require_user_id(request: Request) -> str:
    """
    Get user ID from request state, raising error if missing.

    Use this in route handlers that require authentication.

    Args:
        request: Current request

    Returns:
        User ID

    Raises:
        AuthRequiredError: If no user ID in request state
    """
    user_id = await get_optional_user_id(request)
    if not user_id:
        raise AuthRequiredError(
            message="Authentication required for this endpoint",
        )
    return user_id
