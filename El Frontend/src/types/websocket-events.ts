/**
 * WebSocket Event Type Definitions
 *
 * This file serves as the contract between Frontend and Backend for WebSocket events.
 * Backend team should reference this file when implementing new WebSocket events.
 *
 * BACKEND-TEAM: Please implement these events as specified.
 *
 * @see El Servador/god_kaiser_server/src/websocket/manager.py
 */

// =============================================================================
// BASE EVENT INTERFACE
// =============================================================================

/**
 * Base WebSocket event structure
 * All events must follow this format
 */
export interface WebSocketEventBase {
  /** Event type identifier */
  event: string
  /** ISO timestamp when event occurred */
  timestamp: string
  /** Event severity */
  severity: 'info' | 'warning' | 'error' | 'critical'
  /** Source type */
  source_type: 'esp32' | 'user' | 'system' | 'api' | 'mqtt' | 'scheduler'
  /** Source identifier (e.g., device ID, user ID) */
  source_id: string
  /** Event-specific data payload */
  data: Record<string, unknown>
}

// =============================================================================
// EXISTING EVENTS (Already Implemented in Backend)
// =============================================================================

/**
 * Sensor data event
 * Sent when a sensor reading is received
 */
export interface SensorDataEvent extends WebSocketEventBase {
  event: 'sensor_data'
  severity: 'info'
  source_type: 'esp32'
  data: {
    esp_id: string
    gpio: number
    sensor_type: string
    value: number | null
    unit: string
    quality: string
    timestamp: number
    // Address-based matching for multi-sensor GPIOs (Phase 3)
    config_id?: string
    i2c_address?: number
    onewire_address?: string
  }
}

/**
 * Actuator status event
 * Sent when actuator state changes
 */
export interface ActuatorStatusEvent extends WebSocketEventBase {
  event: 'actuator_status'
  source_type: 'esp32'
  data: {
    esp_id: string
    gpio: number
    actuator_type: string
    state: boolean
    value: number
    emergency_stopped: boolean
    timestamp: number
    command_source?: string
  }
}

/**
 * ESP health event
 * Sent on heartbeat
 */
export interface ESPHealthEvent extends WebSocketEventBase {
  event: 'esp_health'
  severity: 'info'
  source_type: 'esp32'
  data: {
    esp_id: string
    status: 'online' | 'offline'
    heap_free: number
    wifi_rssi: number
    uptime: number
    sensor_count: number
    actuator_count: number
    source?: 'lwt' | 'heartbeat' | 'heartbeat_timeout' | 'api'
    reason?: string
    timeout_seconds?: number
    actuator_states_reset?: number
    is_reconnect?: boolean
    is_flapping?: boolean
    lwt_count_5m?: number
    handover_contract_reject_startup?: number
    handover_contract_reject_runtime?: number
    handover_contract_reject?: number
    handover_epoch?: number
    session_epoch?: number
    gpio_status?: Array<{ gpio: number; state: boolean; [key: string]: unknown }>
    metrics_delta_ts?: number
    metrics_freshness_seconds?: number
    metrics_schema_version?: number
    critical_outcome_drop_count?: number
    publish_outbox_drop_count?: number
    persistence_drift_count?: number
    heartbeat_degraded_count?: number
    publish_queue_drop_count?: number
    safe_publish_retry_count?: number
    persistence_degraded?: boolean
    persistence_degraded_reason?: string
    runtime_state_degraded?: boolean
    network_degraded?: boolean
    mqtt_circuit_breaker_open?: boolean
    wifi_circuit_breaker_open?: boolean
    degraded?: boolean
    degraded_reason?: string
    degraded_reason_codes?: string[]
    timestamp?: number
  }
}

/**
 * Config response event
 * Sent when ESP32 acknowledges config change
 */
export interface ConfigResponseEvent extends WebSocketEventBase {
  event: 'config_response'
  source_type: 'esp32'
  data: {
    esp_id: string
    status: 'success' | 'failed'
    error_code?: string
    message?: string
    correlation_id: string
    request_id?: string
    reason_code?: string
    generation?: number
    config_fingerprint?: string
    trigger_source?: string
    timestamp: number
  }
}

/**
 * ESP reconnect phase event
 * Sent during reconnect adoption/evaluation flow
 */
