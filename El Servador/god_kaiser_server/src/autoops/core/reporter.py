"""
AutoOps Reporter - Generates comprehensive documentation of all actions.

Every AutoOps session generates a timestamped report documenting:
- What was done (every API call, every configuration change)
- What was found (diagnostics, health checks)
- What failed and why
- Recommendations for follow-up
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .base_plugin import PluginAction, PluginResult


class AutoOpsReporter:
    """
    Generates markdown reports for AutoOps sessions.

    Reports are saved to autoops/reports/ with timestamps.
    """

    def __init__(self, reports_dir: str | Path | None = None):
        if reports_dir:
            self.reports_dir = Path(reports_dir)
        else:
            self.reports_dir = Path(__file__).parent.parent / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def generate_session_report(
        self,
        session_id: str,
        context_summary: dict[str, Any],
        plugin_results: list[tuple[str, PluginResult]],
        api_actions: list[PluginAction],
    ) -> str:
        """
        Generate a full session report.

        Args:
            session_id: Unique session identifier
            context_summary: Summary from AutoOpsContext.get_summary()
            plugin_results: List of (plugin_name, PluginResult) tuples
            api_actions: All API actions from the client

        Returns:
            Path to the generated report file.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"autoops_session_{session_id}_{timestamp}.md"
        filepath = self.reports_dir / filename

        lines = [
            f"# AutoOps Session Report",
            f"",
            f"**Session ID:** {session_id}",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Status:** {'ALL PASSED' if all(r.success for _, r in plugin_results) else 'ISSUES FOUND'}",
            f"",
            f"---",
            f"",
        ]

        # Session summary
        lines.extend(
            [
                "## Session Summary",
                "",
                f"| Metric | Value |",
                f"|--------|-------|",
            ]
        )
        for key, value in context_summary.items():
            lines.append(f"| {key} | {value} |")
        lines.append("")

        # Plugin results
        lines.extend(
            [
                "## Plugin Results",
                "",
            ]
        )

        total_success = 0
        total_failed = 0
        for plugin_name, result in plugin_results:
            status = "PASS" if result.success else "FAIL"
            icon = "+" if result.success else "-"
            if result.success:
                total_success += 1
            else:
                total_failed += 1

            lines.extend(
                [
                    f"### {icon} {plugin_name}: {status}",
                    f"",
                    f"**Summary:** {result.summary}",
                    f"",
                ]
            )

            if result.actions:
                lines.append(f"**Actions ({len(result.actions)}):**")
                lines.append("")
                lines.append("| # | Action | Target | Result | API |")
                lines.append("|---|--------|--------|--------|-----|")
                for i, action in enumerate(result.actions, 1):
                    api = (
                        f"`{action.api_method} {action.api_endpoint}`"
                        if action.api_endpoint
                        else "-"
                    )
                    lines.append(
                        f"| {i} | {action.action} | {action.target} | " f"{action.result} | {api} |"
                    )
                lines.append("")

            if result.errors:
                lines.append("**Errors:**")
                for error in result.errors:
                    lines.append(f"- {error}")
                lines.append("")

            if result.warnings:
                lines.append("**Warnings:**")
                for warning in result.warnings:
                    lines.append(f"- {warning}")
                lines.append("")

            if result.data:
                lines.append("**Data:**")
                lines.append("```json")
                lines.append(json.dumps(result.data, indent=2, default=str))
                lines.append("```")
                lines.append("")

        # Claude debug finding sections (one per plugin that produced an llm_finding)
        for _plugin_name, result in plugin_results:
            finding_data = result.data.get("llm_finding") if isinstance(result.data, dict) else None
            if finding_data and isinstance(finding_data, dict):
                lines.append(self._render_debug_finding_section(finding_data))
                lines.append("")

        # Overall API log
        if api_actions:
            lines.extend(
                [
                    "## Complete API Action Log",
                    "",
                    f"Total API calls: {len(api_actions)}",
                    "",
                    "| # | Time | Method | Endpoint | Status | Action |",
                    "|---|------|--------|----------|--------|--------|",
                ]
            )
            for i, action in enumerate(api_actions, 1):
                method = action.api_method or "-"
                endpoint = action.api_endpoint or "-"
                status_code = action.api_response_code or "-"
                lines.append(
                    f"| {i} | {action.timestamp} | {method} | "
                    f"`{endpoint}` | {status_code} | {action.action} |"
                )
            lines.append("")

        # Final summary
        lines.extend(
            [
                "---",
                "",
                "## Final Summary",
                "",
                f"- **Plugins executed:** {len(plugin_results)}",
                f"- **Passed:** {total_success}",
                f"- **Failed:** {total_failed}",
                f"- **Total API calls:** {len(api_actions)}",
                f"- **Errors:** {sum(len(r.errors) for _, r in plugin_results)}",
                f"- **Warnings:** {sum(len(r.warnings) for _, r in plugin_results)}",
                "",
            ]
        )

        content = "\n".join(lines)
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    def _render_debug_finding_section(self, finding_data: dict) -> str:
        """Render a Claude debug finding as a markdown section."""
        lines = [
            "## Claude Debug-Befund",
            "",
            f"**Root Cause:** {finding_data.get('root_cause', '?')}",
            f"**Confidence:** {finding_data.get('confidence', '?')}",
            "",
            "**Betroffene Komponenten:**",
        ]
        for comp in finding_data.get("affected_components", []):
            lines.append(f"- {comp}")

        code_refs = finding_data.get("code_references", [])
        if code_refs:
            lines.extend(["", "**Code-Referenzen:**"])
            for ref in code_refs:
                if isinstance(ref, dict):
                    lines.append(
                        f"- `{ref.get('file', '?')}:{ref.get('line', '?')}` — {ref.get('symbol', '?')}"
                    )

        actions = finding_data.get("recommended_actions", [])
        if actions:
            lines.extend(["", "**Empfohlene Aktionen:**"])
            for i, action in enumerate(actions, 1):
                lines.append(f"{i}. {action}")

        evidence = finding_data.get("evidence", [])
        if evidence:
            lines.extend(["", "**Evidenz:**"])
            for ev in evidence[:5]:
                lines.append(f"> {ev}")

        if finding_data.get("auto_fix_applied") and finding_data.get("fix_description"):
            lines.extend(["", f"**Auto-Fix angewendet:** {finding_data['fix_description']}"])

        return "\n".join(lines)

    def generate_daily_report(
        self,
        run_date: datetime,
        run_slot: str,
        findings: list[Any],
        period_hours: int,
    ) -> str:
        """
        Generate a daily-analysis report (AUT-194).

        Output is auto-debugger-compatible: contains TASK-PACKAGES + SPECIALIST-PROMPTS
        sections so the file can be consumed directly as an auto-debugger steering doc.

        Args:
            run_date: Run date (UTC) — used in filename
            run_slot: 'morning' (06:00) or 'evening' (18:00)
            findings: list of ErrorAnalysisFinding (sorted by severity by AiService)
            period_hours: Aggregation window in hours

        Returns:
            Path (str) to the generated report file.
        """
        date_str = run_date.strftime("%Y-%m-%d")
        filename = f"daily_report_{date_str}_{run_slot}.md"
        filepath = self.reports_dir / filename

        lines: list[str] = [
            f"# DAILY-ANALYSIS-REPORT {date_str} {run_slot}",
            "",
            f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
            f"**Period:** last {period_hours}h (slot={run_slot})",
            f"**Findings:** {len(findings)}",
            "",
            "---",
            "",
        ]

        if not findings:
            lines.extend(
                [
                    "## Status",
                    "",
                    "Keine Findings ausserhalb der bekannten harmlosen Patterns.",
                    "",
                ]
            )
            content = "\n".join(lines)
            filepath.write_text(content, encoding="utf-8")
            return str(filepath)

        # ----- TASK-PACKAGES (auto-debugger-compatible) -----
        lines.extend(["## TASK-PACKAGES", ""])
        for idx, finding in enumerate(findings, start=1):
            pkg_id = f"PKG-{idx:02d}"
            verify_gate = f"DA-{run_slot}-{idx:02d}"
            affected = ", ".join(getattr(finding, "affected_components", []) or []) or "-"
            severity = getattr(finding, "severity", "medium")
            title = getattr(finding, "linear_title", "Daily Analysis Finding")
            description = getattr(finding, "linear_description", "") or ""
            lines.extend(
                [
                    f"### {pkg_id} — {title}",
                    f"**Prioritaet:** {severity}",
                    f"**Schicht:** {affected}",
                    f"**Deliverable:** {description}",
                    f"**Verify-Gate:** {verify_gate}",
                    "",
                ]
            )

        # ----- SPECIALIST-PROMPTS (auto-debugger-compatible) -----
        lines.extend(["## SPECIALIST-PROMPTS", ""])
        for idx, finding in enumerate(findings, start=1):
            pkg_id = f"PKG-{idx:02d}"
            agent = self._route_specialist(finding)
            description = getattr(finding, "linear_description", "") or ""
            code_refs = getattr(finding, "code_references", []) or []
            actions = getattr(finding, "recommended_actions", []) or []

            lines.extend(
                [
                    f"### {agent} — {pkg_id}",
                    description,
                    "",
                ]
            )
            if code_refs:
                lines.append("**Code-Referenzen:**")
                for ref in code_refs:
                    file = getattr(ref, "file", "?")
                    line_no = getattr(ref, "line", "?")
                    symbol = getattr(ref, "symbol", "?")
                    lines.append(f"- `{file}:{line_no}` — {symbol}")
                lines.append("")
            if actions:
                lines.append("**Empfohlene Aktionen:**")
                for i, action in enumerate(actions, 1):
                    lines.append(f"{i}. {action}")
                lines.append("")

        content = "\n".join(lines)
        filepath.write_text(content, encoding="utf-8")
        return str(filepath)

    @staticmethod
    def _route_specialist(finding: Any) -> str:
        """
        Map an ErrorAnalysisFinding to the most fitting specialist agent.

        Heuristic: scan ``affected_components`` for layer keywords. Falls back
        to ``server-dev`` because daily snapshots are server-centric.
        """
        components = " ".join(getattr(finding, "affected_components", []) or []).lower()
        if "esp32" in components or "trabajante" in components or "firmware" in components:
            return "esp32-dev"
        if "frontend" in components or "vue" in components or "el frontend" in components:
            return "frontend-dev"
        if "mqtt" in components and "broker" in components:
            return "mqtt-dev"
        return "server-dev"

    def generate_quick_summary(
        self,
        plugin_results: list[tuple[str, PluginResult]],
    ) -> str:
        """Generate a short text summary for console output."""
        lines = ["=" * 50, "AUTOOPS SESSION SUMMARY", "=" * 50, ""]

        for plugin_name, result in plugin_results:
            status = "PASS" if result.success else "FAIL"
            icon = "[+]" if result.success else "[-]"
            lines.append(f"{icon} {plugin_name}: {status}")
            lines.append(f"    {result.summary}")
            if result.errors:
                for error in result.errors:
                    lines.append(f"    ERROR: {error}")
            lines.append("")

        total = len(plugin_results)
        passed = sum(1 for _, r in plugin_results if r.success)
        lines.append(f"Result: {passed}/{total} plugins passed")
        lines.append("=" * 50)

        return "\n".join(lines)
