/**
 * Event Transformer Utilities
 *
 * Transforms raw event data into human-readable German messages
 * and determines event categories for visual styling.
 *
 * KATEGORIE-SYSTEM:
 * - esp-status (Blau):    Heartbeat, Online/Offline, LWT
 * - sensors (Emerald):    Sensor-Messwerte
 * - actuators (Amber):    Aktor-Status, Commands, Alerts
 * - system (Violet):      Config, Auth, Errors, Lifecycle
 */

import type { UnifiedEvent } from '@/types/websocket-events'
import { CONTRACT_OPERATOR_ACTION, extractIntegrationIssueSnapshot } from '@/utils/contractEventMapper'

// ============================================================================
// Types
// ============================================================================

export type EventCategory = 'esp-status' | 'sensors' | 'actuators' | 'system'

export interface TransformedMessage {
  /** Original event type (z.B. "heartbeat") */
  type: string
  /** German title (z.B. "HEARTBEAT") */
  title: string
  /** German label for display (z.B. "Verbindungsstatus") */
  titleDE: string
  /** One-liner for list (z.B. "Online · 48 KB frei · -53 dBm") */
  summary: string
  /** Multi-line for panel (z.B. "Gerät MOCK_9CB4F42A meldet: Online und betriebsbereit") */
  description: string
  /** Lucide icon name */
  icon: string
  /** Category for color coding */
  category: EventCategory
}

export interface OperatorActionGuidance {
  classification: 'integrationsproblem' | 'betriebsproblem'
  priority: 'warning' | 'error' | 'critical'
  cause: string
  nextAction: string
  isTerminal: boolean
}

// ============================================================================
// Constants - Translation Maps
// ============================================================================

const SENSOR_NAMES: Record<string, string> = {
  'temperature': 'Temperatur',
  'humidity': 'Luftfeuchte',
  'ec': 'EC-Wert',
  'ph': 'pH-Wert',
  'water_level': 'Wasserstand',
  'light': 'Lichtstärke',
  'soil_moisture': 'Bodenfeuchte',
  'ds18b20': 'Temperatur',
  'sht31': 'Temp./Luftfeuchte',
  'bme280': 'Umweltsensor',
}

const ACTUATOR_NAMES: Record<string, string> = {
  'pump': 'Pumpe',
  'valve': 'Ventil',
  'relay': 'Relais',
  'pwm': 'PWM-Ausgang',
  'digital': 'Digital-Ausgang',
  'light': 'Beleuchtung',
  'fan': 'Lüfter',
  'heater': 'Heizung',
}

// =============================================================================
// Actuator status display (MQTT/WS Contract: ESP sendet oft 8‑Bit 0–255;
// Legacy-Pfade können 0–1 Duty liefern. Server broadcastet state als "on"|"off".)
// =============================================================================

/**
 * Ein/Aus aus Payload — niemals rohen String wie boolean behandeln
 * (non-empty Strings sind in JS truthy → "off" würde fälschlich EIN sein).
 */
export function normalizeActuatorOnState(raw: unknown): boolean {
  if (typeof raw === 'boolean') return raw
  if (typeof raw === 'string') {
    const s = raw.trim().toLowerCase()
    if (s === 'on') return true
    if (s === 'off') return false
    if (s === 'pwm') return true
    if (s === 'error' || s === 'unknown') return false
  }
  return Boolean(raw)
}

/** 0–1 → Prozent 0–100; >1 bis 255 → 8‑Bit-PWM relativ 255 (nicht ×100!). */
export function actuatorDutyToDisplayPercent(value: number): number {
  if (!Number.isFinite(value)) return 0
  if (value >= 0 && value <= 1) {
    return Math.min(100, Math.max(0, Math.round(value * 100)))
  }
  if (value > 1 && value <= 255) {
    return Math.min(100, Math.max(0, Math.round((value / 255) * 100)))
  }
  return Math.min(100, Math.max(0, Math.round(value)))
}

/** Relais/Ventil/Digital-Ausgang: keine redundanten %-Zusätze wie EIN (0 %) / EIN (100 %). */
function isBinaryStyleActuator(actuatorType: string, hardwareType?: string): boolean {
  const a = actuatorType.toLowerCase()
  const h = (hardwareType || '').toLowerCase()
  if (a === 'relay' || a === 'valve' || a === 'digital') return true
  if (h.includes('digital')) return true
  return false
}

