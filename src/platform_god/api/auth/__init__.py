"""
Authentication module for Platform God API.

Provides JWT token generation/validation and API key authentication.
"""

from platform_god.api.auth.jwt import (
    create_access_token,
    decode_token,
    validate_token,
    extract_token_from_header,
    TokenPayload,
    TokenError,
    InvalidTokenError,
    ExpiredTokenError,
    validate_api_key,
    hash_api_key,
)

__all__ = [
    "create_access_token",
    "decode_token",
    "validate_token",
    "extract_token_from_header",
    "TokenPayload",
    "TokenError",
    "InvalidTokenError",
    "ExpiredTokenError",
    "validate_api_key",
    "hash_api_key",
]
