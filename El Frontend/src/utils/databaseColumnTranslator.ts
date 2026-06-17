/**
 * Database Column Translator (German)
 *
 * Translates technical database column names into human-readable
 * German labels for the System Monitor database explorer.
 *
 * @see El Servador/god_kaiser_server/src/db/models/
 */

import { formatRelativeTime, formatDateTime } from './formatters'
import { getActuatorTypeLabel } from './labels'
import { getSeverityLabel } from './errorCodeTranslator'

// =============================================================================
// TYPES
// =============================================================================

export interface ColumnConfig {
  /** Technical column name */
  key: string
  /** Human-readable label */
  label: string
  /** Tooltip/description text */
  description?: string
  /** Value formatter function */
  formatter?: (value: unknown) => string
  /** Lucide icon name (optional) */
  icon?: string
  /** Whether column should be visible by default */
  defaultVisible?: boolean
  /** Column width hint (narrow, normal, wide) */
  width?: 'narrow' | 'normal' | 'wide'
}

export interface TableConfig {
  /** Table name */
  tableName: string
  /** Human-readable table label */
  tableLabel: string
  /** Table description */
  description?: string
  /** Primary key column */
  primaryKey: string
  /** Column configurations */
  columns: Record<string, ColumnConfig>
}

// =============================================================================
// VALUE FORMATTERS
// =============================================================================

function formatJsonValue(value: unknown): string {
  if (value === null || value === undefined) return '-'
  if (typeof value === 'object') {
    const json = JSON.stringify(value)
    return json.length > 50 ? `${json.slice(0, 47)}...` : json
  }
  return String(value)
}

function formatStatusValue(value: unknown): string {
  if (!value) return '-'
  const status = String(value).toLowerCase()
  const statusMap: Record<string, string> = {
    online: 'Online',
    offline: 'Offline',
    error: 'Fehler',
    unknown: 'Unbekannt',
    pending_approval: 'Wartet auf Freigabe',
    approved: 'Freigegeben',
    rejected: 'Abgelehnt',
    pending: 'Ausstehend'
  }
  return statusMap[status] ?? value
}

function formatHealthStatus(value: unknown): string {
  if (!value) return '-'
  const health = String(value).toLowerCase()
  const healthMap: Record<string, string> = {
    healthy: 'Gesund',
    degraded: 'Eingeschränkt',
    unhealthy: 'Ungesund',
    critical: 'Kritisch'
  }
  return healthMap[health] ?? value
}

function formatBooleanGerman(value: unknown): string {
  if (value === null || value === undefined) return '-'
  return value ? 'Ja' : 'Nein'
}

function formatTimestamp(value: unknown): string {
  if (!value) return '-'
  try {
    const date = new Date(value as string)
    return formatDateTime(date)
  } catch {
    return String(value)
  }
}

function formatRelativeTimestamp(value: unknown): string {
  if (!value) return '-'
  try {
    const date = new Date(value as string)
    return formatRelativeTime(date)
  } catch {
    return String(value)
  }
}

function formatInterfaceType(value: unknown): string {
  if (!value) return '-'
  const type = String(value).toUpperCase()
  const typeMap: Record<string, string> = {
    I2C: 'I2C-Bus',
    ONEWIRE: 'OneWire-Bus',
    ANALOG: 'Analog',
    DIGITAL: 'Digital',
    UART: 'UART',
  }
  return typeMap[type] ?? value
}

function formatSensorType(value: unknown): string {
  if (!value) return '-'
  const type = String(value).toLowerCase()
  const typeMap: Record<string, string> = {
    temperature: 'Temperatur',
    humidity: 'Luftfeuchtigkeit',
    ph: 'pH-Wert',
    ec: 'Leitfähigkeit',
    moisture: 'Bodenfeuchtigkeit',
    ds18b20: 'DS18B20 (Temperatur)',
    sht31: 'SHT31 (Temp./Feuchte)',
    bme280: 'BME280 (Umwelt)',
    generic: 'Generisch'
  }
  return typeMap[type] ?? value
}

// formatSeverity moved to formatSeverityWithIcon (Sprint 3)

function formatSourceType(value: unknown): string {
  if (!value) return '-'
  const source = String(value).toLowerCase()
  const sourceMap: Record<string, string> = {
    esp32: 'ESP32-Gerät',
    user: 'Benutzer',
    system: 'System',
    api: 'API',
    mqtt: 'MQTT',
    scheduler: 'Geplante Aufgabe'
  }
  return sourceMap[source] ?? value
}