export interface ESPReconnectPhaseEvent extends WebSocketEventBase {
  event: 'esp_reconnect_phase'
  severity: 'info'
  source_type: 'system'
  data: {
    esp_id: string
    phase: 'adopting' | 'adopted' | 'delta_enforced' | 'converged'
    timestamp: number
    config_push_pending?: boolean
  }
}

/**
 * Device discovered event
 * Sent when new ESP32 is discovered
 */
export interface DeviceDiscoveredEvent extends WebSocketEventBase {
  event: 'device_discovered'
  severity: 'info'
  source_type: 'system'
  data: {
    esp_id: string
    device_id: string
    discovered_at: string
    zone_id?: string
    heap_free?: number
    wifi_rssi?: number
    sensor_count?: number
    actuator_count?: number
  }
}

/**
 * Error event
 * Sent when ESP32 reports an error
 */
export interface ErrorEvent extends WebSocketEventBase {
  event: 'error_event'
  severity: 'warning' | 'error' | 'critical'
  source_type: 'esp32' | 'system'
  data: {
    esp_id: string
    esp_name?: string
    error_log_id?: string
    error_code: number | string
    /** Short German error title (e.g. "MQTT-Publish fehlgeschlagen") */
    title?: string
    category: string
    /** Detailed user-friendly description */
    message: string
    /** Ordered troubleshooting steps in German */
    troubleshooting?: string[]
    user_action_required: boolean
    recoverable: boolean
    /** Link to relevant documentation */
    docs_link?: string | null
    context?: Record<string, unknown>
    /** Unix timestamp from ESP32 payload */
    timestamp?: number
  }
}

// =============================================================================
// NEW EVENTS (Backend Implementation Required)
// =============================================================================

/**
 * Server log event
 *
 * BACKEND-ANFORDERUNG:
 * - Sende NUR Logs ab Level WARNING (nicht DEBUG/INFO)
 * - Rate-Limit: Max 10 Events/Sekunde pro Client
 * - Broadcast bei jedem neuen Log-Eintrag ab WARNING
 *
 * Implementation in: src/core/logging_config.py
 *
 * Example broadcast:
 * ```python
 * await ws_manager.broadcast("server_log", {
 *     "level": "ERROR",
 *     "logger": "mqtt.handlers.heartbeat_handler",
 *     "module": "heartbeat_handler.py",
 *     "function": "process_heartbeat",
 *     "line": 157,
 *     "message": "Device ESP_12AB34CD timed out",
 *     "exception": None,
 *     "extra": {"esp_id": "ESP_12AB34CD", "timeout_seconds": 300}
 * })
 * ```
 */
export interface ServerLogEvent extends WebSocketEventBase {
  event: 'server_log'
  severity: 'warning' | 'error' | 'critical'
  source_type: 'system'
  source_id: 'god-kaiser-main'
  data: {
    /** Log level (WARNING, ERROR, CRITICAL only) */
    level: 'WARNING' | 'ERROR' | 'CRITICAL'
    /** Logger name (e.g., "mqtt.handlers") */
    logger: string
    /** Module file name (e.g., "heartbeat_handler.py") */
    module: string
    /** Function name */
    function: string
    /** Line number */
    line: number
    /** Log message */
    message: string
    /** Exception info (if applicable) */
    exception?: {
      type: string
      message: string
      traceback: string[]
    } | null
    /** Extra context data */
    extra?: Record<string, unknown>
  }
}

/**
 * Database record changed event (Optional - Post-MVP)
 *
 * BACKEND-ANFORDERUNG:
 * - Sende bei wichtigen DB-Änderungen (ESP-Status, Config-Updates)
 * - Nicht bei hochfrequenten Änderungen (sensor_data)
 *
 * Implementation: Trigger via SQLAlchemy event listeners
 *
 * Priority: LOW (Post-MVP)
 */
export interface DBRecordChangedEvent extends WebSocketEventBase {
  event: 'db_record_changed'
  severity: 'info'
  source_type: 'system'
  source_id: 'god-kaiser-db'
  data: {
    /** Table name (e.g., "esp_devices") */
    table: string
    /** Record ID (UUID) */
    record_id: string
    /** Operation type */
    operation: 'insert' | 'update' | 'delete'
    /** Changed fields (for updates) */
    changes?: Record<string, { old: unknown; new: unknown }>
  }
}

