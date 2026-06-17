"""
Prometheus Custom Metrics for God-Kaiser Server

Module-level Gauge/Counter definitions registered in the default prometheus_client registry.
The prometheus-fastapi-instrumentator exposes these automatically alongside HTTP metrics
at /api/v1/health/metrics.

Update strategy:
- Gauges are updated via update_custom_metrics() called from a periodic scheduler job.
- ESP counts require a DB session, so updates are async.
- Counters (MQTT) are incremented directly in hot paths via increment functions.
"""

import time

try:
    import psutil
except ImportError:
    psutil = None

try:
    from prometheus_client import Counter, Gauge, Histogram
except ImportError:

    class _NoOpMetric:
        """Stub metric when prometheus_client is not installed (e.g. local test runs)."""

        def __init__(self, *args, **kwargs):
            pass

        def set(self, value):
            pass

        def inc(self, amount=1):
            pass

        def observe(self, amount):
            pass

        def labels(self, **kwargs):
            return self

    Counter = _NoOpMetric
    Gauge = _NoOpMetric
    Histogram = _NoOpMetric

from .logging_config import get_logger

logger = get_logger(__name__)

# =============================================================================
# Server Gauges
# =============================================================================

UPTIME_GAUGE = Gauge(
    "god_kaiser_uptime_seconds",
    "Server uptime in seconds",
)

CPU_GAUGE = Gauge(
    "god_kaiser_cpu_percent",
    "Server CPU usage percentage",
)

MEMORY_GAUGE = Gauge(
    "god_kaiser_memory_percent",
    "Server memory usage percentage",
)

# =============================================================================
# MQTT Gauges + Counters
# =============================================================================

MQTT_CONNECTED_GAUGE = Gauge(
    "god_kaiser_mqtt_connected",
    "MQTT broker connection status (1=connected, 0=disconnected)",
)

MQTT_MESSAGES_TOTAL = Counter(
    "god_kaiser_mqtt_messages_total",
    "Total MQTT messages processed by El Servador",
    ["direction"],  # received, published
)

MQTT_ERRORS_TOTAL = Counter(
    "god_kaiser_mqtt_errors_total",
    "Total MQTT message processing errors",
    ["direction"],  # received, published
)

# =============================================================================
# WebSocket Gauges
# =============================================================================

WEBSOCKET_CONNECTIONS_GAUGE = Gauge(
    "god_kaiser_websocket_connections",
    "Active WebSocket connections to frontend clients",
)

# =============================================================================
# Database Histogram
# =============================================================================