function formatMilliseconds(value: unknown): string {
  if (value === null || value === undefined) return '-'
  const ms = Number(value)
  if (isNaN(ms)) return String(value)
  if (ms < 1000) return `${ms} ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`
  return `${(ms / 60000).toFixed(1)} min`
}

function formatGpio(value: unknown): string {
  if (value === null || value === undefined) return '-'
  return `GPIO ${value}`
}

// =============================================================================
// AUDIT LOG SPECIFIC FORMATTERS (Sprint 3: UX-Verbesserung)
// =============================================================================

/**
 * Translate technical event types to German human-readable labels
 *
 * @example "config_response" → "Konfigurations-Antwort"
 */
function formatEventType(value: unknown): string {
  if (!value) return '-'
  const eventType = String(value).toLowerCase()

  const eventTypeMap: Record<string, string> = {
    // Config Events
    config_response: 'Konfigurations-Antwort',
    config_published: 'Konfiguration gesendet',
    config_failed: 'Konfiguration fehlgeschlagen',

    // Device Lifecycle Events
    device_discovered: 'Gerät entdeckt',
    device_approved: 'Gerät freigegeben',
    device_rejected: 'Gerät abgelehnt',
    device_registered: 'Gerät registriert',
    device_online: 'Gerät online',
    device_offline: 'Gerät offline',
    device_rediscovered: 'Gerät wieder entdeckt',
    lwt_received: 'Verbindungsabbruch erkannt',

    // Auth Events
    login_success: 'Anmeldung erfolgreich',
    login_failed: 'Anmeldung fehlgeschlagen',
    logout: 'Abmeldung',
    token_revoked: 'Token widerrufen',

    // Security Events
    permission_denied: 'Zugriff verweigert',
    api_key_invalid: 'API-Schlüssel ungültig',
    rate_limit_exceeded: 'Rate-Limit überschritten',

    // Operational Events
    emergency_stop: 'Not-Aus ausgelöst',
    service_start: 'Dienst gestartet',
    service_stop: 'Dienst gestoppt',

    // Data Events
    sensor_data: 'Sensordaten empfangen',
    actuator_status: 'Aktor-Status',
    actuator_command: 'Aktor-Befehl',

    // Error Events
    mqtt_error: 'MQTT-Fehler',
    database_error: 'Datenbank-Fehler',
    validation_error: 'Validierungs-Fehler',
    error_event: 'Fehlerereignis',

    // Health Events
    esp_health: 'Geräte-Gesundheit',
    heartbeat: 'Heartbeat'
  }

  return eventTypeMap[eventType] ?? value
}

/**
 * Format severity with German labels
 * Uses the imported getSeverityLabel from errorCodeTranslator
 *
 * @example "error" → "Fehler"
 */
function formatSeverityWithIcon(value: unknown): string {
  if (!value) return '-'
  const severity = String(value).toLowerCase()

  // Use the imported function for consistency
  const label = getSeverityLabel(severity as 'info' | 'warning' | 'error' | 'critical')
  return label
}

/**
 * Format error description - shows human-readable error info
 *
 * Strategy:
 * 1. If error_description exists → use it directly (Backend already translated)
 * 2. If empty but it's a success → show "✓ Erfolgreich"
 * 3. Otherwise → show "-"
 *
 * Note: Error code details come from the server (100+ mappings in
 * esp32_error_mapping.py). Frontend displays server-provided messages.
 */
function formatErrorDescription(value: unknown): string {
  if (!value) return '-'

  const description = String(value)

  // Truncate if too long for table display
  if (description.length > 60) {
    return description.substring(0, 57) + '...'
  }

  return description
}

// =============================================================================
// TABLE CONFIGURATIONS
// =============================================================================

