"""
Diagnostics Action Executor — Runs diagnostic checks as Logic Rule actions.

Phase 4D.3.2: New action type 'run_diagnostic' in the Logic Engine.
When a logic rule fires, it can trigger a full diagnostic or single check.
"""

from typing import Dict

from ....core.logging_config import get_logger
from .base import ActionResult, BaseActionExecutor

logger = get_logger(__name__)


class DiagnosticsActionExecutor(BaseActionExecutor):
    """Executes a diagnostic check as a Logic Rule action.

    Action format:
        {
            "type": "run_diagnostic",
            "check_name": "mqtt"  # Optional — omit for full diagnostic
        }
    """

    def __init__(self, session_factory=None):
        """Initialize with async session factory for DiagnosticsService."""
        self._session_factory = session_factory

    def supports(self, action_type: str) -> bool:
        """Support 'run_diagnostic' action type."""
        return action_type == "run_diagnostic"

    async def execute(self, action: Dict, context: Dict) -> ActionResult:
        """Execute a diagnostic check triggered by a logic rule."""
        check_name = action.get("check_name")

        if not self._session_factory:
            return ActionResult(
                success=False,
                message="DiagnosticsActionExecutor: no session factory configured",
            )

        try:
            from ....services.diagnostics_service import DiagnosticsService

            async for session in self._session_factory():
                service = DiagnosticsService(session=session)

                if check_name:
                    # Run single check
                    result = await service.run_single_check(check_name)
                    return ActionResult(
                        success=True,
                        message=(
                            f"Diagnostic check '{check_name}' completed: " f"{result.status.value}"
                        ),
                        data={
                            "check_name": check_name,
                            "status": result.status.value,
                            "message": result.message,
                        },
                    )
                else:
                    # Run full diagnostic
                    report = await service.run_full_diagnostic(
                        triggered_by="logic_rule",
                    )
                    return ActionResult(
                        success=True,
                        message=(f"Full diagnostic completed: " f"{report.overall_status.value}"),
                        data={
                            "report_id": report.id,
                            "overall_status": report.overall_status.value,
                            "duration_seconds": report.duration_seconds,
                        },
                    )

        except ValueError:
            return ActionResult(
                success=False,
                message=f"Diagnostic check '{check_name}' not found",
            )
        except Exception as e:
            logger.error(f"Diagnostic action execution failed: {e}", exc_info=True)
            return ActionResult(
                success=False,
                message=f"Diagnostic execution failed: {str(e)}",
            )
