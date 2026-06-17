// =============================================================================
// GPIO Types (Phase 3)
// =============================================================================
export * from './gpio'

// =============================================================================
// WebSocket Event Types (System Monitor)
// =============================================================================
export * from './websocket-events'

// =============================================================================
// Device Metadata Types
// =============================================================================
export type { DeviceMetadata } from './device-metadata'
export {
  parseDeviceMetadata,
  mergeDeviceMetadata,
  getNextMaintenanceDate,
  isMaintenanceOverdue,
} from './device-metadata'

// =============================================================================
// Discovery/Approval Types (Phase: Device Discovery)
// =============================================================================

/**
 * Pending ESP device awaiting approval.
 * Discovered via heartbeat but not yet approved by admin.
 *
 * Time Fields:
 * - discovered_at: When device was FIRST discovered (historical)
 * - last_seen: When device was LAST active (use for "vor X Zeit" display)
 */
export interface PendingESPDevice {
  /** Device ID (e.g., ESP_D0B19C) */
  device_id: string
  /** When device was first discovered (historical) */
  discovered_at: string
  /** When device was last active - use this for "vor X Zeit" display */
  last_seen?: string | null
  /** IP address of the device */
  ip_address?: string | null
  /** Zone ID if pre-assigned */
  zone_id?: string | null
  /** Free heap memory in bytes */
  heap_free?: number | null
  /** WiFi signal strength in dBm */
  wifi_rssi?: number | null
  /** Number of configured sensors */
  sensor_count: number
  /** Number of configured actuators */
  actuator_count: number
  /** Number of heartbeats received while pending */
  heartbeat_count: number
  /** Hardware type (ESP32_WROOM, etc.) */
  hardware_type?: string | null
  /** Time since discovery in a human-readable format */
  time_ago?: string
}

/**
 * Request to approve a pending device.
 */
export interface ESPApprovalRequest {
  /** Optional friendly name for the device */
  name?: string | null
  /** Optional zone ID to assign */
  zone_id?: string | null
  /** Optional zone name (creates zone if not exists) */
  zone_name?: string | null
}

/**
 * Request to reject a pending device.
 */
export interface ESPRejectionRequest {
  /** Reason for rejection (required) */
  reason: string
}

/**
 * Response from approval/rejection endpoints.
 */
export interface ESPApprovalResponse {
  success: boolean
  message: string
  device_id: string
  status: string
  approved_by?: string | null
  approved_at?: string | null
  rejection_reason?: string | null
}

/**
 * Response containing list of pending devices.
 */
export interface PendingDevicesListResponse {
  success: boolean
  devices: PendingESPDevice[]
  count: number
  message: string
}

/**
 * Payload for device_discovered WebSocket event (data field).
 * For the full event wrapper, use DeviceDiscoveredEvent from websocket-events.ts.
 */
export interface DeviceDiscoveredPayload {
  device_id: string
  discovered_at: string
  /** Last activity timestamp (initial = discovered_at) */
  last_seen?: string | null
  ip_address?: string | null
  heap_free?: number | null
  wifi_rssi?: number | null
  sensor_count: number
  actuator_count: number
  hardware_type?: string | null
}

/**
 * Payload for device_approved WebSocket event (data field).
 * For the full event wrapper, use DeviceApprovedEvent from websocket-events.ts.
 */
export interface DeviceApprovedPayload {
  device_id: string
  approved_by: string
  approved_at: string
  status: string
}

/**
 * Payload for device_rejected WebSocket event (data field).
 * For the full event wrapper, use DeviceRejectedEvent from websocket-events.ts.
 */
export interface DeviceRejectedPayload {
  device_id: string
  rejection_reason: string
  rejected_at: string
  cooldown_until: string
}

// =============================================================================
// Auth Types
// =============================================================================
export interface User {
  id: string
  username: string
  email: string
  full_name: string | null
  role: 'admin' | 'operator' | 'viewer'
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface LoginRequest {
  username: string
  password: string
  remember_me?: boolean
}

export interface SetupRequest {
  username: string
  email: string
  password: string
  full_name?: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface LoginResponse {
  success: boolean
  message: string
  tokens: TokenResponse
  user: User
}

export interface SetupResponse {
  success: boolean
  message: string
  tokens: TokenResponse
  user: User
}

export interface RefreshResponse {
  success: boolean
  message: string
  tokens: TokenResponse
}

export interface AuthStatusResponse {
  setup_required: boolean
  users_exist: boolean
  mqtt_auth_enabled: boolean
  mqtt_tls_enabled: boolean
}

// =============================================================================
// Mock ESP Types
// =============================================================================
export type MockSystemState =
  | 'BOOT'
  | 'WIFI_SETUP'
  | 'WIFI_CONNECTED'
  | 'MQTT_CONNECTING'
  | 'MQTT_CONNECTED'
  | 'AWAITING_USER_CONFIG'
  | 'ZONE_CONFIGURED'
  | 'SENSORS_CONFIGURED'
  | 'OPERATIONAL'
  | 'LIBRARY_DOWNLOADING'
  | 'SAFE_MODE'
  | 'ERROR'

export type QualityLevel = 'excellent' | 'good' | 'fair' | 'poor' | 'bad' | 'stale' | 'error'

/**
 * Sensor kind: distinguishes continuous measurement sensors from snapshot-style
 * sensors (e.g. MultispeQ photosynthesis measurements that produce point readings
 * rather than a time series). Server-side defined in Wave 1 (SensorConfig.sensor_kind).
 *
 * - continuous: Live time-series readings, suitable for line charts / live blink indicators
 * - snapshot: Discrete point readings, suitable for scatter plots / "letzte Messung" labels
 */
export type SensorKind = 'continuous' | 'snapshot'

// =============================================================================
// Multi-Value Sensor Types (Phase 6)
// =============================================================================

/**
 * Single value within a multi-value sensor
 */
export interface MultiValueEntry {
  /** Current value */
  value: number
  /** Unit of measurement */
  unit: string
  /** Data quality */
  quality: QualityLevel
  /** Timestamp of last update (Unix ms) */
  timestamp: number
  /** Sensor type for this value */
  sensorType: string
}

/**
 * Type guard for multi-value sensors
 */
export function isMultiValueSensor(sensor: MockSensor): boolean {
  return sensor.is_multi_value === true && sensor.multi_values !== null && sensor.multi_values !== undefined
}

export interface MockSensor {
  /** Sensor config UUID from database (primary identifier for multi-value sensors) */
  config_id?: string
  gpio: number
  sensor_type: string
  name: string | null
  subzone_id?: string | null
  raw_value: number | null
  processed_value?: number  // Optional - present when Pi-enhanced processing returns data
  unit: string
  quality: QualityLevel
  raw_mode: boolean
  last_read: string | null
  /** Last WS sensor_data event arrival time (frontend-local, for UI finality). */
  last_event_at?: string | null
  // Phase 2E: Health-Status fields
  operating_mode?: SensorOperatingMode
  timeout_seconds?: number
  is_stale?: boolean
  stale_reason?: 'timeout_exceeded' | 'no_data' | 'sensor_error' | 'freshness_exceeded'
  last_reading_at?: string | null
  // Phase 2F: Schedule configuration
  schedule_config?: { type: string; expression: string } | null
  // Sensor-Lifecycle: Freshness & Calibration
  measurement_freshness_hours?: number | null
  calibration_interval_days?: number | null
  freshness_hours?: number | null
  // Config verification status from ESP32
  config_status?: 'pending' | 'applied' | 'failed' | null
  config_error?: string | null
  config_error_detail?: string | null