const ESP_DEVICES_CONFIG: TableConfig = {
  tableName: 'esp_devices',
  tableLabel: 'ESP32-Geräte',
  description: 'Alle registrierten ESP32-Geräte im System',
  primaryKey: 'id',
  columns: {
    // =========================================================================
    // Robin's Prinzipien: Timestamp prominenter, IDs NEVER
    // Reihenfolge: Gerät → Name → Status → Zuletzt gesehen → Zone → Firmware
    // =========================================================================
    id: {
      key: 'id',
      label: 'Datensatz-ID',
      description: 'Eindeutige Geräte-ID (UUID)',
      width: 'narrow',
      defaultVisible: false  // ← UUID: NIEMALS sichtbar
    },
    device_id: {
      key: 'device_id',
      label: 'Geräte-ID',
      description: 'Eindeutige Kennung des ESP32 (z.B. ESP_12AB34CD)',
      icon: 'Cpu',
      defaultVisible: true  // ← ESP_12AB34CD ist menschenlesbar!
    },
    name: {
      key: 'name',
      label: 'Name',
      description: 'Benutzerdefinierter Gerätename',
      icon: 'Tag',
      defaultVisible: true
    },
    status: {
      key: 'status',
      label: 'Status',
      description: 'Ist das Gerät online oder offline?',
      formatter: formatStatusValue,
      icon: 'Activity',
      defaultVisible: true
    },
    // TIMESTAMP prominent (Robin's Anforderung)
    last_seen: {
      key: 'last_seen',
      label: 'Zuletzt gesehen',
      description: 'Wann war das Gerät zuletzt aktiv?',
      formatter: formatRelativeTimestamp,
      icon: 'Clock',
      defaultVisible: true  // ← KRITISCH: Operator braucht das
    },
    zone_name: {
      key: 'zone_name',
      label: 'Zone',
      description: 'Zugewiesene Zone (menschenlesbar)',
      icon: 'MapPin',
      defaultVisible: true  // ← Name statt ID!
    },
    firmware_version: {
      key: 'firmware_version',
      label: 'Firmware',
      description: 'Installierte Firmware-Version',
      icon: 'Package',
      defaultVisible: true
    },
    // =========================================================================
    // Detail-Only Spalten (nur im Modal sichtbar)
    // =========================================================================
    zone_id: {
      key: 'zone_id',
      label: 'Zonen-ID',
      description: 'Technische Zonen-ID (UUID)',
      defaultVisible: false  // ← UUID: in Details
    },
    is_zone_master: {
      key: 'is_zone_master',
      label: 'Zonen-Master',
      description: 'Ist dieses Gerät ein Zonen-Master?',
      formatter: formatBooleanGerman,
      icon: 'Crown',
      defaultVisible: false  // ← Technisches Detail
    },
    hardware_type: {
      key: 'hardware_type',
      label: 'Hardware-Typ',
      description: 'ESP32-Variante (WROOM, XIAO C3)',
      icon: 'Chip',
      defaultVisible: false  // ← Technisches Detail
    },
    ip_address: {
      key: 'ip_address',
      label: 'IP-Adresse',
      description: 'Aktuelle IP-Adresse im Netzwerk',
      icon: 'Globe',
      defaultVisible: false
    },
    mac_address: {
      key: 'mac_address',
      label: 'MAC-Adresse',
      description: 'Hardware-MAC-Adresse',
      defaultVisible: false
    },
    health_status: {
      key: 'health_status',
      label: 'Gesundheit',
      description: 'Geräte-Gesundheitsstatus',
      formatter: formatHealthStatus,
      icon: 'Heart',
      defaultVisible: false
    },
    discovered_at: {
      key: 'discovered_at',
      label: 'Entdeckt am',
      description: 'Zeitpunkt der Erstentdeckung',
      formatter: formatTimestamp,
      defaultVisible: false
    },
    approved_at: {
      key: 'approved_at',
      label: 'Freigegeben am',
      description: 'Zeitpunkt der Freigabe',
      formatter: formatTimestamp,
      defaultVisible: false
    },
    approved_by: {
      key: 'approved_by',
      label: 'Freigegeben von',
      description: 'Administrator der Freigabe',
      defaultVisible: false
    },
    capabilities: {
      key: 'capabilities',
      label: 'Fähigkeiten',
      description: 'Gerätefähigkeiten (max. Sensoren, Aktoren)',
      formatter: formatJsonValue,
      width: 'wide',
      defaultVisible: false
    },
    created_at: {
      key: 'created_at',
      label: 'Registriert am',
      description: 'Zeitpunkt der Registrierung in der Datenbank',
      formatter: formatTimestamp,
      defaultVisible: false
    },
    updated_at: {
      key: 'updated_at',
      label: 'Aktualisiert am',
      description: 'Zeitpunkt der letzten Änderung',
      formatter: formatTimestamp,
      defaultVisible: false
    }
  }
}

