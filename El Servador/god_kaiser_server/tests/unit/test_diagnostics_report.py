"""
Unit Tests: Diagnostics Report Generator (Phase 4D)

Tests the Markdown report generation for diagnostic reports.
"""

import pytest

from src.services.diagnostics_report_generator import generate_markdown
from src.services.diagnostics_service import (
    CheckResult,
    CheckStatus,
    DiagnosticReportData,
)

# =============================================================================
# Helper
# =============================================================================


def _make_report(
    checks: list[CheckResult] | None = None,
    overall_status: CheckStatus = CheckStatus.HEALTHY,
) -> DiagnosticReportData:
    """Create a test report with given checks."""
    if checks is None:
        checks = [
            CheckResult(name="server", status=CheckStatus.HEALTHY, message="OK"),
            CheckResult(
                name="database",
                status=CheckStatus.WARNING,
                message="Slow queries",
                metrics={"avg_query_ms": 250.0},
                recommendations=["Add index"],
            ),
        ]
    return DiagnosticReportData(
        id="test-report-001",
        overall_status=overall_status,
        started_at="2026-03-03T12:00:00+00:00",
        finished_at="2026-03-03T12:00:05+00:00",
        duration_seconds=5.0,
        checks=checks,
        summary="Test report",
        triggered_by="manual",
    )


# =============================================================================
# Tests
# =============================================================================


class TestGenerateMarkdown:
    """Tests for generate_markdown() function."""

    def test_generates_non_empty_markdown(self):
        """generate_markdown returns a non-empty string."""
        report = _make_report()
        md = generate_markdown(report)
        assert isinstance(md, str)
        assert len(md) > 100

    def test_contains_status_emojis(self):
        """Generated markdown contains status emojis for different check statuses."""
        checks = [
            CheckResult(name="server", status=CheckStatus.HEALTHY, message="OK"),
            CheckResult(name="mqtt", status=CheckStatus.CRITICAL, message="Offline"),
            CheckResult(name="db", status=CheckStatus.WARNING, message="Slow"),
            CheckResult(name="err", status=CheckStatus.ERROR, message="Failed"),
        ]
        report = _make_report(checks=checks, overall_status=CheckStatus.CRITICAL)
        md = generate_markdown(report)

        # Should contain all 4 status emojis
        assert "✅" in md  # healthy
        assert "❌" in md  # critical
        assert "⚠️" in md  # warning
        assert "🚨" in md  # error

    def test_contains_recommendations(self):
        """Generated markdown includes recommendations section when present."""
        checks = [
            CheckResult(
                name="database",
                status=CheckStatus.WARNING,
                message="Slow",
                recommendations=["Optimize queries", "Add indexes"],
            ),
        ]
        report = _make_report(checks=checks, overall_status=CheckStatus.WARNING)
        md = generate_markdown(report)

        assert "Optimize queries" in md
        assert "Add indexes" in md

    def test_contains_report_metadata(self):
        """Generated markdown includes report ID, duration, and trigger info."""
        report = _make_report()
        md = generate_markdown(report)

        assert "test-report-001" in md
        assert "manual" in md

    def test_contains_check_names(self):
        """Generated markdown includes all check display names."""
        report = _make_report()
        md = generate_markdown(report)

        # Check names should appear in the markdown
        assert "server" in md.lower() or "Server" in md
        assert "database" in md.lower() or "Database" in md
