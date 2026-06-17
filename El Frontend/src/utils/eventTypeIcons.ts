/**
 * Zentrale Event-Type Icon-Mappings
 *
 * Verwendet von:
 * - UnifiedEventList.vue
 * - EventDetailsPanel.vue
 *
 * Single Source of Truth für Event-Type Icons.
 * Verhindert Code-Duplikation und garantiert Konsistenz.
 *
 * @module utils/eventTypeIcons
 */

import {
  Activity,
  AlertCircle,
  AlertOctagon,
  CheckCircle2,
  Cpu,
  Database,
  Info,
  LogIn,
  LogOut,
  Play,
  Power,
  Radio,
  Server,
  Settings,
  ShieldAlert,
  Square,
  Thermometer,
  Wifi,
  WifiOff,
  XCircle,
  Zap,
  type LucideIcon,
} from 'lucide-vue-next'

// ============================================================================
// ICON MAPPINGS
// ============================================================================

/**
 * Mapping von Event-Types zu Lucide Icons.
 *
 * Gemappte Event-Types (32):
 * - Sensor: sensor_data, sensor_health
 * - Actuator: actuator_status, actuator_response, actuator_alert, actuator_command, actuator_command_failed
 * - ESP: esp_health
 * - Config: config_response, config_published, config_failed
 * - Device Lifecycle: device_discovered, device_rediscovered, device_approved,
 *                     device_rejected, device_online, device_offline, lwt_received
 * - Zone/Logic: zone_assignment, logic_execution
 * - System: system_event, service_start, service_stop, emergency_stop
 * - Errors: error_event, mqtt_error, validation_error, database_error
 * - Auth: login_success, login_failed, logout
 * - Notification: notification
 */
const EVENT_TYPE_ICONS: Record<string, LucideIcon> = {
  // Sensor Events
  sensor_data: Thermometer,
  sensor_health: Thermometer,

  // Actuator Events
  actuator_status: Power,
  actuator_response: Power,
  actuator_alert: AlertOctagon,
  actuator_command: Zap,
  actuator_command_failed: XCircle,

  // ESP Health
  esp_health: Cpu,

  // Config Events
  config_response: CheckCircle2,
  config_published: Settings,
  config_failed: AlertCircle,

  // Device Lifecycle
  device_discovered: Radio,
  device_rediscovered: Radio,
  device_approved: CheckCircle2,
  device_rejected: XCircle,
  device_online: Wifi,
  device_offline: WifiOff,
  lwt_received: WifiOff,

  // Zone & Logic
  zone_assignment: Zap,
  logic_execution: Zap,

  // System Events
  system_event: Server,
  service_start: Play,
  service_stop: Square,
  emergency_stop: ShieldAlert,

  // Error Events
  error_event: AlertCircle,
  mqtt_error: AlertCircle,
  validation_error: AlertCircle,
  database_error: Database,

  // Auth Events
  login_success: LogIn,
  login_failed: XCircle,
  logout: LogOut,

  // Notifications
  notification: Info,

  // Contract integrity
  contract_mismatch: AlertOctagon,
  contract_unknown_event: AlertOctagon,
}

/**
 * Default-Icon für unbekannte Event-Types
 */
const DEFAULT_ICON: LucideIcon = Activity

// ============================================================================
// EXPORTED FUNCTIONS
// ============================================================================

/**
 * Gibt das Icon-Component für einen Event-Type zurück.
 *
 * @param eventType - Der Event-Type (z.B. 'sensor_data', 'device_offline')
 * @returns Lucide Icon Component
 *
 * @example
 * ```vue
 * <component :is="getEventIcon('sensor_data')" class="w-4 h-4" />
 * ```
 */
export function getEventIcon(eventType: string): LucideIcon {
  return EVENT_TYPE_ICONS[eventType] ?? DEFAULT_ICON
}

/**
 * Prüft ob ein Event-Type ein bekanntes Icon hat.
 * Nützlich für DEV-Validierung.
 *
 * @param eventType - Der zu prüfende Event-Type
 * @returns true wenn gemappt, false sonst
 */
export function hasEventIcon(eventType: string): boolean {
  return eventType in EVENT_TYPE_ICONS
}

/**
 * Gibt alle bekannten Event-Types mit Icons zurück.
 * Nützlich für DEV-Validierung und Tests.
 *
 * @returns Array aller gemappten Event-Type-Strings
 */
export function getAllMappedEventTypes(): string[] {
  return Object.keys(EVENT_TYPE_ICONS)
}
