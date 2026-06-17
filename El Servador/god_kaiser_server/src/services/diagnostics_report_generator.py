"""
Diagnostics Report Generator

Phase 4D.1.4: Generates Markdown reports from diagnostic results.
Includes status emojis, metrics tables, recommendations, and next-steps.
"""

from datetime import datetime, timezone

from .diagnostics_service import CheckResult, CheckStatus, DiagnosticReportData

UTC = timezone.utc

_STATUS_EMOJI = {
    CheckStatus.HEALTHY: "\u2705",  # green checkmark
    CheckStatus.WARNING: "\u26a0\ufe0f",  # warning sign
    CheckStatus.CRITICAL: "\u274c",  # red cross
    CheckStatus.ERROR: "\U0001f6a8",  # rotating light
}

_STATUS_LABEL = {
    CheckStatus.HEALTHY: "Healthy",
    CheckStatus.WARNING: "Warning",
    CheckStatus.CRITICAL: "Critical",
    CheckStatus.ERROR: "Error",
}

_CHECK_DISPLAY_NAMES = {
    "server": "Server (CPU/RAM/Uptime)",
    "database": "Database (PostgreSQL)",
    "mqtt": "MQTT Broker",
    "esp_devices": "ESP32 Devices",
    "sensors": "Sensors",
    "actuators": "Actuators",
    "monitoring": "Monitoring Stack",
    "logic_engine": "Logic Engine",
    "alerts": "Alert System (ISA-18.2)",
    "plugins": "Plugin System",
}


def generate_markdown(report: DiagnosticReportData) -> str:
    """Generate a full Markdown report from diagnostic results."""
    lines: list[str] = []
    overall_emoji = _STATUS_EMOJI.get(report.overall_status, "\u2753")
    overall_label = _STATUS_LABEL.get(report.overall_status, "Unknown")

    lines.append(f"# AutomationOne Diagnostic Report {overall_emoji}")
    lines.append("")
    lines.append(f"**Overall Status:** {overall_emoji} {overall_label}")
    lines.append(f"**Generated:** {report.started_at}")
    lines.append(f"**Duration:** {report.duration_seconds:.2f}s")
    lines.append(f"**Triggered by:** {report.triggered_by}")
    lines.append(f"**Report ID:** `{report.id}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary table
    lines.append("## Check Overview")
    lines.append("")
    lines.append("| # | Check | Status | Duration |")
    lines.append("|---|-------|--------|----------|")

    for idx, check in enumerate(report.checks, 1):
        emoji = _STATUS_EMOJI.get(check.status, "\u2753")
        display_name = _CHECK_DISPLAY_NAMES.get(check.name, check.name)
        duration = f"{check.duration_ms:.0f}ms"
        lines.append(
            f"| {idx} | {display_name} | {emoji} {_STATUS_LABEL.get(check.status, '?')} | {duration} |"
        )

    lines.append("")

    # Count by status
    status_counts = _count_by_status(report.checks)
    status_parts = []
    for status in [
        CheckStatus.HEALTHY,
        CheckStatus.WARNING,
        CheckStatus.CRITICAL,
        CheckStatus.ERROR,
    ]:
        count = status_counts.get(status, 0)
        if count > 0:
            emoji = _STATUS_EMOJI[status]
            status_parts.append(f"{emoji} {count} {_STATUS_LABEL[status]}")
    lines.append(f"**Summary:** {' | '.join(status_parts)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Detailed results per check
    lines.append("## Detailed Results")
    lines.append("")

    for check in report.checks:
        _append_check_detail(lines, check)

    # Recommendations
    all_recommendations = _collect_recommendations(report.checks)
    if all_recommendations:
        lines.append("---")
        lines.append("")
        lines.append("## Recommendations")
        lines.append("")
        for rec in all_recommendations:
            lines.append(f"- {rec}")
        lines.append("")

    # Next steps section
    next_steps = _determine_next_steps(report)
    if next_steps:
        lines.append("---")
        lines.append("")
        lines.append("## Next Steps")
        lines.append("")
        for step in next_steps:
            lines.append(f"1. {step}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        f"*AutomationOne Diagnostics v4D | {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}*"
    )
    lines.append("")

    return "\n".join(lines)


def _append_check_detail(lines: list[str], check: CheckResult) -> None:
    """Append detailed section for a single check."""
    emoji = _STATUS_EMOJI.get(check.status, "\u2753")
    display_name = _CHECK_DISPLAY_NAMES.get(check.name, check.name)

    lines.append(f"### {emoji} {display_name}")
    lines.append("")
    lines.append(
        f"**Status:** {_STATUS_LABEL.get(check.status, '?')} | **Duration:** {check.duration_ms:.0f}ms"
    )
    lines.append(f"**Message:** {check.message}")
    lines.append("")

    # Metrics table
    if check.metrics:
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        for key, value in check.metrics.items():
            label = key.replace("_", " ").title()
            lines.append(f"| {label} | {_format_metric_value(value)} |")
        lines.append("")

    # Recommendations for this check
    if check.recommendations:
        lines.append("**Recommendations:**")
        for rec in check.recommendations:
            lines.append(f"- {rec}")
        lines.append("")


def _format_metric_value(value) -> str:
    """Format a metric value for display."""
    if isinstance(value, float):
        if value >= 1000:
            return f"{value:,.0f}"
        return f"{value:.2f}"
    if isinstance(value, bool):
        return "\u2705" if value else "\u274c"
    return str(value)


def _count_by_status(checks: list[CheckResult]) -> dict[CheckStatus, int]:
    """Count checks by status."""
    counts: dict[CheckStatus, int] = {}
    for check in checks:
        counts[check.status] = counts.get(check.status, 0) + 1
    return counts


def _collect_recommendations(checks: list[CheckResult]) -> list[str]:
    """Collect all recommendations from non-healthy checks."""
    recs: list[str] = []
    for check in checks:
        if check.status != CheckStatus.HEALTHY and check.recommendations:
            display_name = _CHECK_DISPLAY_NAMES.get(check.name, check.name)
            for rec in check.recommendations:
                recs.append(f"**{display_name}:** {rec}")
    return recs


def _determine_next_steps(report: DiagnosticReportData) -> list[str]:
    """Determine next steps based on overall report status."""
    steps: list[str] = []

    critical_checks = [c for c in report.checks if c.status == CheckStatus.CRITICAL]
    error_checks = [c for c in report.checks if c.status == CheckStatus.ERROR]
    warning_checks = [c for c in report.checks if c.status == CheckStatus.WARNING]

    if error_checks:
        error_names = ", ".join(_CHECK_DISPLAY_NAMES.get(c.name, c.name) for c in error_checks)
        steps.append(f"Investigate error state in: {error_names}")

    if critical_checks:
        critical_names = ", ".join(
            _CHECK_DISPLAY_NAMES.get(c.name, c.name) for c in critical_checks
        )
        steps.append(f"Address critical issues in: {critical_names}")

    if warning_checks:
        steps.append(f"Review {len(warning_checks)} warning(s) and apply recommendations above")

    if not steps:
        steps.append("System is healthy — no immediate action required")
        steps.append("Schedule next diagnostic run in 24 hours")

    return steps
