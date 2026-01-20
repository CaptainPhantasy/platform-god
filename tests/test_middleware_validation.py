"""Tests for input validation middleware."""

import json
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import Request
from fastapi.responses import Response, JSONResponse

from platform_god.api.middleware.validation import (
    ValidationMiddleware,
    sanitize_query_string,
    validate_content_type,
    ContentValidationError,
    JSONParseError,
    parse_json_enhanced,
    _get_json_error_context,
    ALLOWED_CONTENT_TYPES,
    MAX_QUERY_STRING_LENGTH,
    CONTENT_TYPE_EXEMPT_PATHS,
    add_validation_middleware,
)


# =============================================================================
# sanitize_query_string tests
# =============================================================================


class TestSanitizeQueryString:
    """Tests for sanitize_query_string function."""

    def test_sanitize_empty_string(self):
        """Test sanitizing empty string."""
        assert sanitize_query_string("") == ""

    def test_sitize_none_input(self):
        """Test sanitizing None input."""
        assert sanitize_query_string(None) == ""

    def test_sanitize_normal_string(self):
        """Test normal string is unchanged."""
        assert sanitize_query_string("key=value&foo=bar") == "key=value&foo=bar"

    def test_sanitize_removes_null_bytes(self):
        """Test null bytes are removed."""
        assert sanitize_query_string("key=val\x00ue") == "key=value"

    def test_sanitize_removes_control_characters(self):
        """Test dangerous control characters are removed."""
        # Contains various control characters
        input_str = "key=val\x01\x02\x03ue"
        assert "\x01" not in sanitize_query_string(input_str)
        assert "\x02" not in sanitize_query_string(input_str)
        assert "\x03" not in sanitize_query_string(input_str)

    def test_sanitize_keeps_newline_and_tab(self):
        """Test newlines and tabs are preserved."""
        # Newlines and tabs are allowed
        input_str = "key=val\n\tue"
        result = sanitize_query_string(input_str)
        assert "\n" in result
        assert "\t" in result


# =============================================================================
# validate_content_type tests
# =============================================================================


class TestValidateContentType:
    """Tests for validate_content_type function."""

    def test_validate_get_method(self):
        """Test GET method doesn't require validation."""
        assert validate_content_type(None, "GET") is True
        assert validate_content_type("text/html", "GET") is True

    def test_validate_head_method(self):
        """Test HEAD method doesn't require validation."""
        assert validate_content_type(None, "HEAD") is True

    def test_validate_delete_method(self):
        """Test DELETE method doesn't require validation."""
        assert validate_content_type(None, "DELETE") is True

    def test_validate_allowed_content_types(self):
        """Test allowed content types pass validation."""
        for ct in ALLOWED_CONTENT_TYPES:
            result = validate_content_type(ct, "POST")
            assert result is True

    def test_validate_multipart_with_boundary(self):
        """Test multipart/form-data with boundary passes."""
        result = validate_content_type(
            "multipart/form-data; boundary=----WebKitFormBoundary",
            "POST"
        )
        assert result is True

    def test_validate_form_urlencoded_with_charset(self):
        """Test form-urlencoded with charset passes."""
        result = validate_content_type(
            "application/x-www-form-urlencoded; charset=UTF-8",
            "POST"
        )
        assert result is True

    def test_validate_missing_content_type_for_post(self):
        """Test missing Content-Type for POST raises error."""
        with pytest.raises(ContentValidationError) as exc_info:
            validate_content_type(None, "POST")

        assert "Missing Content-Type header" in str(exc_info.value)

    def test_validate_unsupported_content_type(self):
        """Test unsupported Content-Type raises error."""
        with pytest.raises(ContentValidationError) as exc_info:
            validate_content_type("text/html", "POST")

        assert "Unsupported Content-Type" in str(exc_info.value)


# =============================================================================
# parse_json_enhanced tests
# =============================================================================


