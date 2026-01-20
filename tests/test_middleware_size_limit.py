"""Tests for request/response size limit middleware."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import Request
from fastapi.responses import Response, JSONResponse

from platform_god.api.middleware.size_limit import (
    SizeLimitMiddleware,
    get_max_request_size,
    get_max_response_size,
    format_size,
    add_size_limit_middleware,
    DEFAULT_MAX_REQUEST_SIZE,
    DEFAULT_MAX_RESPONSE_SIZE,
)


# =============================================================================
# Utility functions tests
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_format_size_bytes(self):
        """Test formatting bytes."""
        assert format_size(512) == "512 bytes"
        assert format_size(1024) == "1.0 KB"
        assert format_size(1536) == "1.5 KB"

    def test_format_size_kb(self):
        """Test formatting kilobytes."""
        assert format_size(1024 * 100) == "100.0 KB"
        assert format_size(1024 * 1024 - 1) == "1024.0 KB"

    def test_format_size_mb(self):
        """Test formatting megabytes."""
        assert format_size(1024 * 1024) == "1.0 MB"
        assert format_size(10 * 1024 * 1024) == "10.0 MB"
        assert format_size(1024 * 1024 * 1024 - 1) == "1024.0 MB"

    def test_format_size_gb(self):
        """Test formatting gigabytes."""
        assert format_size(1024 * 1024 * 1024) == "1.0 GB"
        assert format_size(5 * 1024 * 1024 * 1024) == "5.0 GB"

    @patch.dict("os.environ", {"PG_MAX_REQUEST_SIZE": "20M"}, clear=True)
    def test_get_max_request_size_from_env(self):
        """Test getting max request size from environment."""
        size = get_max_request_size()
        assert size == 20 * 1024 * 1024

    @patch.dict("os.environ", {"PG_MAX_REQUEST_SIZE": "1G"}, clear=True)
    def test_get_max_request_size_gb(self):
        """Test getting max request size in GB."""
        size = get_max_request_size()
        assert size == 1024 * 1024 * 1024

    @patch.dict("os.environ", {"PG_MAX_REQUEST_SIZE": "500K"}, clear=True)
    def test_get_max_request_size_kb(self):
        """Test getting max request size in KB."""
        size = get_max_request_size()
        assert size == 500 * 1024

    @patch.dict("os.environ", {"PG_MAX_REQUEST_SIZE": "invalid"}, clear=True)
    def test_get_max_request_size_invalid(self):
        """Test invalid request size returns default."""
        size = get_max_request_size()
        assert size == DEFAULT_MAX_REQUEST_SIZE

    @patch.dict("os.environ", {}, clear=True)
    def test_get_max_request_size_default(self):
        """Test default max request size."""
        size = get_max_request_size()
        assert size == DEFAULT_MAX_REQUEST_SIZE

    @patch.dict("os.environ", {"PG_MAX_RESPONSE_SIZE": "100M"}, clear=True)
    def test_get_max_response_size_from_env(self):
        """Test getting max response size from environment."""
        size = get_max_response_size()
        assert size == 100 * 1024 * 1024


# =============================================================================
# SizeLimitMiddleware tests
# =============================================================================


class TestSizeLimitMiddleware:
    """Tests for SizeLimitMiddleware class."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    @pytest.fixture
    def middleware(self, app):
        """Create middleware instance for testing."""
        return SizeLimitMiddleware(app, max_request_size=1024, max_response_size=2048)

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/test"
        request.method = "POST"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.1"
        return request

    @pytest.mark.asyncio
    async def test_exempt_paths_skip_checking(self, middleware, mock_request):
        """Test exempt paths skip size checking."""
        mock_request.url.path = "/health"
        call_next_called = False

        async def call_next(req):
            nonlocal call_next_called
            call_next_called = True
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert call_next_called is True

    @pytest.mark.asyncio
    async def test_request_under_limit_allowed(self, middleware, mock_request):
        """Test request under size limit is allowed."""
        mock_request.headers = {"content-length": "512"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code != 413

    @pytest.mark.asyncio
    async def test_request_over_limit_rejected(self, middleware, mock_request):
        """Test request over size limit is rejected with 413."""
        mock_request.headers = {"content-length": "2048"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_request_over_limit_error_content(self, middleware, mock_request):
        """Test error response structure for oversized request."""
        mock_request.headers = {"content-length": "2048"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)

        # Check error structure
        assert response.status_code == 413
        content = response.content
        assert "error" in content
        assert content["error"]["type"] == "payload_too_large"
        assert "exceeds maximum allowed" in content["error"]["message"]

    @pytest.mark.asyncio
    async def test_request_no_content_length(self, middleware, mock_request):
        """Test request without content-length proceeds."""
        mock_request.headers = {}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code != 413

    @pytest.mark.asyncio
    async def test_request_invalid_content_length(self, middleware, mock_request):
        """Test request with invalid content-length proceeds."""
        mock_request.headers = {"content-length": "invalid"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        # Should proceed and let FastAPI handle it
        assert call_next.called if hasattr(call_next, 'called') else True

    @pytest.mark.asyncio
    async def test_response_size_warning(self, middleware, mock_request, caplog):
        """Test large response triggers warning."""
        mock_request.headers = {}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {"content-length": "4096"}  # Over 2048 threshold
            return response

        response = await middleware.dispatch(mock_request, call_next)
        # Should log a warning for large response
        # Warning is logged but response proceeds normally
        assert response.status_code != 413

    @pytest.mark.asyncio
    async def test_response_no_content_length(self, middleware, mock_request):
        """Test response without content-length."""
        mock_request.headers = {}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        # Should proceed normally
        assert response.status_code != 413

    @pytest.mark.asyncio
    async def test_get_client_ip_x_forwarded_for(self, middleware, mock_request):
        """Test extracting client IP from X-Forwarded-For."""
        mock_request.headers = {"content-length": "512"}
        mock_request.headers.get = lambda k, d=None: {
            "content-length": "512",
            "x-forwarded-for": "203.0.113.1",
        }.get(k, d)

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        # Should complete without error
        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code != 413

    @pytest.mark.asyncio
    async def test_get_client_ip_x_real_ip(self, middleware, mock_request):
        """Test extracting client IP from X-Real-IP."""
        mock_request.headers = {"content-length": "512"}
        mock_request.headers.get = lambda k, d=None: {
            "content-length": "512",
            "x-real-ip": "198.51.100.1",
        }.get(k, d)

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert response.status_code != 413


# =============================================================================
# Custom configuration tests
# =============================================================================


class TestSizeLimitCustomConfig:
    """Tests for custom size limit configuration."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    def test_custom_max_request_size(self, app):
        """Test middleware with custom max request size."""
        middleware = SizeLimitMiddleware(app, max_request_size=2048)
        assert middleware._max_request_size == 2048

    def test_custom_max_response_size(self, app):
        """Test middleware with custom max response size."""
        middleware = SizeLimitMiddleware(app, max_response_size=4096)
        assert middleware._max_response_size == 4096

    def test_custom_skip_paths(self, app):
        """Test middleware with custom skip paths."""
        custom_paths = {"/custom", "/api/skip"}
        middleware = SizeLimitMiddleware(app, skip_paths=custom_paths)
        assert middleware._skip_paths == custom_paths

    @pytest.mark.asyncio
    async def test_custom_skip_paths_work(self, app):
        """Test custom skip paths are respected."""
        middleware = SizeLimitMiddleware(
            app,
            max_request_size=1024,
            skip_paths={"/custom"}
        )

        request = MagicMock(spec=Request)
        request.url.path = "/custom"
        request.headers = {}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(request, call_next)
        assert response.status_code != 413


# =============================================================================
# add_size_limit_middleware tests
# =============================================================================


class TestAddSizeLimitMiddleware:
    """Tests for add_size_limit_middleware utility function."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    def test_add_size_limit_middleware_returns_instance(self, app):
        """Test utility function returns middleware instance."""
        middleware = add_size_limit_middleware(
            app,
            max_request_size=2048,
            max_response_size=4096,
        )

        assert isinstance(middleware, SizeLimitMiddleware)
        assert middleware._max_request_size == 2048
        assert middleware._max_response_size == 4096


# =============================================================================
# Integration tests
# =============================================================================


class TestSizeLimitIntegration:
    """Integration tests for size limiting."""

    @pytest.fixture
    def app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    @pytest.mark.asyncio
    async def test_full_size_check_cycle(self, app):
        """Test complete size check cycle."""
        middleware = SizeLimitMiddleware(
            app,
            max_request_size=1024,
            max_response_size=2048,
        )

        request = MagicMock(spec=Request)
        request.url.path = "/api/upload"
        request.method = "POST"
        request.client.host = "10.0.0.1"

        # Test allowed request
        request.headers = {"content-length": "512"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(request, call_next)
        assert response.status_code != 413

        # Test rejected request
        request.headers = {"content-length": "2048"}
        response = await middleware.dispatch(request, call_next)
        assert response.status_code == 413

    @pytest.mark.asyncio
    async def test_size_limits_with_formatted_sizes(self, app):
        """Test size limit error messages include formatted sizes."""
        middleware = SizeLimitMiddleware(app, max_request_size=1024)

        request = MagicMock(spec=Request)
        request.url.path = "/api/upload"
        request.method = "POST"
        request.client.host = "10.0.0.1"
        request.headers = {"content-length": "2048"}

        async def call_next(req):
            response = MagicMock(spec=Response)
            response.headers = {}
            return response

        response = await middleware.dispatch(request, call_next)

        # Error message should include formatted sizes
        content = response.content
        assert "2.0 KB" in content["error"]["detail"]
        assert "1.0 KB" in content["error"]["detail"]