DB_QUERY_DURATION = Histogram(
    "god_kaiser_db_query_duration_seconds",
    "Database query duration in seconds (app-side measurement)",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

# =============================================================================
# ESP Gauges
# =============================================================================

ESP_TOTAL_GAUGE = Gauge(
    "god_kaiser_esp_total",
    "Total registered ESP devices",
)

ESP_ONLINE_GAUGE = Gauge(
    "god_kaiser_esp_online",
    "Online ESP devices",
)

ESP_OFFLINE_GAUGE = Gauge(
    "god_kaiser_esp_offline",
    "Offline ESP devices",
)

# =============================================================================
# ESP Heartbeat Aggregated Gauges (no per-device labels to avoid cardinality)
# =============================================================================

ESP_AVG_HEAP_FREE_GAUGE = Gauge(
    "god_kaiser_esp_avg_heap_free_bytes",
    "Average free heap across online ESP devices",
)

ESP_MIN_HEAP_FREE_GAUGE = Gauge(
    "god_kaiser_esp_min_heap_free_bytes",
    "Minimum free heap across online ESP devices",
)

ESP_AVG_WIFI_RSSI_GAUGE = Gauge(
    "god_kaiser_esp_avg_wifi_rssi_dbm",
    "Average WiFi RSSI across online ESP devices",
)

ESP_AVG_UPTIME_GAUGE = Gauge(
    "god_kaiser_esp_avg_uptime_seconds",
    "Average uptime across online ESP devices",
)

# =============================================================================
# Sensor Gauges (Phase 0 — for Grafana alerting)
# =============================================================================

SENSOR_VALUE_GAUGE = Gauge(
    "god_kaiser_sensor_value",
    "Latest sensor reading value",
    ["sensor_type", "esp_id"],
)

SENSOR_LAST_UPDATE_GAUGE = Gauge(
    "god_kaiser_sensor_last_update",
    "Unix timestamp of last sensor data update",
    ["sensor_type", "esp_id"],
)

# =============================================================================
# ESP Per-Device Gauges/Counters (Phase 0 — for Grafana alerting)
# =============================================================================

ESP_LAST_HEARTBEAT_GAUGE = Gauge(
    "god_kaiser_esp_last_heartbeat",
    "Unix timestamp of last heartbeat per ESP device",
    ["esp_id"],
)

ESP_BOOT_COUNT_GAUGE = Gauge(
    "god_kaiser_esp_boot_count",
    "Boot count reported by ESP device (from heartbeat metadata)",
    ["esp_id"],
)

ESP_ERRORS_TOTAL = Counter(
    "god_kaiser_esp_errors_total",
    "Total error reports received from ESP devices",
    ["esp_id"],
)

ESP_SAFE_MODE_GAUGE = Gauge(
    "god_kaiser_esp_safe_mode",
    "Whether ESP device is in safe mode (1=safe_mode, 0=normal)",
    ["esp_id"],
)

# =============================================================================
# Application Counters (Phase 0 — for Grafana alerting)
# =============================================================================

WS_DISCONNECTS_TOTAL = Counter(
    "god_kaiser_ws_disconnects_total",
    "Total WebSocket client disconnections",
)

MQTT_QUEUED_MESSAGES_GAUGE = Gauge(
    "god_kaiser_mqtt_queued_messages",
    "Number of messages currently queued in MQTT offline buffer",
)

HTTP_ERRORS_TOTAL = Counter(
    "god_kaiser_http_errors_total",
    "Total HTTP error responses (4xx/5xx)",
    ["status_class"],  # 4xx, 5xx
)

LOGIC_ERRORS_TOTAL = Counter(
    "god_kaiser_logic_errors_total",
    "Total logic engine evaluation errors",
)

LOGIC_DISPATCH_SKIPPED_CONFIG_PENDING_TOTAL = Counter(
    "god_kaiser_logic_dispatch_skipped_config_pending_total",
    "Actuator dispatches skipped because ESP is in CONFIG_PENDING_AFTER_RESET",
)

LOGIC_DISPATCH_SKIPPED_OFFLINE_TOTAL = Counter(
    "god_kaiser_logic_dispatch_skipped_offline_total",
    "Actuator dispatches skipped because ESP is offline",
)

# AUT-110: Per-rule offline-skip counter (labeled)
RULE_SKIP_TARGET_OFFLINE_TOTAL = Counter(
    "god_kaiser_rule_skip_target_offline_total",
    "Actuator dispatches skipped because target ESP is offline, labeled per rule",
    ["rule_id", "esp_id", "time_window"],
)

ACTUATOR_TIMEOUTS_TOTAL = Counter(
    "god_kaiser_actuator_timeouts_total",
    "Total actuator command timeouts",
)

WS_MISSING_CORRELATION_TOTAL = Counter(
    "god_kaiser_ws_missing_correlation_total",
    "Total WebSocket events without envelope/data correlation_id",
)

WS_ENVELOPE_DATA_DIVERGENCE_TOTAL = Counter(
    "god_kaiser_ws_envelope_data_divergence_total",
    "Total WebSocket events where envelope correlation_id differs from data.correlation_id",
)

WS_CONTRACT_MISMATCH_TOTAL = Counter(
    "god_kaiser_ws_contract_mismatch_total",
    "Total contract mismatch signals emitted by WebSocket contract hardening",
)

CONTRACT_TERMINALIZATION_BLOCKED_TOTAL = Counter(
    "god_kaiser_contract_terminalization_blocked_total",
    "Total terminalization attempts blocked by contract authority guards",
    ["event_class", "reason"],
)

# AUT-715: Sensor batch replay metrics (offline spool)
BATCH_REPLAYED_TOTAL = Counter(
    "autoone_sensor_batch_replayed_total",
    "Total sensor readings replayed from offline spool",
)
BATCH_SKIPPED_TOTAL = Counter(
    "autoone_sensor_batch_skipped_total",
    "Total sensor batch readings skipped (dedup or parse error)",
)
BATCH_QUEUED_TOTAL = Counter(
    "autoone_sensor_batch_queued_total",
    "Total sensor readings received in batch messages",
)

SAFETY_TRIGGERS_TOTAL = Counter(
    "god_kaiser_safety_triggers_total",
    "Total safety system trigger events (emergency stops, rate limits, conflict blocks)",
)

# =============================================================================
# Package 09 Contract/Readiness Metrics (AP-09A freeze names)
# =============================================================================

CONFIG_INTENTS_ACCEPTED_TOTAL = Counter(
    "config_intents_accepted_total",
    "Total config intents accepted",
)

CONFIG_INTENTS_APPLIED_TOTAL = Counter(
    "config_intents_applied_total",
    "Total config intents applied",
)

CONFIG_INTENTS_PERSISTED_TOTAL = Counter(
    "config_intents_persisted_total",
    "Total config intents persisted (final success in v2 contract)",
)

CONFIG_INTENTS_FAILED_TOTAL = Counter(
    "config_intents_failed_total",
    "Total config intents with final failure outcomes",
)

CONFIG_COMMIT_DURATION_MS = Histogram(
    "config_commit_duration_ms",
    "Config persistence commit duration in milliseconds",
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)

INTENT_DUPLICATE_TOTAL = Counter(
    "intent_duplicate_total",
    "Total duplicate/stale intents detected by dedup guard",
)

INTENT_DEDUP_HITS = Counter(
    "intent_dedup_hits",
    "Total idempotent dedup hits for repeated intent processing",
)

OUTCOME_RETRY_COUNT = Counter(
    "outcome_retry_count",
    "Total retries observed on intent_outcome delivery",
)

OUTCOME_RECOVERED_COUNT = Counter(
    "outcome_recovered_count",
    "Total recovered intent_outcomes delivered from retry/outbox path",
)

OUTCOME_DROP_COUNT_CRITICAL = Gauge(
    "outcome_drop_count_critical",
    "Current reported count of critical outcome drops per ESP (must stay 0)",
    ["esp_id"],
)

INTENT_OUTCOME_FIRMWARE_CODE_TOTAL = Counter(
    "intent_outcome_firmware_code_total",
    "Observed intent_outcome code strings from firmware (sanitized label)",
    ["flow", "code"],
)

INTENT_OUTCOME_LIFECYCLE_TOTAL = Counter(
    "intent_outcome_lifecycle_total",
    "CONFIG_PENDING lifecycle events on system/intent_outcome/lifecycle",
    ["event_type", "schema"],
)

INTENT_TRACING_DEGRADED_TOTAL = Counter(
    "intent_tracing_degraded_total",
    "Intent trace ingest degraded (malformed lifecycle, contract-unknown bursts, etc.)",
    ["reason", "esp_id"],
)

MQTT_ACK_REASON_CODE_TOTAL = Counter(
    "mqtt_ack_reason_code_total",
    "Zone/subzone ACK payloads carrying firmware reason_code",
    ["ack_kind", "reason_code"],
)

HEARTBEAT_FIRMWARE_FLAG_TOTAL = Counter(
    "heartbeat_firmware_flag_total",
    "Heartbeat messages reporting a true degraded/flag telemetry field",
    ["flag"],
)

HEARTBEAT_FIRMWARE_COUNTER_GAUGE = Gauge(
    "heartbeat_firmware_counter",
    "Latest firmware counter value reported in heartbeat (drop/reject/drift)",
    ["esp_id", "counter_name"],
)

QUEUE_PRESSURE_EVENT_TOTAL = Counter(
    "queue_pressure_event_total",
    "ESP32 publish-queue pressure events (entered_pressure / recovered)",
    ["esp_id", "event"],
)

CONTRACT_UNKNOWN_CODE_TOTAL = Counter(
    "contract_unknown_code_total",
    "Total unknown/contract-violation codes normalized by server canonicalizer",
    ["event_type"],
)

RECONCILIATION_SESSIONS_TOTAL = Counter(
    "reconciliation_sessions_total",
    "Total reconciliation replay sessions by phase",
    ["phase"],
)

CONNECT_ATTEMPTS_TOTAL = Counter(
    "connect_attempts",
    "Total reconnect/connect attempts observed by server-side handlers",
)

TLS_HANDSHAKE_LATENCY_MS = Histogram(
    "tls_handshake_latency",
    "Estimated TLS handshake latency in milliseconds from telemetry payloads",
    buckets=(5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)

HEARTBEAT_ACK_LATENCY_MS = Histogram(
    "heartbeat_ack_latency",
    "Heartbeat ACK turnaround latency in milliseconds",
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500),
)

SENSOR_E2E_LATENCY_MS = Histogram(
    "sensor_e2e_latency_ms",
    "End-to-end latency from ESP32 sensor publish timestamp to server receive (milliseconds)",
    ["sensor_type"],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000),
)

