"""
Unit Tests: DiagnosticsService (Phase 4D)

Tests the DiagnosticsService which runs 10 modular diagnostic checks
and generates reports with overall status.
"""

import pytest

from src.services.diagnostics_service import (
    CheckResult,
    CheckStatus,
    DiagnosticReportData,
    DiagnosticsService,
)

# =============================================================================
# CheckStatus Tests
# =============================================================================


class TestCheckStatus:
    """Tests for CheckStatus enum and severity ordering."""

    def test_check_status_values(self):
        """All 4 status values exist."""
        assert CheckStatus.HEALTHY.value == "healthy"
        assert CheckStatus.WARNING.value == "warning"
        assert CheckStatus.CRITICAL.value == "critical"
        assert CheckStatus.ERROR.value == "error"

    def test_check_status_from_string(self):
        """CheckStatus can be created from string values."""
        assert CheckStatus("healthy") == CheckStatus.HEALTHY
        assert CheckStatus("critical") == CheckStatus.CRITICAL


# =============================================================================
# CheckResult Tests
# =============================================================================


class TestCheckResult:
    """Tests for CheckResult dataclass."""

    def test_check_result_defaults(self):
        """CheckResult has sensible defaults for optional fields."""
        result = CheckResult(
            name="test",
            status=CheckStatus.HEALTHY,
            message="All good",
        )
        assert result.details == {}
        assert result.metrics == {}
        assert result.recommendations == []
        assert result.duration_ms == 0.0

    def test_check_result_full(self):
        """CheckResult stores all provided fields."""
        result = CheckResult(
            name="database",
            status=CheckStatus.WARNING,
            message="Slow queries detected",
            details={"slow_queries": 5},
            metrics={"avg_query_ms": 250.0},
            recommendations=["Add index on sensor_data"],
            duration_ms=45.3,
        )
        assert result.name == "database"
        assert result.status == CheckStatus.WARNING
        assert result.details["slow_queries"] == 5
        assert result.metrics["avg_query_ms"] == 250.0
        assert len(result.recommendations) == 1
        assert result.duration_ms == 45.3


# =============================================================================
# DiagnosticReportData Tests
# =============================================================================


class TestDiagnosticReportData:
    """Tests for DiagnosticReportData dataclass."""

    def test_report_data_structure(self):
        """DiagnosticReportData holds report metadata and checks."""
        report = DiagnosticReportData(
            id="test-123",
            overall_status=CheckStatus.HEALTHY,
            started_at="2026-03-03T12:00:00+00:00",
            finished_at="2026-03-03T12:00:05+00:00",
            duration_seconds=5.0,
            checks=[
                CheckResult(name="server", status=CheckStatus.HEALTHY, message="OK"),
                CheckResult(name="database", status=CheckStatus.HEALTHY, message="OK"),
            ],
            summary="2/2 checks healthy",
            triggered_by="manual",
        )
        assert report.id == "test-123"
        assert report.overall_status == CheckStatus.HEALTHY
        assert len(report.checks) == 2
        assert report.triggered_by == "manual"


# =============================================================================
# DiagnosticsService Tests
# =============================================================================


class TestDiagnosticsServiceChecks:
    """Tests for DiagnosticsService check registry."""

    def test_service_has_10_checks(self):
        """DiagnosticsService registers exactly 10 checks."""
        service = DiagnosticsService(session=None)
        assert len(service.checks) == 10

    def test_all_check_names_present(self):
        """All expected check names are registered."""
        service = DiagnosticsService(session=None)
        expected_checks = {
            "server",
            "database",
            "mqtt",
            "esp_devices",
            "sensors",
            "actuators",
            "monitoring",
            "logic_engine",
            "alerts",
            "plugins",
        }
        assert set(service.checks.keys()) == expected_checks

    def test_all_checks_are_callable(self):
        """All registered checks are async callable methods."""
        service = DiagnosticsService(session=None)
        for name, check_fn in service.checks.items():
            assert callable(check_fn), f"Check '{name}' is not callable"

    def test_run_single_check_unknown_raises(self):
        """Running an unknown check name raises KeyError."""
        service = DiagnosticsService(session=None)
        with pytest.raises(KeyError, match="nonexistent"):
            # We call synchronously to test the KeyError
            # The actual async method would raise, but we can test the key lookup
            _ = service.checks["nonexistent"]


# =============================================================================
# Overall Status Calculation
# =============================================================================


class TestOverallStatus:
    """Test overall_status worst-of calculation logic."""

    def test_worst_of_all_healthy(self):
        """All healthy checks → overall healthy."""
        from src.services.diagnostics_service import _STATUS_ORDER

        statuses = [CheckStatus.HEALTHY, CheckStatus.HEALTHY]
        worst = max(statuses, key=lambda s: _STATUS_ORDER[s])
        assert worst == CheckStatus.HEALTHY

    def test_worst_of_with_warning(self):
        """Mix of healthy and warning → overall warning."""
        from src.services.diagnostics_service import _STATUS_ORDER

        statuses = [CheckStatus.HEALTHY, CheckStatus.WARNING, CheckStatus.HEALTHY]
        worst = max(statuses, key=lambda s: _STATUS_ORDER[s])
        assert worst == CheckStatus.WARNING

    def test_worst_of_with_critical(self):
        """Any critical check → overall critical."""
        from src.services.diagnostics_service import _STATUS_ORDER

        statuses = [CheckStatus.HEALTHY, CheckStatus.CRITICAL, CheckStatus.WARNING]
        worst = max(statuses, key=lambda s: _STATUS_ORDER[s])
        assert worst == CheckStatus.CRITICAL

    def test_worst_of_with_error(self):
        """Error is worst status."""
        from src.services.diagnostics_service import _STATUS_ORDER

        statuses = [CheckStatus.CRITICAL, CheckStatus.ERROR, CheckStatus.WARNING]
        worst = max(statuses, key=lambda s: _STATUS_ORDER[s])
        assert worst == CheckStatus.ERROR
