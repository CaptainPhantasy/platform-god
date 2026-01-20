"""
Middleware for Platform God API.

This module contains all middleware components for request/response processing.
"""

from platform_god.api.middleware.auth import (
    AuthMiddleware,
    InvalidCredentialsError,
    get_optional_user_id,
)
from platform_god.api.middleware.cors import add_cors_middleware
from platform_god.api.middleware.logging import RequestLoggingMiddleware
from platform_god.api.middleware.rate_limit import (
    InMemoryRateLimiter,
    RateLimitMiddleware,
    add_rate_limit_middleware,
    check_rate_limit,
    get_client_ip,
    get_rate_limit_info,
)
from platform_god.api.middleware.validation import (
    ContentValidationError,
    JSONParseError,
    ValidationMiddleware,
    add_validation_middleware,
    parse_json_enhanced,
    sanitize_query_string,
    validate_content_type,
)

__all__ = [
    "AuthMiddleware",
    "InvalidCredentialsError",
    "get_optional_user_id",
    "add_cors_middleware",
    "RequestLoggingMiddleware",
    "InMemoryRateLimiter",
    "RateLimitMiddleware",
    "add_rate_limit_middleware",
    "check_rate_limit",
    "get_client_ip",
    "get_rate_limit_info",
    "ValidationMiddleware",
    "add_validation_middleware",
    "validate_content_type",
    "sanitize_query_string",
    "parse_json_enhanced",
    "ContentValidationError",
    "JSONParseError",
]
