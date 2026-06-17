"""
Event Aggregator Service
Vereinheitlicht Events aus verschiedenen DB-Tabellen für System Monitor.

Architektur-Pattern:
- Transformer-Pattern für Unified Events
- Async/Await für parallele Queries
- Menschenverständliche Nachrichten

Standard: Industrial-Grade Gewächshausautomation
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, TypedDict


def ensure_utc_isoformat(dt: datetime) -> str:
    """
    Konvertiert datetime zu ISO-Format mit UTC-Timezone.

    Naive datetimes (ohne tzinfo) werden als UTC behandelt,
    da der Server intern immer UTC verwendet.

    Args:
        dt: datetime Objekt (naive oder aware)

    Returns:
        ISO 8601 String mit Timezone, z.B. "2026-01-26T17:32:02+00:00"
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Naive datetime: Server speichert UTC, also explizit markieren
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logging_config import get_logger
from ..db.models.audit_log import AuditLog
from ..db.models.sensor import SensorData
from ..db.models.esp import ESPDevice
from ..db.models.esp_heartbeat import ESPHeartbeatLog
from ..db.models.actuator import ActuatorHistory
from ..services.event_contract_serializers import (
    serialize_actuator_response_event,
    serialize_config_response_event,
    serialize_error_event,
    serialize_esp_health_event,
)
from ..utils.sensor_formatters import format_sensor_message, format_sensor_title

logger = get_logger(__name__)

DataSource = Literal["audit_log", "sensor_data", "esp_health", "actuators"]


class SourceCounts(TypedDict):
    """Count information for a single data source."""

    loaded: int
    available: int


class AggregationResult(TypedDict):
    """Result of event aggregation with counts."""

    events: List[Dict[str, Any]]
    total_loaded: int
    total_available: int
    source_counts: Dict[str, SourceCounts]


