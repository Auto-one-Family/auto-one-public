"""
Pure ASGI middleware for request_id generation and tracking.

Uses raw ASGI interface instead of BaseHTTPMiddleware to ensure
ContextVar propagation works correctly across async boundaries.
BaseHTTPMiddleware creates an anyio.TaskGroup that does NOT inherit
ContextVars from the outer scope (Starlette Issue #1012).

Generates a UUID for each incoming HTTP request, stores it in a
context variable (accessible by loggers and services), and adds
an X-Request-ID header to the response.

If the client sends a W3C **traceparent** header (optional), it is kept in a
ContextVar, echoed on the HTTP response, and may appear in structured JSON logs.
"""

import time
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

from ..core.metrics import increment_http_error
from ..core.request_context import (
    generate_request_id,
    set_request_id,
    clear_request_id,
    set_traceparent,
    clear_traceparent,
    get_traceparent,
)

logger = logging.getLogger(__name__)


class RequestIdMiddleware:
    """Pure ASGI middleware for request ID propagation.

    - Accepts X-Request-ID from client or generates a new UUID
    - Optionally accepts traceparent; stores in ContextVar; echoes on HTTP response
    - Stores in ContextVar (for logging and audit)
    - Adds X-Request-ID header to response
    - Logs request completion with method, path, status, and duration
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract X-Request-ID and optional traceparent from headers
        request_id = None
        incoming_traceparent = None
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"x-request-id" and request_id is None:
                request_id = header_value.decode("latin-1")
            elif header_name == b"traceparent" and incoming_traceparent is None:
                incoming_traceparent = header_value.decode("latin-1")

        if not request_id:
            request_id = generate_request_id()

        # Set ContextVar BEFORE calling inner app — this is the key fix.
        # In pure ASGI, the inner app runs in the SAME coroutine context,
        # so ContextVars propagate correctly to all handlers and filters.
        token = set_request_id(request_id)
        tp_token = set_traceparent(incoming_traceparent)

        # Extract method and path for logging
        method = scope.get("method", "WS")
        path = scope.get("path", "/")
        start_time = time.monotonic()

        status_code = None

        async def send_with_request_id(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                tp_out = get_traceparent()
                if tp_out:
                    headers.append((b"traceparent", tp_out.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)

            # Log request completion (HTTP only, not WebSocket upgrades)
            if scope["type"] == "http" and status_code is not None:
                duration_ms = (time.monotonic() - start_time) * 1000
                logger.info(
                    "Request completed: %s %s status=%d duration=%.1fms",
                    method,
                    path,
                    status_code,
                    duration_ms,
                )
                if status_code >= 400:
                    increment_http_error(status_code)

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Request failed: %s %s error=%s duration=%.1fms",
                method,
                path,
                str(e),
                duration_ms,
            )
            raise

        finally:
            clear_traceparent(tp_token)
            clear_request_id(token)
