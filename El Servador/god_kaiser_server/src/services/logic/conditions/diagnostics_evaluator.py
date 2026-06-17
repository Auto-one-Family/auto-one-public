"""
Diagnostics Condition Evaluator

Phase 4D.3.1: Evaluates diagnostic check status as a Logic Rule condition.
Allows rules to trigger based on system health (e.g. "if MQTT is critical, notify").
"""

from typing import Dict

from ....core.logging_config import get_logger
from .base import BaseConditionEvaluator

logger = get_logger(__name__)


class DiagnosticsConditionEvaluator(BaseConditionEvaluator):
    """
    Evaluates conditions based on the latest diagnostic report status.

    Condition format:
        {
            "type": "diagnostics_status",
            "check_name": "mqtt",           # Name of the diagnostic check
            "expected_status": "critical",   # Status to match: healthy, warning, critical, error
            "operator": "=="                 # ==, != (default: ==)
        }

    The evaluator reads the latest diagnostic report from the database
    and checks if the specified check has the expected status.
    """

    def __init__(self, session_factory=None):
        """Initialize with optional async session factory for DB access."""
        self._session_factory = session_factory

    def supports(self, condition_type: str) -> bool:
        """Support 'diagnostics_status' condition type."""
        return condition_type == "diagnostics_status"

    async def evaluate(self, condition: Dict, context: Dict) -> bool:
        """
        Evaluate diagnostics status condition.

        Args:
            condition: Condition dictionary with:
                - type: "diagnostics_status"
                - check_name: Name of the diagnostic check (e.g. "mqtt", "database")
                - expected_status: Status to compare (healthy, warning, critical, error)
                - operator: "==" or "!=" (default: "==")
            context: Evaluation context (unused for diagnostics — reads from DB)

        Returns:
            True if the check status matches the expected status
        """
        check_name = condition.get("check_name")
        expected_status = condition.get("expected_status")
        operator = condition.get("operator", "==")

        if not check_name or not expected_status:
            logger.warning("DiagnosticsConditionEvaluator: missing check_name or expected_status")
            return False

        # Get latest diagnostic report from DB
        actual_status = await self._get_check_status(check_name)

        if actual_status is None:
            logger.debug(f"No diagnostic report found for check '{check_name}'")
            return False

        if operator == "!=":
            return actual_status != expected_status
        return actual_status == expected_status

    async def _get_check_status(self, check_name: str) -> str | None:
        """Read latest diagnostic report from DB and extract check status."""
        if not self._session_factory:
            logger.warning("DiagnosticsConditionEvaluator: no session factory configured")
            return None

        try:
            from ....db.models.diagnostic import DiagnosticReport
            from sqlalchemy import select

            async for session in self._session_factory():
                stmt = (
                    select(DiagnosticReport).order_by(DiagnosticReport.started_at.desc()).limit(1)
                )
                result = await session.execute(stmt)
                report = result.scalar_one_or_none()

                if not report or not report.checks:
                    return None

                # Find the check by name in the JSONB checks array
                for check in report.checks:
                    if check.get("name") == check_name:
                        return check.get("status")

                return None
        except Exception as e:
            logger.error(f"Failed to read diagnostic report: {e}")
            return None
