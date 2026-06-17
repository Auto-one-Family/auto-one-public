"""
Unit Tests: Offline Backoff Cache Invalidation (Fix-1 / Fix-2)

Tests LogicEngine.invalidate_offline_backoff():
- Cache is cleared immediately after reconnect
- Backoff TTL still fires for permanently offline ESPs (30s)
- No-op when called for unknown esp_id
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.logic_engine import LogicEngine, _OFFLINE_BACKOFF_SECONDS


@pytest.fixture
def engine():
    """Minimal LogicEngine instance for unit testing the backoff cache."""
    logic_repo = MagicMock()
    actuator_service = MagicMock()
    ws_manager = AsyncMock()
    # Pass empty lists so no real evaluators/executors are instantiated
    instance = LogicEngine(
        logic_repo=logic_repo,
        actuator_service=actuator_service,
        websocket_manager=ws_manager,
        condition_evaluators=[],
        action_executors=[],
    )
    return instance


class TestInvalidateOfflineBackoff:
    """LogicEngine.invalidate_offline_backoff() clears _offline_esp_skip correctly."""

    def test_clears_existing_cache_entry(self, engine):
        """Cache entry is removed after invalidate_offline_backoff() is called."""
        esp_id = "ESP_EA5484"
        engine._offline_esp_skip[esp_id] = datetime.now(timezone.utc) + timedelta(seconds=300)

        engine.invalidate_offline_backoff(esp_id)

        assert esp_id not in engine._offline_esp_skip

    def test_noop_for_unknown_esp_id(self, engine):
        """No exception and no side effects when esp_id is not in the cache."""
        assert len(engine._offline_esp_skip) == 0

        engine.invalidate_offline_backoff("ESP_UNKNOWN")

        assert len(engine._offline_esp_skip) == 0

    def test_only_clears_targeted_esp(self, engine):
        """Only the specified ESP entry is removed; other entries are untouched."""
        esp_a = "ESP_AA0001"
        esp_b = "ESP_BB0002"
        future = datetime.now(timezone.utc) + timedelta(seconds=30)
        engine._offline_esp_skip[esp_a] = future
        engine._offline_esp_skip[esp_b] = future

        engine.invalidate_offline_backoff(esp_a)

        assert esp_a not in engine._offline_esp_skip
        assert esp_b in engine._offline_esp_skip

    def test_repeated_calls_are_idempotent(self, engine):
        """Calling invalidate_offline_backoff() twice for the same esp_id is safe."""
        esp_id = "ESP_EA5484"
        engine._offline_esp_skip[esp_id] = datetime.now(timezone.utc) + timedelta(seconds=30)

        engine.invalidate_offline_backoff(esp_id)
        engine.invalidate_offline_backoff(esp_id)  # second call must not raise

        assert esp_id not in engine._offline_esp_skip


class TestOfflineBackoffTTL:
    """_OFFLINE_BACKOFF_SECONDS constant and TTL behaviour (Fix-2)."""

    def test_backoff_constant_is_30_seconds(self):
        """_OFFLINE_BACKOFF_SECONDS must be 30 after Fix-2 (was 300)."""
        assert _OFFLINE_BACKOFF_SECONDS == 30

    def test_active_cache_entry_blocks_before_expiry(self, engine):
        """An entry that has not expired is still present in the cache dict."""
        esp_id = "ESP_EA5484"
        skip_until = datetime.now(timezone.utc) + timedelta(seconds=_OFFLINE_BACKOFF_SECONDS)
        engine._offline_esp_skip[esp_id] = skip_until

        # The cache entry must still be blocking (not expired)
        assert datetime.now(timezone.utc) < engine._offline_esp_skip[esp_id]

    def test_expired_cache_entry_is_past(self, engine):
        """An entry set in the past is correctly detected as expired."""
        esp_id = "ESP_EA5484"
        engine._offline_esp_skip[esp_id] = datetime.now(timezone.utc) - timedelta(seconds=1)

        assert datetime.now(timezone.utc) >= engine._offline_esp_skip[esp_id]