// =============================================================================
// ACTUATOR COMMAND LIFECYCLE EVENTS
// =============================================================================

/**
 * Actuator command sent event
 * Sent when server successfully publishes command to MQTT
 */
export interface ActuatorCommandEvent extends WebSocketEventBase {
  event: 'actuator_command'
  severity: 'info'
  source_type: 'system'
  data: {
    esp_id: string
    gpio: number
    command: string
    value?: number
    issued_by?: string
    correlation_id?: string
  }
}

/**
 * Actuator command failed event
 * Sent when server cannot publish command (safety check, MQTT failure)
 */
export interface ActuatorCommandFailedEvent extends WebSocketEventBase {
  event: 'actuator_command_failed'
  severity: 'error'
  source_type: 'system'
  data: {
    esp_id: string
    gpio: number
    command: string
    value?: number
    error: string
    issued_by?: string
    correlation_id?: string
  }
}

// =============================================================================
// CONFIG PUBLISH LIFECYCLE EVENTS
// =============================================================================

export interface OfflineRuleStrippedEntry {
  rule_id: string
  rule_name: string
  actuator_gpio: number | null
  reason_code: string
  reason_detail: string
  resolution_hint?: string
}

export interface OfflineRulesDiagnostics {
  total_candidate_rules: number
  accepted_count: number
  stripped_count: number
  stripped_rules: OfflineRuleStrippedEntry[]
}

/**
 * Config published event
 * Sent when config is successfully published to ESP via MQTT
 */
export interface ConfigPublishedEvent extends WebSocketEventBase {
  event: 'config_published'
  severity: 'info'
  source_type: 'system'
  data: {
    esp_id: string
    config_keys: string[]
    correlation_id?: string
    queued?: boolean
    device_status?: string
    offline_rules_stripped?: number
    offline_rules_diagnostics?: OfflineRulesDiagnostics
    reason_code?: string
    generation?: number
    config_fingerprint?: string
    trigger_source?: string
  }
}

/**
 * Config failed event
 * Sent when config publishing fails
 */
export interface ConfigFailedEvent extends WebSocketEventBase {
  event: 'config_failed'
  severity: 'error'
  source_type: 'system'
  data: {
    esp_id: string
    config_keys: string[]
    error: string
    correlation_id: string
    request_id?: string
    reason_code?: string
    generation?: number
    config_fingerprint?: string
    trigger_source?: string
  }
}

// =============================================================================
// SEQUENCE EVENTS (Automation)
// =============================================================================

/**
 * Sequence started event
 */
export interface SequenceStartedEvent extends WebSocketEventBase {
  event: 'sequence_started'
  severity: 'info'
  source_type: 'scheduler'
  data: {
    sequence_id: string
    rule_id?: string
    rule_name?: string
    total_steps: number
    description?: string
  }
}

/**
 * Sequence step progress event
 */
export interface SequenceStepEvent extends WebSocketEventBase {
  event: 'sequence_step'
  severity: 'info'
  source_type: 'scheduler'
  data: {
    sequence_id: string
    step: number
    step_name: string
    total_steps: number
    progress_percent: number
    status: string
  }
}

/**
 * Sequence completed event
 */
export interface SequenceCompletedEvent extends WebSocketEventBase {
  event: 'sequence_completed'
  severity: 'info'
  source_type: 'scheduler'
  data: {
    sequence_id: string
    status: string
    success: boolean
    duration_seconds?: number
    steps_completed?: number
    steps_failed?: number
    error?: string
    error_code?: string
  }
}

/**
 * Sequence error event
 */
export interface SequenceErrorEvent extends WebSocketEventBase {
  event: 'sequence_error'
  severity: 'error'
  source_type: 'scheduler'
  data: {
    sequence_id: string
    error_code?: string
    message: string
  }
}

/**
 * Sequence cancelled event
 */
export interface SequenceCancelledEvent extends WebSocketEventBase {
  event: 'sequence_cancelled'
  severity: 'warning'
  source_type: 'scheduler'
  data: {
    sequence_id: string
    reason?: string
  }
}

// =============================================================================
// EVENT TYPE UNION
// =============================================================================

