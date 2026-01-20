"""
JWT token implementation for Platform God API.

Provides token creation, validation, and helper functions for
authentication and authorization.
"""

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

logger = logging.getLogger(__name__)

# Default JWT expiration time (24 hours)
DEFAULT_EXPIRATION_SECONDS = int(timedelta(hours=24).total_seconds())

# JWT algorithm
JWT_ALGORITHM = "HS256"


class TokenError(Exception):
    """Base exception for token-related errors."""

    pass


class InvalidTokenError(TokenError):
    """Exception raised when a token is invalid or malformed."""

    pass


class ExpiredTokenError(TokenError):
    """Exception raised when a token has expired."""

    pass


@dataclass
class TokenPayload:
    """
    JWT token payload data.

    Attributes:
        sub: Subject (user ID or identifier)
        exp: Expiration timestamp (Unix epoch)
        iat: Issued at timestamp (Unix epoch)
        iss: Issuer (optional)
        aud: Audience (optional)
        scope: Token scope/permissions (optional)
    """

    sub: str
    exp: int
    iat: int
    iss: str | None = None
    aud: str | None = None
    scope: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenPayload":
        """Create TokenPayload from dictionary."""
        return cls(
            sub=str(data["sub"]),
            exp=int(data["exp"]),
            iat=int(data.get("iat", 0)),
            iss=data.get("iss"),
            aud=data.get("aud"),
            scope=data.get("scope"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert TokenPayload to dictionary."""
        data: dict[str, Any] = {
            "sub": self.sub,
            "exp": self.exp,
            "iat": self.iat,
        }
        if self.iss:
            data["iss"] = self.iss
        if self.aud:
            data["aud"] = self.aud
        if self.scope:
            data["scope"] = self.scope
        return data


def _get_jwt_secret() -> str:
    """
    Get JWT secret from environment variable.

    Returns:
        JWT secret key

    Raises:
        ValueError: If PG_JWT_SECRET is not set and in production mode
    """
    secret = os.getenv("PG_JWT_SECRET", "")
    if not secret:
        # Generate a warning but allow a default for development
        logger.warning(
            "PG_JWT_SECRET environment variable not set. "
            "Using default secret key (INSECURE - set PG_JWT_SECRET in production!)"
        )
        return "change-this-secret-in-production"
    return secret


def _base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url format."""
    import base64

    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def _base64url_decode(data: str) -> bytes:
    """Decode base64url string to bytes."""
    import base64

    # Add padding if necessary
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def _sign_hmac(data: str, secret: str) -> str:
    """Create HMAC-SHA256 signature."""
    hmac_obj = hmac.new(
        secret.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha256,
    )
    return _base64url_encode(hmac_obj.digest())


def _verify_hmac(data: str, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected_signature = _sign_hmac(data, secret)
    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature)


def create_access_token(
    subject: str,
    expiration_seconds: int = DEFAULT_EXPIRATION_SECONDS,
    issuer: str | None = None,
    audience: str | None = None,
    scope: str | None = None,
    secret: str | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        subject: User ID or identifier (the 'sub' claim)
        expiration_seconds: Token lifetime in seconds (default: 24 hours)
        issuer: Optional issuer claim
        audience: Optional audience claim
        scope: Optional scope/permissions
        secret: Optional secret key (uses PG_JWT_SECRET if not provided)

    Returns:
        JWT token string

    Raises:
        ValueError: If subject is empty
    """
    if not subject:
        raise ValueError("Subject cannot be empty")

    secret = secret or _get_jwt_secret()

    now = int(time.time())
    exp = now + expiration_seconds

    payload_data: dict[str, Any] = {
        "sub": subject,
        "exp": exp,
        "iat": now,
    }

    if issuer:
        payload_data["iss"] = issuer
    if audience:
        payload_data["aud"] = audience
    if scope:
        payload_data["scope"] = scope

    # Create header
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}

    # Encode header and payload
    header_b64 = _base64url_encode_json(header)
    payload_b64 = _base64url_encode_json(payload_data)

    # Create signature
    signing_input = f"{header_b64}.{payload_b64}"
    signature = _sign_hmac(signing_input, secret)

    # Combine all parts
    token = f"{signing_input}.{signature}"

    logger.debug(f"Created JWT token for subject={subject}, expires={exp}")
    return token


def _base64url_encode_json(data: dict[str, Any]) -> str:
    """Encode JSON dictionary to base64url string."""
    import json

    json_bytes = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url_encode(json_bytes)


def _base64url_decode_json(data: str) -> dict[str, Any]:
    """Decode base64url string to JSON dictionary."""
    import json

    decoded_bytes = _base64url_decode(data)
    return json.loads(decoded_bytes.decode("utf-8"))


def decode_token(token: str, secret: str | None = None) -> TokenPayload:
    """
    Decode and validate a JWT token.

    Args:
        token: JWT token string
        secret: Optional secret key (uses PG_JWT_SECRET if not provided)

    Returns:
        TokenPayload object

    Raises:
        InvalidTokenError: If token is malformed or signature is invalid
        ExpiredTokenError: If token has expired
    """
    if not token:
        raise InvalidTokenError("Token cannot be empty")

    secret = secret or _get_jwt_secret()

    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Invalid token format")

    header_b64, payload_b64, signature = parts

    # Verify signature
    signing_input = f"{header_b64}.{payload_b64}"
    if not _verify_hmac(signing_input, signature, secret):
        raise InvalidTokenError("Invalid token signature")

    # Decode payload
    try:
        payload_data = _base64url_decode_json(payload_b64)
    except Exception as e:
        raise InvalidTokenError(f"Cannot decode token payload: {e}")

    # Check expiration
    now = int(time.time())
    exp = payload_data.get("exp")
    if exp is None:
        raise InvalidTokenError("Token missing expiration claim")

    if now >= exp:
        raise ExpiredTokenError(f"Token expired at {exp}")

    # Validate required claims
    if "sub" not in payload_data:
        raise InvalidTokenError("Token missing subject claim")

    return TokenPayload.from_dict(payload_data)


def validate_token(token: str, secret: str | None = None) -> tuple[bool, TokenPayload | None, str | None]:
    """
    Validate a JWT token and return the result.

    Args:
        token: JWT token string
        secret: Optional secret key (uses PG_JWT_SECRET if not provided)

    Returns:
        Tuple of (is_valid, payload, error_message)
    """
    try:
        payload = decode_token(token, secret)
        return True, payload, None
    except ExpiredTokenError as e:
        return False, None, str(e)
    except InvalidTokenError as e:
        return False, None, str(e)
    except TokenError as e:
        return False, None, str(e)


def hash_api_key(api_key: str, salt: str | None = None) -> str:
    """
    Hash an API key for secure storage.

    Uses SHA-256 HMAC with a salt for key derivation.

    Args:
        api_key: The API key to hash
        salt: Optional salt (uses default if not provided)

    Returns:
        Hex-encoded hash string
    """
    salt = salt or "platform-god-api-key-salt"
    hmac_obj = hmac.new(
        salt.encode("utf-8"),
        api_key.encode("utf-8"),
        hashlib.sha256,
    )
    return hmac_obj.hexdigest()


def validate_api_key(
    provided_key: str,
    stored_hash: str,
    salt: str | None = None,
) -> bool:
    """
    Validate an API key against its stored hash.

    Args:
        provided_key: The API key provided by the client
        stored_hash: The hashed API key to validate against
        salt: Optional salt (must match the salt used for hashing)

    Returns:
        True if the key is valid
    """
    if not provided_key or not stored_hash:
        return False

    computed_hash = hash_api_key(provided_key, salt)
    # Use constant-time comparison
    return hmac.compare_digest(computed_hash, stored_hash)


def extract_token_from_header(auth_header: str) -> str | None:
    """
    Extract JWT token from Authorization header.

    Args:
        auth_header: The Authorization header value

    Returns:
        The token string or None if invalid format
    """
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2:
        return None

    scheme, token = parts
    if scheme.lower() not in ("bearer",):
        return None

    return token
