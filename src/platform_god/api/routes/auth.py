"""
Authentication routes for Platform God API.

Provides endpoints for token generation and validation.
"""

import logging
import os
from datetime import timedelta

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field, field_validator

from platform_god.api.auth import (
    TokenError,
    TokenPayload,
    ExpiredTokenError,
    InvalidTokenError,
    create_access_token,
    decode_token,
    validate_token,
    hash_api_key,
)
from platform_god.api.middleware.auth import require_user_id, get_optional_user_id
from platform_god.api.schemas.exceptions import APIException

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Schemas
# ============================================================================


class TokenRequest(BaseModel):
    """Request body for token generation."""

    user_id: str = Field(
        ...,
        description="User ID or identifier to include in the token",
        min_length=1,
        max_length=256,
    )
    expiration_hours: float | None = Field(
        default=24.0,
        description="Token expiration time in hours (default: 24, max: 168)",
        ge=0.1,
        le=168,
    )
    scope: str | None = Field(
        default=None,
        description="Optional scope/permissions for the token",
        max_length=256,
    )

    @field_validator("expiration_hours")
    @classmethod
    def validate_expiration(cls, v: float | None) -> float | None:
        """Ensure expiration is within bounds."""
        if v is not None and v > 168:  # 1 week max
            v = 168.0
        return v


