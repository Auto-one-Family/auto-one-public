/**
 * Canonical labels for event types used in monitor views.
 * Single Source of Truth for short, operator-facing event labels.
 */
export const EVENT_TYPE_LABELS: Record<string, string> = {
  // Sensor & Actuator
  sensor_data: 'Sensordaten',
  sensor_health: 'Sensor-Status',
  actuator_status: 'Aktor-Status',
  actuator_response: 'Aktor-Antwort',
  actuator_alert: 'Aktor-Alarm',
  actuator_command: 'Aktor-Befehl',
  actuator_command_failed: 'Aktor-Befehl fehlgeschlagen',
  esp_health: 'Heartbeat',

  // Configuration
  config_response: 'Konfiguration empfangen',
  config_published: 'Konfiguration gesendet',
  config_failed: 'Konfigurationsfehler',

  // Device lifecycle
  device_discovered: 'Neues Geraet',
  device_rediscovered: 'Geraet wieder da',
  device_approved: 'Genehmigt',
  device_rejected: 'Abgelehnt',
  device_online: 'Geraet online',
  device_offline: 'Geraet offline',
  lwt_received: 'Verbindungsabbruch',

  // System
  zone_assignment: 'Zonen-Zuweisung',
  subzone_assignment: 'Subzonen-Zuweisung',
  device_scope_changed: 'Geraete-Scope',
  device_context_changed: 'Geraete-Kontext',
  sensor_config_deleted: 'Sensor-Konfiguration geloescht',
  actuator_config_deleted: 'Aktor-Konfiguration geloescht',
  notification_new: 'Benachrichtigung (neu)',
  notification_updated: 'Benachrichtigung (aktualisiert)',
  notification_unread_count: 'Ungelesene Benachrichtigungen',
  intent_outcome: 'Vorgang — Ergebnis',
  intent_outcome_lifecycle: 'Vorgang — Zwischenstand',
  plugin_execution_started: 'Plugin gestartet',
  plugin_execution_completed: 'Plugin beendet',
  logic_execution: 'Regel ausgefuehrt',
  system_event: 'System',
  service_start: 'Server-Start',
  service_stop: 'Server-Stop',
  emergency_stop: 'Notfall-Stopp',

  // Errors
  error_event: 'Fehler',
  mqtt_error: 'MQTT-Fehler',
  validation_error: 'Validierungsfehler',
  database_error: 'Datenbankfehler',

  // Auth
  login_success: 'Anmeldung erfolgreich',
  login_failed: 'Anmeldung fehlgeschlagen',
  logout: 'Abmeldung',

  // Notifications
  notification: 'Benachrichtigung',

  // WebSocket/internal signals
  events_restored: 'Wiederhergestellt',
  contract_mismatch: 'Contract-Mismatch',
  contract_unknown_event: 'Unbekannter Contract-Event',
}

export function getEventTypeLabel(eventType: string): string {
  return EVENT_TYPE_LABELS[eventType] || eventType
}

/**
 * Labels for system_event sub-types.
 *
 * The server wraps system notices in a top-level `system_event` envelope and
 * carries the concrete discriminator in the nested payload. The live broadcast
 * uses `data.event` (e.g. `{ event: 'mqtt_disconnected' }`); the documented
 * contract field is `data.event_type`. SSOT for operator-facing sub-event
 * labels — keep in sync with the server broadcasts (maintenance health check,
 * backup restore pipeline).
 */
export const SYSTEM_EVENT_LABELS: Record<string, string> = {
  mqtt_disconnected: 'MQTT-Verbindung getrennt',
  database_restore_status: 'Datenbank-Wiederherstellung',
}

/**
 * Wandelt einen rohen Sub-Event-Key in eine lesbare Form um
 * (z.B. "some_unknown_event" → "Some Unknown Event").
 */
function humanizeSystemEvent(key: string): string {
  return key
    .replace(/[_.]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim()
}

/**
 * Liefert ein menschenlesbares Label fuer einen system_event-Subtyp.
 * Fallback-Kette: bekanntes Label → humanisierter Key → generisches "System".
 */
export function getSystemEventLabel(subEvent: string | null | undefined): string {
  const key = (subEvent ?? '').trim()
  if (!key) return EVENT_TYPE_LABELS.system_event
  return SYSTEM_EVENT_LABELS[key] ?? humanizeSystemEvent(key)
}
