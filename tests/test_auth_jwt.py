"""Tests for JWT authentication module."""

import time
from unittest.mock import patch

import pytest

from platform_god.api.auth.jwt import (
    TokenError,
    InvalidTokenError,
    ExpiredTokenError,
    TokenPayload,
    create_access_token,
    decode_token,
    validate_token,
    hash_api_key,
    validate_api_key,
    extract_token_from_header,
    _get_jwt_secret,
    _base64url_encode,
    _base64url_decode,
    _sign_hmac,
    _verify_hmac,
    DEFAULT_EXPIRATION_SECONDS,
    JWT_ALGORITHM,
)


# =============================================================================
# TokenPayload tests
# =============================================================================


class TestTokenPayload:
    """Tests for TokenPayload dataclass."""

    def test_create_token_payload(self):
        """Test creating a token payload."""
        now = int(time.time())
        payload = TokenPayload(
            sub="user123",
            exp=now + 3600,
            iat=now,
            iss="platform-god",
            aud="api",
            scope="read write",
        )

        assert payload.sub == "user123"
        assert payload.exp == now + 3600
        assert payload.iat == now
        assert payload.iss == "platform-god"
        assert payload.aud == "api"
        assert payload.scope == "read write"

    def test_token_payload_from_dict(self):
        """Test creating TokenPayload from dictionary."""
        data = {
            "sub": "user456",
            "exp": 1234567890,
            "iat": 1234567500,
            "iss": "test",
            "aud": "test-aud",
            "scope": "admin",
        }
        payload = TokenPayload.from_dict(data)

        assert payload.sub == "user456"
        assert payload.exp == 1234567890
        assert payload.iat == 1234567500
        assert payload.iss == "test"
        assert payload.aud == "test-aud"
        assert payload.scope == "admin"

    def test_token_payload_to_dict(self):
        """Test converting TokenPayload to dictionary."""
        payload = TokenPayload(
            sub="user789",
            exp=1234567890,
            iat=1234567500,
            iss="test",
        )
        data = payload.to_dict()

        assert data["sub"] == "user789"
        assert data["exp"] == 1234567890
        assert data["iat"] == 1234567500
        assert data["iss"] == "test"
        assert "aud" not in data


# =============================================================================
# create_access_token tests
# =============================================================================


class TestCreateAccessToken:
    """Tests for create_access_token function."""

    def test_create_basic_token(self):
        """Test creating a basic access token."""
        token = create_access_token("user123")

        assert isinstance(token, str)
        assert len(token) > 0
        # JWT has 3 parts separated by dots
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_token_with_custom_expiration(self):
        """Test creating token with custom expiration."""
        token = create_access_token("user456", expiration_seconds=7200)

        parts = token.split(".")
        assert len(parts) == 3

    def test_create_token_with_all_options(self):
        """Test creating token with all options."""
        token = create_access_token(
            subject="user789",
            expiration_seconds=3600,
            issuer="platform-god",
            audience="api",
            scope="read write",
        )

        parts = token.split(".")
        assert len(parts) == 3

    def test_create_token_with_custom_secret(self):
        """Test creating token with custom secret."""
        custom_secret = "my-custom-secret-key"
        token = create_access_token("user999", secret=custom_secret)

        assert isinstance(token, str)
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_token_empty_subject_raises_error(self):
        """Test creating token with empty subject raises error."""
        with pytest.raises(ValueError) as exc_info:
            create_access_token("")

        assert "Subject cannot be empty" in str(exc_info.value)


# =============================================================================
# decode_token tests
# =============================================================================