const SENSOR_CONFIGS_CONFIG: TableConfig = {
  tableName: 'sensor_configs',
  tableLabel: 'Sensorkonfigurationen',
  description: 'Konfigurierte Sensoren auf ESP32-Geräten',
  primaryKey: 'id',
  columns: {
    // =========================================================================
    // Robin's Prinzipien: IDs NEVER, wichtige Info zuerst
    // Reihenfolge: Name → Typ → GPIO → Schnittstelle → Aktiviert → Intervall
    // =========================================================================
    id: {
      key: 'id',
      label: 'Datensatz-ID',
      description: 'Eindeutige Sensor-ID (UUID)',
      width: 'narrow',
      defaultVisible: false  // ← UUID: NIEMALS sichtbar
    },
    sensor_name: {
      key: 'sensor_name',
      label: 'Name',
      description: 'Wie heißt dieser Sensor?',
      icon: 'Tag',
      defaultVisible: true
    },
    sensor_type: {
      key: 'sensor_type',
      label: 'Typ',
      description: 'Welche Art von Sensor? (Temperatur, pH, etc.)',
      formatter: formatSensorType,
      icon: 'Thermometer',
      defaultVisible: true
    },
    gpio: {
      key: 'gpio',
      label: 'GPIO',
      description: 'An welchem Pin ist der Sensor angeschlossen?',
      formatter: formatGpio,
      icon: 'CircuitBoard',
      defaultVisible: true
    },
    interface_type: {
      key: 'interface_type',
      label: 'Schnittstelle',
      description: 'Wie kommuniziert der Sensor? (I2C, OneWire, Analog)',
      formatter: formatInterfaceType,
      icon: 'Cable',
      defaultVisible: true
    },
    enabled: {
      key: 'enabled',
      label: 'Aktiv',
      description: 'Ist der Sensor aktiviert?',
      formatter: formatBooleanGerman,
      icon: 'Power',
      defaultVisible: true
    },
    sample_interval_ms: {
      key: 'sample_interval_ms',
      label: 'Messintervall',
      description: 'Wie oft wird gemessen?',
      formatter: formatMilliseconds,
      icon: 'Timer',
      defaultVisible: true
    },
    // =========================================================================
    // Detail-Only Spalten (nur im Modal sichtbar)
    // =========================================================================
    esp_id: {
      key: 'esp_id',
      label: 'Gerät (UUID)',
      description: 'Zugehöriges ESP32-Gerät (technische ID)',
      icon: 'Cpu',
      defaultVisible: false  // ← UUID: in Details
    },
    i2c_address: {
      key: 'i2c_address',
      label: 'I2C-Adresse',
      description: 'I2C-Bus-Adresse (z.B. 0x44)',
      formatter: (v) => v ? `0x${Number(v).toString(16).toUpperCase()}` : '-',
      defaultVisible: false
    },
    onewire_address: {
      key: 'onewire_address',
      label: 'OneWire-Adresse',
      description: 'OneWire-ROM-Code',
      defaultVisible: false
    },
    pi_enhanced: {
      key: 'pi_enhanced',
      label: 'Pi-Enhanced',
      description: 'Server-seitige Verarbeitung aktiv?',
      formatter: formatBooleanGerman,
      icon: 'Server',
      defaultVisible: false
    },
    calibration_data: {
      key: 'calibration_data',
      label: 'Kalibrierung (JSON)',
      description: 'Kalibrierungsparameter',
      formatter: formatJsonValue,
      width: 'wide',
      defaultVisible: false
    },
    thresholds: {
      key: 'thresholds',
      label: 'Schwellwerte (JSON)',
      description: 'Alarm-Schwellwerte (min, max)',
      formatter: formatJsonValue,
      width: 'wide',
      defaultVisible: false
    },
    created_at: {
      key: 'created_at',
      label: 'Erstellt am',
      description: 'Zeitpunkt der Erstellung',
      formatter: formatTimestamp,
      defaultVisible: false
    },
    updated_at: {
      key: 'updated_at',
      label: 'Aktualisiert am',
      description: 'Zeitpunkt der letzten Änderung',
      formatter: formatTimestamp,
      defaultVisible: false
    }
  }
}

