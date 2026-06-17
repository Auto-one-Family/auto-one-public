"""Compatibility shim for ``api.dependencies`` (AUT-224 A5).

The previous module shipped its own simplified ``RateLimiter``/``verify_api_key``/
``check_rate_limit`` implementations. These have been consolidated into
``api.deps`` (with Redis fallback, debug-mode guard, and stricter typing).

This module is now a *thin re-export* so external imports such as
``from src.api.dependencies import check_rate_limit, verify_api_key`` keep
working without dragging the legacy duplicates along. New code should import
directly from :mod:`src.api.deps`.

Removed (intentionally):
- ``RateLimiter`` class — replaced by ``InMemoryRateLimiter`` /
  ``RedisRateLimiter`` in :mod:`src.api.deps`.
- ``rate_limiter`` global instance — replaced by ``_rate_limiter`` in
  :mod:`src.api.deps`.
"""

from .deps import check_rate_limit, verify_api_key

__all__ = [
    "check_rate_limit",
    "verify_api_key",
]