class TestDecodeToken:
    """Tests for decode_token function."""

    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        token = create_access_token("user123")
        payload = decode_token(token)

        assert isinstance(payload, TokenPayload)
        assert payload.sub == "user123"
        assert payload.exp > int(time.time())
        assert payload.iat <= int(time.time())

    def test_decode_token_custom_secret(self):
        """Test decoding token with custom secret."""
        custom_secret = "another-secret-key"
        token = create_access_token("user456", secret=custom_secret)
        payload = decode_token(token, secret=custom_secret)

        assert payload.sub == "user456"

    def test_decode_token_wrong_secret_fails(self):
        """Test decoding token with wrong secret fails."""
        token = create_access_token("user789", secret="secret1")

        with pytest.raises(InvalidTokenError) as exc_info:
            decode_token(token, secret="secret2")

        assert "Invalid token signature" in str(exc_info.value)

    def test_decode_empty_token_raises_error(self):
        """Test decoding empty token raises error."""
        with pytest.raises(InvalidTokenError) as exc_info:
            decode_token("")

        assert "Token cannot be empty" in str(exc_info.value)

    def test_decode_malformed_token_raises_error(self):
        """Test decoding malformed token raises error."""
        with pytest.raises(InvalidTokenError) as exc_info:
            decode_token("invalid.token")

        assert "Invalid token format" in str(exc_info.value)

    def test_decode_token_with_invalid_signature(self):
        """Test decoding token with invalid signature."""
        token = create_access_token("user123")
        # Corrupt the signature
        parts = token.split(".")
        corrupted_token = f"{parts[0]}.{parts[1]}.invalidsignature"

        with pytest.raises(InvalidTokenError) as exc_info:
            decode_token(corrupted_token)

        assert "Invalid token signature" in str(exc_info.value)

    def test_decode_expired_token_raises_error(self):
        """Test decoding expired token raises error."""
        # Create a token that's already expired
        token = create_access_token(
            "user999",
            expiration_seconds=-100,  # Already expired
        )

        with pytest.raises(ExpiredTokenError) as exc_info:
            decode_token(token)

        assert "Token expired" in str(exc_info.value)

    def test_decode_token_without_expiration_raises_error(self):
        """Test decoding token without expiration raises error."""
        # Manually construct a token without exp claim
        header = _base64url_encode_json({"alg": JWT_ALGORITHM, "typ": "JWT"})
        payload = _base64url_encode_json({"sub": "user123", "iat": int(time.time())})
        signing_input = f"{header}.{payload}"
        signature = _sign_hmac(signing_input, _get_jwt_secret())
        token = f"{signing_input}.{signature}"

        with pytest.raises(InvalidTokenError) as exc_info:
            decode_token(token)

        assert "missing expiration" in str(exc_info.value)

    def test_decode_token_without_subject_raises_error(self):
        """Test decoding token without subject raises error."""
        header = _base64url_encode_json({"alg": JWT_ALGORITHM, "typ": "JWT"})
        payload = _base64url_encode_json({
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        })
        signing_input = f"{header}.{payload}"
        signature = _sign_hmac(signing_input, _get_jwt_secret())
        token = f"{signing_input}.{signature}"

        with pytest.raises(InvalidTokenError) as exc_info:
            decode_token(token)

        assert "missing subject" in str(exc_info.value)


def _base64url_encode_json(data):
    """Helper to encode JSON dict to base64url."""
    import json
    from platform_god.api.auth.jwt import _base64url_encode
    json_bytes = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return _base64url_encode(json_bytes)


# =============================================================================
# validate_token tests
# =============================================================================


class TestValidateToken:
    """Tests for validate_token function."""

    def test_validate_valid_token(self):
        """Test validating a valid token."""
        token = create_access_token("user123")
        is_valid, payload, error = validate_token(token)

        assert is_valid is True
        assert payload is not None
        assert payload.sub == "user123"
        assert error is None

    def test_validate_expired_token(self):
        """Test validating an expired token."""
        token = create_access_token("user456", expiration_seconds=-100)
        is_valid, payload, error = validate_token(token)

        assert is_valid is False
        assert payload is None
        assert error is not None
        assert "expired" in error.lower()

    def test_validate_invalid_token(self):
        """Test validating an invalid token."""
        is_valid, payload, error = validate_token("invalid.token.format")

        assert is_valid is False
        assert payload is None
        assert error is not None

    def test_validate_empty_token(self):
        """Test validating an empty token."""
        is_valid, payload, error = validate_token("")

        assert is_valid is False
        assert payload is None
        assert error is not None