const CONFIG_ERROR_MESSAGES: Record<string, string> = {
  'MISSING_FIELD': 'Erforderliches Feld fehlt',
  'INVALID_VALUE': 'Ungültiger Wert',
  'GPIO_CONFLICT': 'GPIO-Konflikt erkannt',
  'SENSOR_NOT_FOUND': 'Sensor nicht gefunden',
  'ACTUATOR_NOT_FOUND': 'Aktor nicht gefunden',
  'VALIDATION_ERROR': 'Validierungsfehler',
  'TIMEOUT': 'Zeitüberschreitung',
}

// ============================================================================
// Category Determination
// ============================================================================

/**
 * Bestimmt die Kategorie eines Events für farbliche Markierung
 */
export function getEventCategory(event: UnifiedEvent): EventCategory {
  const type = event.event_type

  // ESP-Status Events (Blau)
  const espStatusEvents = [
    'esp_health',
    'device_online',
    'device_offline',
    'lwt_received',
    'device_discovered',
    'device_rediscovered',
    'device_approved',
    'device_rejected',
  ]
  if (espStatusEvents.includes(type)) {
    return 'esp-status'
  }

  // Sensor Events (Emerald)
  const sensorEvents = ['sensor_data', 'sensor_health']
  if (sensorEvents.includes(type)) {
    return 'sensors'
  }

  // Actuator Events (Amber)
  const actuatorEvents = ['actuator_status', 'actuator_response', 'actuator_alert', 'actuator_command', 'actuator_command_failed']
  if (actuatorEvents.includes(type)) {
    return 'actuators'
  }

  // System Events (Violet) - alles andere
  return 'system'
}

// ============================================================================
// Uptime Formatting
// ============================================================================

/**
 * Formatiert Uptime in lesbares Format
 */