/**
 * Union type of all WebSocket events
 */
export type WebSocketEvent =
  | SensorDataEvent
  | ActuatorStatusEvent
  | ESPHealthEvent
  | ESPReconnectPhaseEvent
  | ConfigResponseEvent
  | DeviceDiscoveredEvent
  | DeviceRediscoveredEvent
  | DeviceApprovedEvent
  | DeviceRejectedEvent
  | ActuatorResponseEvent
  | ActuatorAlertEvent
  | ActuatorCommandEvent
  | ActuatorCommandFailedEvent
  | ZoneAssignmentEvent
  | SubzoneAssignmentEvent
  | LogicExecutionEvent
  | SystemEvent
  | SensorHealthEvent
  | NotificationEvent
  | ErrorEvent
  | ConfigPublishedEvent
  | ConfigFailedEvent
  | SequenceStartedEvent
  | SequenceStepEvent
  | SequenceCompletedEvent
  | SequenceErrorEvent
  | SequenceCancelledEvent
  | ServerLogEvent
  | DBRecordChangedEvent
  | RuleDegradedEvent
  | RuleRecoveredEvent

/**
 * Event type string union
 */
export type WebSocketEventType = WebSocketEvent['event']

// =============================================================================
// HELPER TYPE GUARDS
// =============================================================================

export function isSensorDataEvent(event: WebSocketEvent): event is SensorDataEvent {
  return event.event === 'sensor_data'
}

export function isActuatorStatusEvent(event: WebSocketEvent): event is ActuatorStatusEvent {
  return event.event === 'actuator_status'
}

export function isESPHealthEvent(event: WebSocketEvent): event is ESPHealthEvent {
  return event.event === 'esp_health'
}

export function isConfigResponseEvent(event: WebSocketEvent): event is ConfigResponseEvent {
  return event.event === 'config_response'
}

export function isDeviceDiscoveredEvent(event: WebSocketEvent): event is DeviceDiscoveredEvent {
  return event.event === 'device_discovered'
}

export function isErrorEvent(event: WebSocketEvent): event is ErrorEvent {
  return event.event === 'error_event'
}

export function isServerLogEvent(event: WebSocketEvent): event is ServerLogEvent {
  return event.event === 'server_log'
}

export function isDBRecordChangedEvent(event: WebSocketEvent): event is DBRecordChangedEvent {
  return event.event === 'db_record_changed'
}

// =============================================================================
// ADDITIONAL EVENTS (Implemented in Backend)
// =============================================================================

/**
 * Device rediscovered event
 * Sent when a known device comes back online
 */
export interface DeviceRediscoveredEvent extends WebSocketEventBase {
  event: 'device_rediscovered'
  severity: 'info'
  source_type: 'system'
  data: {
    esp_id: string
    device_id: string
    zone_id?: string
    zone_name?: string
    previous_status: string
    heap_free?: number
    wifi_rssi?: number
  }
}

/**
 * Device approved event
 * Sent when admin approves a pending device
 */
export interface DeviceApprovedEvent extends WebSocketEventBase {
  event: 'device_approved'
  severity: 'info'
  source_type: 'user'
  data: {
    device_id: string
    approved_by: string
    zone_id?: string
    zone_name?: string
  }
}

/**
 * Device rejected event
 * Sent when admin rejects a pending device
 */
export interface DeviceRejectedEvent extends WebSocketEventBase {
  event: 'device_rejected'
  severity: 'warning'
  source_type: 'user'
  data: {
    device_id: string
    rejection_reason: string
    rejected_by: string
  }
}

/**
 * Actuator response event
 * Sent when ESP32 confirms command execution
 */
export interface ActuatorResponseEvent extends WebSocketEventBase {
  event: 'actuator_response'
  source_type: 'esp32'
  data: {
    esp_id: string
    gpio: number
    actuator_type: string
    command: string
    success: boolean
    error_code?: number
    message?: string
    issued_by?: string
    /**
     * Correlation ID propagated from the originating command (REST/MQTT send_command).
     * Required for terminal toast finality dedup per correlation_id (AUT-123).
     * Backend sends this from the originating send_command(); not all legacy paths
     * may include it, hence optional.
     */
    correlation_id?: string
    /** Optional trace context (request_id) for log correlation */
    request_id?: string
  }
}