# =============================================================================
# API key functions tests
# =============================================================================


class TestApiKeyFunctions:
    """Tests for API key hashing and validation."""

    def test_hash_api_key(self):
        """Test hashing an API key."""
        api_key = "sk_test_1234567890abcdef"
        hash_result = hash_api_key(api_key)

        assert isinstance(hash_result, str)
        assert len(hash_result) == 64  # SHA-256 produces 64 hex characters
        assert hash_result != api_key

    def test_hash_api_key_with_custom_salt(self):
        """Test hashing API key with custom salt."""
        api_key = "sk_test_1234567890abcdef"
        hash1 = hash_api_key(api_key, salt="salt1")
        hash2 = hash_api_key(api_key, salt="salt2")

        assert hash1 != hash2

    def test_hash_api_key_same_input_same_hash(self):
        """Test same input produces same hash."""
        api_key = "sk_test_1234567890abcdef"
        salt = "test-salt"

        hash1 = hash_api_key(api_key, salt)
        hash2 = hash_api_key(api_key, salt)

        assert hash1 == hash2

    def test_validate_api_key_valid(self):
        """Test validating a valid API key."""
        api_key = "sk_test_1234567890abcdef"
        salt = "test-salt"
        stored_hash = hash_api_key(api_key, salt)

        is_valid = validate_api_key(api_key, stored_hash, salt)
        assert is_valid is True

    def test_validate_api_key_invalid(self):
        """Test validating an invalid API key."""
        stored_hash = hash_api_key("correct_key", "salt")

        is_valid = validate_api_key("wrong_key", stored_hash, "salt")
        assert is_valid is False

    def test_validate_api_key_empty_inputs(self):
        """Test validating with empty inputs."""
        assert validate_api_key("", "somehash") is False
        assert validate_api_key("key", "") is False
        assert validate_api_key(None, "hash") is False

    def test_validate_api_key_wrong_salt(self):
        """Test validating with wrong salt fails."""
        api_key = "sk_test_1234567890abcdef"
        stored_hash = hash_api_key(api_key, salt="salt1")

        is_valid = validate_api_key(api_key, stored_hash, salt="salt2")
        assert is_valid is False


# =============================================================================
# extract_token_from_header tests
# =============================================================================


class TestExtractTokenFromHeader:
    """Tests for extract_token_from_header function."""

    def test_extract_valid_bearer_token(self):
        """Test extracting valid Bearer token."""
        auth_header = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        token = extract_token_from_header(auth_header)

        assert token == "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"

    def test_extract_bearer_lowercase(self):
        """Test extracting bearer token with lowercase scheme."""
        auth_header = "bearer token123"
        token = extract_token_from_header(auth_header)

        assert token == "token123"

    def test_extract_bearer_mixed_case(self):
        """Test extracting bearer token with mixed case."""
        auth_header = "BEARER token456"
        token = extract_token_from_header(auth_header)

        assert token == "token456"

    def test_extract_token_empty_header(self):
        """Test extracting from empty header."""
        assert extract_token_from_header("") is None
        assert extract_token_from_header(None) is None

    def test_extract_token_invalid_scheme(self):
        """Test extracting token with invalid scheme."""
        assert extract_token_from_header("Basic token") is None
        assert extract_token_from_header("token") is None

    def test_extract_token_missing_parts(self):
        """Test extracting token with missing parts."""
        assert extract_token_from_header("Bearer") is None
        assert extract_token_from_header("Bearer ") is None