const ACTUATOR_CONFIGS_CONFIG: TableConfig = {
  tableName: 'actuator_configs',
  tableLabel: 'Aktorkonfigurationen',
  description: 'Konfigurierte Aktoren auf ESP32-Geräten',
  primaryKey: 'id',
  columns: {
    // =========================================================================
    // Robin's Prinzipien: IDs NEVER, wichtige Info zuerst
    // Reihenfolge: Name → Typ → GPIO → Aktiviert → Max. Laufzeit
    // =========================================================================
    id: {
      key: 'id',
      label: 'Datensatz-ID',
      description: 'Eindeutige Aktor-ID (UUID)',
      width: 'narrow',
      defaultVisible: false  // ← UUID: NIEMALS sichtbar
    },
    actuator_name: {
      key: 'actuator_name',
      label: 'Name',
      description: 'Wie heißt dieser Aktor?',
      icon: 'Tag',
      defaultVisible: true
    },
    actuator_type: {
      key: 'actuator_type',
      label: 'Typ',
      description: 'Welche Art von Aktor? (Relais, Pumpe, PWM)',
      formatter: (v) => getActuatorTypeLabel(String(v)),
      icon: 'Power',
      defaultVisible: true
    },
    gpio: {
      key: 'gpio',
      label: 'GPIO',
      description: 'An welchem Pin ist der Aktor angeschlossen?',
      formatter: formatGpio,
      icon: 'CircuitBoard',
      defaultVisible: true
    },
    enabled: {
      key: 'enabled',
      label: 'Aktiv',
      description: 'Ist der Aktor aktiviert?',
      formatter: formatBooleanGerman,
      icon: 'Power',
      defaultVisible: true
    },
    max_runtime_seconds: {
      key: 'max_runtime_seconds',
      label: 'Sicherheitslimit',
      description: 'Geraete-Sicherheitslimit (Emergency Stop bei Ueberschreitung)',
      formatter: (v) => v ? `${v} s` : 'Unbegrenzt',
      icon: 'Timer',
      defaultVisible: true  // ← Wichtig für Operator (Sicherheit!)
    },
    // =========================================================================
    // Detail-Only Spalten (nur im Modal sichtbar)
    // =========================================================================
    esp_id: {
      key: 'esp_id',
      label: 'Gerät (UUID)',
      description: 'Zugehöriges ESP32-Gerät (technische ID)',
      icon: 'Cpu',
      defaultVisible: false  // ← UUID: in Details
    },
    default_state: {
      key: 'default_state',
      label: 'Standardzustand',
      description: 'Zustand beim Systemstart',
      formatter: (v) => v ? 'Ein' : 'Aus',
      defaultVisible: false
    },
    inverted: {
      key: 'inverted',
      label: 'Invertiert',
      description: 'Ist die Logik invertiert?',
      formatter: formatBooleanGerman,
      defaultVisible: false
    },
    pwm_frequency: {
      key: 'pwm_frequency',
      label: 'PWM-Frequenz',
      description: 'PWM-Frequenz in Hz',
      formatter: (v) => v ? `${v} Hz` : '-',
      defaultVisible: false
    },
    created_at: {
      key: 'created_at',
      label: 'Erstellt am',
      description: 'Zeitpunkt der Erstellung',
      formatter: formatTimestamp,
      defaultVisible: false
    },
    updated_at: {
      key: 'updated_at',
      label: 'Aktualisiert am',
      description: 'Zeitpunkt der letzten Änderung',
      formatter: formatTimestamp,
      defaultVisible: false
    }
  }
}