  // ═══════════════════════════════════════════════════════════════════════════
  // Phase 6: Multi-Value Sensor Fields
  // ═══════════════════════════════════════════════════════════════════════════
  /** Device type if multi-value (e.g., "sht31"), null for single-value */
  device_type?: string | null
  /** All values for multi-value sensors, keyed by sensor_type */
  multi_values?: Record<string, MultiValueEntry> | null
  /** Is this a multi-value sensor? */
  is_multi_value?: boolean

  // ═══════════════════════════════════════════════════════════════════════════
  // Interface / Address Fields (for Orbital display)
  // ═══════════════════════════════════════════════════════════════════════════
  /** Interface type: I2C, ONEWIRE, ANALOG, DIGITAL, UART, VIRTUAL */
  interface_type?: 'I2C' | 'ONEWIRE' | 'ANALOG' | 'DIGITAL' | 'UART' | 'VIRTUAL' | null
  /** I2C address (0-127) for I2C sensors */
  i2c_address?: number | null
  /** OneWire ROM address for DS18B20 sensors (16 hex chars) */
  onewire_address?: string | null

  // ═══════════════════════════════════════════════════════════════════════════
  // Device Scope Fields (T13-R3 WP4)
  // ═══════════════════════════════════════════════════════════════════════════
  /** Device scope: zone_local, multi_zone, mobile */
  device_scope?: DeviceScope | null
  /** Assigned zones for multi_zone/mobile devices */
  assigned_zones?: string[] | null

  // ═══════════════════════════════════════════════════════════════════════════
  // Sensor Kind (Wave 1 — MultispeQ / Snapshot Sensors)
  // ═══════════════════════════════════════════════════════════════════════════
  /** Sensor kind: continuous (default) or snapshot (point measurements) */
  sensor_kind?: SensorKind | null

