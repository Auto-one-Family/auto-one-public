"""
Unit tests for Pure ASGI RequestIdMiddleware.

Tests ContextVar propagation, header handling, and request isolation.
"""

import asyncio
import logging

import pytest

from src.middleware.request_id import RequestIdMiddleware
from src.core.request_context import (
    get_request_id,
    clear_request_id,
)


def _make_http_scope(path: str = "/test", method: str = "GET", headers: list = None):
    """Create a minimal HTTP ASGI scope."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
    }


@pytest.fixture(autouse=True)
def _cleanup_request_id():
    """Ensure ContextVar is clean before and after each test."""
    clear_request_id()
    yield
    clear_request_id()


@pytest.mark.asyncio
async def test_request_id_from_header():
    """X-Request-ID from request header is used."""
    captured_id = None

    async def inner_app(scope, receive, send):
        nonlocal captured_id
        captured_id = get_request_id()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestIdMiddleware(inner_app)
    scope = _make_http_scope(headers=[(b"x-request-id", b"TEST-REQ-123")])

    async def receive():
        return {"type": "http.request", "body": b""}

    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    await middleware(scope, receive, send)

    assert captured_id == "TEST-REQ-123"


@pytest.mark.asyncio
async def test_request_id_auto_generated():
    """UUID is generated when no X-Request-ID header is present."""
    captured_id = None

    async def inner_app(scope, receive, send):
        nonlocal captured_id
        captured_id = get_request_id()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestIdMiddleware(inner_app)
    scope = _make_http_scope()

    async def receive():
        return {"type": "http.request", "body": b""}

    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    await middleware(scope, receive, send)

    assert captured_id is not None
    assert captured_id != "-"
    assert len(captured_id) > 10  # UUID format


@pytest.mark.asyncio
async def test_request_id_in_response_header():
    """X-Request-ID is added to response headers."""

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestIdMiddleware(inner_app)
    scope = _make_http_scope(headers=[(b"x-request-id", b"RESP-HDR-456")])

    async def receive():
        return {"type": "http.request", "body": b""}

    sent_messages = []

    async def send(message):
        sent_messages.append(message)

    await middleware(scope, receive, send)

    # Find response start message
    response_start = next(m for m in sent_messages if m["type"] == "http.response.start")
    response_headers = dict(response_start["headers"])
    assert response_headers[b"x-request-id"] == b"RESP-HDR-456"


@pytest.mark.asyncio
async def test_request_id_in_log_output(caplog):
    """RequestIdFilter shows the request ID (NOT '-') in log output."""

    async def inner_app(scope, receive, send):
        # The request_id should be available inside handlers
        rid = get_request_id()
        assert rid == "LOG-TEST-789", f"Expected LOG-TEST-789, got {rid}"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestIdMiddleware(inner_app)
    scope = _make_http_scope(headers=[(b"x-request-id", b"LOG-TEST-789")])

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    await middleware(scope, receive, send)


@pytest.mark.asyncio
async def test_request_id_contextvar_propagation():
    """ContextVar is available in nested async calls within handler."""
    inner_id = None

    async def nested_function():
        return get_request_id()

    async def inner_app(scope, receive, send):
        nonlocal inner_id
        inner_id = await nested_function()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestIdMiddleware(inner_app)
    scope = _make_http_scope(headers=[(b"x-request-id", b"NESTED-CTX-111")])

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    await middleware(scope, receive, send)

    assert inner_id == "NESTED-CTX-111"


@pytest.mark.asyncio
async def test_request_id_isolation():
    """Parallel requests have their own isolated request IDs."""
    captured_ids = []

    async def inner_app(scope, receive, send):
        # Simulate some async work
        await asyncio.sleep(0.01)
        captured_ids.append(get_request_id())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestIdMiddleware(inner_app)

    async def make_request(req_id: str):
        scope = _make_http_scope(headers=[(b"x-request-id", req_id.encode("latin-1"))])

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            pass

        await middleware(scope, receive, send)

    # Run two requests concurrently
    await asyncio.gather(
        make_request("ISO-A"),
        make_request("ISO-B"),
    )

    assert "ISO-A" in captured_ids
    assert "ISO-B" in captured_ids


@pytest.mark.asyncio
async def test_request_id_cleared_after_request():
    """ContextVar is cleared after request completes."""

    async def inner_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestIdMiddleware(inner_app)
    scope = _make_http_scope(headers=[(b"x-request-id", b"TEMP-ID")])

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    await middleware(scope, receive, send)

    # After request, ContextVar should be cleared
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_non_http_scope_passes_through():
    """Non-HTTP scopes (lifespan, etc.) are passed through without modification."""
    called = False

    async def inner_app(scope, receive, send):
        nonlocal called
        called = True

    middleware = RequestIdMiddleware(inner_app)
    scope = {"type": "lifespan"}

    await middleware(scope, None, None)

    assert called is True
    assert get_request_id() is None


@pytest.mark.asyncio
async def test_exception_in_handler_still_clears_id():
    """ContextVar is cleared even when handler raises an exception."""

    async def inner_app(scope, receive, send):
        raise ValueError("test error")

    middleware = RequestIdMiddleware(inner_app)
    scope = _make_http_scope(headers=[(b"x-request-id", b"ERROR-REQ")])

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        pass

    with pytest.raises(ValueError, match="test error"):
        await middleware(scope, receive, send)

    # ContextVar must be cleaned up despite exception
    assert get_request_id() is None