const AUDIT_LOGS_CONFIG: TableConfig = {
  tableName: 'audit_logs',
  tableLabel: 'Ereignisprotokoll',
  description: 'Systemweites Ereignis- und Audit-Protokoll',
  primaryKey: 'id',
  columns: {
    // =========================================================================
    // Robin's Prinzipien: Timestamp FIRST, IDs NEVER
    // Sprint 3 Fix: Status entfernt (redundant zu Schweregrad), Fehlerbeschreibung hinzugefügt
    // Reihenfolge: Zeitpunkt → Ereignis → Schweregrad → Gerät → Fehlerbeschreibung
    // =========================================================================
    id: {
      key: 'id',
      label: 'Datensatz-ID',
      description: 'Eindeutige Ereignis-ID (UUID)',
      width: 'narrow',
      defaultVisible: false  // ← UUID: NIEMALS sichtbar
    },
    // TIMESTAMP FIRST! (Robin's kritischste Anforderung)
    created_at: {
      key: 'created_at',
      label: 'Zeitpunkt',
      description: 'Wann ist das Ereignis aufgetreten?',
      formatter: formatTimestamp,
      icon: 'Clock',
      defaultVisible: true  // ← KRITISCH: Operator braucht das SOFORT
    },
    event_type: {
      key: 'event_type',
      label: 'Ereignis',
      description: 'Was ist passiert?',
      formatter: formatEventType,  // ← NEU: Übersetzt technische Event-Types
      icon: 'Activity',
      defaultVisible: true
    },
    severity: {
      key: 'severity',
      label: 'Schweregrad',
      description: 'Wie kritisch ist das Ereignis?',
      formatter: formatSeverityWithIcon,  // ← NEU: Mit Icon und Farbe
      icon: 'AlertCircle',
      defaultVisible: true
    },
    source_id: {
      key: 'source_id',
      label: 'Gerät',
      description: 'Welches Gerät hat das Ereignis ausgelöst?',
      defaultVisible: true  // ← ESP_00000001 ist menschenlesbar
    },
    // Fehlerbeschreibung (Server-provided, already human-readable)
    error_description: {
      key: 'error_description',
      label: 'Beschreibung',
      description: 'Was bedeutet dieser Fehler?',
      formatter: formatErrorDescription,  // Server liefert bereits deutsche Message
      width: 'wide',
      defaultVisible: true
    },
    // =========================================================================
    // Detail-Only Spalten (nur im Modal sichtbar)
    // =========================================================================
    status: {
      key: 'status',
      label: 'Status',
      description: 'Ergebnisstatus des Ereignisses',
      formatter: formatStatusValue,
      defaultVisible: false  // ← Sprint 3: Redundant zu severity, ausgeblendet!
    },
    source_type: {
      key: 'source_type',
      label: 'Quelltyp',
      description: 'Typ der Ereignisquelle (ESP32, System, API)',
      formatter: formatSourceType,
      icon: 'Box',
      defaultVisible: false
    },
    error_code: {
      key: 'error_code',
      label: 'Fehlercode',
      description: 'Technischer Fehlercode (für Support)',
      defaultVisible: false  // ← Technisch, nur in Details
    },
    message: {
      key: 'message',
      label: 'Nachricht',
      description: 'System-Nachricht zum Ereignis',
      width: 'wide',
      defaultVisible: false
    },
    details: {
      key: 'details',
      label: 'Details (JSON)',
      description: 'Zusätzliche technische Details',
      formatter: formatJsonValue,
      width: 'wide',
      defaultVisible: false
    },
    correlation_id: {
      key: 'correlation_id',
      label: 'Korrelations-ID',
      description: 'ID zur Verknüpfung zusammenhängender Ereignisse',
      defaultVisible: false
    },
    ip_address: {
      key: 'ip_address',
      label: 'IP-Adresse',
      description: 'IP-Adresse der Anfrage',
      defaultVisible: false
    }
  }
}

// =============================================================================
// TABLE REGISTRY
// =============================================================================

const TABLE_CONFIGS: Record<string, TableConfig> = {
  esp_devices: ESP_DEVICES_CONFIG,
  sensor_configs: SENSOR_CONFIGS_CONFIG,
  actuator_configs: ACTUATOR_CONFIGS_CONFIG,
  audit_logs: AUDIT_LOGS_CONFIG
}

// =============================================================================
// PUBLIC API
// =============================================================================

/**
 * Get human-readable label for a database column
 */
export function getColumnLabel(table: string, column: string): string {
  const tableConfig = TABLE_CONFIGS[table]
  if (!tableConfig) return column

  const columnConfig = tableConfig.columns[column]
  return columnConfig?.label ?? column
}

/**
 * Get column description (tooltip text)
 */
export function getColumnDescription(table: string, column: string): string | undefined {
  const tableConfig = TABLE_CONFIGS[table]
  if (!tableConfig) return undefined

  return tableConfig.columns[column]?.description
}

/**
 * Format a cell value for display
 */
export function formatCellValue(table: string, column: string, value: unknown): string {
  if (value === null || value === undefined) return '-'

  const tableConfig = TABLE_CONFIGS[table]
  if (!tableConfig) return String(value)

  const columnConfig = tableConfig.columns[column]
  if (columnConfig?.formatter) {
    return columnConfig.formatter(value)
  }

  return String(value)
}

/**
 * Get all column configurations for a table
 */