export function formatUptime(seconds: number): string {
  if (seconds < 60) return `${seconds} Sek`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} Min`
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    return mins > 0 ? `${hours} Std ${mins} Min` : `${hours} Std`
  }
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  return hours > 0 ? `${days} Tage ${hours} Std` : `${days} Tage`
}

/**
 * Formatiert Speichergröße
 */
export function formatMemory(bytes: number): string {
  const kb = Math.round(bytes / 1024)
  return `${kb} KB`
}

/**
 * Formatiert Sensor-Wert je nach Typ
 */
export function formatSensorValue(value: number, sensorType?: string): string {
  if (sensorType === 'temperature' || sensorType === 'ds18b20') {
    return `${value.toFixed(1)} °C`
  }
  if (sensorType === 'humidity') {
    return `${Math.round(value)}%`
  }
  if (sensorType === 'ph') {
    return value.toFixed(2)
  }
  if (sensorType === 'ec') {
    return `${value.toFixed(0)} µS/cm`
  }
  return value.toFixed(1)
}

// ============================================================================
// Message Transformation
// ============================================================================

/**
 * Transformiert ein Event in ein menschenlesbares Format
 */
export function transformEventMessage(event: UnifiedEvent): TransformedMessage {
  const category = getEventCategory(event)
  const data = (event.data || {}) as Record<string, unknown>

  switch (event.event_type) {
    case 'contract_mismatch':
      return transformContractMismatch(event, data)
    case 'contract_unknown_event':
      return transformContractUnknownEvent(event, data)
    case 'esp_health':
      return transformHeartbeat(event, data)
    case 'sensor_data':
      return transformSensorData(event, data)
    case 'actuator_status':
      return transformActuatorStatus(event, data)
    case 'actuator_response':
      return transformActuatorResponse(event, data)
    case 'actuator_alert':
      return transformActuatorAlert(event, data)
    case 'actuator_command':
      return transformActuatorCommand(event, data)
    case 'actuator_command_failed':
      return transformActuatorCommandFailed(event, data)
    case 'config_published':
      return transformConfigPublished(event, data)
    case 'device_offline':
      return transformDeviceOffline(event, data)
    case 'device_online':
      return transformDeviceOnline(event, data)
    case 'config_response':
      return transformConfigResponse(event, data)
    case 'device_discovered':
      return transformDeviceDiscovered(event, data)
    case 'device_approved':
      return transformDeviceApproved(event, data)
    case 'lwt_received':
      return transformLWT(event, data)
    default:
      return transformDefault(event, category)
  }
}

/**
 * Liefert eine einheitliche Operator-Hilfe fuer terminale Fehler-/Abbruch-Events.
 * Ziel: Ursache + Schwere + naechster Schritt in jedem relevanten UI-Pfad.
 */
export function getOperatorActionGuidance(event: UnifiedEvent): OperatorActionGuidance | null {
  const data = (event.data || {}) as Record<string, unknown>

  if (event.event_type === 'contract_mismatch' || event.event_type === 'contract_unknown_event') {
    const snapshot = extractIntegrationIssueSnapshot(event)
    return {
      classification: 'integrationsproblem',
      priority: 'critical',
      cause: snapshot.reason || `Contract-Event "${snapshot.originalEventType || 'unknown'}" nicht verarbeitbar`,
      nextAction: snapshot.operatorAction || CONTRACT_OPERATOR_ACTION,
      isTerminal: true,
    }
  }

  if (event.event_type === 'actuator_command_failed') {
    const rawError = typeof data.error === 'string' ? data.error : 'Aktor-Befehl serverseitig fehlgeschlagen'
    const errorLower = rawError.toLowerCase()
    const isSafetyRelated = errorLower.includes('safety') || errorLower.includes('not-aus') || errorLower.includes('emergency')
    return {
      classification: 'betriebsproblem',
      priority: 'error',
      cause: rawError,
      nextAction: isSafetyRelated
        ? 'Safety-Freigabe pruefen (Not-Aus, Interlocks), danach Befehl erneut ausloesen'
        : 'Aktorzustand und Verbindungsweg pruefen, dann Befehl gezielt erneut senden',
      isTerminal: true,
    }
  }

  if (event.event_type === 'actuator_response' && data.success === false) {
    const rawError = typeof data.message === 'string'
      ? data.message
      : typeof data.error === 'string'
        ? data.error
        : 'ESP meldet fehlgeschlagene Aktor-Ausfuehrung'
    return {
      classification: 'betriebsproblem',
      priority: 'error',
      cause: rawError,
      nextAction: 'Hardwarezustand/GPIO pruefen und nur bei klarer Ursache erneut ausfuehren',
      isTerminal: true,
    }
  }

  if (event.event_type === 'config_failed') {
    return {
      classification: 'betriebsproblem',
      priority: 'error',
      cause: typeof data.error === 'string' ? data.error : 'Config-Publish fehlgeschlagen',
      nextAction: 'Config-Validitaet und Zielgeraet pruefen, danach Konfiguration erneut publizieren',
      isTerminal: true,
    }
  }

  if (event.event_type === 'config_response') {
    const status = String(data.status || '').toLowerCase()
    if (status === 'failed' || status === 'error') {
      return {
        classification: 'betriebsproblem',
        priority: 'error',
        cause: typeof data.message === 'string' ? data.message : 'ESP hat Konfiguration abgelehnt',
        nextAction: 'Konfigurationsparameter korrigieren und die betroffene Config erneut anwenden',
        isTerminal: true,
      }
    }
  }

  if (event.event_type === 'sequence_error') {
    return {
      classification: 'betriebsproblem',
      priority: 'error',
      cause: typeof data.message === 'string' ? data.message : 'Sequenz wurde mit Fehler beendet',
      nextAction: 'Fehler im Sequenzschritt pruefen und Regel/Abhaengigkeiten vor erneutem Start verifizieren',
      isTerminal: true,
    }
  }

  if (event.event_type === 'sequence_cancelled') {
    return {
      classification: 'betriebsproblem',
      priority: 'warning',
      cause: typeof data.reason === 'string' ? data.reason : 'Sequenz wurde abgebrochen',
      nextAction: 'Abbruchgrund bestaetigen und Sequenz nur bei weiterhin gueltiger Lage neu starten',
      isTerminal: true,
    }
  }

  return null
}

function transformHeartbeat(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const heapFree = typeof data.heap_free === 'number' ? data.heap_free : 0
  const wifiRssi = typeof data.wifi_rssi === 'number' ? data.wifi_rssi : 0
  const uptime = typeof data.uptime === 'number' ? data.uptime : 0

  const heapKB = Math.round(heapFree / 1024)
  const uptimeStr = formatUptime(uptime)

  return {
    type: 'esp_health',
    title: 'HEARTBEAT',
    titleDE: 'Verbindungsstatus',
    summary: `Online · ${heapKB} KB frei · ${wifiRssi} dBm · ${uptimeStr}`,
    description: `Gerät ${event.esp_id || 'Unbekannt'} meldet: Online und betriebsbereit`,
    icon: 'Radio',
    category: 'esp-status',
  }
}

function transformSensorData(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const sensorType = (data.sensor_type || event.device_type || 'sensor') as string
  // Server sends processed_value and raw_value — no plain "value" field
  const value = typeof data.processed_value === 'number' ? data.processed_value
    : typeof data.raw_value === 'number' ? data.raw_value
    : typeof data.value === 'number' ? data.value
    : null
  const unit = (data.unit || '') as string
  const gpio = event.gpio ?? data.gpio

  const sensorName = SENSOR_NAMES[sensorType.toLowerCase()] || sensorType
  const formattedValue = value !== null ? formatSensorValue(value, sensorType.toLowerCase()) : '-'

  return {
    type: 'sensor_data',
    title: 'SENSORDATEN',
    titleDE: sensorName,
    summary: `${sensorName}: ${formattedValue}${value !== null && unit ? ` ${unit}` : ''} · GPIO ${gpio}`,
    description: `Neuer Messwert von ${sensorName}`,
    icon: 'Thermometer',
    category: 'sensors',
  }
}

function transformActuatorStatus(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const actuatorType = (data.actuator_type || event.device_type || 'actuator') as string
  const hwType = typeof data.hardware_type === 'string' ? data.hardware_type : undefined
  const state = normalizeActuatorOnState(data.state)
  const value = typeof data.value === 'number' ? data.value : undefined
  const gpio = event.gpio ?? data.gpio
  const commandSource = typeof data.command_source === 'string' ? data.command_source.trim() : ''

  const actuatorName = ACTUATOR_NAMES[actuatorType.toLowerCase()] || actuatorType
  const stateStr = state ? 'EIN' : 'AUS'
  const binary = isBinaryStyleActuator(actuatorType, hwType)
  let valueStr = ''
  if (value !== undefined && !binary) {
    const pct = actuatorDutyToDisplayPercent(value)
    valueStr = ` (${pct}%)`
  }

  return {
    type: 'actuator_status',
    title: 'AKTOR-STATUS',
    titleDE: actuatorName,
    summary: `${actuatorName}: ${stateStr}${valueStr} · GPIO ${gpio}${commandSource ? ` · via ${commandSource}` : ''}`,
    description: `${actuatorName} ist jetzt ${stateStr.toLowerCase()}${commandSource ? ` (Quelle: ${commandSource})` : ''}`,
    icon: 'Power',
    category: 'actuators',
  }
}

function transformActuatorResponse(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const success = data.success as boolean
  const command = (data.command || 'Befehl') as string
  const gpio = event.gpio ?? data.gpio
  const issuedBy = typeof data.issued_by === 'string' ? data.issued_by.trim() : ''

  return {
    type: 'actuator_response',
    title: 'AKTOR-ANTWORT',
    titleDE: success ? 'Befehl erfolgreich' : 'Befehl fehlgeschlagen',
    summary: success
      ? `${command} · GPIO ${gpio} · Erfolgreich${issuedBy ? ` · via ${issuedBy}` : ''}`
      : `${command} · GPIO ${gpio} · Fehlgeschlagen${issuedBy ? ` · via ${issuedBy}` : ''}`,
    description: success
      ? `Aktor-Befehl "${command}" wurde erfolgreich ausgeführt${issuedBy ? ` (Quelle: ${issuedBy})` : ''}`
      : `Aktor-Befehl "${command}" konnte nicht ausgeführt werden${issuedBy ? ` (Quelle: ${issuedBy})` : ''}`,
    icon: success ? 'CheckCircle' : 'XCircle',
    category: 'actuators',
  }
}

function transformActuatorAlert(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const alertType = (data.alert_type || 'unknown') as string
  const gpio = event.gpio ?? data.gpio

  const alertMessages: Record<string, string> = {
    'emergency_stop': 'Not-Aus aktiviert',
    'timeout': 'Zeitüberschreitung',
    'runtime_exceeded': 'Laufzeit überschritten',
    'safety_triggered': 'Sicherheitsstopp',
  }

  const alertMessage = alertMessages[alertType] || alertType

  return {
    type: 'actuator_alert',
    title: 'AKTOR-ALARM',
    titleDE: 'Sicherheitswarnung',
    summary: `${alertMessage} · GPIO ${gpio}`,
    description: `Aktor an GPIO ${gpio}: ${alertMessage}`,
    icon: 'AlertTriangle',
    category: 'actuators',
  }
}

function transformDeviceOffline(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const reason = (data.reason || 'timeout') as string
  const espId = event.esp_id || 'Unbekannt'

  const reasonDE = reason === 'lwt'
    ? 'Verbindung unerwartet getrennt'
    : 'Kein Heartbeat empfangen'

  return {
    type: 'device_offline',
    title: 'GERÄT OFFLINE',
    titleDE: 'Verbindung verloren',
    summary: `Offline · ${reasonDE}`,
    description: `Gerät ${espId} ist nicht mehr erreichbar`,
    icon: 'WifiOff',
    category: 'esp-status',
  }
}

function transformDeviceOnline(event: UnifiedEvent, _data: Record<string, unknown>): TransformedMessage {
  const espId = event.esp_id || 'Unbekannt'

  return {
    type: 'device_online',
    title: 'GERÄT ONLINE',
    titleDE: 'Verbindung hergestellt',
    summary: `${espId} wieder verbunden`,
    description: `Gerät ${espId} ist wieder online`,
    icon: 'Wifi',
    category: 'esp-status',
  }
}

function transformConfigResponse(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const status = (data.status || 'unknown') as string
  const configType = (data.type || data.config_type || 'Config') as string
  const errorCode = data.error_code as string | undefined
  const espId = event.esp_id || 'Unbekannt'

  if (status === 'error' || status === 'failed') {
    const errorDE = errorCode
      ? (CONFIG_ERROR_MESSAGES[errorCode] || errorCode)
      : (data.message || 'Unbekannter Fehler') as string

    return {
      type: 'config_response',
      title: 'KONFIGURATION',
      titleDE: 'Konfiguration fehlgeschlagen',
      summary: `Fehlgeschlagen · ${errorDE}`,
      description: `${configType}-Konfiguration für ${espId} konnte nicht angewendet werden`,
      icon: 'AlertCircle',
      category: 'system',
    }
  }

  return {
    type: 'config_response',
    title: 'KONFIGURATION',
    titleDE: 'Konfiguration empfangen',
    summary: `Erfolgreich · ${configType} konfiguriert`,
    description: `${configType}-Konfiguration für ${espId} wurde erfolgreich angewendet`,
    icon: 'CheckCircle',
    category: 'system',
  }
}

function transformDeviceDiscovered(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const espId = event.esp_id || data.device_id || 'Unbekannt'
  const zoneName = (data.zone_name || data.zone_id) as string | undefined

  return {
    type: 'device_discovered',
    title: 'NEUES GERÄT',
    titleDE: 'Gerät entdeckt',
    summary: zoneName
      ? `${espId} · Zone: ${zoneName}`
      : `${espId} · Wartet auf Freigabe`,
    description: `Neues Gerät ${espId} wurde erkannt und wartet auf Admin-Freigabe`,
    icon: 'Search',
    category: 'esp-status',
  }
}

function transformDeviceApproved(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const espId = event.esp_id || data.device_id || 'Unbekannt'
  const approvedBy = (data.approved_by || 'Admin') as string

  return {
    type: 'device_approved',
    title: 'GENEHMIGT',
    titleDE: 'Gerät freigegeben',
    summary: `${espId} · von ${approvedBy}`,
    description: `Gerät ${espId} wurde von ${approvedBy} genehmigt`,
    icon: 'CheckCircle',
    category: 'esp-status',
  }
}

function transformLWT(event: UnifiedEvent, _data: Record<string, unknown>): TransformedMessage {
  const espId = event.esp_id || 'Unbekannt'

  return {
    type: 'lwt_received',
    title: 'VERBINDUNGSABBRUCH',
    titleDE: 'Unerwartete Trennung',
    summary: `${espId} · Verbindung unerwartet getrennt`,
    description: `Gerät ${espId} hat die Verbindung unerwartet verloren (Last Will Testament)`,
    icon: 'Unplug',
    category: 'esp-status',
  }
}

function transformActuatorCommand(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const command = (data.command || 'Befehl') as string
  const gpio = event.gpio ?? data.gpio
  const value = data.value as number | undefined
  const issuedBy = (data.issued_by || 'API') as string

  let valueStr = ''
  if (value !== undefined && value !== 1.0 && value !== 0.0) {
    valueStr = ` (${actuatorDutyToDisplayPercent(value)}%)`
  }

  return {
    type: 'actuator_command',
    title: 'AKTOR-BEFEHL',
    titleDE: 'Befehl ausstehend',
    summary: `Pending · ${command}${valueStr} · GPIO ${gpio} · von ${issuedBy}`,
    description: `Aktor-Befehl "${command}" ist ausstehend (nicht terminal). Quelle: ${issuedBy}`,
    icon: 'Zap',
    category: 'actuators',
  }
}

function transformActuatorCommandFailed(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const command = (data.command || 'Befehl') as string
  const gpio = event.gpio ?? data.gpio
  const error = (data.error || 'Unbekannter Fehler') as string
  const hasContractIssue = typeof data.contract_issue === 'string' || error === 'Unbekannter Fehler'

  return {
    type: 'actuator_command_failed',
    title: 'AKTOR-BEFEHL FEHLGESCHLAGEN',
    titleDE: hasContractIssue ? 'Integrationsstoerung' : 'Befehl fehlgeschlagen',
    summary: hasContractIssue
      ? `${command} · GPIO ${gpio} · ${CONTRACT_OPERATOR_ACTION}`
      : `${command} · GPIO ${gpio} · ${error}`,
    description: hasContractIssue
      ? `Aktor-Befehl "${command}" an GPIO ${gpio} konnte nicht contract-scharf ausgewertet werden. ${CONTRACT_OPERATOR_ACTION}.`
      : `Aktor-Befehl "${command}" an GPIO ${gpio} fehlgeschlagen: ${error}`,
    icon: 'XCircle',
    category: 'actuators',
  }
}

function transformContractMismatch(_event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const snapshot = extractIntegrationIssueSnapshot({
    event_type: 'contract_mismatch',
    data,
  })
  const rawType = snapshot.originalEventType || 'unknown'
  const reason = snapshot.reason || 'Schema-Mismatch'
  const action = snapshot.operatorAction || CONTRACT_OPERATOR_ACTION
  const isConfigTerminalDrift = rawType === 'config_response' || rawType === 'config_failed'
  return {
    type: 'contract_mismatch',
    title: 'CONTRACT-MISMATCH',
    titleDE: 'Integrationsstoerung',
    summary: isConfigTerminalDrift
      ? `Config-Terminalevent nicht finalisierbar: ${reason} · ${action}`
      : `${rawType}: ${reason} · ${action}`,
    description: isConfigTerminalDrift
      ? `Config-Intent bleibt pending: terminales Event (${rawType}) verletzt den Contract (${reason}). ${action}.`
      : `Event konnte nicht contract-scharf verarbeitet werden (${rawType}). ${action}.`,
    icon: 'AlertOctagon',
    category: 'system',
  }
}

function transformContractUnknownEvent(_event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const snapshot = extractIntegrationIssueSnapshot({
    event_type: 'contract_unknown_event',
    data,
  })
  const rawType = snapshot.originalEventType || 'unknown'
  const action = snapshot.operatorAction || CONTRACT_OPERATOR_ACTION
  return {
    type: 'contract_unknown_event',
    title: 'UNKNOWN CONTRACT EVENT',
    titleDE: 'Integrationsstoerung',
    summary: `${rawType} nicht im bekannten Contract · ${action}`,
    description: `Unbekannter Event-Typ "${rawType}" empfangen. ${action}.`,
    icon: 'AlertOctagon',
    category: 'system',
  }
}

function transformConfigPublished(event: UnifiedEvent, data: Record<string, unknown>): TransformedMessage {
  const espId = event.esp_id || (data.esp_id as string) || 'Unbekannt'
  const configKeys = (data.config_keys || []) as string[]

  return {
    type: 'config_published',
    title: 'KONFIGURATION GESENDET',
    titleDE: 'Config gesendet',
    summary: `Config an ${espId} gesendet`,
    description: `Konfiguration an ${espId} gesendet. Keys: ${configKeys.join(', ') || 'keine'}`,
    icon: 'Settings',
    category: 'system',
  }
}

function transformDefault(event: UnifiedEvent, category: EventCategory): TransformedMessage {
  return {
    type: event.event_type,
    title: event.event_type.toUpperCase().replace(/_/g, ' '),
    titleDE: event.event_type,
    summary: event.message || 'Keine Details verfügbar',
    description: event.message || 'System-Ereignis',
    icon: 'Info',
    category,
  }
}