HEARTBEAT_ACK_VALID_TOTAL = Counter(
    "heartbeat_ack_valid_total",
    "Total heartbeat ACKs sent with valid contract fields",
)

HEARTBEAT_CONTRACT_REJECT_TOTAL = Counter(
    "heartbeat_contract_reject_total",
    "Total heartbeat ACK contract rejections reported by ESP",
    ["reason"],
)

DISCONNECT_REASON_DISTRIBUTION = Counter(
    "disconnect_reason_distribution",
    "Distribution of disconnect reasons",
    ["reason"],
)

READY_TRANSITION_TOTAL = Counter(
    "ready_transition_total",
    "Total runtime transitions to ready=true",
)

READY_BLOCKED_TOTAL = Counter(
    "ready_blocked_total",
    "Total readiness computations blocked by guard conditions",
)

NOT_FOUND_EXPECTED_TOTAL = Counter(
    "not_found_expected_total",
    "Total expected not-found events",
)

NOT_FOUND_UNEXPECTED_TOTAL = Counter(
    "not_found_unexpected_total",
    "Total unexpected missing-key events",
)

SENSOR_IMPLAUSIBLE_TOTAL = Counter(
    "god_kaiser_sensor_implausible_total",
    "Total implausible sensor values received (outside physical datasheet limits)",
    ["sensor_type", "esp_id"],
)

# =============================================================================
# API Error Code Counter (per numeric_code from GodKaiserException)
# =============================================================================

API_ERROR_CODE_COUNTER = Counter(
    "god_kaiser_api_error_code_total",
    "Total API errors by numeric error code and source type",
    ["error_code", "source_type"],  # e.g. error_code="5210", source_type="server"
)

# =============================================================================
# Notification Pipeline Metrics (Phase 4A)
# =============================================================================

NOTIFICATIONS_TOTAL = Counter(
    "god_kaiser_notifications_total",
    "Total notifications created",
    ["severity", "category", "source"],
)

NOTIFICATIONS_SUPPRESSED_TOTAL = Counter(
    "god_kaiser_notifications_suppressed_total",
    "Total suppressed notifications",
    ["reason"],
)

NOTIFICATIONS_DEDUPLICATED_TOTAL = Counter(
    "god_kaiser_notifications_deduplicated_total",
    "Total deduplicated notifications (fingerprint or title)",
)

EMAIL_SENT_TOTAL = Counter(
    "god_kaiser_email_sent_total",
    "Total emails sent",
    ["provider", "status"],
)

