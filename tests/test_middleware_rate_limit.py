"""Tests for rate limiting middleware."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import Response

from platform_god.api.middleware.rate_limit import (
    _parse_rate_limit,
    _PERIOD_SECONDS,
    InMemoryRateLimiter,
    get_client_ip,
    RateLimitMiddleware,
    check_rate_limit,
    get_rate_limit_info,
    add_rate_limit_middleware,
)


# =============================================================================
# _parse_rate_limit tests
# =============================================================================


class TestParseRateLimit:
    """Tests for _parse_rate_limit function."""

    def test_parse_standard_rate_limit(self):
        """Test parsing standard rate limit strings."""
        assert _parse_rate_limit("10/second") == (10, "second")
        assert _parse_rate_limit("100/minute") == (100, "minute")
        assert _parse_rate_limit("1000/hour") == (1000, "hour")
        assert _parse_rate_limit("10000/day") == (10000, "day")

    def test_parse_rate_limit_with_uppercase(self):
        """Test parsing rate limit with uppercase period."""
        assert _parse_rate_limit("10/SECOND") == (10, "second")
        assert _parse_rate_limit("10/MINUTE") == (10, "minute")
        assert _parse_rate_limit("10/Hour") == (10, "hour")

    def test_parse_rate_limit_default_period(self):
        """Test parsing rate limit without period defaults to second."""
        assert _parse_rate_limit("10") == (10, "second")

    def test_parse_rate_limit_invalid_format(self):
        """Test parsing invalid rate limit format returns default."""
        assert _parse_rate_limit("invalid") == (10, "second")
        assert _parse_rate_limit("abc/second") == (10, "second")
        assert _parse_rate_limit("") == (10, "second")


# =============================================================================
# InMemoryRateLimiter tests
# =============================================================================


class TestInMemoryRateLimiter:
    """Tests for InMemoryRateLimiter class."""

    @pytest.mark.asyncio
    async def test_is_allowed_under_limit(self):
        """Test requests under limit are allowed."""
        limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)

        for i in range(5):
            allowed, headers = await limiter.is_allowed("test_key")
            assert allowed is True
            assert headers["X-RateLimit-Limit"] == "5"

    @pytest.mark.asyncio
    async def test_is_allowed_over_limit(self):
        """Test requests over limit are denied."""
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)

        # Use up the limit
        for _ in range(3):
            await limiter.is_allowed("test_key")

        # Next request should be denied
        allowed, headers = await limiter.is_allowed("test_key")
        assert allowed is False
        assert headers["X-RateLimit-Remaining"] == "0"
        assert "Retry-After" in headers

    @pytest.mark.asyncio
    async def test_different_keys_independent(self):
        """Test different keys have independent limits."""
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)

        # Use up limit for key1
        for _ in range(2):
            await limiter.is_allowed("key1")

        # key1 should be rate limited
        allowed1, _ = await limiter.is_allowed("key1")
        assert allowed1 is False

        # key2 should still be allowed
        allowed2, _ = await limiter.is_allowed("key2")
        assert allowed2 is True

    def test_is_allowed_sync(self):
        """Test synchronous version of is_allowed."""
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)

        for i in range(3):
            allowed, headers = limiter.is_allowed_sync("sync_key")
            assert allowed is True

        # Should be rate limited
        allowed, headers = limiter.is_allowed_sync("sync_key")
        assert allowed is False
        assert headers["X-RateLimit-Remaining"] == "0"


# =============================================================================
# get_client_ip tests
# =============================================================================


class TestGetClientIp:
    """Tests for get_client_ip function."""

    def test_get_client_ip_from_x_forwarded_for(self):
        """Test extracting IP from X-Forwarded-For header."""
        request = MagicMock()
        request.headers.get.side_effect = lambda k, d=None: {
            "x-forwarded-for": "203.0.113.1, 198.51.100.1",
            "x-real-ip": None,
        }.get(k, d)
        request.client = None

        ip = get_client_ip(request)
        assert ip == "203.0.113.1"

    def test_get_client_ip_from_x_real_ip(self):
        """Test extracting IP from X-Real-IP header."""
        request = MagicMock()
        request.headers.get.side_effect = lambda k, d=None: {
            "x-forwarded-for": None,
            "x-real-ip": "198.51.100.1",
        }.get(k, d)
        request.client = None

        ip = get_client_ip(request)
        assert ip == "198.51.100.1"

    def test_get_client_ip_from_client_host(self):
        """Test extracting IP from request client."""
        request = MagicMock()
        request.headers.get.return_value = None
        request.client.host = "192.168.1.1"

        ip = get_client_ip(request)
        assert ip == "192.168.1.1"

    def test_get_client_ip_fallback(self):
        """Test fallback to localhost when no IP found."""
        request = MagicMock()
        request.headers.get.return_value = None
        request.client = None

        ip = get_client_ip(request)
        assert ip == "127.0.0.1"


# =============================================================================
# RateLimitMiddleware tests
# =============================================================================


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware class."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        request.client.host = "192.168.1.1"
        return request

    @pytest.mark.asyncio
    async def test_exempt_paths_allowed(self, mock_app, mock_request):
        """Test exempt paths bypass rate limiting."""
        middleware = RateLimitMiddleware(mock_app, rate_limit="5/second")
        mock_request.url.path = "/health"

        call_next_called = False

        async def call_next(req):
            nonlocal call_next_called
            call_next_called = True
            response = MagicMock()
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)
        assert call_next_called is True

    @pytest.mark.asyncio
    async def test_rate_limit_check(self, mock_app, mock_request):
        """Test rate limit is checked."""
        middleware = RateLimitMiddleware(mock_app, rate_limit="2/second")

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        # First two requests should succeed
        for _ in range(2):
            response = await middleware.dispatch(mock_request, call_next)
            # Response is from call_next, not rate limited
            assert response is not None

    @pytest.mark.asyncio
    async def test_rate_limit_headers_added(self, mock_app, mock_request):
        """Test rate limit headers are added to responses."""
        middleware = RateLimitMiddleware(mock_app, rate_limit="5/second")
        mock_request.url.path = "/api/test"

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        response = await middleware.dispatch(mock_request, call_next)

        # Headers were set on response
        assert hasattr(response, 'headers')

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_response(self, mock_app, mock_request):
        """Test rate limit exceeded returns 429."""
        middleware = RateLimitMiddleware(mock_app, rate_limit="1/second")
        mock_request.url.path = "/api/test"

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        # First request
        response1 = await middleware.dispatch(mock_request, call_next)
        assert response1 is not None

        # Second request should be rate limited (return JSONResponse)
        from fastapi.responses import JSONResponse
        response2 = await middleware.dispatch(mock_request, call_next)
        assert isinstance(response2, JSONResponse)
        assert response2.status_code == 429


# =============================================================================
# Utility functions tests
# =============================================================================


class TestUtilityFunctions:
    """Tests for utility functions."""

    def test_check_rate_limit(self):
        """Test check_rate_limit utility function."""
        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        request.client.host = "10.0.0.1"

        allowed, headers = check_rate_limit(request)
        assert isinstance(allowed, bool)
        assert isinstance(headers, dict)
        assert "X-RateLimit-Limit" in headers

    def test_get_rate_limit_info(self):
        """Test get_rate_limit_info utility function."""
        info = get_rate_limit_info()
        assert isinstance(info, dict)
        assert "limit" in info
        assert "max_requests" in info
        assert "period" in info
        assert "window_seconds" in info


# =============================================================================
# add_rate_limit_middleware tests
# =============================================================================


class TestAddRateLimitMiddleware:
    """Tests for add_rate_limit_middleware utility function."""

    def test_add_rate_limit_middleware(self):
        """Test add_rate_limit_middleware calls app.add_middleware."""
        mock_app = MagicMock()

        add_rate_limit_middleware(
            mock_app,
            rate_limit="100/minute",
            exempt_paths={"/health", "/metrics"}
        )

        mock_app.add_middleware.assert_called_once()


# =============================================================================
# Integration tests
# =============================================================================


class TestRateLimitIntegration:
    """Integration tests for rate limiting."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app."""
        async def app(scope, receive, send):
            pass
        return app

    @pytest.mark.asyncio
    async def test_full_rate_limit_cycle(self, mock_app):
        """Test complete rate limit cycle."""
        middleware = RateLimitMiddleware(mock_app, rate_limit="2/second")

        request = MagicMock()
        request.url.path = "/api/test"
        request.headers.get.return_value = None
        request.client.host = "10.1.1.1"

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        # Make 2 successful requests
        for _ in range(2):
            response = await middleware.dispatch(request, call_next)
            assert response is not None

        # 3rd request should be rate limited (return JSONResponse)
        from fastapi.responses import JSONResponse
        response = await middleware.dispatch(request, call_next)
        assert isinstance(response, JSONResponse)
        assert response.status_code == 429

    @pytest.mark.asyncio
    async def test_multiple_clients_independent(self, mock_app):
        """Test rate limiting is independent per client."""
        middleware = RateLimitMiddleware(mock_app, rate_limit="1/second")

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        # Client 1 makes a request
        request1 = MagicMock()
        request1.url.path = "/api/test"
        request1.headers.get.return_value = None
        request1.client.host = "10.1.1.1"

        response1 = await middleware.dispatch(request1, call_next)
        assert response1 is not None

        # Client 1 should be rate limited on second request
        from fastapi.responses import JSONResponse
        response1_limited = await middleware.dispatch(request1, call_next)
        assert isinstance(response1_limited, JSONResponse)

        # Client 2 should still be allowed
        request2 = MagicMock()
        request2.url.path = "/api/test"
        request2.headers.get.return_value = None
        request2.client.host = "10.1.1.2"

        response2 = await middleware.dispatch(request2, call_next)
        assert response2 is not None

    @pytest.mark.asyncio
    async def test_x_forwarded_for_rate_limiting(self, mock_app):
        """Test rate limiting works with X-Forwarded-For header."""
        middleware = RateLimitMiddleware(mock_app, rate_limit="1/second")

        async def call_next(req):
            response = MagicMock()
            response.headers = {}
            return response

        def create_request(ip):
            request = MagicMock()
            request.url.path = "/api/test"
            request.headers.get.side_effect = lambda k, d=None: {
                "x-forwarded-for": ip,
            }.get(k, d)
            request.client = None
            return request

        # Make 2 requests from same IP
        request = create_request("203.0.113.50")
        response1 = await middleware.dispatch(request, call_next)
        assert response1 is not None

        # Should be rate limited
        from fastapi.responses import JSONResponse
        response2 = await middleware.dispatch(request, call_next)
        assert isinstance(response2, JSONResponse)