class EventAggregatorService:
    """
    Aggregiert Events aus mehreren Datenquellen.

    Verantwortlichkeiten:
    1. Queries zu verschiedenen Tabellen
    2. Transformation in Unified Event Format
    3. Chronologische Sortierung
    4. Performance-Optimierung (Limits, Indices)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def aggregate_events(
        self,
        sources: List[DataSource],
        after: Optional[datetime],
        limit_per_source: int = 500,
        severity_filter: Optional[List[str]] = None,
        esp_id_filter: Optional[List[str]] = None,
        before: Optional[datetime] = None,
    ) -> AggregationResult:
        """
        Haupt-Aggregations-Methode.

        Args:
            sources: Liste der zu aggregierenden Quellen
            after: Zeitstempel ab wann Events geladen werden (None = alle Events)
            limit_per_source: Max. Events pro Quelle (Performance)
            severity_filter: Filter nach Severity-Levels (nur für audit_log)
            esp_id_filter: Filter nach ESP-Device-IDs (für alle Quellen)
            before: Cursor für Pagination - lädt Events VOR diesem Zeitstempel

        Returns:
            AggregationResult mit:
            - events: Liste von Unified Events, chronologisch sortiert
            - total_loaded: Anzahl geladener Events
            - total_available: Gesamt-Anzahl verfügbarer Events über alle Quellen
            - source_counts: Dict mit Count pro Quelle (loaded/available)

        Performance:
        - Limit pro Quelle verhindert Überlastung
        - DB-Indices auf created_at/timestamp nutzen
        - COUNT queries nutzen dieselben Indizes
        - WARNUNG: after=None kann bei großen Datenbanken langsam sein

        Pagination:
        - Nutze before_timestamp um ältere Events zu laden (Infinite Scroll)
        - Events werden chronologisch sortiert (neueste zuerst)
        """
        from datetime import timezone as tz

        # Ensure 'after' is timezone-aware (UTC) if provided
        if after is not None and after.tzinfo is None:
            logger.warning(f"aggregate_events received naive datetime: {after}. " f"Assuming UTC.")
            after = after.replace(tzinfo=tz.utc)

        # Ensure 'before' is timezone-aware (UTC) if provided
        if before is not None and before.tzinfo is None:
            logger.warning(
                f"aggregate_events received naive datetime for 'before': {before}. "
                f"Assuming UTC."
            )
            before = before.replace(tzinfo=tz.utc)

        all_events: List[Dict[str, Any]] = []
        source_counts: Dict[str, SourceCounts] = {}
        total_available = 0

        # Query jede Quelle (wenn ausgewählt)
        if "audit_log" in sources:
            try:
                # audit_log supports both severity_filter and esp_id_filter
                audit_events = await self._get_audit_events(
                    after, limit_per_source, severity_filter, esp_id_filter, before
                )
                all_events.extend(audit_events)

                # Count verfügbare Events (with same filters)
                audit_count = await self._count_audit_events(after, severity_filter, esp_id_filter)
                source_counts["audit_log"] = {"loaded": len(audit_events), "available": audit_count}
                total_available += audit_count
            except Exception as e:
                logger.error(f"Failed to get audit events: {e}")
                source_counts["audit_log"] = {"loaded": 0, "available": 0}

        if "sensor_data" in sources:
            try:
                # sensor_data only supports esp_id_filter (no severity column)
                sensor_events = await self._get_sensor_events(
                    after, limit_per_source, esp_id_filter, before
                )
                all_events.extend(sensor_events)

                sensor_count = await self._count_sensor_events(after, esp_id_filter)
                source_counts["sensor_data"] = {
                    "loaded": len(sensor_events),
                    "available": sensor_count,
                }
                total_available += sensor_count
            except Exception as e:
                logger.error(f"Failed to get sensor events: {e}")
                source_counts["sensor_data"] = {"loaded": 0, "available": 0}

        if "esp_health" in sources:
            try:
                # esp_health only supports esp_id_filter (no severity column)
                health_events = await self._get_health_events(
                    after, limit_per_source, esp_id_filter, before
                )
                all_events.extend(health_events)

                health_count = await self._count_health_events(after, esp_id_filter)
                source_counts["esp_health"] = {
                    "loaded": len(health_events),
                    "available": health_count,
                }
                total_available += health_count
            except Exception as e:
                logger.error(f"Failed to get health events: {e}")
                source_counts["esp_health"] = {"loaded": 0, "available": 0}

        if "actuators" in sources:
            try:
                # actuators only supports esp_id_filter (no severity column)
                actuator_events = await self._get_actuator_events(
                    after, limit_per_source, esp_id_filter, before
                )
                all_events.extend(actuator_events)

                actuator_count = await self._count_actuator_events(after, esp_id_filter)
                source_counts["actuators"] = {
                    "loaded": len(actuator_events),
                    "available": actuator_count,
                }
                total_available += actuator_count
            except Exception as e:
                logger.error(f"Failed to get actuator events: {e}")
                source_counts["actuators"] = {"loaded": 0, "available": 0}

        # Sortiere chronologisch (neueste zuerst)
        all_events.sort(key=lambda e: e["timestamp"], reverse=True)

        return {
            "events": all_events,
            "total_loaded": len(all_events),
            "total_available": total_available,
            "source_counts": source_counts,
        }

    # =====================================================================
    # PRIVATE TRANSFORMER-METHODEN
    # =====================================================================

    async def _get_audit_events(
        self,
        after: Optional[datetime],
        limit: int,
        severity_filter: Optional[List[str]] = None,
        esp_id_filter: Optional[List[str]] = None,
        before: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lädt und transformiert Audit-Log Events.

        Args:
            after: Zeitstempel ab wann Events geladen werden
            limit: Max. Anzahl Events
            severity_filter: Filter nach Severity-Levels (info, warning, error, critical)
            esp_id_filter: Filter nach ESP-Device-IDs (über source_id Spalte)
            before: Cursor für Pagination - Events VOR diesem Zeitstempel
        """
        query = select(AuditLog)

        # Add time filter only if 'after' is specified
        if after is not None:
            query = query.where(AuditLog.created_at >= after)

        # Add 'before' filter for pagination (cursor-based)
        if before is not None:
            query = query.where(AuditLog.created_at < before)

        # Add severity filter (audit_log has severity column)
        if severity_filter:
            query = query.where(AuditLog.severity.in_(severity_filter))

        # Add ESP-ID filter (audit_log uses source_id for device identification)
        if esp_id_filter:
            query = query.where(AuditLog.source_id.in_(esp_id_filter))

        query = query.order_by(desc(AuditLog.created_at)).limit(limit)

        result = await self.db.execute(query)
        logs = result.scalars().all()

        return [self._transform_audit_to_unified(log) for log in logs]

    def _transform_audit_to_unified(self, log: AuditLog) -> Dict[str, Any]:
        """
        Audit-Log → Unified Event Format.

        Menschenverständliche Transformation:
        - event_type → Kategorie + Titel
        - severity übernehmen
        - message formatieren
        """
        # Kategorisierung (menschenverständlich)
        category_map = {
            "config_response": "Konfiguration",
            "config_published": "Konfiguration",
            "config_failed": "Konfiguration",
            "emergency_stop": "Notfall",
            "device_offline": "Geräte-Status",
            "device_online": "Geräte-Status",
            "device_discovered": "Geräte-Status",
            "device_approved": "Geräte-Status",
            "device_rejected": "Geräte-Status",
            "device_rediscovered": "Geräte-Status",
            "lwt_received": "Geräte-Status",
            "mqtt_error": "Kommunikation",
            "validation_error": "Validierung",
            "database_error": "System",
            "login_success": "Authentifizierung",
            "login_failed": "Authentifizierung",
            "logout": "Authentifizierung",
            "service_start": "System",
            "service_stop": "System",
        }

        # Titel-Generierung (prägnant, deutsch)
        title_map = {
            "config_response": "Konfiguration empfangen",
            "config_published": "Konfiguration gesendet",
            "config_failed": "Konfigurationsfehler",
            "emergency_stop": "Notfall-Stopp ausgelöst",
            "device_offline": "Gerät offline",
            "device_online": "Gerät online",
            "device_discovered": "Neues Gerät entdeckt",
            "device_approved": "Gerät genehmigt",
            "device_rejected": "Gerät abgelehnt",
            "device_rediscovered": "Gerät wieder online",
            "lwt_received": "Unerwarteter Verbindungsabbruch",
            "mqtt_error": "MQTT-Fehler",
            "validation_error": "Validierungsfehler",
            "database_error": "Datenbankfehler",
            "login_success": "Anmeldung erfolgreich",
            "login_failed": "Anmeldung fehlgeschlagen",
            "logout": "Abmeldung",
            "service_start": "Dienst gestartet",
            "service_stop": "Dienst gestoppt",
        }

        category = category_map.get(log.event_type, "System")
        base_title = title_map.get(log.event_type, log.event_type.replace("_", " ").title())

        # Titel mit Device-ID anreichern
        device_id = None
        if log.source_id:
            device_id = log.source_id
            title = f"{log.source_id}: {base_title}"
        else:
            title = base_title

        metadata: Dict[str, Any] = {
            "event_type": log.event_type,
            "source_type": log.source_type,
            "status": log.status,
            "error_code": log.error_code,
            "error_description": log.error_description,
            "request_id": log.request_id,
            "correlation_id": log.correlation_id,
            **(log.details or {}),
        }

        event_ts = ensure_utc_isoformat(log.created_at)
        event_ts_seconds = int(log.created_at.replace(tzinfo=timezone.utc).timestamp())
        details = log.details or {}

        if log.event_type == "config_response":
            metadata["contract_payload"] = serialize_config_response_event(
                esp_id=log.source_id or "unknown",
                config_type=details.get("config_type"),
                status=log.status or "error",
                count=details.get("count", 0),
                failed_count=details.get("failed_count", 0),
                message=log.message or details.get("message", ""),
                timestamp=event_ts_seconds,
                correlation_id=log.correlation_id,
                request_id=log.request_id,
                error_code=log.error_code,
                error_description=log.error_description,
                failures=details.get("failures"),
                failed_item=details.get("failed_item"),
            )
        elif log.event_type == "mqtt_error":
            metadata["contract_payload"] = serialize_error_event(
                esp_id=log.source_id or "unknown",
                esp_name=log.source_id or "unknown",
                error_log_id=log.id,
                error_code=details.get("error_code", log.error_code),
                severity=log.severity or "error",
                category=details.get("category"),
                title=(log.message or f"Fehler {details.get('error_code', log.error_code)}"),
                message=log.error_description or log.message or "Unbekannter MQTT-Fehler",
                troubleshooting=details.get("troubleshooting", []),
                user_action_required=details.get("user_action_required", False),
                recoverable=details.get("recoverable", True),
                docs_link=details.get("docs_link"),
                context=details.get("context", {}),
                timestamp=details.get("esp_timestamp", event_ts_seconds),
            )

        return {
            "id": f"audit_{log.id}",
            "timestamp": event_ts,
            "source": "audit_log",
            "category": category,
            "title": title,
            "message": log.message or base_title,
            "severity": log.severity or "info",
            "device_id": device_id,
            "metadata": metadata,
        }

    async def _get_sensor_events(
        self,
        after: Optional[datetime],
        limit: int,
        esp_id_filter: Optional[List[str]] = None,
        before: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lädt und transformiert Sensor-Daten.

        Args:
            after: Zeitstempel ab wann Events geladen werden
            limit: Max. Anzahl Events
            esp_id_filter: Filter nach ESP-Device-IDs (über ESPDevice.device_id)
            before: Cursor für Pagination - Events VOR diesem Zeitstempel
        """
        # Join mit ESPDevice um device_id zu bekommen
        query = select(SensorData, ESPDevice.device_id).join(
            ESPDevice, SensorData.esp_id == ESPDevice.id
        )

        # Add time filter only if 'after' is specified
        if after is not None:
            query = query.where(SensorData.timestamp >= after)

        # Add 'before' filter for pagination (cursor-based)
        if before is not None:
            query = query.where(SensorData.timestamp < before)

        # Add ESP-ID filter (filter on ESPDevice.device_id from JOIN)
        if esp_id_filter:
            query = query.where(ESPDevice.device_id.in_(esp_id_filter))

        query = query.order_by(desc(SensorData.timestamp)).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()

        return [
            self._transform_sensor_to_unified(sensor_data, device_id)
            for sensor_data, device_id in rows
        ]

    def _transform_sensor_to_unified(self, data: SensorData, device_id: str) -> Dict[str, Any]:
        """
        Sensor-Data -> Unified Event Format.

        Menschenverstandliche Transformation via zentrale Formatter-Funktion.
        Format: "[SENSOR-NAME] GPIO [X]: [WERT][EINHEIT]"
        Beispiel: "Temperatur GPIO 4: 25.3degC"

        Server-Centric: Gleiche Formatter-Funktion wie im WebSocket-Broadcast.
        """
        # Wert ermitteln (processed hat Prioritat)
        value = data.processed_value if data.processed_value is not None else data.raw_value

        # Einheitliche Message via zentrale Formatter-Funktion
        message = format_sensor_message(
            sensor_type=data.sensor_type,
            gpio=data.gpio,
            value=value,
            unit=data.unit,
        )

        # Einheitlicher Titel via zentrale Formatter-Funktion
        title = format_sensor_title(data.sensor_type, device_id)

        return {
            "id": f"sensor_{data.id}",
            "timestamp": ensure_utc_isoformat(data.timestamp),
            "source": "sensor_data",
            "category": "Sensordaten",
            "title": title,
            "message": message,
            "severity": "info",
            "device_id": device_id,
            "metadata": {
                "gpio": data.gpio,
                "sensor_type": data.sensor_type,
                "raw_value": data.raw_value,
                "processed_value": data.processed_value,
                "unit": data.unit,
                "processing_mode": data.processing_mode,
                "quality": data.quality,
                "data_source": data.data_source,
            },
        }

    async def _get_health_events(
        self,
        after: Optional[datetime],
        limit: int,
        esp_id_filter: Optional[List[str]] = None,
        before: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lädt ESP-Health Events aus esp_heartbeat_logs Tabelle.

        Echte historische Heartbeat-Events (Time-Series) statt synthetischer
        Events aus esp_devices.last_seen.

        Args:
            after: Zeitstempel ab wann Events geladen werden
            limit: Max. Anzahl Events
            esp_id_filter: Filter nach ESP-Device-IDs (über device_id Spalte)
            before: Cursor für Pagination - Events VOR diesem Zeitstempel

        Performance:
        - Index auf timestamp für schnelle Time-Range Queries
        - Limit verhindert Überlastung bei vielen Heartbeats
        """
        query = select(ESPHeartbeatLog)

        # Add time filter only if 'after' is specified
        if after is not None:
            query = query.where(ESPHeartbeatLog.timestamp >= after)

        # Add 'before' filter for pagination (cursor-based)
        if before is not None:
            query = query.where(ESPHeartbeatLog.timestamp < before)

        # Add ESP-ID filter (esp_heartbeat_logs has device_id column directly)
        if esp_id_filter:
            query = query.where(ESPHeartbeatLog.device_id.in_(esp_id_filter))

        query = query.order_by(desc(ESPHeartbeatLog.timestamp)).limit(limit)

        result = await self.db.execute(query)
        heartbeats = result.scalars().all()

        return [self._transform_heartbeat_to_unified(hb) for hb in heartbeats]

    def _transform_heartbeat_to_unified(self, heartbeat: ESPHeartbeatLog) -> Dict[str, Any]:
        """
        ESPHeartbeatLog → Unified Event Format.

        Menschenverständliche Transformation:
        - Health-Metriken formatieren (RAM, WiFi, Uptime)
        - Severity basierend auf health_status

        EINHEITLICHES FORMAT (identisch mit Frontend WebSocket-Fallback):
        "{device_id} online ({heap_kb}KB frei, RSSI: {wifi_rssi}dBm)"
        Mit optionalem Uptime: "| Uptime: Xh Ym"
        """
        rt = getattr(heartbeat, "runtime_telemetry", None) or {}
        contract_payload = serialize_esp_health_event(
            esp_id=heartbeat.device_id,
            status="online",
            heap_free=heartbeat.heap_free,
            wifi_rssi=heartbeat.wifi_rssi,
            uptime=heartbeat.uptime,
            sensor_count=heartbeat.sensor_count,
            actuator_count=heartbeat.actuator_count,
            timestamp=int(heartbeat.timestamp.replace(tzinfo=timezone.utc).timestamp()),
            gpio_reserved_count=heartbeat.gpio_reserved_count or 0,
            runtime_telemetry=rt,
        )

        # Severity basierend auf health_status (Ampel-System)
        severity_map = {
            "healthy": "info",
            "degraded": "warning",
            "critical": "error",
        }
        severity = severity_map.get(heartbeat.health_status, "info")
        if isinstance(rt, dict) and (
            rt.get("persistence_degraded") is True
            or rt.get("runtime_state_degraded") is True
            or rt.get("network_degraded") is True
        ):
            if severity == "info":
                severity = "warning"

        return {
            "id": f"heartbeat_{heartbeat.id}",
            "timestamp": ensure_utc_isoformat(heartbeat.timestamp),
            "source": "esp_health",
            "category": "ESP-Status",
            "title": f"{heartbeat.device_id}: Heartbeat",
            "message": contract_payload["message"],
            "severity": severity,
            "device_id": heartbeat.device_id,
            "metadata": {
                "health_status": heartbeat.health_status,
                "data_source": heartbeat.data_source,
                "contract_payload": contract_payload,
                "runtime_telemetry": rt,
            },
        }

    async def _get_actuator_events(
        self,
        after: Optional[datetime],
        limit: int,
        esp_id_filter: Optional[List[str]] = None,
        before: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lädt und transformiert Aktor-History.

        Args:
            after: Zeitstempel ab wann Events geladen werden
            limit: Max. Anzahl Events
            esp_id_filter: Filter nach ESP-Device-IDs (über ESPDevice.device_id)
            before: Cursor für Pagination - Events VOR diesem Zeitstempel
        """
        # Join mit ESPDevice um device_id zu bekommen
        query = select(ActuatorHistory, ESPDevice.device_id).join(
            ESPDevice, ActuatorHistory.esp_id == ESPDevice.id
        )

        # Add time filter only if 'after' is specified
        if after is not None:
            query = query.where(ActuatorHistory.timestamp >= after)

        # Add 'before' filter for pagination (cursor-based)
        if before is not None:
            query = query.where(ActuatorHistory.timestamp < before)

        # Add ESP-ID filter (filter on ESPDevice.device_id from JOIN)
        if esp_id_filter:
            query = query.where(ESPDevice.device_id.in_(esp_id_filter))

        query = query.order_by(desc(ActuatorHistory.timestamp)).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()

        return [
            self._transform_actuator_to_unified(history, device_id) for history, device_id in rows
        ]

    def _transform_actuator_to_unified(
        self, history: ActuatorHistory, device_id: str
    ) -> Dict[str, Any]:
        """
        Actuator-History → Unified Event Format.
        """
        # Aktor-Typen (deutsch)
        actuator_type_names = {
            "pump": "Pumpe",
            "valve": "Ventil",
            "relay": "Relais",
            "pwm": "PWM-Ausgang",
            "light": "Beleuchtung",
            "fan": "Lüfter",
            "heater": "Heizung",
        }

        # Command-Typen (deutsch)
        command_names = {
            "set": "gesetzt",
            "stop": "gestoppt",
            "emergency_stop": "Notfall-Stopp",
            "on": "eingeschaltet",
            "off": "ausgeschaltet",
        }

        actuator_name = actuator_type_names.get(history.actuator_type, history.actuator_type)
        command = command_names.get(history.command_type, history.command_type)

        contract_payload = serialize_actuator_response_event(
            esp_id=device_id,
            gpio=history.gpio,
            command=history.command_type,
            value=history.value if history.value is not None else 0.0,
            success=history.success,
            message=history.error_message or "",
            timestamp=int(history.timestamp.replace(tzinfo=timezone.utc).timestamp()),
        )

        # Message formatieren
        parts = [f"GPIO {history.gpio}"]
        if history.value is not None:
            if history.actuator_type == "pwm":
                parts.append(f"PWM: {int(history.value * 100)}%")
            else:
                parts.append(f"Wert: {history.value}")

        message = " | ".join(parts)

        # Titel
        if history.success:
            title = f"{device_id}: {actuator_name} {command}"
            severity = "info"
        else:
            title = f"{device_id}: {actuator_name} Fehler"
            severity = "error"

        return {
            "id": f"actuator_{history.id}",
            "timestamp": ensure_utc_isoformat(history.timestamp),
            "source": "actuators",
            "category": "Aktoren",
            "title": title,
            "message": (
                message if history.success else (history.error_message or "Unbekannter Fehler")
            ),
            "severity": severity,
            "device_id": device_id,
            "metadata": {
                "actuator_type": history.actuator_type,
                "issued_by": history.issued_by,
                "data_source": history.data_source,
                "contract_payload": contract_payload,
                **(history.command_metadata or {}),
            },
        }

    # =====================================================================
    # PRIVATE COUNT-METHODEN (für total_available Berechnung)
    # =====================================================================

    async def _count_audit_events(
        self,
        after: Optional[datetime],
        severity_filter: Optional[List[str]] = None,
        esp_id_filter: Optional[List[str]] = None,
    ) -> int:
        """Zählt verfügbare Audit-Log Events (mit denselben Filtern wie _get_audit_events)."""
        query = select(func.count(AuditLog.id))
        if after is not None:
            query = query.where(AuditLog.created_at >= after)
        if severity_filter:
            query = query.where(AuditLog.severity.in_(severity_filter))
        if esp_id_filter:
            query = query.where(AuditLog.source_id.in_(esp_id_filter))
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _count_sensor_events(
        self, after: Optional[datetime], esp_id_filter: Optional[List[str]] = None
    ) -> int:
        """Zählt verfügbare Sensor-Data Events (mit denselben Filtern wie _get_sensor_events)."""
        # Need to join with ESPDevice if filtering by esp_id
        if esp_id_filter:
            query = select(func.count(SensorData.id)).join(
                ESPDevice, SensorData.esp_id == ESPDevice.id
            )
            query = query.where(ESPDevice.device_id.in_(esp_id_filter))
        else:
            query = select(func.count(SensorData.id))

        if after is not None:
            query = query.where(SensorData.timestamp >= after)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _count_health_events(
        self, after: Optional[datetime], esp_id_filter: Optional[List[str]] = None
    ) -> int:
        """Zählt verfügbare ESP-Heartbeat Events (mit denselben Filtern wie _get_health_events)."""
        query = select(func.count(ESPHeartbeatLog.id))
        if after is not None:
            query = query.where(ESPHeartbeatLog.timestamp >= after)
        if esp_id_filter:
            query = query.where(ESPHeartbeatLog.device_id.in_(esp_id_filter))
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def _count_actuator_events(
        self, after: Optional[datetime], esp_id_filter: Optional[List[str]] = None
    ) -> int:
        """Zählt verfügbare Actuator-History Events (mit denselben Filtern wie _get_actuator_events)."""
        # Need to join with ESPDevice if filtering by esp_id
        if esp_id_filter:
            query = select(func.count(ActuatorHistory.id)).join(
                ESPDevice, ActuatorHistory.esp_id == ESPDevice.id
            )
            query = query.where(ESPDevice.device_id.in_(esp_id_filter))
        else:
            query = select(func.count(ActuatorHistory.id))

        if after is not None:
            query = query.where(ActuatorHistory.timestamp >= after)
        result = await self.db.execute(query)
        return result.scalar() or 0