# =============================================================================
# Helper function tests
# =============================================================================


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_base64url_encode(self):
        """Test base64url encoding."""
        data = b"test data"
        encoded = _base64url_encode(data)

        assert isinstance(encoded, str)
        assert "=" not in encoded  # No padding
        assert "+" not in encoded  # No + characters
        assert "/" not in encoded  # No / characters

    def test_base64url_decode(self):
        """Test base64url decoding."""
        encoded = "dGVzdCBkYXRh"  # "test data" in base64url
        decoded = _base64url_decode(encoded)

        assert decoded == b"test data"

    def test_base64url_decode_with_padding(self):
        """Test decoding adds padding if needed."""
        # Encoded "test" without padding
        encoded = "dGVzdA"
        decoded = _base64url_decode(encoded)

        assert decoded == b"test"

    def test_sign_hmac(self):
        """Test HMAC signing."""
        data = "message to sign"
        secret = "secret-key"
        signature = _sign_hmac(data, secret)

        assert isinstance(signature, str)
        assert len(signature) > 0

    def test_verify_hmac_valid(self):
        """Test verifying valid HMAC."""
        data = "message to sign"
        secret = "secret-key"
        signature = _sign_hmac(data, secret)

        is_valid = _verify_hmac(data, signature, secret)
        assert is_valid is True

    def test_verify_hmac_invalid(self):
        """Test verifying invalid HMAC."""
        data = "message to sign"
        secret = "secret-key"

        is_valid = _verify_hmac(data, "invalid-signature", secret)
        assert is_valid is False

    def test_verify_hmac_wrong_secret(self):
        """Test verifying HMAC with wrong secret fails."""
        data = "message to sign"
        secret1 = "secret-key-1"
        secret2 = "secret-key-2"
        signature = _sign_hmac(data, secret1)

        is_valid = _verify_hmac(data, signature, secret2)
        assert is_valid is False

    @patch.dict("os.environ", {"PG_JWT_SECRET": "custom-secret-from-env"}, clear=True)
    def test_get_jwt_secret_from_env(self):
        """Test getting JWT secret from environment."""
        secret = _get_jwt_secret()
        assert secret == "custom-secret-from-env"

    @patch.dict("os.environ", {}, clear=True)
    def test_get_jwt_secret_default(self):
        """Test getting default JWT secret."""
        secret = _get_jwt_secret()
        assert secret == "change-this-secret-in-production"


# =============================================================================
# Integration tests
# =============================================================================


class TestJwtIntegration:
    """Integration tests for JWT functionality."""

    def test_full_token_cycle(self):
        """Test complete create-validate-decode cycle."""
        # Create token
        token = create_access_token("integration_user")

        # Validate
        is_valid, payload, error = validate_token(token)
        assert is_valid is True
        assert error is None

        # Decode
        decoded = decode_token(token)
        assert decoded.sub == "integration_user"
        assert decoded.sub == payload.sub

    def test_token_with_all_claims(self):
        """Test token with all optional claims."""
        token = create_access_token(
            subject="full_user",
            expiration_seconds=7200,
            issuer="platform-god",
            audience="api",
            scope="read write admin",
        )

        payload = decode_token(token)
        assert payload.sub == "full_user"
        assert payload.iss == "platform-god"
        assert payload.aud == "api"
        assert payload.scope == "read write admin"

    def test_multiple_tokens_same_subject(self):
        """Test creating multiple tokens for same subject."""
        subject = "multi_token_user"

        # Create tokens with different expiration times to ensure uniqueness
        token1 = create_access_token(subject, expiration_seconds=3600)
        token2 = create_access_token(subject, expiration_seconds=7200)

        # Decode both tokens
        payload1 = decode_token(token1)
        payload2 = decode_token(token2)

        # Both should be valid
        assert payload1.sub == subject
        assert payload2.sub == subject
        # exp should be different due to different expiration times
        assert payload1.exp != payload2.exp

    def test_token_expiration_accuracy(self):
        """Test token expiration time is accurate."""
        expiration_seconds = 3600
        token = create_access_token("exp_test_user", expiration_seconds)

        payload = decode_token(token)
        now = int(time.time())

        # exp should be approximately expiration_seconds in the future
        time_diff = payload.exp - now
        assert 3590 <= time_diff <= 3610  # Allow 10 second tolerance

    def test_extract_and_validate_cycle(self):
        """Test extracting from header and validating."""
        token = create_access_token("header_user")
        auth_header = f"Bearer {token}"

        # Extract
        extracted = extract_token_from_header(auth_header)
        assert extracted == token

        # Validate
        is_valid, payload, error = validate_token(extracted)
        assert is_valid is True
        assert payload.sub == "header_user"