class TokenResponse(BaseModel):
    """Response containing generated token."""

    access_token: str = Field(description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type (always Bearer)")
    expires_in: int = Field(description="Token expiration time in seconds")
    user_id: str = Field(description="User ID from the token subject")


class TokenValidateRequest(BaseModel):
    """Request body for token validation."""

    token: str = Field(..., description="JWT token to validate", min_length=1)


class TokenValidateResponse(BaseModel):
    """Response from token validation."""

    valid: bool = Field(description="Whether the token is valid")
    user_id: str | None = Field(default=None, description="User ID if token is valid")
    expires_at: int | None = Field(default=None, description="Expiration timestamp if valid")
    error: str | None = Field(default=None, description="Error message if invalid")


class ApiKeyHashRequest(BaseModel):
    """Request body for API key hashing."""

    api_key: str = Field(..., description="API key to hash", min_length=1)


class ApiKeyHashResponse(BaseModel):
    """Response containing API key hash."""

    hash: str = Field(description="SHA-256 HMAC hash of the API key")


class ApiKeyValidateRequest(BaseModel):
    """Request body for API key validation."""

    api_key: str = Field(..., description="API key to validate", min_length=1)
    stored_hash: str = Field(..., description="Stored hash to validate against", min_length=1)


class ApiKeyValidateResponse(BaseModel):
    """Response from API key validation."""

    valid: bool = Field(description="Whether the API key is valid")


# ============================================================================
# Exceptions
# ============================================================================


class UnauthorizedError(APIException):
    """Exception raised for unauthorized access."""

    status_code = 403
    error_type = "unauthorized"
    message = "Unauthorized"


class TokenGenerationError(APIException):
    """Exception raised when token generation fails."""

    status_code = 500
    error_type = "token_generation_error"
    message = "Failed to generate access token"


# ============================================================================
# Routes
# ============================================================================


@router.post("/token", response_model=TokenResponse, status_code=201)
async def generate_token(
    request: TokenRequest,
    http_request: Request,
) -> TokenResponse:
    """
    Generate a JWT access token.

    This endpoint creates a signed JWT token for the specified user.
    The token can be used for authentication via the Authorization header.

    **Note:** This endpoint is for administrative/token generation purposes.
    In production, consider restricting access to this endpoint.

    Args:
        request: Token generation request
        http_request: FastAPI Request object

    Returns:
        Generated token information

    Raises:
        TokenGenerationError: If token generation fails
    """
    try:
        # Convert expiration hours to seconds
        expiration_seconds = int(timedelta(hours=request.expiration_hours).total_seconds())

        # Generate the token
        token = create_access_token(
            subject=request.user_id,
            expiration_seconds=expiration_seconds,
            scope=request.scope,
        )

        # Log token generation (but don't log the actual token)
        user_id = await get_optional_user_id(http_request)
        logger.info(f"Token generated for user_id={request.user_id} by operator={user_id}")

        return TokenResponse(
            access_token=token,
            token_type="Bearer",
            expires_in=expiration_seconds,
            user_id=request.user_id,
        )

    except Exception as e:
        logger.error(f"Failed to generate token: {e}")
        raise TokenGenerationError(detail=str(e))


@router.post("/token/validate", response_model=TokenValidateResponse)
async def validate_token_endpoint(request: TokenValidateRequest) -> TokenValidateResponse:
    """
    Validate a JWT token.

    This endpoint checks if a token is valid and returns its payload information.

    Args:
        request: Token validation request

    Returns:
        Token validation result
    """
    try:
        is_valid, payload, error = validate_token(request.token)

        if is_valid and payload:
            return TokenValidateResponse(
                valid=True,
                user_id=payload.sub,
                expires_at=payload.exp,
                error=None,
            )
        else:
            return TokenValidateResponse(
                valid=False,
                user_id=None,
                expires_at=None,
                error=error,
            )

    except Exception as e:
        return TokenValidateResponse(
            valid=False,
            user_id=None,
            expires_at=None,
            error=str(e),
        )


@router.get("/token/decode")
async def decode_token_endpoint(
    authorization: str = Header(..., description="Authorization header with Bearer token"),
) -> dict:
    """
    Decode and return the current JWT token payload.

    This endpoint extracts and returns the JWT payload from the Authorization header.

    Args:
        authorization: Authorization header value

    Returns:
        Decoded token payload

    Raises:
        InvalidTokenError: If token is invalid
        ExpiredTokenError: If token has expired
    """
    from platform_god.api.auth import extract_token_from_header

    token = extract_token_from_header(authorization)
    if not token:
        raise InvalidTokenError("Invalid Authorization header format")

    payload = decode_token(token)
    return payload.to_dict()


@router.post("/api-key/hash", response_model=ApiKeyHashResponse)
async def hash_api_key_endpoint(request: ApiKeyHashRequest) -> ApiKeyHashResponse:
    """
    Hash an API key for secure storage.

    This endpoint generates a SHA-256 HMAC hash of an API key.
    Use this to generate hashes for the PG_API_KEYS environment variable.

    **Security Note:** Never store raw API keys. Always store and use hashes.

    Args:
        request: API key to hash

    Returns:
        The API key hash
    """
    key_hash = hash_api_key(request.api_key)
    return ApiKeyHashResponse(hash=key_hash)


@router.post("/api-key/validate", response_model=ApiKeyValidateResponse)
async def validate_api_key_endpoint(request: ApiKeyValidateRequest) -> ApiKeyValidateResponse:
    """
    Validate an API key against a stored hash.

    This endpoint checks if a provided API key matches the stored hash.

    Args:
        request: API key validation request

    Returns:
        Validation result
    """
    from platform_god.api.auth import validate_api_key

    is_valid = validate_api_key(request.api_key, request.stored_hash)
    return ApiKeyValidateResponse(valid=is_valid)


@router.get("/me")
async def get_current_user(http_request: Request) -> dict:
    """
    Get information about the current authenticated user.

    Returns user information from the JWT token or other authentication method.

    Args:
        http_request: FastAPI Request object

    Returns:
        Current user information
    """
    user_id = await get_optional_user_id(http_request)
    auth_method = getattr(http_request.state, "auth_method", None)

    return {
        "authenticated": user_id is not None,
        "user_id": user_id,
        "auth_method": auth_method,
    }


@router.get("/config")
async def get_auth_config() -> dict:
    """
    Get authentication configuration information.

    Returns public-facing configuration details about the authentication system.

    Returns:
        Authentication configuration
    """
    jwt_secret_set = bool(os.getenv("PG_JWT_SECRET"))
    api_keys_set = bool(os.getenv("PG_API_KEYS"))

    return {
        "jwt_enabled": True,
        "jwt_secret_configured": jwt_secret_set,
        "api_keys_enabled": True,
        "api_keys_configured": api_keys_set,
        "default_token_expiration_hours": 24,
        "max_token_expiration_hours": 168,
        "supported_auth_methods": ["jwt", "api_key", "user_id_header"],
    }