export function getTableColumns(table: string): ColumnConfig[] {
  const tableConfig = TABLE_CONFIGS[table]
  if (!tableConfig) return []

  return Object.values(tableConfig.columns)
}

/**
 * Get visible columns for a table (default visibility)
 */
export function getDefaultVisibleColumns(table: string): string[] {
  const tableConfig = TABLE_CONFIGS[table]
  if (!tableConfig) return []

  return Object.entries(tableConfig.columns)
    .filter(([_, config]) => config.defaultVisible !== false)
    .map(([key]) => key)
}

/**
 * Get human-readable table label
 */
export function getTableLabel(table: string): string {
  return TABLE_CONFIGS[table]?.tableLabel ?? table
}

/**
 * Get table description
 */
export function getTableDescription(table: string): string | undefined {
  return TABLE_CONFIGS[table]?.description
}

/**
 * Get all available table names
 */
export function getAvailableTables(): string[] {
  return Object.keys(TABLE_CONFIGS)
}

/**
 * Check if a table has a configuration
 */
export function hasTableConfig(table: string): boolean {
  return table in TABLE_CONFIGS
}

/**
 * Get column icon name
 */
export function getColumnIcon(table: string, column: string): string | undefined {
  const tableConfig = TABLE_CONFIGS[table]
  if (!tableConfig) return undefined

  return tableConfig.columns[column]?.icon
}

/**
 * Get column width hint
 */
export function getColumnWidth(table: string, column: string): 'narrow' | 'normal' | 'wide' {
  const tableConfig = TABLE_CONFIGS[table]
  if (!tableConfig) return 'normal'

  return tableConfig.columns[column]?.width ?? 'normal'
}

/**
 * Get the full table configuration
 */
export function getTableConfig(table: string): TableConfig | undefined {
  return TABLE_CONFIGS[table]
}

// =============================================================================
// PRIMARY / DETAIL COLUMN HELPERS
// Sprint 3: UX-Verbesserung - Trennung von Haupttabelle und Detail-Modal
// =============================================================================

/**
 * Get columns that should be visible in the main table (defaultVisible: true)
 * These are the "primary" columns that an operator needs to see at a glance.
 *
 * @param tableName - The database table name
 * @returns Array of ColumnConfig for primary/visible columns
 */
export function getPrimaryColumns(tableName: string): ColumnConfig[] {
  const config = TABLE_CONFIGS[tableName]
  if (!config) return []

  return Object.values(config.columns).filter((col) => col.defaultVisible === true)
}

/**
 * Get columns that should only show in detail modal (defaultVisible: false)
 * These are technical/metadata columns not needed in the main table view.
 *
 * @param tableName - The database table name
 * @returns Array of ColumnConfig for detail-only columns
 */
export function getDetailOnlyColumns(tableName: string): ColumnConfig[] {
  const config = TABLE_CONFIGS[tableName]
  if (!config) return []

  return Object.values(config.columns).filter((col) => col.defaultVisible !== true)
}

/**
 * Get all columns ordered: primary first, then detail columns.
 * Useful for RecordDetailModal to show important info first.
 *
 * @param tableName - The database table name
 * @returns Array of all ColumnConfig, ordered with primary columns first
 */
export function getAllColumnsOrdered(tableName: string): ColumnConfig[] {
  return [...getPrimaryColumns(tableName), ...getDetailOnlyColumns(tableName)]
}

/**
 * Get column keys that are primary (for quick filtering)
 *
 * @param tableName - The database table name
 * @returns Array of column key strings
 */
export function getPrimaryColumnKeys(tableName: string): string[] {
  return getPrimaryColumns(tableName).map((col) => col.key)
}

/**
 * Get column keys that are detail-only (for quick filtering)
 *
 * @param tableName - The database table name
 * @returns Array of column key strings
 */
export function getDetailOnlyColumnKeys(tableName: string): string[] {
  return getDetailOnlyColumns(tableName).map((col) => col.key)
}

/**
 * Check if a column is a primary/visible column
 *
 * @param tableName - The database table name
 * @param columnKey - The column key to check
 * @returns true if the column is primary (defaultVisible: true)
 */
export function isPrimaryColumn(tableName: string, columnKey: string): boolean {
  const config = TABLE_CONFIGS[tableName]
  if (!config) return false

  return config.columns[columnKey]?.defaultVisible === true
}
