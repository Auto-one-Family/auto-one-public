"""
Diagnostics REST API Endpoints

Phase 4D.1.5: REST-API for System Diagnostics Hub.
Provides endpoints to run diagnostic checks, view history, and export reports.

Endpoints:
- POST   /v1/diagnostics/run              - Run full diagnostic
- POST   /v1/diagnostics/run/{check_name} - Run single check
- GET    /v1/diagnostics/history           - Report history
- GET    /v1/diagnostics/history/{id}      - Single report detail
- POST   /v1/diagnostics/export/{id}       - Export report as Markdown
- GET    /v1/diagnostics/checks            - List available checks
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ...core.logging_config import get_logger
from ...services.diagnostics_report_generator import generate_markdown
from ...services.diagnostics_service import CheckStatus, DiagnosticsService
from ..deps import ActiveUser, DBSession, OperatorUser

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/diagnostics", tags=["diagnostics"])


# --- Response Models ---


class CheckResultResponse(BaseModel):
    name: str
    status: str
    message: str
    details: dict = {}
    metrics: dict = {}
    recommendations: list[str] = []
    duration_ms: float = 0.0


class DiagnosticReportResponse(BaseModel):
    id: str
    overall_status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    checks: list[CheckResultResponse]
    summary: str
    triggered_by: str


class ReportHistoryItem(BaseModel):
    id: str
    overall_status: str
    started_at: str
    finished_at: str
    duration_seconds: float
    triggered_by: str
    summary: Optional[str] = None


class AvailableCheck(BaseModel):
    name: str
    display_name: str


class ExportResponse(BaseModel):
    markdown: str
    report_id: str


# --- Check display name mapping ---

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


# --- Helper ---


def _build_diagnostics_service(db: DBSession) -> DiagnosticsService:
    """Build DiagnosticsService for request scope with plugin_service."""
    from ...autoops.core.plugin_registry import PluginRegistry
    from ...services.plugin_service import PluginService

    registry = PluginRegistry()
    registry.discover_plugins()
    plugin_service = PluginService(db, registry)
    return DiagnosticsService(session=db, plugin_service=plugin_service)


def _report_to_response(report) -> DiagnosticReportResponse:
    """Convert DiagnosticReportData to response model."""
    return DiagnosticReportResponse(
        id=report.id,
        overall_status=(
            report.overall_status.value
            if isinstance(report.overall_status, CheckStatus)
            else report.overall_status
        ),
        started_at=report.started_at,
        finished_at=report.finished_at,
        duration_seconds=report.duration_seconds,
        checks=[
            CheckResultResponse(
                name=c.name,
                status=c.status.value if isinstance(c.status, CheckStatus) else c.status,
                message=c.message,
                details=c.details,
                metrics=c.metrics,
                recommendations=c.recommendations,
                duration_ms=c.duration_ms,
            )
            for c in report.checks
        ],
        summary=report.summary,
        triggered_by=report.triggered_by,
    )


# --- Endpoints ---


@router.post(
    "/run",
    response_model=DiagnosticReportResponse,
    summary="Run full diagnostic",
    description="Execute all 10 diagnostic checks and generate a report.",
)
async def run_full_diagnostic(
    db: DBSession,
    user: OperatorUser,  # TODO replace isViewer with capability check
):
    service = _build_diagnostics_service(db)
    try:
        report = await service.run_full_diagnostic(
            triggered_by="manual",
            user_id=user.id,
        )
        return _report_to_response(report)
    except Exception as e:
        logger.error(f"Full diagnostic failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Diagnostic run failed: {str(e)}")


@router.post(
    "/run/{check_name}",
    response_model=CheckResultResponse,
    summary="Run single check",
    description="Execute a single diagnostic check by name.",
)
async def run_single_check(
    check_name: str,
    db: DBSession,
    user: ActiveUser,
):
    service = _build_diagnostics_service(db)
    try:
        result = await service.run_single_check(check_name)
        return CheckResultResponse(
            name=result.name,
            status=result.status.value,
            message=result.message,
            details=result.details,
            metrics=result.metrics,
            recommendations=result.recommendations,
            duration_ms=result.duration_ms,
        )
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Check '{check_name}' not found. Use GET /checks for available checks.",
        )
    except Exception as e:
        logger.error(f"Single check '{check_name}' failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Check failed: {str(e)}")


@router.get(
    "/history",
    response_model=list[ReportHistoryItem],
    summary="Diagnostic report history",
    description="Get list of past diagnostic reports, newest first.",
)
async def get_diagnostic_history(
    db: DBSession,
    user: ActiveUser,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    service = _build_diagnostics_service(db)
    reports = await service.get_history(limit=limit, offset=offset)
    return [
        ReportHistoryItem(
            id=str(r.id),
            overall_status=r.overall_status,
            started_at=r.started_at.isoformat() if r.started_at else "",
            finished_at=r.finished_at.isoformat() if r.finished_at else "",
            duration_seconds=r.duration_seconds or 0.0,
            triggered_by=r.triggered_by,
            summary=r.summary,
        )
        for r in reports
    ]


@router.get(
    "/history/{report_id}",
    response_model=DiagnosticReportResponse,
    summary="Single report detail",
    description="Get full details for a specific diagnostic report.",
)
async def get_diagnostic_report(
    report_id: UUID,
    db: DBSession,
    user: ActiveUser,
):
    service = _build_diagnostics_service(db)
    report = await service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")

    # Reconstruct response from DB model
    checks_data = report.checks or []
    return DiagnosticReportResponse(
        id=str(report.id),
        overall_status=report.overall_status,
        started_at=report.started_at.isoformat() if report.started_at else "",
        finished_at=report.finished_at.isoformat() if report.finished_at else "",
        duration_seconds=report.duration_seconds or 0.0,
        checks=[
            CheckResultResponse(
                name=c.get("name", ""),
                status=c.get("status", "error"),
                message=c.get("message", ""),
                details=c.get("details", {}),
                metrics=c.get("metrics", {}),
                recommendations=c.get("recommendations", []),
                duration_ms=c.get("duration_ms", 0.0),
            )
            for c in checks_data
        ],
        summary=report.summary or "",
        triggered_by=report.triggered_by,
    )


@router.post(
    "/export/{report_id}",
    response_model=ExportResponse,
    summary="Export report as Markdown",
    description="Generate a Markdown export of a diagnostic report.",
)
async def export_report(
    report_id: UUID,
    db: DBSession,
    user: OperatorUser,  # TODO replace isViewer with capability check
):
    service = _build_diagnostics_service(db)
    report_data = await service.get_report_by_id(report_id)
    if not report_data:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found")

    # Convert DB model back to runtime report for Markdown generation
    from ...services.diagnostics_service import CheckResult as CR
    from ...services.diagnostics_service import DiagnosticReportData

    checks_data = report_data.checks or []
    check_results = [
        CR(
            name=c.get("name", ""),
            status=CheckStatus(c.get("status", "error")),
            message=c.get("message", ""),
            details=c.get("details", {}),
            metrics=c.get("metrics", {}),
            recommendations=c.get("recommendations", []),
            duration_ms=c.get("duration_ms", 0.0),
        )
        for c in checks_data
    ]

    runtime_report = DiagnosticReportData(
        id=str(report_data.id),
        overall_status=CheckStatus(report_data.overall_status),
        started_at=report_data.started_at.isoformat() if report_data.started_at else "",
        finished_at=report_data.finished_at.isoformat() if report_data.finished_at else "",
        duration_seconds=report_data.duration_seconds or 0.0,
        checks=check_results,
        summary=report_data.summary or "",
        triggered_by=report_data.triggered_by,
    )

    markdown = generate_markdown(runtime_report)

    # Mark report as exported
    from datetime import datetime, timezone

    report_data.exported_at = datetime.now(timezone.utc)
    await db.commit()

    return ExportResponse(markdown=markdown, report_id=str(report_id))


@router.get(
    "/checks",
    response_model=list[AvailableCheck],
    summary="List available checks",
    description="List all available diagnostic check names.",
)
async def list_available_checks(
    user: ActiveUser,
):
    return [
        AvailableCheck(name=name, display_name=display)
        for name, display in _CHECK_DISPLAY_NAMES.items()
    ]