  // ═══════════════════════════════════════════════════════════════════════════
  // AUT-299: ATC (Automatic Temperature Compensation)
  // ═══════════════════════════════════════════════════════════════════════════
  /** UUID of the linked temperature sensor config for ATC. Null = no sensor linked. */
  temp_sensor_config_id?: string | null
  /** Last measurement metadata (e.g. temp_source, temp_compensation_value for EC/pH sensors) */
  metadata?: Record<string, unknown> | null
}

export interface MockActuator {
  gpio: number
  actuator_type: string
  /** Original ESP32 hardware type (relay, pump, valve, pwm) before server normalization */
  hardware_type?: string | null
  name: string | null
  state: boolean
  pwm_value: number
  emergency_stopped: boolean
  last_command_at: string | null
  subzone_id?: string | null
  // Config verification status from ESP32
  config_status?: 'pending' | 'applied' | 'failed' | null
  config_error?: string | null
  config_error_detail?: string | null
  // Device Scope Fields (T13-R3 WP4)
  /** Device scope: zone_local, multi_zone, mobile */
  device_scope?: DeviceScope | null
  /** Assigned zones for multi_zone/mobile devices */
  assigned_zones?: string[] | null
}

/** Lightweight zone context summary inherited from ZoneContext */
export interface ZoneContextSummary {
  zone_id: string
  zone_name?: string | null
  variety?: string | null
  substrate?: string | null
  growth_phase?: string | null
  plant_count?: number | null
  plant_age_days?: number | null
  days_to_harvest?: number | null
  responsible_person?: string | null
}

export interface MockESP {
  esp_id: string
  name: string | null  // Human-readable device name (from DB)
  zone_id: string | null
  zone_name: string | null  // User-friendly zone name (allows spaces)
  master_zone_id: string | null
  subzone_id: string | null
  system_state: MockSystemState
  status: 'online' | 'offline' | 'error' | 'unknown' | 'pending_approval' | 'approved' | 'rejected'  // Device lifecycle + connection status
  sensors: MockSensor[]
  actuators: MockActuator[]
  auto_heartbeat: boolean
  heap_free: number
  wifi_rssi: number
  uptime: number
  last_heartbeat: string | null
  created_at: string
  connected: boolean
  hardware_type: string
  zone_context?: ZoneContextSummary | null
}

export interface MockESPCreate {
  esp_id: string
  zone_id?: string  // Technical zone ID (auto-generated from zone_name if not provided)
  zone_name?: string  // User-friendly zone name (allows spaces, e.g., "Zelt 1")
  master_zone_id?: string
  subzone_id?: string
  sensors?: MockSensorConfig[]
  actuators?: MockActuatorConfig[]
  auto_heartbeat?: boolean
  heartbeat_interval_seconds?: number
}

export interface MockSensorConfig {
  gpio: number
  sensor_type: string
  name?: string
  /** Subzone ID (optional); null = "Keine Subzone" */
  subzone_id?: string | null
  raw_value?: number
  unit?: string
  quality?: QualityLevel
  raw_mode?: boolean
  // =========================================================================
  // Phase 6: OneWire Support (DS18B20)
  // =========================================================================
  /** OneWire ROM address for DS18B20 sensors (16 hex chars) */
  onewire_address?: string
  /** I2C address for I2C sensors (e.g., SHT31: 0x44=68 or 0x45=69) */
  i2c_address?: number | null
  /** Interface type for sensor (I2C, ONEWIRE, ANALOG, DIGITAL, UART, VIRTUAL) */
  interface_type?: 'I2C' | 'ONEWIRE' | 'ANALOG' | 'DIGITAL' | 'UART' | 'VIRTUAL'
}

export interface MockActuatorConfig {
  gpio: number
  actuator_type: string
  name?: string
  state?: boolean
  pwm_value?: number
  min_value?: number
  max_value?: number
  /** Subzone ID (optional); sent as top-level in ActuatorConfigCreate */
  subzone_id?: string | null
  // Phase 7: Actuator Sidebar fields
  aux_gpio?: number | null      // 255 = nicht verwendet (für Ventile: Direction-Pin)
  inverted_logic?: boolean      // LOW = ON (für Pumpen, Ventile, Relais)
  max_runtime_seconds?: number  // RuntimeProtection (für Pumpen)
  cooldown_seconds?: number     // RuntimeProtection (für Pumpen)
}

// =============================================================================
// WebSocket Message Types
// =============================================================================
/**
 * All WebSocket message types from server broadcasts.
 * 
 * Server-side origins (handler → message_type):
 * - sensor_handler.py       → sensor_data
 * - actuator_handler.py     → actuator_status
 * - actuator_response.py    → actuator_response
 * - actuator_alert.py       → actuator_alert
 * - config_handler.py       → config_response
 * - zone_ack_handler.py     → zone_assignment
 * - heartbeat_handler.py    → esp_health
 * - audit_backup_service.py → events_restored (Backup-Restore)
 */
export type MessageType =
  // Core sensor/actuator events
  | 'sensor_data'
  | 'actuator_status'
  | 'actuator_response'
  | 'actuator_alert'
  // Device health & status
  | 'esp_health'
  | 'esp_reconnect_phase'
  | 'sensor_health'  // Phase 2E: Sensor timeout events
  // Configuration events
  | 'config_response'
  | 'config_response_guard_replay'  // PKG-04b: Guard-Replay distinct event type
  | 'zone_assignment'
  // Discovery/Approval events (Phase: Device Discovery)
  | 'device_discovered'
  | 'device_approved'
  | 'device_rejected'
  | 'device_rediscovered'
  // Actuator command lifecycle
  | 'actuator_command'
  | 'actuator_command_failed'
  // Config publish lifecycle
  | 'config_published'
  | 'config_failed'
  // Sequence events (automation)
  | 'sequence_started'
  | 'sequence_step'
  | 'sequence_completed'
  | 'sequence_error'
  | 'sequence_cancelled'
  // Sensor/actuator config lifecycle
  | 'sensor_config_deleted'
  | 'actuator_config_deleted'
  // Device scope & context events (T13-R2)
  | 'device_scope_changed'
  | 'device_context_changed'
  // Subzone assignment (dispatched in esp.store)
  | 'subzone_assignment'
  // System events
  | 'logic_execution'
  | 'conflict.arbitration'
  | 'system_event'
  | 'notification'
  | 'notification_new'
  | 'notification_updated'
  | 'notification_unread_count'
  | 'error_event'
  // Intent / Outcome (April 2026 contract)
  | 'intent_outcome'
  | 'intent_outcome_lifecycle'
  // Calibration lifecycle (S-P6)
  | 'calibration_session_started'
  | 'calibration_session_finalized'
  | 'calibration_session_applied'
  | 'calibration_session_rejected'
  | 'calibration_point_added'
  | 'calibration_point_rejected'
  | 'calibration_measurement_received'
  | 'calibration_measurement_failed'
  // Rule degradation lifecycle (AUT-111)
  | 'rule_degraded'
  | 'rule_recovered'
  // Rule health snapshot (AUT-115 climate cockpit)
  | 'rule.health'
  // Backup restore notify (audit_backup_service → WS broadcast)
  | 'events_restored'

export interface MqttMessage {
  id: string
  timestamp: string
  type: MessageType
  topic: string
  payload: Record<string, unknown>
  esp_id?: string
}

export interface WebSocketFilters {
  types: MessageType[]
  esp_ids: string[]
  topicPattern: string
}

// =============================================================================
// Offline Reason Types (LWT & Heartbeat Timeout)
// =============================================================================

/**
 * Grund für Offline-Status eines ESP-Geräts.
 *
 * - 'lwt': Verbindung unerwartet verloren (Power-Loss, Crash, Netzwerkfehler)
 * - 'heartbeat_timeout': Keine Antwort seit 5 Minuten
 * - 'shutdown': Gerät wurde absichtlich heruntergefahren (Future)
 * - 'unknown': Unbekannter Grund (Legacy-Daten)
 */
export type OfflineReason = 'lwt' | 'heartbeat_timeout' | 'shutdown' | 'unknown'

/**
 * Quelle der Status-Änderung.
 *
 * - 'lwt': Last-Will-Testament vom MQTT Broker
 * - 'heartbeat': Regulärer Heartbeat
 * - 'heartbeat_timeout': Timeout-Check im Server
 * - 'api': Manueller Status-Update via API
 */
export type StatusSource = 'lwt' | 'heartbeat' | 'heartbeat_timeout' | 'api'

/**
 * Offline-Informationen für ein ESP-Gerät.
 * Wird im ESP Store gespeichert wenn status = 'offline'.
 */
export interface OfflineInfo {
  /** Grund für Offline-Status */
  reason: OfflineReason
  /** Quelle der Status-Änderung */
  source: StatusSource
  /** Zeitstempel wann offline ging (Unix timestamp) */
  timestamp: number
  /** Menschenlesbarer Text für UI */
  displayText: string
}

/**
 * Terminales Config-Reject-Ergebnis pro ESP-Gerät (AUT-134 PKG-04).
 *
 * Wird gesetzt, wenn der Server (PKG-01) ein `config_failed` mit
 * `reason_code='config_oversize'` sendet ODER wenn ein `intent_outcome`
 * mit `flow='config'` und `code='PAYLOAD_TOO_LARGE'` (ESP32 PKG-02)
 * eintrifft.
 *
 * Semantik:
 * - Read-only informational state (kein Auto-Retry)
 * - Wird durch nächste erfolgreiche Config-Operation NICHT automatisch
 *   gelöscht — Operator sieht den letzten Reject bis ein neues Reject
 *   eintrifft oder explizit abgewiesen wird.
 * - SEPARATER Pfad zum runtime_health_view.degraded `Eingeschränkt`-Badge.
 */
export interface ConfigLastReject {
  /** Maschinenlesbarer Reject-Grund (z. B. 'config_oversize', 'PAYLOAD_TOO_LARGE') */
  reason_code: string
  /** Größe des abgelehnten Config-Payloads in Bytes (optional) */
  payload_size_bytes: number | null
  /** Maximal erlaubte Größe in Bytes (optional) */
  budget_bytes: number | null
  /** Korrelations-ID des fehlgeschlagenen Intents (optional) */
  correlation_id: string | null
  /** ISO-Timestamp oder Unix-ms wann das Reject empfangen wurde */
  timestamp: string
  /** Quelle des Rejects: Server (config_failed) oder ESP32 (intent_outcome) */
  source: 'config_failed' | 'intent_outcome'
}

/**
 * WebSocket esp_health Event Payload.
 * Erweitert um source und reason Felder.
 */
export interface EspHealthEvent {
  esp_id: string
  status: 'online' | 'offline'
  heap_free?: number
  wifi_rssi?: number
  uptime?: number
  sensor_count?: number
  actuator_count?: number
  timestamp?: number
  /** Nur bei status='offline': Quelle der Offline-Erkennung */
  source?: StatusSource
  /** Nur bei status='offline': Grund für Offline */
  reason?: string
  /** Nur bei heartbeat_timeout: Timeout-Dauer in Sekunden */
  timeout_seconds?: number
  critical_outcome_drop_count?: number
  publish_outbox_drop_count?: number
  persistence_drift_count?: number
  heartbeat_degraded_count?: number
  publish_queue_drop_count?: number
  safe_publish_retry_count?: number
  spool_pending_count?: number        // AUT-716: LittleFS spool entries pending replay
  spool_dropped_count?: number        // AUT-716: LittleFS spool entries dropped
}

/**
 * WebSocket sensor_health Event Payload (Phase 2E).
 * Wird vom Server bei Sensor-Timeout-Überschreitung gesendet.
 */
export interface SensorHealthEvent {
  esp_id: string
  gpio: number
  sensor_type: string
  sensor_name: string | null
  is_stale: boolean
  stale_reason: 'timeout_exceeded' | 'no_data' | 'sensor_error' | 'freshness_exceeded'
  last_reading_at: string | null
  timeout_seconds: number
  /** Freshness limit in hours for on-demand/scheduled sensors */
  freshness_hours?: number | null
  seconds_overdue: number
  operating_mode: SensorOperatingMode
  config_source: 'instance' | 'type_default' | 'system_default'
  timestamp: number
}

// =============================================================================
// API Response Types
// =============================================================================
export interface ApiResponse<T> {
  success: boolean
  data?: T
  error?: string
  message?: string
}

export interface PaginatedResponse<T> {
  success: boolean
  data: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface CommandResponse {
  success: boolean
  esp_id: string
  command: string
  result?: Record<string, unknown>
  error?: string
}

// =============================================================================
// Logic Types (re-exported from logic.ts for detailed types)
// =============================================================================
export type {
  LogicRule,
  LogicCondition,
  SensorCondition,
  TimeCondition,
  CompoundCondition,
  LogicAction,
  ActuatorAction,
  NotificationAction,
  DelayAction,
  LogicConnection,
  LogicRulesResponse,
  ExecutionHistoryResponse,
  ExecutionHistoryItem,
} from './logic'

export { generateRuleDescription, extractConnections } from './logic'

// Legacy LogicExecution (kept for backward compatibility)
export interface LogicExecution {
  id: string
  rule_id: string
  rule_name: string
  triggered_at: string
  conditions_met: boolean
  actions_executed: number
  execution_time_ms: number
  error: string | null
}

// =============================================================================
// Sensor Operating Modes (Phase 2B)
// =============================================================================

/**
 * Operating Mode für Sensor-Messverhalten.
 *
 * - continuous: Automatische Messungen im Intervall
 * - on_demand: Nur manuelle Messungen (User-triggered)
 * - scheduled: Messungen zu definierten Zeiten
 * - paused: Temporär deaktiviert
 */
export type SensorOperatingMode = 'continuous' | 'on_demand' | 'scheduled' | 'paused'

// =============================================================================
// Sensor & Actuator Config Types (Real ESPs)
// =============================================================================

export interface SensorConfigCreate {
  esp_id: string
  gpio: number
  sensor_type: string
  name?: string | null
  enabled?: boolean
  interval_ms?: number
  processing_mode?: 'pi_enhanced' | 'local' | 'raw'
  calibration?: Record<string, unknown> | null
  threshold_min?: number | null
  threshold_max?: number | null
  warning_min?: number | null
  warning_max?: number | null
  metadata?: Record<string, unknown> | null
  // =========================================================================
  // MULTI-VALUE SENSOR SUPPORT (I2C/OneWire)
  // =========================================================================
  /** Interface type: I2C, ONEWIRE, ANALOG, DIGITAL, UART, VIRTUAL (auto-inferred if not provided) */
  interface_type?: 'I2C' | 'ONEWIRE' | 'ANALOG' | 'DIGITAL' | 'UART' | 'VIRTUAL'
  /** I2C address (0-127) - required for I2C sensors */
  i2c_address?: number | null
  /** OneWire device ROM address - optional, server auto-generates if not provided */
  onewire_address?: string | null
  /** List of value types this sensor provides (for multi-value sensors) */
  provides_values?: string[] | null
  // =========================================================================
  // EXTERNAL ADC SOURCE (ADS1115) — per-sensor acquisition source for pH/EC
  // =========================================================================
  /** ADC acquisition source: 'internal' (ESP32 12-bit, default) or 'ads1115' (external 16-bit I2C ADC) */
  adc_source?: 'internal' | 'ads1115' | null
  /** ADS1115 single-ended channel 0-3 (only for adc_source='ads1115') */
  adc_channel?: number | null
  /** ADS1115 PGA full-scale range in volts (only for adc_source='ads1115'; default '4.096') */
  pga_gain?: '6.144' | '4.096' | '2.048' | '1.024' | '0.512' | '0.256' | null
  // =========================================================================
  // OPERATING MODE FIELDS (Phase 2B)
  // =========================================================================
  /** Betriebsmodus: continuous, on_demand, scheduled, paused */
  operating_mode?: SensorOperatingMode
  /** Timeout in Sekunden für Stale-Erkennung (0 = kein Timeout) */
  timeout_seconds?: number
  /** Ob Timeout-Warnungen aktiviert sind */
  timeout_warning_enabled?: boolean
  /** Schedule-Konfiguration für scheduled-Modus */
  schedule_config?: Record<string, unknown> | null
  /** Hours after which on-demand/scheduled measurement is stale */
  measurement_freshness_hours?: number | null
  /** Days between recommended recalibrations */
  calibration_interval_days?: number | null
  /** Subzone ID to assign this sensor to. Null/empty = remove from all subzones */
  subzone_id?: string | null
  /** Device scope: zone_local, multi_zone, mobile (T13-R2) */
  device_scope?: DeviceScope
  /** Zones this sensor is assigned to for multi_zone scope (T13-R2) */
  assigned_zones?: string[] | null
  /** Subzones this sensor is assigned to (T13-R2) */
  assigned_subzones?: string[] | null
  /** Sensor kind: continuous (default) or snapshot (Wave 1, MultispeQ) */
  sensor_kind?: SensorKind
  /** AUT-299: UUID of the linked temperature sensor config for ATC. Null = no sensor linked. */
  temp_sensor_config_id?: string | null
}

export interface SensorConfigResponse {
  id: string
  esp_id: string
  esp_device_id?: string
  gpio: number
  sensor_type: string
  name: string
  enabled: boolean
  interval_ms: number
  processing_mode: string
  calibration: Record<string, unknown> | null
  threshold_min: number | null
  threshold_max: number | null
  warning_min: number | null
  warning_max: number | null
  /** I2C address (0-127) - backend returns as int */
  i2c_address?: number | null
  /** ADC acquisition source: 'internal' (default) or 'ads1115' (external 16-bit I2C ADC) */
  adc_source?: 'internal' | 'ads1115' | null
  /** ADS1115 single-ended channel 0-3 (only for adc_source='ads1115') */
  adc_channel?: number | null
  /** ADS1115 PGA full-scale range in volts (only for adc_source='ads1115') */
  pga_gain?: string | null
  metadata: Record<string, unknown> | null
  // Config status from ESP32 verification (Phase 2: write-after-verification)
  config_status?: 'pending' | 'applied' | 'failed' | null
  config_error?: string | null
  config_error_detail?: string | null
  /** Subzone ID this sensor belongs to (if any) */
  subzone_id?: string | null
  /** Operating mode: continuous, on_demand, scheduled, paused */
  operating_mode?: SensorOperatingMode | null
  /** Timeout for stale detection in seconds (0 = disabled) */
  timeout_seconds?: number | null
  /** Schedule config for scheduled mode: { type: 'cron', expression: string } */
  schedule_config?: { type: string; expression: string } | Record<string, unknown> | null
  /** Hours after which on-demand/scheduled measurement is stale */
  measurement_freshness_hours?: number | null
  /** Days between recommended recalibrations */
  calibration_interval_days?: number | null
  /** Device scope: zone_local, multi_zone, mobile (T13-R2) */
  device_scope: DeviceScope | null
  /** Zones this sensor is assigned to for multi_zone scope (T13-R2) */
  assigned_zones: string[] | null
  /** Subzones this sensor is assigned to (T13-R2) */
  assigned_subzones?: string[] | null
  /** Sensor kind: continuous (default) or snapshot (Wave 1, MultispeQ) */
  sensor_kind?: SensorKind | null
  latest_value?: number | null
  latest_quality?: QualityLevel | null
  latest_timestamp?: string | null
  created_at: string
  updated_at: string
  /** MQTT send_config correlation_id for this save; matches WS config_response / config_published */
  correlation_id?: string | null
  /** AUT-299: UUID of the linked temperature sensor config for ATC (Automatic Temperature Compensation). Null = no sensor linked. */
  temp_sensor_config_id?: string | null
}

// =============================================================================
// Sensor History Types (Phase 3 - Server History Endpoint)
// =============================================================================

/**
 * Single sensor reading from history (raw or aggregated bucket).
 * Matches server schema: SensorReading (schemas/sensor.py:488-555)
 */
export interface SensorReading {
  timestamp: string
  raw_value: number
  processed_value: number | null
  unit: string | null
  quality: string
  sensor_type?: string | null
  zone_id?: string | null
  subzone_id?: string | null
  /** Minimum value in bucket (aggregated only) */
  min_value?: number | null
  /** Maximum value in bucket (aggregated only) */
  max_value?: number | null
  /** Number of samples in bucket (aggregated only) */
  sample_count?: number | null
}

/** Valid resolution values for sensor data aggregation */
export type SensorDataResolution = 'raw' | '1m' | '5m' | '1h' | '1d'

/**
 * Query parameters for sensor data history.
 * Matches server endpoint: GET /v1/sensors/data
 */
export interface SensorDataQuery {
  esp_id?: string
  gpio?: number
  sensor_type?: string
  start_time?: string  // ISO datetime
  end_time?: string    // ISO datetime
  quality?: string
  limit?: number       // 1-1000, default 100
  /** Time resolution for aggregation (raw, 1m, 5m, 1h, 1d) */
  resolution?: SensorDataResolution
  /** Cursor: only return data before this timestamp */
  before_timestamp?: string
  zone_id?: string
  subzone_id?: string
  sensor_config_id?: string
}

/**
 * Response from sensor data query.
 * Matches server schema: SensorDataResponse (schemas/sensor.py:612-656)
 */
export interface SensorDataResponse {
  success: boolean
  esp_id: string | null
  gpio: number | null
  sensor_type: string | null
  readings: SensorReading[]
  count: number
  /** Resolution applied (raw, 1m, 5m, 1h, 1d) */
  resolution: string | null
  time_range: {
    start: string
    end: string
    has_more?: boolean
    next_cursor?: string
  } | null
}

/**
 * Statistical summary for sensor data.
 * Matches server schema: SensorStats (schemas/sensor.py:424-454)
 */
export interface SensorStats {
  min_value: number | null
  max_value: number | null
  avg_value: number | null
  std_dev: number | null
  reading_count: number
  quality_distribution: Record<QualityLevel, number>
}

/**
 * Response from sensor statistics query.
 * Matches server schema: SensorStatsResponse (schemas/sensor.py:457-466)
 */
export interface SensorStatsResponse {
  success: boolean
  esp_id: string
  gpio: number
  sensor_type: string
  stats: SensorStats
  time_range: {
    start: string
    end: string
  }
}

// =============================================================================
// Drag & Drop Types (Phase 4 - Multi-Sensor Chart)
// =============================================================================

/**
 * Drag data for sensor satellite.
 * Used by SensorSatellite → AnalysisDropZone
 */
export interface SensorDragData {
  type: 'sensor'
  espId: string
  gpio: number
  sensorType: string
  name: string
  unit: string
}

/**
 * Drag data for actuator satellite.
 * Used by ActuatorSatellite → AnalysisDropZone
 */
export interface ActuatorDragData {
  type: 'actuator'
  espId: string
  gpio: number
  actuatorType: string
  name: string
}

/**
 * Union type for all drag data.
 */
export type DragData = SensorDragData | ActuatorDragData

/**
 * Selected sensor for Multi-Sensor Chart.
 */
export interface ChartSensor {
  id: string  // Unique ID: `${espId}_${gpio}_${sensorType}` (includes sensorType for multi-value sensors like SHT31)
  espId: string
  gpio: number
  sensorType: string
  name: string
  unit: string
  color: string  // Chart line color
}

export interface ActuatorConfigCreate {
  esp_id: string
  gpio: number
  actuator_type: string
  name?: string | null
  enabled?: boolean
  max_runtime_seconds?: number | null
  cooldown_seconds?: number | null
  pwm_frequency?: number | null
  servo_min_pulse?: number | null
  servo_max_pulse?: number | null
  metadata?: Record<string, unknown> | null
  /** Subzone ID to assign this actuator to. Null/empty = remove from all subzones */
  subzone_id?: string | null
  /** Device scope: zone_local, multi_zone, mobile (T13-R2) */
  device_scope?: DeviceScope
  /** Zones this actuator is assigned to for multi_zone scope (T13-R2) */
  assigned_zones?: string[] | null
  /** Subzones this actuator is assigned to (T13-R2) */
  assigned_subzones?: string[] | null
}

export interface ActuatorConfigResponse {
  id: string
  esp_id: string
  esp_device_id?: string
  gpio: number
  actuator_type: string
  /** Original ESP32 hardware type (relay, pump, valve, pwm) before server normalization */
  hardware_type?: string | null
  name: string
  enabled: boolean
  max_runtime_seconds: number | null
  cooldown_seconds: number | null
  pwm_frequency: number | null
  servo_min_pulse: number | null
  servo_max_pulse: number | null
  metadata: Record<string, unknown> | null
  subzone_id?: string | null
  // Config status from ESP32 verification (Phase 2: write-after-verification)
  config_status?: 'pending' | 'applied' | 'failed' | null
  config_error?: string | null
  config_error_detail?: string | null
  /** Device scope: zone_local, multi_zone, mobile (T13-R2) */
  device_scope: DeviceScope | null
  /** Zones this actuator is assigned to for multi_zone scope (T13-R2) */
  assigned_zones: string[] | null
  /** Subzones this actuator is assigned to (T13-R2) */
  assigned_subzones?: string[] | null
  current_value?: number | null
  is_active?: boolean
  last_command_at?: string | null
  created_at: string
  updated_at: string
}

// =============================================================================
// Config Response Types (WebSocket Events)
// =============================================================================

export interface ConfigResponse {
  esp_id: string
  config_type: 'sensor' | 'actuator'
  status: 'success' | 'partial_success' | 'error'
  count: number
  message: string
  error_code?: string
  reason_code?: string
  generation?: number
  config_fingerprint?: string
  trigger_source?: string
  timestamp: number
}

/**
 * Phase 4: Individual configuration failure from ESP32.
 */
export interface ConfigFailure {
  type: 'sensor' | 'actuator'
  gpio: number
  error_code: number
  error: string
  detail: string | null
}

/**
 * Phase 4: Extended config response with failures array and partial_success status.
 */
export interface ConfigResponseExtended extends ConfigResponse {
  status: 'success' | 'partial_success' | 'error'
  failed_count?: number
  failures?: ConfigFailure[]
  error_description?: string
  failed_item?: Record<string, unknown>  // Legacy backward compatibility
}

// =============================================================================
// Zone Entity Types (T13-R1 Backend)
// =============================================================================

export type ZoneStatus = 'active' | 'archived' | 'deleted'

export interface ZoneEntity {
  id: string
  zone_id: string
  name: string
  description: string | null
  status: ZoneStatus
  deleted_at: string | null
  created_at: string
  updated_at: string
}

export interface ZoneEntityCreate {
  zone_id: string
  name: string
  description?: string | null
}

export interface ZoneEntityUpdate {
  name?: string | null
  description?: string | null
}

export interface ZoneEntityListResponse {
  zones: ZoneEntity[]
  total: number
}

// =============================================================================
// Device Scope Types (T13-R2 Backend)
// =============================================================================

export type DeviceScope = 'zone_local' | 'multi_zone' | 'mobile'

export interface DeviceContextSet {
  active_zone_id: string | null
  active_subzone_id?: string | null
  context_source?: 'manual' | 'sequence' | 'mqtt'
}

export interface DeviceContextResponse {
  success: boolean
  config_type: 'sensor' | 'actuator'
  config_id: string
  active_zone_id: string | null
  active_subzone_id: string | null
  context_source: string
  context_since: string | null
}

// =============================================================================
// Zone Assignment Types
// =============================================================================

/**
 * Zone assignment request to assign ESP to a zone.
 */
export interface ZoneAssignRequest {
  zone_id: string
  master_zone_id?: string
  zone_name?: string
  /** Strategy for subzone handling during zone transfer (T13-R2) */
  subzone_strategy?: 'transfer' | 'copy' | 'reset'
}

/**
 * Zone assignment response from server.
 */
export interface ZoneAssignResponse {
  success: boolean
  message: string
  device_id: string
  zone_id: string
  master_zone_id?: string
  zone_name?: string
  mqtt_topic: string
  mqtt_sent: boolean
}

/**
 * Zone removal response from server.
 */
export interface ZoneRemoveResponse {
  success: boolean
  message: string
  device_id: string
  mqtt_topic: string
  mqtt_sent: boolean
}

/**
 * Zone info for display.
 */
export interface ZoneInfo {
  zone_id: string | null
  master_zone_id: string | null
  zone_name: string | null
  is_zone_master: boolean
  kaiser_id: string | null
}

/**
 * Zone list entry from GET /v1/zone/zones.
 * Includes empty zones (from ZoneContext table, 0 devices).
 */
export interface ZoneListEntry {
  zone_id: string
  zone_name: string | null
  device_count: number
  sensor_count: number
  actuator_count: number
}

/**
 * Response from GET /v1/zone/zones.
 */
export interface ZoneListResponse {
  zones: ZoneListEntry[]
  total: number
}

/**
 * Zone update from WebSocket (ESP ACK confirmation).
 */
export interface ZoneUpdate {
  esp_id: string
  status: 'zone_assigned' | 'error'
  zone_id: string
  master_zone_id?: string
  timestamp: number
  message?: string
}

// =============================================================================
// Subzone Management Types (Phase 9)
// =============================================================================

/**
 * Subzone information for display.
 */
export interface SubzoneInfo {
  subzone_id: string
  subzone_name: string | null
  parent_zone_id: string
  assigned_gpios: number[]
  safe_mode_active: boolean
  sensor_count: number
  actuator_count: number
  custom_data: Record<string, unknown>
  created_at?: string
}

/**
 * Subzone assignment request.
 */
export interface SubzoneAssignRequest {
  subzone_id: string
  subzone_name?: string
  parent_zone_id?: string
  assigned_gpios: number[]
  safe_mode_active?: boolean
}

/**
 * Subzone assignment response from server.
 */
export interface SubzoneAssignResponse {
  success: boolean
  message: string
  device_id: string
  subzone_id: string
  assigned_gpios: number[]
  mqtt_topic: string
  mqtt_sent: boolean
}

/**
 * Subzone removal response from server.
 */
export interface SubzoneRemoveResponse {
  success: boolean
  message: string
  device_id: string
  subzone_id: string
  mqtt_topic: string
  mqtt_sent: boolean
}

/**
 * Subzone list response from server.
 */
export interface SubzoneListResponse {
  success: boolean
  message: string
  device_id: string
  zone_id: string | null
  subzones: SubzoneInfo[]
  total_count: number
}

/**
 * Subzone update from WebSocket (ESP ACK confirmation).
 */
export interface SubzoneUpdate {
  device_id: string
  subzone_id: string
  status: 'subzone_assigned' | 'subzone_removed' | 'error'
  timestamp: number
  error_code?: number
  message?: string
}

/**
 * Safe-mode control request.
 */
export interface SafeModeRequest {
  reason?: string
}

/**
 * Safe-mode control response.
 */
export interface SafeModeResponse {
  success: boolean
  message: string
  device_id: string
  subzone_id: string
  safe_mode_active: boolean
  mqtt_sent: boolean
}

// =============================================================================
// Plant Lifecycle Types (AUT-221 / AUT-222)
// =============================================================================

/**
 * Plant lifecycle phase (15 + archived states).
 * Mirrors the backend `plants.phase` enum.
 */
export type PlantPhase =
  | 'invitro_donor'
  | 'invitro_initiation'
  | 'invitro_multiplication'
  | 'invitro_rooting'
  | 'invitro_acclimatization'
  | 'clone'
  | 'veg-frueh'
  | 'veg-spaet'
  | 'bluete-stretch'
  | 'bluete-bulk'
  | 'bluete-ende'
  | 'mutter'
  | 'steckling_wurzelung'
  | 'steckling_vor_versand'
  | 'harvested'
  | 'archived'

/** Available phases as a runtime list (for select dropdowns / filter chips). */
export const PLANT_PHASES: readonly PlantPhase[] = [
  'invitro_donor',
  'invitro_initiation',
  'invitro_multiplication',
  'invitro_rooting',
  'invitro_acclimatization',
  'clone',
  'veg-frueh',
  'veg-spaet',
  'bluete-stretch',
  'bluete-bulk',
  'bluete-ende',
  'mutter',
  'steckling_wurzelung',
  'steckling_vor_versand',
  'harvested',
  'archived',
] as const

/**
 * Plant entity returned from `GET /v1/plants` and `GET /v1/plants/{id}`.
 *
 * Server endpoint: AUT-221 / AUT-222.
 */
export interface Plant {
  /** UUID */
  id: string
  /** QR-Code label (e.g. "P-2026-0001") */
  qr_code: string
  /** Optional external/legacy identifier */
  external_plant_id?: string | null
  /** Genotype/strain name */
  genotype: string
  /** Optional charge/batch identifier */
  batch?: string | null
  /** Lifecycle phase */
  phase: PlantPhase
  /** ISO date string (YYYY-MM-DD) */
  planting_date?: string | null
  /** Zone assignment */
  zone_id?: string | null
  /** Subzone assignment */
  subzone_id?: string | null
  /** Soft-delete timestamp */
  deleted_at?: string | null
  /** ISO timestamp */
  created_at: string
  /** Optional list returned by GET /v1/plants/{id} */
  lifecycle_events?: PlantLifecycleEvent[]
  /** Optional list returned by GET /v1/plants/{id} */
  audit_logs?: PlantAuditLog[]
}

/**
 * Lifecycle event (phase change, note, harvest, etc.) attached to a plant.
 */
export interface PlantLifecycleEvent {
  /** UUID */
  id: string
  /** Owning plant UUID */
  plant_id: string
  /** Event type, e.g. "phase_change", "note", "harvest" */
  event_type: string
  /** Free-text note from the operator */
  note?: string | null
  /** ISO timestamp */
  created_at: string
  /** Optional metadata (phase transitions: { from: PlantPhase, to: PlantPhase }) */
  metadata?: Record<string, unknown>
}

/**
 * Audit-log entry for a plant (who changed what, when).
 */
export interface PlantAuditLog {
  id: string
  action: string
  user?: string | null
  created_at: string
  changes?: Record<string, unknown>
}

/**
 * Single MultispeQ measurement aggregated to a plant.
 */
export interface PlantMeasurement {
  /** UUID */
  id: string
  /** ISO timestamp */
  timestamp: string
  /** Phi2 (PSII operating efficiency) */
  phi2?: number | null
  /** Fv/Fm (max quantum yield) */
  fv_fm?: number | null
  /** Non-photochemical quenching */
  npq?: number | null
  /** Other measured parameters */
  sensor_values?: Record<string, number>
}

/**
 * Create-payload for `POST /v1/plants`.
 */
export interface PlantCreate {
  genotype: string
  batch?: string | null
  zone_id?: string | null
  subzone_id?: string | null
  /** ISO date "YYYY-MM-DD" */
  planting_date?: string | null
  phase?: PlantPhase
  external_plant_id?: string | null
}

/**
 * Update-payload for `PATCH /v1/plants/{id}`.
 */
export type PlantUpdate = Partial<PlantCreate>

/**
 * Create-payload for `POST /v1/plants/{id}/lifecycle-event`.
 */
export interface PlantLifecycleEventCreate {
  event_type: string
  note?: string | null
  metadata?: Record<string, unknown>
}