class TestParseJsonEnhanced:
    """Tests for parse_json_enhanced function."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON."""
        body = b'{"key": "value", "number": 123}'
        result = parse_json_enhanced(body)
        assert result == {"key": "value", "number": 123}

    def test_parse_json_array(self):
        """Test parsing JSON array."""
        body = b'[{"id": 1}, {"id": 2}]'
        result = parse_json_enhanced(body)
        assert result == [{"id": 1}, {"id": 2}]

    def test_parse_empty_body(self):
        """Test parsing empty body raises error."""
        with pytest.raises(JSONParseError) as exc_info:
            parse_json_enhanced(b"")

        assert "Empty request body" in str(exc_info.value)

    def test_parse_invalid_utf8(self):
        """Test invalid UTF-8 raises error."""
        with pytest.raises(JSONParseError) as exc_info:
            parse_json_enhanced(b"\xff\xfe")

        assert "Invalid UTF-8" in str(exc_info.value.message)

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON raises error with position."""
        body = b'{"key": "value"'

        with pytest.raises(JSONParseError) as exc_info:
            parse_json_enhanced(body)

        assert exc_info.value.message == "Invalid JSON format"
        assert exc_info.value.line is not None
        assert exc_info.value.position is not None


# =============================================================================
# _get_json_error_context tests
# =============================================================================


class TestGetJsonErrorContext:
    """Tests for _get_json_error_context function."""

    def test_get_error_context(self):
        """Test getting context around error position."""
        body = b'{"key1": "value1", "key2": "value2", "key3": "value3"}'
        context = _get_json_error_context(body, 20)

        # Should include parts before and after error
        assert "..." in context
        assert "<ERROR>" in context

    def test_get_error_context_binary_data(self):
        """Test error context for binary data."""
        body = b"\xff\xfe\x00\x01"
        context = _get_json_error_context(body, 2)
        assert context == "[binary data]"


# =============================================================================
# ValidationMiddleware tests
# =============================================================================


class TestValidationMiddleware:
    """Tests for ValidationMiddleware class."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    @pytest.fixture
    def middleware(self, app):
        """Create middleware instance for testing."""
        return ValidationMiddleware(app, strict_mode=True)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/test"
        request.url.query = ""
        request.method = "GET"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        return request

    @pytest.mark.asyncio
    async def test_exempt_paths_skip_validation(self, middleware, mock_request):
        """Test exempt paths skip validation."""
        mock_request.url.path = "/health"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response is not None

    @pytest.mark.asyncio
    async def test_skip_paths_parameter(self, app):
        """Test custom skip paths are respected."""
        middleware = ValidationMiddleware(
            app,
            skip_paths={"/custom"}
        )

        request = MagicMock(spec=Request)
        request.url.path = "/custom"
        request.url.query = ""
        request.method = "GET"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(request, call_next)
        assert response is not None

    @pytest.mark.asyncio
    async def test_query_string_too_long(self, middleware, mock_request):
        """Test overly long query string is rejected."""
        mock_request.url.query = "a" * 3000
        mock_request.method = "GET"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 414

    @pytest.mark.asyncio
    async def test_query_string_too_long_error_content(self, middleware, mock_request):
        """Test query string too long error structure."""
        mock_request.url.query = "a" * 3000
        mock_request.method = "GET"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)

        assert response.status_code == 414
        content = response.content
        assert "error" in content
        assert content["error"]["type"] == "uri_too_long"

    @pytest.mark.asyncio
    async def test_valid_query_string_allowed(self, middleware, mock_request):
        """Test valid query string is allowed."""
        mock_request.url.query = "key=value&foo=bar"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code != 414

    @pytest.mark.asyncio
    async def test_sanitize_dangerous_query_string(self, middleware, mock_request, caplog):
        """Test dangerous characters in query string are sanitized."""
        mock_request.url.query = "key=val\x00ue"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        # Request proceeds but should log warning
        assert response is not None

    @pytest.mark.asyncio
    async def test_missing_content_type_for_post(self, middleware, mock_request):
        """Test POST without Content-Type is rejected."""
        mock_request.method = "POST"
        mock_request.headers = {}
        mock_request.headers.get = lambda k, d=None: None

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_invalid_content_type_for_post(self, middleware, mock_request):
        """Test POST with invalid Content-Type is rejected."""
        mock_request.method = "POST"
        mock_request.headers = {"content-type": "text/html"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 415

    @pytest.mark.asyncio
    async def test_valid_content_type_for_post(self, middleware, mock_request):
        """Test POST with valid Content-Type is allowed."""
        mock_request.method = "POST"
        mock_request.headers = {"content-type": "application/json"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code != 415

    @pytest.mark.asyncio
    async def test_get_method_no_content_type_check(self, middleware, mock_request):
        """Test GET doesn't require Content-Type."""
        mock_request.method = "GET"
        mock_request.headers = {}

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code != 415

    @pytest.mark.asyncio
    async def test_json_parse_error_caught(self, app):
        """Test JSON parse errors are caught and handled."""
        middleware = ValidationMiddleware(app)

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.url.query = ""
        request.method = "POST"
        request.headers = {"content-type": "application/json"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        async def call_next(req):
            # Simulate JSON parse error
            raise json.JSONDecodeError("Invalid JSON", "test", 1)

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 400
        content = response.content
        assert "error" in content
        assert content["error"]["type"] == "invalid_json"


# =============================================================================
# Non-strict mode tests
# =============================================================================


class TestValidationMiddlewareNonStrict:
    """Tests for non-strict validation mode."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    @pytest.mark.asyncio
    async def test_non_strict_mode_allows_unknown_content_type(self, app):
        """Test non-strict mode allows unknown content types."""
        middleware = ValidationMiddleware(app, strict_mode=False)

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.url.query = ""
        request.method = "POST"
        request.headers = {"content-type": "text/html"}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(request, call_next)
        # Should not be rejected
        assert response.status_code != 415


# =============================================================================
# Custom configuration tests
# =============================================================================


class TestValidationMiddlewareCustomConfig:
    """Tests for custom validation configuration."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    def test_custom_max_query_length(self, app):
        """Test custom max query length."""
        middleware = ValidationMiddleware(app, max_query_length=5000)
        assert middleware._max_query_length == 5000

    @pytest.mark.asyncio
    async def test_custom_max_query_length_works(self, app):
        """Test custom max query length is enforced."""
        middleware = ValidationMiddleware(app, max_query_length=100)

        request = MagicMock(spec=Request)
        request.url.path = "/api/test"
        request.url.query = "a" * 200  # Over custom limit
        request.method = "GET"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 414


# =============================================================================
# add_validation_middleware tests
# =============================================================================


class TestAddValidationMiddleware:
    """Tests for add_validation_middleware utility function."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    def test_add_validation_middleware_returns_instance(self, app):
        """Test utility function returns middleware instance."""
        middleware = add_validation_middleware(
            app,
            strict_mode=False,
            max_query_length=5000,
        )

        assert isinstance(middleware, ValidationMiddleware)
        assert middleware._strict_mode is False
        assert middleware._max_query_length == 5000


# =============================================================================
# Integration tests
# =============================================================================


class TestValidationIntegration:
    """Integration tests for validation middleware."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    @pytest.mark.asyncio
    async def test_full_validation_cycle(self, app):
        """Test complete validation cycle."""
        middleware = ValidationMiddleware(app)

        # Test valid GET request
        request = MagicMock(spec=Request)
        request.url.path = "/api/data"
        request.url.query = "id=123"
        request.method = "GET"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "10.0.0.1"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(request, call_next)
        assert response.status_code != 414
        assert response.status_code != 415

    @pytest.mark.asyncio
    async def test_all_exempt_paths(self, app):
        """Test all default exempt paths."""
        middleware = ValidationMiddleware(app)

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        for path in CONTENT_TYPE_EXEMPT_PATHS:
            request = MagicMock(spec=Request)
            request.url.path = path
            request.url.query = ""
            request.method = "POST"
            request.headers = {}
            request.client = MagicMock()
            request.client.host = "192.168.1.1"

            response = await middleware.dispatch(request, call_next)
            # Should skip validation
            assert response is not None

    @pytest.mark.asyncio
    async def test_query_string_with_control_chars(self, app):
        """Test query string with control characters is sanitized."""
        middleware = ValidationMiddleware(app)

        request = MagicMock(spec=Request)
        request.url.path = "/api/search"
        request.url.query = "q=test\x00\x01\x02data"
        request.method = "GET"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"

        async def call_next(req):
            response = MagicMock(spec=Response)
            return response

        response = await middleware.dispatch(request, call_next)
        # Should be sanitized and allowed
        assert response.status_code != 414