/**
 * Actuator alert event
 * Sent on emergency stop or timeout
 */
export interface ActuatorAlertEvent extends WebSocketEventBase {
  event: 'actuator_alert'
  severity: 'warning' | 'error' | 'critical'
  source_type: 'esp32'
  data: {
    esp_id: string
    gpio: number
    actuator_type: string
    alert_type: 'emergency_stop' | 'timeout' | 'runtime_exceeded' | 'safety_triggered'
    reason: string
    error_code?: number
    /** MQTT ingress correlation (Server: generate_mqtt_correlation_id / ContextVar) */
    correlation_id?: string
  }
}

/**
 * Zone assignment event
 * Sent when ESP acknowledges zone assignment
 */
export interface ZoneAssignmentEvent extends WebSocketEventBase {
  event: 'zone_assignment'
  severity: 'info'
  source_type: 'esp32'
  data: {
    esp_id: string
    zone_id: string
    zone_name?: string
    master_zone_id?: string
    kaiser_id?: string
    status: 'zone_assigned' | 'zone_removed' | 'error'
    timestamp: number
    error_code?: string
    message?: string
  }
}

/**
 * Subzone assignment event
 * Sent when ESP acknowledges subzone assignment or removal
 * WP4: Added to support subzone real-time UI updates
 */
export interface SubzoneAssignmentEvent extends WebSocketEventBase {
  event: 'subzone_assignment'
  severity: 'info'
  source_type: 'esp32'
  data: {
    esp_id: string
    subzone_id: string
    status: 'subzone_assigned' | 'subzone_removed' | 'error'
    timestamp: number
    error_code?: string
    message?: string
  }
}

/**
 * Logic execution event
 * Sent when automation rule is executed
 */
export interface LogicExecutionEvent extends WebSocketEventBase {
  event: 'logic_execution'
  severity: 'info'
  source_type: 'scheduler'
  data: {
    rule_id: string
    rule_name: string
    triggered_by: string
    actions_executed: number
    success: boolean
    duration_ms?: number
  }
}

/**
 * System event (maintenance, health checks, backup restore)
 * Sent by maintenance jobs and the backup restore pipeline.
 *
 * Hinweis: Der konkrete Subtyp steht im verschachtelten Feld `event`
 * (Live-Broadcast, z.B. `mqtt_disconnected`). `event_type` ist das
 * dokumentierte Contract-Feld; `message` wird nicht immer mitgesendet.
 * Labels/Aufloesung via `getSystemEventLabel` (utils/eventTypeLabels).
 */
export interface SystemEvent extends WebSocketEventBase {
  event: 'system_event'
  source_type: 'system'
  data: {
    /** Concrete sub-type discriminator (server broadcast field). */
    event?: string
    /** Documented contract alias for the sub-type. */
    event_type?: string
    message?: string
    /** database_restore_status: pipeline phase (preflight/quiesce/restore/reconcile/terminal). */
    phase?: string
    /** database_restore_status: outcome (started/success/failed). */
    status?: string
    run_id?: string
    timestamp?: string
    details?: Record<string, unknown>
    payload?: Record<string, unknown>
    [key: string]: unknown
  }
}

/**
 * Sensor health event
 * Sent on sensor timeout or freshness exceeded (maintenance/jobs/sensor_health.py).
 */
export interface SensorHealthEvent extends WebSocketEventBase {
  event: 'sensor_health'
  severity: 'warning' | 'info'
  source_type: 'system'
  data: {
    esp_id: string
    gpio: number
    sensor_type: string
    sensor_name: string | null
    is_stale: boolean
    stale_reason: 'timeout_exceeded' | 'no_data' | 'sensor_error' | 'freshness_exceeded'
    last_reading_at: string | null
    timeout_seconds: number
    freshness_hours?: number | null
    seconds_overdue: number
    operating_mode: string
    config_source: 'instance' | 'type_default' | 'system_default'
    timestamp: number
  }
}

/**
 * Notification event from logic rules
 */
export interface NotificationEvent extends WebSocketEventBase {
  event: 'notification'
  source_type: 'scheduler'
  data: {
    title: string
    message: string
    priority: 'low' | 'normal' | 'high'
    rule_id?: string
    rule_name?: string
  }
}

