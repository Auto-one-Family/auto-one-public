"""
Frontend Log Ingestion Endpoint

Receives error logs from the Vue 3 frontend via HTTP POST.
Solves the browser-console blind spot for debugging agents.

Endpoint:
- POST /logs/frontend - Accept frontend error reports (no auth, rate-limited)

The endpoint is intentionally unauthenticated (fire-and-forget from browser).
Rate limiting prevents log flooding.
"""

import re
import time
from typing import Optional

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field

from ...core.logging_config import get_logger

# Strip newlines and ANSI escape sequences to prevent log-injection attacks.
_CONTROL_CHARS = re.compile(r"[\r\n\x00-\x1f\x7f]|\x1b\[[0-9;]*[A-Za-z]")


def _sanitize(value: str) -> str:
    """Remove control characters and ANSI escapes from a log field."""
    return _CONTROL_CHARS.sub(" ", value)


router = APIRouter(prefix="/v1/logs", tags=["logs"])

# Rate limiting: max 10 requests per minute per IP
_rate_limit_store: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60.0  # seconds
RATE_LIMIT_MAX = 10  # requests per window

# Dedicated logger namespace for frontend errors
frontend_logger = get_logger("frontend.error")


class FrontendLogEntry(BaseModel):
    """Schema for frontend error log entries."""

    level: str = Field(
        default="error",
        description="Log level: debug, info, warn, error",
    )
    component: str = Field(
        default="unknown",
        description="Vue component name",
        max_length=100,
    )
    message: str = Field(
        description="Error message",
        max_length=2000,
    )
    stack: Optional[str] = Field(
        default=None,
        description="Error stack trace",
        max_length=5000,
    )
    info: Optional[str] = Field(
        default=None,
        description="Vue error info string",
        max_length=500,
    )
    url: Optional[str] = Field(
        default=None,
        description="Page URL where error occurred",
        max_length=500,
    )
    timestamp: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp from browser",
    )


def _check_rate_limit(client_ip: str) -> bool:
    """Check if client IP is within rate limit. Returns True if allowed."""
    now = time.time()
    if client_ip not in _rate_limit_store:
        _rate_limit_store[client_ip] = []

    # Remove expired entries
    _rate_limit_store[client_ip] = [
        ts for ts in _rate_limit_store[client_ip] if now - ts < RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_MAX:
        return False

    _rate_limit_store[client_ip].append(now)
    return True


@router.post(
    "/frontend",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Receive frontend error logs",
    description="Fire-and-forget endpoint for Vue 3 error handler. No auth required.",
)
async def receive_frontend_log(entry: FrontendLogEntry, request: Request) -> Response:
    """
    Receive and log a frontend error report.

    Rate-limited to 10 requests/minute per IP to prevent flooding.
    Logs are written to the server log with [FRONTEND] prefix for easy filtering.
    """
    client_ip = request.client.host if request.client else "unknown"

    if not _check_rate_limit(client_ip):
        return Response(status_code=status.HTTP_429_TOO_MANY_REQUESTS)

    # Sanitize all free-text fields before logging to prevent log-injection
    # (newlines, ANSI codes) from unauthenticated callers.
    component = _sanitize(entry.component)
    message = _sanitize(entry.message)
    url = _sanitize(entry.url or "-")
    info = _sanitize(entry.info or "-")

    # Build log message with structured context
    log_msg = f"[FRONTEND] [{component}] {message}" f" (url: {url}, info: {info})"

    # Log at appropriate level
    level = entry.level.lower()
    if level == "error":
        frontend_logger.error(log_msg)
        if entry.stack:
            frontend_logger.error(f"[FRONTEND] [{component}] Stack: {_sanitize(entry.stack)}")
    elif level == "warn":
        frontend_logger.warning(log_msg)
    elif level == "info":
        frontend_logger.info(log_msg)
    else:
        frontend_logger.debug(log_msg)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
