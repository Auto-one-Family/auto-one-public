"""
Unit Tests: NotificationCreate source validation for lifecycle reminders.

AUT-36: Validates that freshness_reminder and calibration_reminder are accepted
as valid notification sources by the Pydantic schema, and that unknown sources
are rejected by the field_validator.

Related: src/schemas/notification.py — NOTIFICATION_SOURCES, NotificationCreate
"""

import pytest
from pydantic import ValidationError

from src.schemas.notification import NOTIFICATION_SOURCES, NotificationCreate

# =============================================================================
# Helpers
# =============================================================================

_VALID_BASE = {
    "title": "Sensor lifecycle alert",
    "severity": "warning",
    "category": "lifecycle",
}


def make_notification(**kwargs) -> NotificationCreate:
    """Build a NotificationCreate with minimal valid defaults."""
    return NotificationCreate(**{**_VALID_BASE, **kwargs})


# =============================================================================
# Test: lifecycle reminder sources accepted
# =============================================================================


class TestLifecycleReminderSources:
    """AUT-36: freshness_reminder and calibration_reminder must be valid sources."""

    def test_freshness_reminder_accepted(self):
        """NotificationCreate accepts source='freshness_reminder'."""
        n = make_notification(source="freshness_reminder")
        assert n.source == "freshness_reminder"

    def test_calibration_reminder_accepted(self):
        """NotificationCreate accepts source='calibration_reminder'."""
        n = make_notification(source="calibration_reminder")
        assert n.source == "calibration_reminder"

    def test_freshness_reminder_in_sources_list(self):
        """freshness_reminder is present in the canonical NOTIFICATION_SOURCES list."""
        assert "freshness_reminder" in NOTIFICATION_SOURCES

    def test_calibration_reminder_in_sources_list(self):
        """calibration_reminder is present in the canonical NOTIFICATION_SOURCES list."""
        assert "calibration_reminder" in NOTIFICATION_SOURCES


# =============================================================================
# Test: unknown source rejected
# =============================================================================


class TestUnknownSourceRejected:
    """Negative case: unknown sources must be rejected by the validator."""

    def test_unknown_source_raises_validation_error(self):
        """An unregistered source string is rejected with ValidationError."""
        with pytest.raises(ValidationError, match="source must be one of"):
            make_notification(source="nonexistent_source")

    def test_empty_source_raises_validation_error(self):
        """An empty-string source is rejected (not in NOTIFICATION_SOURCES)."""
        with pytest.raises(ValidationError, match="source must be one of"):
            make_notification(source="")


# =============================================================================
# Test: existing sources still work (regression guard)
# =============================================================================


class TestExistingSourcesRegression:
    """Ensure pre-existing sources are not broken by lifecycle additions."""

    @pytest.mark.parametrize(
        "source",
        ["logic_engine", "mqtt_handler", "sensor_threshold", "device_event", "system", "manual"],
    )
    def test_established_source_accepted(self, source: str):
        """Pre-existing sources remain valid after NOTIFICATION_SOURCES extension."""
        n = make_notification(source=source)
        assert n.source == source