// =============================================================================
// RULE DEGRADATION EVENTS (AUT-111)
// =============================================================================

/**
 * Rule degraded event
 * Sent when a rule enters degraded state (e.g. sensor offline, actuator unreachable)
 */
export interface RuleDegradedEvent extends WebSocketEventBase {
  event: 'rule_degraded'
  severity: 'warning' | 'error'
  source_type: 'system'
  data: {
    rule_id: string
    rule_name: string
    is_critical: boolean
    degraded_since: string
    degraded_reason: string
    escalation_policy?: Record<string, unknown> | null
  }
}

/**
 * Rule recovered event
 * Sent when a previously degraded rule recovers
 */
export interface RuleRecoveredEvent extends WebSocketEventBase {
  event: 'rule_recovered'
  severity: 'info'
  source_type: 'system'
  data: {
    rule_id: string
    rule_name: string
    is_critical: boolean
    recovered_at: string
    degraded_duration_seconds: number
  }
}

// =============================================================================
// UNIFIED EVENT (for System Monitor)
// =============================================================================

/**
 * Unified event interface for the System Monitor
 * Normalizes all event types into a common format for display
 *
 * @see El Trabajante/src/models/error_codes.h - ESP32 Error Codes
 * @see El Servador/god_kaiser_server/src/core/error_codes.py - Server Error Codes
 */
export interface UnifiedEvent {
  /** Unique event ID */
  id: string
  /** ISO timestamp */
  timestamp: string
  /** Event type (e.g., 'sensor_data', 'error_event', 'server_log') */
  event_type: string
  /** Normalized severity */
  severity: 'info' | 'warning' | 'error' | 'critical'
  /** Event source category */
  source: 'server' | 'mqtt' | 'database' | 'esp' | 'logic' | 'user'
  /** Data source for client-side filtering */
  dataSource?: 'audit_log' | 'sensor_data' | 'esp_health' | 'actuators'
  /** Associated ESP ID (if applicable) */
  esp_id?: string
  /** Associated Zone ID (if applicable) */
  zone_id?: string
  /** Zone display name */
  zone_name?: string
  /** Human-readable message (German) */
  message: string
  /** Error code from ESP32 or Server (1000-5999) */
  error_code?: number | string
  /** Error category (hardware, service, communication, application, server) */
  error_category?: string
  /** GPIO pin (for sensor/actuator events) */
  gpio?: number
  /** Sensor or actuator type */
  device_type?: string
  /** Correlation ID for tracking related events (Phase 3) */
  correlation_id?: string
  /** Request ID for server-log correlation (Phase 4) */
  request_id?: string
  /** Raw event data */
  data: Record<string, unknown>
  /**
   * Event source type for filter optimization (Phase 4)
   * - 'server': Event loaded from API (already server-filtered, skip client filter)
   * - 'websocket': Event received via WebSocket (needs client-side filtering)
   */
  _sourceType?: 'server' | 'websocket'
}

/**
 * Generic WebSocket event data for flexible handling
 * Used when the exact event type is not known at compile time
 */
export interface WebSocketEventData {
  type: string
  timestamp?: string
  data: Record<string, unknown>
}

// =============================================================================
// BACKEND COORDINATION
// =============================================================================

/**
 * BACKEND-TEAM IMPLEMENTATION CHECKLIST
 *
 * Priority 1 (Required for System Monitor):
 * - [ ] ServerLogEvent - Stream server logs via WebSocket
 *       File: src/core/logging_config.py
 *       Requirements:
 *       - Filter: Only WARNING, ERROR, CRITICAL
 *       - Rate limit: 10 events/sec per client
 *       - Include: logger, module, function, line, message, exception, extra
 *
 * Priority 2 (Nice to have):
 * - [ ] DBRecordChangedEvent - Notify on DB changes
 *       File: src/db/event_listeners.py (new file)
 *       Requirements:
 *       - Tables: esp_devices, sensor_configs, actuator_configs
 *       - Operations: insert, update, delete
 *       - Exclude: sensor_data (too frequent)
 *
 * Testing:
 * - Use existing WebSocket test infrastructure
 * - Tests should be in tests/unit/test_websocket_events.py
 */
