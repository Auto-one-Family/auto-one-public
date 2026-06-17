"""
Unit tests for SensorDataHandler._try_get_atc_temperature() — AUT-672 SOLL-Matrix.

Covers all scenarios from the AUT-672 behaviour matrix for both Priority-1
(explicit temp_sensor_config_id link) and Priority-2 (same-ESP auto-discovery).

Scenarios tested (explicit-link):
  P1-A: No reading ever (reading is None)                → (None, "default_25c")
  P1-B: Reading present, processed_value is None         → (None, "default_25c")
  P1-C: Reading age < FRESH_AGE (5 s)                   → (temp, "config:<uuid>")
  P1-D: Reading FRESH_AGE ≤ age < MAX_AGE (5s–5min)     → (temp, "cached_temp")
  P1-E: Reading age ≥ MAX_AGE (> 5 min)                 → (None, "default_25c_degraded")

Scenarios tested (auto-discovery):
  P2-A: No reading on ESP                                → (None, "default_25c")
  P2-B: Reading age < FRESH_AGE                          → (temp, "same_esp")
  P2-C: Reading FRESH_AGE ≤ age < MAX_AGE                → (temp, "cached_temp")
  P2-D: Reading age ≥ MAX_AGE (Ghost-fix: silent)        → (None, "default_25c")

No-sensor scenario:
  NS-A: sensor_config is None                            → (None, "default_25c")
  NS-B: sensor_config.temp_sensor_config_id is None      → falls through to P2 path
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: F401

import pytest

from src.mqtt.handlers.sensor_handler import SensorDataHandler

# ─── Helpers ─────────────────────────────────────────────────────────────────

FRESH_AGE = timedelta(seconds=5)
MAX_AGE = timedelta(minutes=5)
NOW = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)


def _make_reading(*, age: timedelta | None, value: float | None = 22.5):
    """Return a mock SensorData reading with the given age and processed_value."""
    if age is None:
        return None
    reading = MagicMock()
    reading.timestamp = NOW - age
    reading.processed_value = value
    return reading


def _make_sensor_config(*, temp_sensor_config_id=None):
    cfg = MagicMock()
    cfg.temp_sensor_config_id = temp_sensor_config_id
    return cfg


def _make_linked_config(esp_id="ESP_TEST", gpio=4, sensor_type="temperature"):
    cfg = MagicMock()
    cfg.esp_id = esp_id
    cfg.gpio = gpio
    cfg.sensor_type = sensor_type
    return cfg


def _make_esp_device(esp_id="ESP_TEST"):
    dev = MagicMock()
    dev.id = esp_id
    return dev


@pytest.fixture
def handler():
    """SensorDataHandler with mocked publisher (no MQTT needed for unit tests)."""
    return SensorDataHandler(publisher=MagicMock())


# ─── Priority-1: Explicit temp_sensor_config_id ──────────────────────────────


class TestPriority1ExplicitLink:
    """AUT-672 SOLL-Matrix: Priority-1 scenarios (explicit temp sensor link)."""

    TEMP_UUID = uuid.uuid4()

    def _sensor_config(self):
        return _make_sensor_config(temp_sensor_config_id=self.TEMP_UUID)

    @pytest.mark.asyncio
    async def test_p1a_no_reading_returns_default_25c(self, handler):
        """P1-A: linked sensor configured, never connected → silent 25°C fallback."""
        linked_cfg = _make_linked_config()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = linked_cfg
        mock_repo.get_latest_reading.return_value = None  # never measured

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            result = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config()
            )

        assert result == (None, "default_25c"), f"Expected default_25c, got {result}"

    @pytest.mark.asyncio
    async def test_p1b_value_none_returns_default_25c(self, handler):
        """P1-B: linked sensor reading exists but processed_value is None → silent fallback."""
        linked_cfg = _make_linked_config()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = linked_cfg
        mock_repo.get_latest_reading.return_value = _make_reading(age=timedelta(seconds=10), value=None)

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            result = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config()
            )

        assert result == (None, "default_25c"), f"Expected default_25c, got {result}"

    @pytest.mark.asyncio
    async def test_p1c_fresh_reading_returns_config_label(self, handler):
        """P1-C: linked sensor fresh (age < 5s) → (temp, 'config:<uuid>')."""
        linked_cfg = _make_linked_config()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = linked_cfg
        mock_repo.get_latest_reading.return_value = _make_reading(age=timedelta(seconds=2), value=22.5)

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            temp, source = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config()
            )

        assert temp == pytest.approx(22.5)
        assert source == f"config:{self.TEMP_UUID}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("age_seconds", [10, 90, 270])
    async def test_p1d_stale_within_max_returns_cached_temp(self, handler, age_seconds):
        """P1-D: FRESH_AGE ≤ age < MAX_AGE (5s–5min) → (temp, 'cached_temp')."""
        linked_cfg = _make_linked_config()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = linked_cfg
        mock_repo.get_latest_reading.return_value = _make_reading(
            age=timedelta(seconds=age_seconds), value=19.0
        )

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            temp, source = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config()
            )

        assert temp == pytest.approx(19.0)
        assert source == "cached_temp"

    @pytest.mark.asyncio
    async def test_p1e_expired_beyond_max_returns_degraded(self, handler):
        """P1-E: age >= MAX_AGE (>5 min) → (None, 'default_25c_degraded') + caller emits Warning."""
        linked_cfg = _make_linked_config()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = linked_cfg
        mock_repo.get_latest_reading.return_value = _make_reading(
            age=timedelta(minutes=6), value=21.0
        )

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            result = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config()
            )

        assert result == (None, "default_25c_degraded"), f"Expected degraded signal, got {result}"

    @pytest.mark.asyncio
    async def test_p1_linked_config_not_found_falls_through_to_p2(self, handler):
        """linked_config lookup returns None → fall through to auto-discovery (P2)."""
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None  # config row deleted
        mock_repo.get_latest_reading_for_esp.return_value = None

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            result = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config()
            )

        assert result == (None, "default_25c")


# ─── Priority-2: Same-ESP Auto-Discovery ─────────────────────────────────────


class TestPriority2AutoDiscovery:
    """AUT-672 SOLL-Matrix: Priority-2 scenarios (no explicit link)."""

    def _sensor_config_no_link(self):
        return _make_sensor_config(temp_sensor_config_id=None)

    @pytest.mark.asyncio
    async def test_p2a_no_reading_returns_default_25c(self, handler):
        """P2-A: no temperature reading on this ESP → silent 25°C."""
        mock_repo = AsyncMock()
        mock_repo.get_latest_reading_for_esp.return_value = None

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            result = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config_no_link()
            )

        assert result == (None, "default_25c")

    @pytest.mark.asyncio
    async def test_p2b_fresh_reading_returns_same_esp(self, handler):
        """P2-B: fresh same-ESP reading (age < 5s) → (temp, 'same_esp')."""
        mock_repo = AsyncMock()
        mock_repo.get_latest_reading_for_esp.side_effect = [
            _make_reading(age=timedelta(seconds=3), value=23.0),
            None,
        ]

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            temp, source = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config_no_link()
            )

        assert temp == pytest.approx(23.0)
        assert source == "same_esp"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("age_seconds", [10, 90, 270])
    async def test_p2c_stale_within_max_returns_cached_temp(self, handler, age_seconds):
        """P2-C: FRESH_AGE ≤ age < MAX_AGE → (temp, 'cached_temp') [no abort, ghost-fix]."""
        mock_repo = AsyncMock()
        mock_repo.get_latest_reading_for_esp.side_effect = [
            _make_reading(age=timedelta(seconds=age_seconds), value=20.5),
            None,
        ]

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            temp, source = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config_no_link()
            )

        assert temp == pytest.approx(20.5)
        assert source == "cached_temp"

    @pytest.mark.asyncio
    async def test_p2d_ghost_entry_beyond_max_returns_default_25c(self, handler):
        """P2-D: Ghost-fix — stale DB entry (>5min) is ignored, no read_failed (AUT-672/Edit-3)."""
        mock_repo = AsyncMock()
        mock_repo.get_latest_reading_for_esp.side_effect = [
            _make_reading(age=timedelta(minutes=10), value=18.0),  # too old
            None,
        ]

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            result = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=self._sensor_config_no_link()
            )

        # Ghost-fix: silent fallback, NOT "read_failed"
        assert result == (None, "default_25c"), f"Ghost-fix failed: got {result}"

    @pytest.mark.asyncio
    async def test_p2_no_sensor_config_also_uses_discovery(self, handler):
        """sensor_config=None falls through to auto-discovery and returns default_25c."""
        mock_repo = AsyncMock()
        mock_repo.get_latest_reading_for_esp.return_value = None

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            result = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=None
            )

        assert result == (None, "default_25c")


# ─── "read_failed" is never returned ─────────────────────────────────────────


class TestNoReadFailedReturned:
    """AUT-672: verify "read_failed" is never returned in any scenario."""

    ALL_SCENARIOS = [
        ("no_reading_explicit_link", True),
        ("expired_explicit_link", True),
        ("ghost_auto_discovery", False),
        ("all_expired_both_types", False),
    ]

    @pytest.mark.asyncio
    async def test_expired_linked_never_read_failed(self, handler):
        """Explicit-link sensor expired >5min must return degraded, never read_failed."""
        cfg = _make_sensor_config(temp_sensor_config_id=uuid.uuid4())
        linked = _make_linked_config()
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = linked
        mock_repo.get_latest_reading.return_value = _make_reading(age=timedelta(minutes=10), value=19.0)

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            _, source = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=cfg
            )

        assert source != "read_failed", "'read_failed' must never be returned (AUT-672)"

    @pytest.mark.asyncio
    async def test_ghost_auto_discovery_never_read_failed(self, handler):
        """Auto-discovery with ghost entry >5min must return default_25c, never read_failed."""
        cfg = _make_sensor_config(temp_sensor_config_id=None)
        mock_repo = AsyncMock()
        mock_repo.get_latest_reading_for_esp.side_effect = [
            _make_reading(age=timedelta(hours=1), value=17.0),
            _make_reading(age=timedelta(hours=2), value=16.0),
        ]

        with (
            patch("src.mqtt.handlers.sensor_handler.SensorRepository", return_value=mock_repo),
            patch("src.mqtt.handlers.sensor_handler.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = NOW
            _, source = await handler._try_get_atc_temperature(
                _make_esp_device(), session=AsyncMock(), sensor_config=cfg
            )

        assert source != "read_failed", "'read_failed' must never be returned (AUT-672)"
        assert source == "default_25c"
