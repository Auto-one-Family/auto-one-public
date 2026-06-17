"""
Diagnostics Service

Phase 4D.1.3: 10 modulare Diagnose-Checks fuer System-Gesundheit.
Jeder Check evaluiert einen Aspekt des Systems und gibt ein CheckResult zurueck.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.actuator import ActuatorConfig
from ..db.models.diagnostic import DiagnosticReport as DiagnosticReportModel
from ..db.models.esp import ESPDevice
from ..db.models.logic import CrossESPLogic, LogicExecutionHistory
from ..db.models.notification import Notification
from ..db.models.sensor import SensorConfig

logger = get_logger(__name__)

UTC = timezone.utc


class CheckStatus(Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    ERROR = "error"


# Severity ordering for worst-of calculation
_STATUS_ORDER = {
    CheckStatus.HEALTHY: 0,
    CheckStatus.WARNING: 1,
    CheckStatus.CRITICAL: 2,
    CheckStatus.ERROR: 3,
}


@dataclass
class CheckResult:
    name: str
    status: CheckStatus
    message: str
    details: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class DiagnosticReportData:
    """Runtime report object (not the DB model)."""

    id: str
    overall_status: CheckStatus
    started_at: str
    finished_at: str
    duration_seconds: float
    checks: list[CheckResult]
    summary: str
    triggered_by: str


class DiagnosticsService:
    """10 modulare Diagnose-Checks — einzeln oder als Batch ausfuehrbar."""

    MONITORING_URLS = {
        "grafana": "http://grafana:3000",
        "prometheus": "http://prometheus:9090",
        "loki": "http://loki:3100",
    }

    def __init__(
        self,
        session: AsyncSession,
        mqtt_manager=None,
        plugin_service=None,
    ):
        self.session = session
        self.mqtt_manager = mqtt_manager
        self.plugin_service = plugin_service

        self.checks: dict[str, callable] = {
            "server": self._check_server,
            "database": self._check_database,
            "mqtt": self._check_mqtt,
            "esp_devices": self._check_esp_devices,
            "sensors": self._check_sensors,
            "actuators": self._check_actuators,
            "monitoring": self._check_monitoring,
            "logic_engine": self._check_logic_engine,
            "alerts": self._check_alerts,
            "plugins": self._check_plugins,
        }

    async def run_full_diagnostic(
        self, triggered_by: str = "manual", user_id: Optional[int] = None
    ) -> DiagnosticReportData:
        """Run all 10 checks and generate a report."""
        start = datetime.now(UTC)
        results: list[CheckResult] = []

        for name, check_fn in self.checks.items():
            check_start = datetime.now(UTC)
            try:
                result = await check_fn()
            except Exception as e:
                logger.warning(f"Diagnostic check '{name}' failed: {e}")
                result = CheckResult(
                    name=name,
                    status=CheckStatus.ERROR,
                    message=f"Check fehlgeschlagen: {str(e)}",
                )
            result.duration_ms = (datetime.now(UTC) - check_start).total_seconds() * 1000
            results.append(result)

        finished = datetime.now(UTC)
        overall = max(
            (r.status for r in results),
            key=lambda s: _STATUS_ORDER[s],
        )

        report = DiagnosticReportData(
            id=str(uuid.uuid4()),
            overall_status=overall,
            started_at=start.isoformat(),
            finished_at=finished.isoformat(),
            duration_seconds=(finished - start).total_seconds(),
            checks=results,
            summary=self._generate_summary(results),
            triggered_by=triggered_by,
        )

        await self._persist_report(report, user_id)
        return report

    async def run_single_check(self, check_name: str) -> CheckResult:
        """Run a single diagnostic check."""
        check_fn = self.checks.get(check_name)
        if not check_fn:
            raise ValueError(
                f"Unbekannter Check: {check_name}. " f"Verfuegbar: {list(self.checks.keys())}"
            )
        check_start = datetime.now(UTC)
        try:
            result = await check_fn()
        except Exception as e:
            logger.warning(f"Diagnostic check '{check_name}' failed: {e}")
            result = CheckResult(
                name=check_name,
                status=CheckStatus.ERROR,
                message=f"Check fehlgeschlagen: {str(e)}",
            )
        result.duration_ms = (datetime.now(UTC) - check_start).total_seconds() * 1000
        return result

    async def get_latest_report(self) -> Optional[DiagnosticReportModel]:
        """Get the most recent diagnostic report from DB."""
        result = await self.session.execute(
            select(DiagnosticReportModel).order_by(DiagnosticReportModel.started_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_history(self, limit: int = 20, offset: int = 0) -> list[DiagnosticReportModel]:
        """Get diagnostic report history."""
        result = await self.session.execute(
            select(DiagnosticReportModel)
            .order_by(DiagnosticReportModel.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_report_by_id(self, report_id: uuid.UUID | str) -> Optional[DiagnosticReportModel]:
        """Get a specific report by ID."""
        result = await self.session.execute(
            select(DiagnosticReportModel).where(DiagnosticReportModel.id == report_id)
        )
        return result.scalar_one_or_none()

    async def cleanup_old_reports(self, max_age_days: int = 90) -> int:
        """Archive diagnostic reports older than max_age_days.

        Archives by setting `checks` JSON to NULL while keeping
        summary fields (overall_status, started_at, triggered_by).
        This preserves the history timeline without consuming storage.

        Requires: checks column must be nullable (Alembic migration).

        Args:
            max_age_days: Reports older than this are archived. Default 90.

        Returns:
            Number of archived reports.
        """
        from sqlalchemy import update

        cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

        stmt = (
            update(DiagnosticReportModel)
            .where(DiagnosticReportModel.started_at < cutoff)
            .where(DiagnosticReportModel.checks.isnot(None))
            .values(checks=None)
        )
        result = await self.session.execute(stmt)
        await self.session.commit()

        archived = result.rowcount
        if archived > 0:
            logger.info(f"Archived {archived} diagnostic reports older than {max_age_days} days")
        return archived

    # ─── Check Implementations ─────────────────────────────────────

    async def _check_server(self) -> CheckResult:
        """Server: Uptime, Memory, CPU."""
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0.5)
            memory = psutil.virtual_memory()
        except ImportError:
            return CheckResult(
                name="server",
                status=CheckStatus.WARNING,
                message="psutil nicht installiert — Server-Metriken nicht verfuegbar",
            )

        import time
        from ..core.metrics import _server_start_time

        uptime_seconds = time.time() - _server_start_time if _server_start_time else 0

        status = CheckStatus.HEALTHY
        recommendations: list[str] = []

        if memory.percent > 90:
            status = CheckStatus.CRITICAL
            recommendations.append("Memory > 90% — pruefe Speicherlecks oder erhoehe RAM")
        elif memory.percent > 75:
            status = CheckStatus.WARNING
            recommendations.append("Memory > 75% — beobachten")

        if cpu > 80:
            status = max(status, CheckStatus.WARNING, key=lambda s: _STATUS_ORDER[s])
            recommendations.append(f"CPU bei {cpu}% — pruefe ob Background-Tasks laufen")

        uptime_str = self._format_uptime(uptime_seconds)

        return CheckResult(
            name="server",
            status=status,
            message=f"Server laeuft seit {uptime_str}, CPU {cpu}%, RAM {memory.percent}%",
            metrics={
                "cpu_percent": cpu,
                "memory_percent": memory.percent,
                "uptime_seconds": uptime_seconds,
            },
            recommendations=recommendations,
        )

    async def _check_database(self) -> CheckResult:
        """Database: Connections, Tables, Size, Orphans."""
        table_count = await self.session.scalar(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        )

        db_size = await self.session.scalar(
            text("SELECT pg_size_pretty(pg_database_size(current_database()))")
        )

        active_conns = await self.session.scalar(
            text("SELECT count(*) FROM pg_stat_activity WHERE state = 'active'")
        )

        # Orphan check: notifications without valid user
        orphan_count = await self.session.scalar(
            text(
                "SELECT count(*) FROM notifications n "
                "LEFT JOIN user_accounts u ON n.user_id = u.id "
                "WHERE u.id IS NULL"
            )
        )

        status = CheckStatus.HEALTHY
        recommendations: list[str] = []

        if orphan_count and orphan_count > 0:
            status = CheckStatus.WARNING
            recommendations.append(
                f"{orphan_count} Notifications ohne gueltigen User — Cleanup empfohlen"
            )
        if active_conns and active_conns > 20:
            status = max(status, CheckStatus.WARNING, key=lambda s: _STATUS_ORDER[s])
            recommendations.append(
                f"{active_conns} aktive DB-Connections — Connection-Pool pruefen"
            )

        return CheckResult(
            name="database",
            status=status,
            message=f"{table_count} Tabellen, {db_size}, {active_conns} aktive Connections",
            metrics={
                "tables": table_count,
                "size": db_size,
                "active_connections": active_conns,
                "orphans": orphan_count or 0,
            },
            recommendations=recommendations,
        )

    async def _check_mqtt(self) -> CheckResult:
        """MQTT: Broker-Status, Stale Devices."""
        from ..mqtt.client import MQTTClient

        try:
            mqtt_client = MQTTClient.get_instance()
            connected = mqtt_client.is_connected()
        except Exception:
            connected = False

        status = CheckStatus.HEALTHY if connected else CheckStatus.CRITICAL
        recommendations: list[str] = []

        if not connected:
            recommendations.append("MQTT-Broker nicht erreichbar — Docker-Container pruefen")

        # Stale check: devices with outdated heartbeat (>5 min)
        stale_threshold = datetime.now(UTC) - timedelta(minutes=5)
        stale_count = (
            await self.session.scalar(
                select(func.count())
                .select_from(ESPDevice)
                .where(ESPDevice.last_seen < stale_threshold)
                .where(ESPDevice.status != "offline")
            )
            or 0
        )

        if stale_count > 0:
            status = max(status, CheckStatus.WARNING, key=lambda s: _STATUS_ORDER[s])
            recommendations.append(f"{stale_count} Devices mit veraltetem Heartbeat (>5 Min)")

        return CheckResult(
            name="mqtt",
            status=status,
            message="MQTT verbunden" if connected else "MQTT NICHT verbunden",
            metrics={"connected": connected, "stale_devices": stale_count},
            recommendations=recommendations,
        )

    async def _check_esp_devices(self) -> CheckResult:
        """ESP-Devices: Online/Offline, Heap, RSSI."""
        total = await self.session.scalar(select(func.count()).select_from(ESPDevice)) or 0
        online = (
            await self.session.scalar(
                select(func.count()).select_from(ESPDevice).where(ESPDevice.status == "online")
            )
            or 0
        )
        offline = (
            await self.session.scalar(
                select(func.count()).select_from(ESPDevice).where(ESPDevice.status == "offline")
            )
            or 0
        )
        error_count = (
            await self.session.scalar(
                select(func.count()).select_from(ESPDevice).where(ESPDevice.status == "error")
            )
            or 0
        )

        status = CheckStatus.HEALTHY
        problems: list[str] = []
        recommendations: list[str] = []

        if offline > 0:
            status = CheckStatus.WARNING
            problems.append(f"{offline} Devices offline")
        if error_count > 0:
            status = max(status, CheckStatus.CRITICAL, key=lambda s: _STATUS_ORDER[s])
            problems.append(f"{error_count} Devices im Error-Status")

        message = f"{online}/{total} online"
        if problems:
            message += f", Probleme: {', '.join(problems)}"

        return CheckResult(
            name="esp_devices",
            status=status,
            message=message,
            metrics={
                "total": total,
                "online": online,
                "offline": offline,
                "error": error_count,
            },
            recommendations=recommendations,
        )

    async def _check_sensors(self) -> CheckResult:
        """Sensors: Count, Alert-Config coverage."""
        total_sensors = (
            await self.session.scalar(select(func.count()).select_from(SensorConfig)) or 0
        )

        with_alerts = (
            await self.session.scalar(
                select(func.count())
                .select_from(SensorConfig)
                .where(SensorConfig.alert_config.isnot(None))
            )
            or 0
        )

        status = CheckStatus.HEALTHY
        recommendations: list[str] = []

        if total_sensors > 0 and with_alerts == 0:
            status = CheckStatus.WARNING
            recommendations.append(
                "Keine Sensor-Alert-Configs aktiv — Schwellwerte einrichten empfohlen"
            )

        return CheckResult(
            name="sensors",
            status=status,
            message=f"{total_sensors} Sensoren registriert, {with_alerts} mit Alert-Config",
            metrics={"total": total_sensors, "with_alerts": with_alerts},
            recommendations=recommendations,
        )

    async def _check_actuators(self) -> CheckResult:
        """Actuators: Count."""
        total = await self.session.scalar(select(func.count()).select_from(ActuatorConfig)) or 0

        return CheckResult(
            name="actuators",
            status=CheckStatus.HEALTHY,
            message=f"{total} Aktoren registriert",
            metrics={"total": total},
        )

    # Health endpoints per monitoring service (must match docker-compose healthchecks)
    MONITORING_HEALTH_PATHS = {
        "grafana": "/api/health",
        "prometheus": "/-/ready",
        "loki": "/ready",
    }

    async def _check_monitoring(self) -> CheckResult:
        """Monitoring: Grafana, Prometheus, Loki availability."""
        results: dict[str, str] = {}

        for name, url in self.MONITORING_URLS.items():
            try:
                path = self.MONITORING_HEALTH_PATHS[name]
                endpoint = f"{url}{path}"
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(endpoint)
                    results[name] = "up" if resp.status_code == 200 else "down"
            except Exception:
                results[name] = "unreachable"

        all_up = all(v == "up" for v in results.values())
        status = CheckStatus.HEALTHY if all_up else CheckStatus.WARNING
        recommendations: list[str] = []

        for name, state in results.items():
            if state != "up":
                recommendations.append(f"{name.capitalize()} ist {state} — Container pruefen")

        return CheckResult(
            name="monitoring",
            status=status,
            message=(
                f"Grafana: {results['grafana']}, "
                f"Prometheus: {results['prometheus']}, "
                f"Loki: {results['loki']}"
            ),
            metrics=results,
            recommendations=recommendations,
        )

    async def _check_logic_engine(self) -> CheckResult:
        """Logic Engine: Active rules, executions, error rate."""
        active_rules = (
            await self.session.scalar(
                select(func.count())
                .select_from(CrossESPLogic)
                .where(CrossESPLogic.enabled == True)  # noqa: E712
            )
            or 0
        )

        day_ago = datetime.now(UTC) - timedelta(hours=24)

        executions_24h = (
            await self.session.scalar(
                select(func.count())
                .select_from(LogicExecutionHistory)
                .where(LogicExecutionHistory.timestamp >= day_ago)
            )
            or 0
        )

        errors_24h = (
            await self.session.scalar(
                select(func.count())
                .select_from(LogicExecutionHistory)
                .where(LogicExecutionHistory.timestamp >= day_ago)
                .where(LogicExecutionHistory.success == False)  # noqa: E712
            )
            or 0
        )

        error_rate = (errors_24h / executions_24h * 100) if executions_24h > 0 else 0

        status = CheckStatus.HEALTHY
        recommendations: list[str] = []

        if error_rate > 10:
            status = CheckStatus.WARNING
            recommendations.append(f"Logic Engine Fehlerrate {error_rate:.1f}% — Rules pruefen")

        return CheckResult(
            name="logic_engine",
            status=status,
            message=(
                f"{active_rules} aktive Rules, "
                f"{executions_24h} Ausfuehrungen/24h, "
                f"{errors_24h} Fehler"
            ),
            metrics={
                "active_rules": active_rules,
                "executions_24h": executions_24h,
                "errors_24h": errors_24h,
                "error_rate": round(error_rate, 1),
            },
            recommendations=recommendations,
        )

    async def _check_alerts(self) -> CheckResult:
        """Alerts: ISA-18.2 metrics, alert rate."""
        from ..db.repositories.notification_repo import NotificationRepository

        repo = NotificationRepository(self.session)
        stats = await repo.get_alert_stats()
        severity_counts = await repo.get_active_counts_by_severity()

        active_count = stats.get("active_count", 0)
        standing_alerts = active_count + stats.get("acknowledged_count", 0)

        # Alerts per hour (last 24h)
        day_ago = datetime.now(UTC) - timedelta(hours=24)
        alerts_24h = (
            await self.session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.created_at >= day_ago)
                .where(Notification.severity.in_(["critical", "warning"]))
            )
            or 0
        )
        alerts_per_hour = alerts_24h / 24

        status = CheckStatus.HEALTHY
        recommendations: list[str] = []

        if alerts_per_hour > 6:
            status = CheckStatus.WARNING
            recommendations.append(
                f"Alarm-Rate {alerts_per_hour:.1f}/h ueberschreitet ISA-18.2 Limit (6/h)"
            )
        if standing_alerts > 5:
            status = max(status, CheckStatus.WARNING, key=lambda s: _STATUS_ORDER[s])
            recommendations.append(f"{standing_alerts} stehende Alarme — pruefen ob valide")

        return CheckResult(
            name="alerts",
            status=status,
            message=f"{alerts_per_hour:.1f} Alarme/h, {standing_alerts} stehend",
            metrics={
                "alerts_per_hour": round(alerts_per_hour, 1),
                "standing_alerts": standing_alerts,
                "active": active_count,
                "severity_counts": severity_counts,
                "mtta_seconds": stats.get("mean_time_to_acknowledge_s"),
                "mttr_seconds": stats.get("mean_time_to_resolve_s"),
            },
            recommendations=recommendations,
        )

    async def _check_plugins(self) -> CheckResult:
        """Plugins: Registered, enabled, recent executions."""
        if not self.plugin_service:
            return CheckResult(
                name="plugins",
                status=CheckStatus.WARNING,
                message="Plugin-Service nicht verfuegbar",
            )

        try:
            plugins = await self.plugin_service.get_all_plugins()
        except Exception as e:
            return CheckResult(
                name="plugins",
                status=CheckStatus.ERROR,
                message=f"Plugin-Abfrage fehlgeschlagen: {str(e)}",
            )

        enabled = sum(1 for p in plugins if p.get("is_enabled"))
        registered = sum(1 for p in plugins if p.get("is_registered"))
        total = len(plugins)

        return CheckResult(
            name="plugins",
            status=CheckStatus.HEALTHY if registered == total else CheckStatus.WARNING,
            message=f"{total} Plugins, {enabled} aktiv, {registered} registriert",
            metrics={"total": total, "enabled": enabled, "registered": registered},
        )

    # ─── Helpers ───────────────────────────────────────────────────

    def _generate_summary(self, results: list[CheckResult]) -> str:
        """Generate a human-readable summary from check results."""
        healthy = sum(1 for r in results if r.status == CheckStatus.HEALTHY)
        warnings = sum(1 for r in results if r.status == CheckStatus.WARNING)
        critical = sum(1 for r in results if r.status == CheckStatus.CRITICAL)
        errors = sum(1 for r in results if r.status == CheckStatus.ERROR)

        parts: list[str] = []
        parts.append(f"{healthy}/{len(results)} Checks gesund")
        if warnings:
            parts.append(f"{warnings} Warnungen")
        if critical:
            parts.append(f"{critical} kritisch")
        if errors:
            parts.append(f"{errors} fehlgeschlagen")

        return ", ".join(parts)

    async def _persist_report(
        self, report: DiagnosticReportData, user_id: Optional[int] = None
    ) -> None:
        """Persist a diagnostic report to the database."""
        checks_json = [
            {
                "name": c.name,
                "status": c.status.value,
                "message": c.message,
                "details": c.details,
                "metrics": c.metrics,
                "recommendations": c.recommendations,
                "duration_ms": c.duration_ms,
            }
            for c in report.checks
        ]

        db_report = DiagnosticReportModel(
            id=uuid.UUID(report.id),
            overall_status=report.overall_status.value,
            started_at=datetime.fromisoformat(report.started_at),
            finished_at=datetime.fromisoformat(report.finished_at),
            duration_seconds=report.duration_seconds,
            checks=checks_json,
            summary=report.summary,
            triggered_by=report.triggered_by,
            triggered_by_user=user_id,
        )
        self.session.add(db_report)
        try:
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to persist diagnostic report: {e}", exc_info=True)

    @staticmethod
    def _format_uptime(seconds: float) -> str:
        """Format uptime seconds to human-readable string."""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        parts: list[str] = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