EMAIL_LATENCY_SECONDS = Histogram(
    "god_kaiser_email_latency_seconds",
    "Email sending latency in seconds",
    ["provider"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

DIGEST_PROCESSED_TOTAL = Counter(
    "god_kaiser_digest_processed_total",
    "Total digest batches processed",
)

DIGEST_NOTIFICATIONS_PER_BATCH = Histogram(
    "god_kaiser_digest_notifications_per_batch",
    "Number of notifications per digest batch",
    buckets=(1, 3, 5, 10, 20, 50),
)

WS_NOTIFICATION_BROADCAST_TOTAL = Counter(
    "god_kaiser_ws_notification_broadcast_total",
    "Total WebSocket notification broadcasts",
    ["event_type"],
)

WEBHOOK_RECEIVED_TOTAL = Counter(
    "god_kaiser_webhook_received_total",
    "Total webhooks received",
    ["source", "status"],
)

ALERT_SUPPRESSION_ACTIVE = Gauge(
    "god_kaiser_alert_suppression_active",
    "Currently suppressed entities",
    ["entity_type"],
)

ALERT_SUPPRESSION_EXPIRED_TOTAL = Counter(
    "god_kaiser_alert_suppression_expired_total",
    "Total suppressions auto-expired by scheduler",
)

NOTIFICATIONS_READ_TOTAL = Counter(
    "god_kaiser_notifications_read_total",
    "Total notifications marked as read",
)

EMAIL_ERRORS_TOTAL = Counter(
    "god_kaiser_email_errors_total",
    "Total email errors by type",
    ["provider", "error_type"],
)

# Phase 4B: Alert Lifecycle Metrics (ISA-18.2)
ALERTS_ACKNOWLEDGED_TOTAL = Counter(
    "god_kaiser_alerts_acknowledged_total",
    "Total alerts acknowledged",
    ["severity"],
)

ALERTS_RESOLVED_TOTAL = Counter(
    "god_kaiser_alerts_resolved_total",
    "Total alerts resolved",
    ["severity", "resolution_type"],
)

ALERTS_ACTIVE_GAUGE = Gauge(
    "god_kaiser_alerts_active",
    "Currently active alerts",
    ["severity"],
)

ALERTS_ROOT_CAUSE_SUPPRESSED_TOTAL = Counter(
    "god_kaiser_alerts_root_cause_suppressed_total",
    "Total dependent alerts suppressed by root-cause correlation",
    ["source"],
)

# =============================================================================
# Database Backup Metrics (Phase A V5.1)
# =============================================================================

BACKUP_CREATED_TOTAL = Counter(
    "god_kaiser_backup_created_total",
    "Total successful database backups",
)

BACKUP_FAILED_TOTAL = Counter(
    "god_kaiser_backup_failed_total",
    "Total failed database backup attempts",
)

BACKUP_SIZE_BYTES = Gauge(
    "god_kaiser_backup_size_bytes",
    "Size of the last successful database backup in bytes",
)

BACKUP_LAST_SUCCESS_TIMESTAMP = Gauge(
    "god_kaiser_backup_last_success_timestamp",
    "Unix timestamp of the last successful database backup",
)

# =============================================================================
# Plugin System Metrics (Phase 4C)
# =============================================================================

PLUGIN_EXECUTIONS_TOTAL = Counter(
    "god_kaiser_plugin_executions_total",
    "Total plugin executions",
    ["plugin_id", "status", "trigger_source"],
)

PLUGIN_EXECUTION_DURATION = Histogram(
    "god_kaiser_plugin_execution_duration_seconds",
    "Plugin execution duration in seconds",
    ["plugin_id"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

PLUGIN_ERRORS_TOTAL = Counter(
    "god_kaiser_plugin_errors_total",
    "Total plugin execution errors",
    ["plugin_id", "error_type"],
)

PLUGINS_REGISTERED_GAUGE = Gauge(
    "god_kaiser_plugins_registered",
    "Number of registered plugins in the registry",
)

PLUGINS_ENABLED_GAUGE = Gauge(
    "god_kaiser_plugins_enabled",
    "Number of enabled plugins",
)

# Track server start time
_server_start_time: float = time.time()
_metrics_initialized: bool = False


def set_server_start_time(start_time: float) -> None:
    """Set server start time (called once during startup)."""
    global _server_start_time
    _server_start_time = start_time


def init_metrics() -> None:
    """Initialize all labeled metrics so they appear in Prometheus at startup.

    Counters and Gauges with labels are invisible in Prometheus until their
    first increment/set. This causes alerts referencing them to evaluate
    to NoData. Initializing with 0 makes them visible immediately.
    """
    global _metrics_initialized
    if _metrics_initialized:
        return
    _metrics_initialized = True

    # MQTT error counters (referenced by ao-high-mqtt-error-rate alert)
    MQTT_ERRORS_TOTAL.labels(direction="received")
    MQTT_ERRORS_TOTAL.labels(direction="published")

    # MQTT message counters
    MQTT_MESSAGES_TOTAL.labels(direction="received")
    MQTT_MESSAGES_TOTAL.labels(direction="published")

    # HTTP error counters
    HTTP_ERRORS_TOTAL.labels(status_class="4xx")
    HTTP_ERRORS_TOTAL.labels(status_class="5xx")

    # Notification pipeline counters (Phase 4A)
    for sev in ("critical", "warning", "info"):
        NOTIFICATIONS_TOTAL.labels(severity=sev, category="system", source="sensor_threshold")
    NOTIFICATIONS_SUPPRESSED_TOTAL.labels(reason="maintenance")
    NOTIFICATIONS_SUPPRESSED_TOTAL.labels(reason="calibration")
    EMAIL_SENT_TOTAL.labels(provider="resend", status="success")
    EMAIL_SENT_TOTAL.labels(provider="resend", status="failure")
    EMAIL_SENT_TOTAL.labels(provider="smtp", status="success")
    EMAIL_SENT_TOTAL.labels(provider="smtp", status="failure")
    WS_NOTIFICATION_BROADCAST_TOTAL.labels(event_type="notification_new")
    WS_NOTIFICATION_BROADCAST_TOTAL.labels(event_type="notification_unread_count")
    WEBHOOK_RECEIVED_TOTAL.labels(source="grafana", status="processed")
    WEBHOOK_RECEIVED_TOTAL.labels(source="grafana", status="skipped")
    WEBHOOK_RECEIVED_TOTAL.labels(source="grafana", status="error")
    DISCONNECT_REASON_DISTRIBUTION.labels(reason="unexpected_disconnect")
    DISCONNECT_REASON_DISTRIBUTION.labels(reason="heartbeat_timeout")
    DISCONNECT_REASON_DISTRIBUTION.labels(reason="unknown")
    HEARTBEAT_CONTRACT_REJECT_TOTAL.labels(reason="UNKNOWN")
    HEARTBEAT_CONTRACT_REJECT_TOTAL.labels(reason="HANDOVER_EPOCH_MISMATCH")
    HEARTBEAT_CONTRACT_REJECT_TOTAL.labels(reason="MISSING_HANDOVER_EPOCH")
    CONTRACT_UNKNOWN_CODE_TOTAL.labels(event_type="intent_outcome")
    CONTRACT_UNKNOWN_CODE_TOTAL.labels(event_type="config_response")
    for _flow in ("config", "zone", "command", "publish"):
        for _code in (
            "pending_ring_eviction",
            "config_lane_busy",
            "json_parse_error",
            "publish_outbox_full",
            "none",
        ):
            INTENT_OUTCOME_FIRMWARE_CODE_TOTAL.labels(flow=_flow, code=_code)
    for _et in ("entered_config_pending", "exit_blocked_config_pending", "exited_config_pending"):
        INTENT_OUTCOME_LIFECYCLE_TOTAL.labels(event_type=_et, schema="config_pending_lifecycle_v1")
    for _reason in (
        "malformed_lifecycle_payload",
        "contract_unknown_intent_outcome",
        "intent_outcome_missing_intent_id",
    ):
        for _esp in ("unknown", "ESP_TEST"):
            INTENT_TRACING_DEGRADED_TOTAL.labels(reason=_reason, esp_id=_esp)
    for _kind in ("zone", "subzone"):
        for _rc in ("config_lane_busy", "json_parse_error", "subzone_not_found", "none"):
            MQTT_ACK_REASON_CODE_TOTAL.labels(ack_kind=_kind, reason_code=_rc)
    for _flag in (
        "persistence_degraded",
        "runtime_state_degraded",
        "network_degraded",
        "mqtt_circuit_breaker_open",
        "wifi_circuit_breaker_open",
    ):
        HEARTBEAT_FIRMWARE_FLAG_TOTAL.labels(flag=_flag)
    CONTRACT_UNKNOWN_CODE_TOTAL.labels(event_type="actuator_response")
    RECONCILIATION_SESSIONS_TOTAL.labels(phase="start")
    RECONCILIATION_SESSIONS_TOTAL.labels(phase="progress")
    RECONCILIATION_SESSIONS_TOTAL.labels(phase="end")
    ALERT_SUPPRESSION_ACTIVE.labels(entity_type="sensor")
    ALERT_SUPPRESSION_ACTIVE.labels(entity_type="actuator")
    ALERT_SUPPRESSION_ACTIVE.labels(entity_type="device")
    EMAIL_ERRORS_TOTAL.labels(provider="resend", error_type="connection")
    EMAIL_ERRORS_TOTAL.labels(provider="smtp", error_type="connection")

    # Phase 4B: Alert lifecycle metrics
    for sev in ("critical", "warning", "info"):
        ALERTS_ACKNOWLEDGED_TOTAL.labels(severity=sev)
        ALERTS_RESOLVED_TOTAL.labels(severity=sev, resolution_type="manual")
        ALERTS_RESOLVED_TOTAL.labels(severity=sev, resolution_type="auto")
        ALERTS_ACTIVE_GAUGE.labels(severity=sev)
    ALERTS_ROOT_CAUSE_SUPPRESSED_TOTAL.labels(source="grafana")
    ALERTS_ROOT_CAUSE_SUPPRESSED_TOTAL.labels(source="sensor_threshold")

    # Phase 4C: Plugin system metrics
    for pid in ("health_check", "esp_configurator", "debug_fix", "system_cleanup"):
        for status in ("success", "error"):
            for trigger in ("manual", "schedule", "logic_rule"):
                PLUGIN_EXECUTIONS_TOTAL.labels(plugin_id=pid, status=status, trigger_source=trigger)
        PLUGIN_EXECUTION_DURATION.labels(plugin_id=pid)
        PLUGIN_ERRORS_TOTAL.labels(plugin_id=pid, error_type="execution_failed")
        PLUGIN_ERRORS_TOTAL.labels(plugin_id=pid, error_type="rollback_failed")

    # PKG-01b: Queue pressure events (esp_id="unknown" baseline for alert visibility)
    for _evt in ("entered_pressure", "recovered"):
        QUEUE_PRESSURE_EVENT_TOTAL.labels(esp_id="unknown", event=_evt)

    # PKG-03: Pre-init common sensor types so e2e latency histogram is visible
    for _st in (
        "temperature",
        "humidity",
        "ph",
        "ec",
        "co2",
        "pressure",
        "light",
        "flow",
        "soil",
    ):
        SENSOR_E2E_LATENCY_MS.labels(sensor_type=_st)

    logger.info("Prometheus metrics initialized (all label combinations visible)")


def update_system_metrics() -> None:
    """Update system-level metrics (CPU, memory, uptime). No DB needed."""
    UPTIME_GAUGE.set(time.time() - _server_start_time)
    if psutil:
        CPU_GAUGE.set(psutil.cpu_percent(interval=None))
        MEMORY_GAUGE.set(psutil.virtual_memory().percent)


def update_mqtt_metrics(connected: bool) -> None:
    """Update MQTT connection gauge."""
    MQTT_CONNECTED_GAUGE.set(1 if connected else 0)


def increment_mqtt_received() -> None:
    """Increment MQTT received message counter. Called from _on_message."""
    MQTT_MESSAGES_TOTAL.labels(direction="received").inc()


def increment_mqtt_published() -> None:
    """Increment MQTT published message counter. Called from publish()."""
    MQTT_MESSAGES_TOTAL.labels(direction="published").inc()


def increment_mqtt_receive_error() -> None:
    """Increment MQTT receive error counter."""
    MQTT_ERRORS_TOTAL.labels(direction="received").inc()


def increment_mqtt_publish_error() -> None:
    """Increment MQTT publish error counter."""
    MQTT_ERRORS_TOTAL.labels(direction="published").inc()


def update_websocket_metrics(active_connections: int) -> None:
    """Update WebSocket active connections gauge."""
    WEBSOCKET_CONNECTIONS_GAUGE.set(active_connections)


def update_esp_metrics(total: int, online: int, offline: int) -> None:
    """Update ESP device count gauges."""
    ESP_TOTAL_GAUGE.set(total)
    ESP_ONLINE_GAUGE.set(online)
    ESP_OFFLINE_GAUGE.set(offline)


def update_esp_heartbeat_metrics(
    avg_heap_free: float,
    min_heap_free: float,
    avg_wifi_rssi: float,
    avg_uptime: float,
) -> None:
    """Update aggregated ESP heartbeat gauges."""
    ESP_AVG_HEAP_FREE_GAUGE.set(avg_heap_free)
    ESP_MIN_HEAP_FREE_GAUGE.set(min_heap_free)
    ESP_AVG_WIFI_RSSI_GAUGE.set(avg_wifi_rssi)
    ESP_AVG_UPTIME_GAUGE.set(avg_uptime)


# =========================================================================
# Phase 0 metric update helpers
# =========================================================================


def update_sensor_value(esp_id: str, sensor_type: str, value: float) -> None:
    """Update sensor reading gauge. Call from sensor MQTT handler."""
    SENSOR_VALUE_GAUGE.labels(sensor_type=sensor_type, esp_id=esp_id).set(value)
    SENSOR_LAST_UPDATE_GAUGE.labels(sensor_type=sensor_type, esp_id=esp_id).set(time.time())


def update_esp_heartbeat_timestamp(esp_id: str) -> None:
    """Record heartbeat timestamp for an ESP. Call from heartbeat MQTT handler."""
    ESP_LAST_HEARTBEAT_GAUGE.labels(esp_id=esp_id).set(time.time())


def update_esp_boot_count(esp_id: str, boot_count: int) -> None:
    """Update boot count from heartbeat metadata."""
    ESP_BOOT_COUNT_GAUGE.labels(esp_id=esp_id).set(boot_count)


def increment_esp_error(esp_id: str) -> None:
    """Increment ESP error counter. Call from error MQTT handler."""
    ESP_ERRORS_TOTAL.labels(esp_id=esp_id).inc()


def update_esp_safe_mode(esp_id: str, in_safe_mode: bool) -> None:
    """Update safe mode gauge for an ESP device."""
    ESP_SAFE_MODE_GAUGE.labels(esp_id=esp_id).set(1 if in_safe_mode else 0)


def increment_ws_disconnect() -> None:
    """Increment WebSocket disconnect counter."""
    WS_DISCONNECTS_TOTAL.inc()


def update_mqtt_queue_size(size: int) -> None:
    """Update MQTT offline buffer queue size."""
    MQTT_QUEUED_MESSAGES_GAUGE.set(size)


def increment_http_error(status_code: int) -> None:
    """Increment HTTP error counter by status class (4xx or 5xx)."""
    if 400 <= status_code < 500:
        HTTP_ERRORS_TOTAL.labels(status_class="4xx").inc()
    elif 500 <= status_code < 600:
        HTTP_ERRORS_TOTAL.labels(status_class="5xx").inc()


def increment_logic_error() -> None:
    """Increment logic engine error counter."""
    LOGIC_ERRORS_TOTAL.inc()


def increment_logic_dispatch_skipped_config_pending() -> None:
    """Increment counter for actuator dispatches skipped due to CONFIG_PENDING_AFTER_RESET."""
    LOGIC_DISPATCH_SKIPPED_CONFIG_PENDING_TOTAL.inc()


def increment_logic_dispatch_skipped_offline() -> None:
    """Increment counter for actuator dispatches skipped due to ESP offline."""
    LOGIC_DISPATCH_SKIPPED_OFFLINE_TOTAL.inc()


def increment_rule_skip_target_offline(rule_id: str, esp_id: str, time_window: str = "unknown") -> None:
    """Increment per-rule offline-skip counter (AUT-110)."""
    RULE_SKIP_TARGET_OFFLINE_TOTAL.labels(rule_id=rule_id, esp_id=esp_id, time_window=time_window).inc()


def increment_actuator_timeout() -> None:
    """Increment actuator timeout counter."""
    ACTUATOR_TIMEOUTS_TOTAL.inc()


def increment_ws_missing_correlation() -> None:
    """Increment WebSocket missing-correlation counter."""
    WS_MISSING_CORRELATION_TOTAL.inc()


def increment_ws_envelope_data_divergence() -> None:
    """Increment envelope/data divergence counter for WebSocket events."""
    WS_ENVELOPE_DATA_DIVERGENCE_TOTAL.inc()


def increment_ws_contract_mismatch() -> None:
    """Increment WebSocket contract-mismatch counter."""
    WS_CONTRACT_MISMATCH_TOTAL.inc()


def increment_contract_terminalization_blocked(event_class: str, reason: str) -> None:
    """Increment blocked terminalization counter for contract guards."""
    normalized_event_class = (event_class or "unknown").strip().lower() or "unknown"
    normalized_reason = (reason or "unknown").strip().lower() or "unknown"
    CONTRACT_TERMINALIZATION_BLOCKED_TOTAL.labels(
        event_class=normalized_event_class,
        reason=normalized_reason,
    ).inc()


def increment_sensor_implausible(sensor_type: str, esp_id: str) -> None:
    """Increment implausible sensor value counter."""
    SENSOR_IMPLAUSIBLE_TOTAL.labels(sensor_type=sensor_type, esp_id=esp_id).inc()


def increment_safety_trigger() -> None:
    """Increment safety system trigger counter."""
    SAFETY_TRIGGERS_TOTAL.inc()


def increment_config_intent_outcome(outcome: str) -> None:
    """Increment AP-09A config outcome counters using canonical outcome."""
    normalized = str(outcome or "").lower()
    if normalized == "accepted":
        CONFIG_INTENTS_ACCEPTED_TOTAL.inc()
    elif normalized == "applied":
        CONFIG_INTENTS_APPLIED_TOTAL.inc()
    elif normalized == "persisted":
        CONFIG_INTENTS_PERSISTED_TOTAL.inc()
    elif normalized in {"failed", "expired", "rejected"}:
        CONFIG_INTENTS_FAILED_TOTAL.inc()


def observe_config_commit_duration_ms(duration_ms: float) -> None:
    """Observe config commit duration in milliseconds."""
    CONFIG_COMMIT_DURATION_MS.observe(max(float(duration_ms), 0.0))


def increment_intent_duplicate() -> None:
    """Increment dedup/duplicate counter."""
    INTENT_DUPLICATE_TOTAL.inc()
    INTENT_DEDUP_HITS.inc()


def increment_outcome_retry_count(amount: int = 1) -> None:
    """Increment retry counter for intent_outcome delivery."""
    OUTCOME_RETRY_COUNT.inc(max(int(amount), 0))


def increment_outcome_recovered_count(amount: int = 1) -> None:
    """Increment recovered counter for outbox-delivered intent outcomes."""
    OUTCOME_RECOVERED_COUNT.inc(max(int(amount), 0))


def set_outcome_drop_count_critical(esp_id: str, value: int) -> None:
    """Set current critical-outcome drop count per ESP."""
    if not esp_id:
        return
    OUTCOME_DROP_COUNT_CRITICAL.labels(esp_id=esp_id).set(max(int(value), 0))


def _sanitize_metric_label(value: str, *, max_len: int = 48) -> str:
    cleaned = (value or "").strip()[:max_len]
    if not cleaned:
        return "none"
    safe = []
    for ch in cleaned.lower():
        if ch.isalnum() or ch == "_":
            safe.append(ch)
        elif ch in ".:-/@":
            safe.append("_")
    out = "".join(safe).strip("_") or "other"
    return out[:max_len]


def observe_intent_outcome_firmware_code(flow: str, code: str) -> None:
    """Count firmware intent_outcome code strings (bounded labels)."""
    flow_l = _sanitize_metric_label(flow, max_len=32)
    code_l = _sanitize_metric_label(code, max_len=48)
    INTENT_OUTCOME_FIRMWARE_CODE_TOTAL.labels(flow=flow_l, code=code_l).inc()


def increment_intent_outcome_lifecycle(event_type: str, schema: str) -> None:
    """Count CONFIG_PENDING lifecycle telemetry events."""
    et = _sanitize_metric_label(event_type, max_len=48)
    sc = _sanitize_metric_label(schema, max_len=48)
    INTENT_OUTCOME_LIFECYCLE_TOTAL.labels(event_type=et, schema=sc).inc()


def increment_intent_tracing_degraded(reason: str, esp_id: str, amount: int = 1) -> None:
    """Count degraded intent-trace ingest paths (AUT-347 / Loki-friendly correlation)."""
    r = _sanitize_metric_label(reason, max_len=48)
    e = _sanitize_metric_label(esp_id, max_len=48)
    INTENT_TRACING_DEGRADED_TOTAL.labels(reason=r, esp_id=e).inc(max(int(amount), 1))


def increment_mqtt_ack_reason_code(ack_kind: str, reason_code: str) -> None:
    """Count zone/subzone ACK reason_code values from firmware."""
    kind = _sanitize_metric_label(ack_kind, max_len=16)
    rc = _sanitize_metric_label(reason_code, max_len=48)
    MQTT_ACK_REASON_CODE_TOTAL.labels(ack_kind=kind, reason_code=rc).inc()


def observe_heartbeat_firmware_flags(payload: dict) -> None:
    """Increment counters when boolean telemetry flags are true (low-cardinality flags)."""
    if not isinstance(payload, dict):
        return
    flag_map = (
        ("persistence_degraded", "persistence_degraded"),
        ("runtime_state_degraded", "runtime_state_degraded"),
        ("network_degraded", "network_degraded"),
        ("mqtt_circuit_breaker_open", "mqtt_circuit_breaker_open"),
        ("wifi_circuit_breaker_open", "wifi_circuit_breaker_open"),
    )
    for key, label in flag_map:
        if payload.get(key) is True:
            HEARTBEAT_FIRMWARE_FLAG_TOTAL.labels(flag=label).inc()


def observe_heartbeat_firmware_counters(esp_id: str, payload: dict) -> None:
    """Track latest firmware counter values as Prometheus Gauges (per ESP).

    Called from heartbeat_handler after successful payload validation (AUT-133 B-MU-04).
    Covers both existing telemetry fields and the new B-MU-02 queue/retry counters.

    Args:
        esp_id: ESP device identifier used as Gauge label.
        payload: Merged heartbeat payload dict.
    """
    if not isinstance(payload, dict):
        return
    counter_fields = (
        "critical_outcome_drop_count",
        "publish_outbox_drop_count",
        "persistence_drift_count",
        "heartbeat_degraded_count",
        "publish_queue_drop_count",
        "safe_publish_retry_count",
        "intent_chain_stage_enqueue_fail_count",
    )
    esp_label = str(esp_id) if esp_id else "unknown"
    for field in counter_fields:
        value = payload.get(field)
        if isinstance(value, (int, float)) and value >= 0:
            HEARTBEAT_FIRMWARE_COUNTER_GAUGE.labels(
                esp_id=esp_label, counter_name=field
            ).set(value)


def increment_contract_unknown_code(event_type: str, amount: int = 1) -> None:
    """Increment contract-unknown normalization counter."""
    normalized = (event_type or "unknown").strip().lower() or "unknown"
    CONTRACT_UNKNOWN_CODE_TOTAL.labels(event_type=normalized).inc(max(int(amount), 1))


def increment_reconciliation_session(phase: str, amount: int = 1) -> None:
    """Increment reconciliation lifecycle marker counter."""
    normalized = (phase or "progress").strip().lower() or "progress"
    if normalized not in {"start", "progress", "end"}:
        normalized = "progress"
    RECONCILIATION_SESSIONS_TOTAL.labels(phase=normalized).inc(max(int(amount), 1))


def increment_connect_attempt(amount: int = 1) -> None:
    """Increment connect attempt counter."""
    CONNECT_ATTEMPTS_TOTAL.inc(max(int(amount), 1))


def observe_tls_handshake_latency_ms(duration_ms: float) -> None:
    """Observe TLS handshake latency in milliseconds."""
    TLS_HANDSHAKE_LATENCY_MS.observe(max(float(duration_ms), 0.0))


def observe_heartbeat_ack_latency_ms(duration_ms: float) -> None:
    """Observe heartbeat ACK roundtrip latency in milliseconds."""
    HEARTBEAT_ACK_LATENCY_MS.observe(max(float(duration_ms), 0.0))


def increment_queue_pressure_event(esp_id: str, event: str) -> None:
    """Increment ESP queue-pressure event counter (PKG-01b).

    Pure observability — no DB/WS side effects. Called from the
    queue_pressure MQTT handler.

    Args:
        esp_id: ESP device identifier (fallback to "unknown" if missing).
        event: Lifecycle event label (typically "entered_pressure" or "recovered").
    """
    esp_label = str(esp_id) if esp_id else "unknown"
    event_label = str(event) if event else "unknown"
    QUEUE_PRESSURE_EVENT_TOTAL.labels(esp_id=esp_label, event=event_label).inc()


def observe_sensor_e2e_latency_ms(sensor_type: str, latency_ms: float) -> None:
    """Observe end-to-end sensor latency in milliseconds (PKG-03).

    Measures the delta between the ESP32 publish timestamp and the server
    receive time. Called from sensor_handler after payload timestamp
    extraction and before DB write.

    Args:
        sensor_type: Sensor type label (e.g. "temperature", "ph").
        latency_ms: Latency in milliseconds (non-negative).
    """
    SENSOR_E2E_LATENCY_MS.labels(sensor_type=str(sensor_type) or "unknown").observe(
        max(float(latency_ms), 0.0)
    )


def increment_heartbeat_ack_valid(amount: int = 1) -> None:
    """Increment successful heartbeat ACK contract counter."""
    HEARTBEAT_ACK_VALID_TOTAL.inc(max(int(amount), 1))


def increment_heartbeat_contract_reject(reason: str | None, amount: int = 1) -> None:
    """Increment heartbeat ACK contract reject counter by reason."""
    normalized = (reason or "unknown").strip().upper() or "UNKNOWN"
    HEARTBEAT_CONTRACT_REJECT_TOTAL.labels(reason=normalized).inc(max(int(amount), 1))


def increment_disconnect_reason(reason: str | None) -> None:
    """Increment disconnect reason distribution counter."""
    normalized = (reason or "unknown").strip().lower() or "unknown"
    DISCONNECT_REASON_DISTRIBUTION.labels(reason=normalized).inc()


def increment_ready_transition() -> None:
    """Increment ready-transition counter."""
    READY_TRANSITION_TOTAL.inc()


def increment_ready_blocked() -> None:
    """Increment ready-blocked counter."""
    READY_BLOCKED_TOTAL.inc()


def increment_not_found_expected() -> None:
    """Increment expected not-found counter."""
    NOT_FOUND_EXPECTED_TOTAL.inc()


def increment_not_found_unexpected() -> None:
    """Increment unexpected not-found counter."""
    NOT_FOUND_UNEXPECTED_TOTAL.inc()


def increment_api_error_code(numeric_code: int) -> None:
    """Increment per-code API error counter. Called from exception_handlers."""
    source_type = "esp" if numeric_code < 5000 else "server"
    API_ERROR_CODE_COUNTER.labels(
        error_code=str(numeric_code),
        source_type=source_type,
    ).inc()


# =========================================================================
# Notification Pipeline metric helpers (Phase 4A)
# =========================================================================


def increment_notification_created(severity: str, category: str, source: str) -> None:
    """Increment notification counter. Called from NotificationRouter.route()."""
    NOTIFICATIONS_TOTAL.labels(severity=severity, category=category, source=source).inc()


def increment_notification_suppressed(reason: str) -> None:
    """Increment suppressed counter. Called from NotificationRouter.persist_suppressed()."""
    NOTIFICATIONS_SUPPRESSED_TOTAL.labels(reason=reason or "unknown").inc()


def increment_notification_deduplicated() -> None:
    """Increment dedup counter. Called from NotificationRouter.route() dedup branch."""
    NOTIFICATIONS_DEDUPLICATED_TOTAL.inc()


def increment_email_sent(provider: str, success: bool) -> None:
    """Increment email counter. Called from EmailService.send_email()."""
    EMAIL_SENT_TOTAL.labels(provider=provider, status="success" if success else "failure").inc()


def observe_email_latency(provider: str, duration: float) -> None:
    """Observe email latency. Called from EmailService.send_email()."""
    EMAIL_LATENCY_SECONDS.labels(provider=provider).observe(duration)


def increment_digest_processed() -> None:
    """Increment digest counter. Called from DigestService.process_digests()."""
    DIGEST_PROCESSED_TOTAL.inc()


def observe_digest_batch_size(count: int) -> None:
    """Observe digest batch size. Called from DigestService.process_digests()."""
    DIGEST_NOTIFICATIONS_PER_BATCH.observe(count)


def increment_ws_notification_broadcast(event_type: str) -> None:
    """Increment WS broadcast counter. Called from NotificationRouter._broadcast_websocket()."""
    WS_NOTIFICATION_BROADCAST_TOTAL.labels(event_type=event_type).inc()


def increment_webhook_received(source: str, status: str) -> None:
    """Increment webhook counter. Called from webhooks.py."""
    WEBHOOK_RECEIVED_TOTAL.labels(source=source, status=status).inc()


def update_alert_suppression_active(entity_type: str, count: int) -> None:
    """Set active suppression gauge. Called from scheduler."""
    ALERT_SUPPRESSION_ACTIVE.labels(entity_type=entity_type).set(count)


def increment_alert_suppression_expired() -> None:
    """Increment suppression expired counter. Called from scheduler."""
    ALERT_SUPPRESSION_EXPIRED_TOTAL.inc()


def increment_notification_read(count: int = 1) -> None:
    """Increment read counter. Called from notifications.py mark_read endpoints."""
    NOTIFICATIONS_READ_TOTAL.inc(count)


def increment_email_error(provider: str, error_type: str) -> None:
    """Increment email error counter. Called from EmailService on failures."""
    EMAIL_ERRORS_TOTAL.labels(provider=provider, error_type=error_type).inc()


# =========================================================================
# Alert Lifecycle metric helpers (Phase 4B)
# =========================================================================


def increment_alert_acknowledged(severity: str) -> None:
    """Increment acknowledged counter. Called from notifications.py acknowledge endpoint."""
    ALERTS_ACKNOWLEDGED_TOTAL.labels(severity=severity).inc()


def increment_alert_resolved(severity: str, resolution_type: str = "manual") -> None:
    """Increment resolved counter. Called from notifications.py resolve endpoint."""
    ALERTS_RESOLVED_TOTAL.labels(severity=severity, resolution_type=resolution_type).inc()


def update_alerts_active_gauge(severity: str, count: int) -> None:
    """Set active alerts gauge. Called from metrics update cycle."""
    ALERTS_ACTIVE_GAUGE.labels(severity=severity).set(count)


def increment_root_cause_suppressed(source: str) -> None:
    """Increment root-cause suppressed counter. Called when dependent alerts are suppressed."""
    ALERTS_ROOT_CAUSE_SUPPRESSED_TOTAL.labels(source=source).inc()


async def update_all_metrics_async(get_session_func: callable) -> None:
    """
    Full metrics update cycle (called by scheduler every 15s).

    Updates system metrics, MQTT status, WebSocket connections,
    and ESP counts + heartbeat aggregates from DB.
    """
    try:
        # System metrics (no DB needed)
        update_system_metrics()

        # MQTT status
        from ..mqtt.client import MQTTClient

        mqtt_client = MQTTClient.get_instance()
        update_mqtt_metrics(mqtt_client.is_connected())

        # WebSocket connections
        try:
            from ..websocket.manager import WebSocketManager

            ws_manager = await WebSocketManager.get_instance()
            if ws_manager:
                update_websocket_metrics(ws_manager.connection_count)
        except ImportError:
            pass  # WebSocket module not yet importable during early startup
        except Exception as e:
            logger.debug(f"WebSocket metrics update skipped: {e}")

        # ESP counts + heartbeat aggregates (needs DB)
        from ..db.repositories import ESPRepository

        async for session in get_session_func():
            esp_repo = ESPRepository(session)
            devices = await esp_repo.get_all()
            total = len(devices)
            online = sum(1 for d in devices if d.status == "online")
            offline = sum(1 for d in devices if d.status == "offline")
            update_esp_metrics(total, online, offline)

            # Aggregate heartbeat metrics from online device metadata
            heap_values: list[float] = []
            rssi_values: list[float] = []
            uptime_values: list[float] = []

            for d in devices:
                esp_id = d.esp_id if hasattr(d, "esp_id") else str(d.id)
                meta = d.device_metadata or {}

                # Per-device Phase 0 metrics (from metadata)
                boot_count = meta.get("boot_count") or meta.get("last_boot_count")
                if boot_count is not None:
                    update_esp_boot_count(esp_id, int(boot_count))

                safe_mode = meta.get("safe_mode", False)
                update_esp_safe_mode(esp_id, bool(safe_mode))

                last_seen = getattr(d, "last_seen", None)
                if last_seen is not None:
                    try:
                        ts = (
                            last_seen.timestamp()
                            if hasattr(last_seen, "timestamp")
                            else float(last_seen)
                        )
                        ESP_LAST_HEARTBEAT_GAUGE.labels(esp_id=esp_id).set(ts)
                    except (TypeError, ValueError):
                        pass

                if d.status != "online":
                    continue
                heap = meta.get("last_heap_free")
                rssi = meta.get("last_wifi_rssi")
                uptime = meta.get("last_uptime")
                if heap is not None:
                    heap_values.append(float(heap))
                if rssi is not None:
                    rssi_values.append(float(rssi))
                if uptime is not None:
                    uptime_values.append(float(uptime))

            if heap_values:
                update_esp_heartbeat_metrics(
                    avg_heap_free=sum(heap_values) / len(heap_values),
                    min_heap_free=min(heap_values),
                    avg_wifi_rssi=sum(rssi_values) / len(rssi_values) if rssi_values else 0.0,
                    avg_uptime=sum(uptime_values) / len(uptime_values) if uptime_values else 0.0,
                )
            else:
                # No online devices with data - set to 0
                update_esp_heartbeat_metrics(0.0, 0.0, 0.0, 0.0)

            # Phase 4B: Update active alerts gauge from DB
            try:
                from ..db.repositories.notification_repo import NotificationRepository

                notification_repo = NotificationRepository(session)
                alert_counts = await notification_repo.get_active_counts_by_severity()
                for severity, count in alert_counts.items():
                    update_alerts_active_gauge(severity, count)
            except Exception as alert_err:
                logger.debug(f"Alert gauge update skipped: {alert_err}")

            break  # Only need one session

    except Exception as e:
        logger.warning(f"Metrics update failed (non-critical): {e}")


# =========================================================================
# Plugin System metric helpers (Phase 4C)
# =========================================================================


def increment_plugin_execution(plugin_id: str, status: str, trigger_source: str) -> None:
    """Increment plugin execution counter. Called from PluginService.execute_plugin()."""
    PLUGIN_EXECUTIONS_TOTAL.labels(
        plugin_id=plugin_id, status=status, trigger_source=trigger_source
    ).inc()


def observe_plugin_duration(plugin_id: str, duration: float) -> None:
    """Observe plugin execution duration. Called from PluginService.execute_plugin()."""
    PLUGIN_EXECUTION_DURATION.labels(plugin_id=plugin_id).observe(duration)


def increment_plugin_error(plugin_id: str, error_type: str) -> None:
    """Increment plugin error counter. Called from PluginService on failures."""
    PLUGIN_ERRORS_TOTAL.labels(plugin_id=plugin_id, error_type=error_type).inc()


def update_plugins_registered(count: int) -> None:
    """Set registered plugins gauge. Called after registry sync."""
    PLUGINS_REGISTERED_GAUGE.set(count)


def update_plugins_enabled(count: int) -> None:
    """Set enabled plugins gauge. Called during metrics update cycle."""
    PLUGINS_ENABLED_GAUGE.set(count)
