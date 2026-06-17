/**
 * Human-Readable Labels (German)
 * 
 * Central file for all UI text translations and label mappings.
 * Ensures consistent German translations throughout the application.
 */

// =============================================================================
// QUALITY LABELS
// =============================================================================

export const QUALITY_LABELS: Record<string, string> = {
  'excellent': 'Exzellent',
  'good': 'Gut',
  'fair': 'Mittel',
  'degraded': 'Eingeschränkt',
  'poor': 'Schlecht',
  'bad': 'Kritisch',
  'stale': 'Veraltet',
  'error': 'Fehler',
  'unknown': 'Unbekannt',
}

/**
 * Get quality label with color class
 */
export function getQualityInfo(quality: string): { label: string; colorClass: string } {
  const info: Record<string, { label: string; colorClass: string }> = {
    'excellent': { label: 'Exzellent', colorClass: 'text-success' },
    'good': { label: 'Gut', colorClass: 'text-success' },
    'fair': { label: 'Mittel', colorClass: 'text-warning' },
    'degraded': { label: 'Eingeschränkt', colorClass: 'text-warning' },
    'poor': { label: 'Schlecht', colorClass: 'text-error' },
    'bad': { label: 'Kritisch', colorClass: 'text-error' },
    'stale': { label: 'Veraltet', colorClass: 'text-muted' },
    'error': { label: 'Fehler', colorClass: 'text-error' },
    'unknown': { label: 'Unbekannt', colorClass: 'text-muted' },
  }
  return info[quality] ?? { label: quality, colorClass: 'text-muted' }
}

// =============================================================================
// SYSTEM STATE LABELS
// =============================================================================

export const STATE_LABELS: Record<string, string> = {
  'OPERATIONAL': 'Betriebsbereit',
  'SAFE_MODE': 'Sicherheitsmodus',
  'ERROR': 'Fehler',
  'INITIALIZING': 'Startet...',
  'OFFLINE': 'Offline',
  'CONNECTED': 'Verbunden',
  'DISCONNECTED': 'Getrennt',
  'UNKNOWN': 'Unbekannt',
}

/**
 * Get system state label with badge variant
 */
export function getStateInfo(state: string): { label: string; variant: string } {
  const info: Record<string, { label: string; variant: string }> = {
    'OPERATIONAL': { label: 'Betriebsbereit', variant: 'success' },
    'SAFE_MODE': { label: 'Sicherheitsmodus', variant: 'warning' },
    'ERROR': { label: 'Fehler', variant: 'danger' },
    'INITIALIZING': { label: 'Startet...', variant: 'info' },
    'OFFLINE': { label: 'Offline', variant: 'gray' },
    'CONNECTED': { label: 'Verbunden', variant: 'success' },
    'DISCONNECTED': { label: 'Getrennt', variant: 'gray' },
  }
  return info[state] ?? { label: state, variant: 'gray' }
}

// =============================================================================
// ACTUATOR TYPE LABELS
// =============================================================================

export const ACTUATOR_TYPE_LABELS: Record<string, string> = {
  'relay': 'Relais',
  'pwm': 'PWM-Ausgang',
  'valve': 'Ventil',
  'pump': 'Pumpe',
  'fan': 'Lüfter (PWM)',
  'heater': 'Heizung',
  'light': 'Beleuchtung',
  'motor': 'Motor',
  // Server-normalized types (actuator_configs stores interface type, not logical type)
  'digital': 'Relais',
  'servo': 'Servo',
}

/**
 * Get actuator type label with icon name.
 *
 * Prefers hardware_type (original ESP32 logical type like pump/valve/relay)
 * over the server-normalized actuator_type (digital/pwm/servo) for icon lookup.
 * This allows differentiated icons even though actuator_configs stores 'digital'
 * for all relay/pump/valve actuators.
 */
export function getActuatorTypeInfo(type: string, hardwareType?: string | null): { label: string; icon: string } {
  const info: Record<string, { label: string; icon: string }> = {
    'relay': { label: 'Relais', icon: 'ToggleRight' },
    'pwm': { label: 'PWM-Ausgang', icon: 'Activity' },
    'valve': { label: 'Ventil', icon: 'GitBranch' },
    'pump': { label: 'Pumpe', icon: 'Waves' },
    'fan': { label: 'Lüfter (PWM)', icon: 'Fan' },
    'heater': { label: 'Heizung', icon: 'Flame' },
    'light': { label: 'Beleuchtung', icon: 'Lightbulb' },
    'motor': { label: 'Motor', icon: 'Cog' },
    // Server-normalized types: actuator_configs stores interface type (digital/pwm/servo)
    // while ESP32 uses logical type (relay/pump/valve). Map server types as default fallback.
    'digital': { label: 'Digital', icon: 'ToggleRight' },
    'servo': { label: 'Servo', icon: 'Cog' },
  }
  // hardware_type carries the ESP32 logical type (relay/pump/valve) — use it first
  const lookupType = hardwareType ?? type
  return info[lookupType] ?? info[type] ?? { label: type, icon: 'Power' }
}

// =============================================================================
// ACTUATOR STATE LABELS
// =============================================================================

export const ACTUATOR_STATE_LABELS: Record<string, string> = {
  'on': 'Ein',
  'off': 'Aus',
  'true': 'Ein',
  'false': 'Aus',
}

// =============================================================================
// CONNECTION STATUS LABELS
// =============================================================================

export const CONNECTION_LABELS: Record<string, string> = {
  'online': 'Online',
  'offline': 'Offline',
  'connecting': 'Verbinde...',
  'reconnecting': 'Verbinde erneut...',
  'error': 'Verbindungsfehler',
}

// =============================================================================
// NOTIFICATION SOURCE LABELS (Alert-Basis 3 — Filter nach source)
// =============================================================================

/** Backend notification.source → lesbares Label für Filter-Chips und Badges */
export const NOTIFICATION_SOURCE_LABELS: Record<string, string> = {
  sensor_threshold: 'Sensor',
  grafana: 'Infrastruktur',
  mqtt_handler: 'Aktor',
  logic_engine: 'Regel',
  ai_anomaly_service: 'KI-Anomalie',
  freshness_reminder: 'Frische-Hinweis',
  calibration_reminder: 'Kalibrier-Hinweis',
  manual: 'System',
  system: 'System',
  device_event: 'System',
  autoops: 'System',
}

/**
 * Lesbares Label für notification.source.
 * Fallback: unbekannte Werte werden unverändert zurückgegeben.
 */
export function getNotificationSourceLabel(source: string | null | undefined): string {
  if (!source) return ''
  return NOTIFICATION_SOURCE_LABELS[source] ?? source
}

export const NOTIFICATION_SEVERITY_LABELS: Record<string, string> = {
  critical: 'Kritisch',
  warning: 'Warnung',
  info: 'Info',
}

export function getNotificationSeverityLabel(severity: string | null | undefined): string {
  if (!severity) return ''
  return NOTIFICATION_SEVERITY_LABELS[severity] ?? severity
}

export const NOTIFICATION_CATEGORY_LABELS: Record<string, string> = {
  connectivity: 'Konnektivität',
  data_quality: 'Datenqualität',
  infrastructure: 'Infrastruktur',
  lifecycle: 'Lifecycle',
  maintenance: 'Wartung',
  security: 'Sicherheit',
  system: 'System',
  ai_anomaly: 'KI-Anomalie',
}

export function getNotificationCategoryLabel(category: string | null | undefined): string {
  if (!category) return ''
  return NOTIFICATION_CATEGORY_LABELS[category] ?? category
}

// =============================================================================
// EMAIL STATUS LABELS (Phase C V1.2 — Email-Retry)
// =============================================================================

/** Email-Versandstatus aus Email-Log und Notification-Metadata */
export const EMAIL_STATUS_LABELS: Record<string, string> = {
  'sent': 'Zugestellt',
  'failed': 'Fehlgeschlagen',
  'pending': 'Ausstehend',
  'permanently_failed': 'Dauerhaft fehlgeschlagen',
}

/**
 * Lesbares Label für Email-Status (sent, failed, pending, permanently_failed).
 * Fallback: unbekannte Werte werden unverändert zurückgegeben.
 */
export function getEmailStatusLabel(status: string): string {
  return EMAIL_STATUS_LABELS[status] ?? status
}

// =============================================================================
// DEVICE TYPE LABELS
// =============================================================================

export const DEVICE_TYPE_LABELS: Record<string, string> = {
  'mock': 'Simuliert',
  'real': 'Echtes Gerät',
  'MOCK_ESP32': 'Mock ESP32',
  'ESP32': 'ESP32',
  'ESP32_S2': 'ESP32-S2',
  'ESP32_S3': 'ESP32-S3',
  'ESP32_C3': 'ESP32-C3',
}

// =============================================================================
// GPIO DESCRIPTIONS
// =============================================================================

const GPIO_DESCRIPTIONS: Record<number, string> = {
  0: 'GPIO0 - Boot-Pin, mit Vorsicht verwenden',
  1: 'GPIO1 - TX0 (UART)',
  2: 'GPIO2 - Onboard LED bei vielen Boards',
  3: 'GPIO3 - RX0 (UART)',
  4: 'GPIO4 - Standard I2C SDA',
  5: 'GPIO5 - Standard I2C SCL',
  12: 'GPIO12 - Boot-Strapping Pin',
  13: 'GPIO13 - Sicher für allgemeine Verwendung',
  14: 'GPIO14 - Sicher für allgemeine Verwendung',
  15: 'GPIO15 - Boot-Strapping Pin',
  16: 'GPIO16 - Sicher für allgemeine Verwendung',
  17: 'GPIO17 - Sicher für allgemeine Verwendung',
  18: 'GPIO18 - Sicher für allgemeine Verwendung',
  19: 'GPIO19 - Sicher für allgemeine Verwendung',
  21: 'GPIO21 - Standard I2C SDA (alternativ)',
  22: 'GPIO22 - Standard I2C SCL (alternativ)',
  23: 'GPIO23 - Sicher für allgemeine Verwendung',
  25: 'GPIO25 - DAC1 verfügbar',
  26: 'GPIO26 - DAC2 verfügbar',
  27: 'GPIO27 - Sicher für allgemeine Verwendung',
  32: 'GPIO32 - ADC1 verfügbar',
  33: 'GPIO33 - ADC1 verfügbar',
  34: 'GPIO34 - Nur Eingang (kein Pull-Up)',
  35: 'GPIO35 - Nur Eingang (kein Pull-Up)',
  36: 'GPIO36 - Nur Eingang (VP)',
  39: 'GPIO39 - Nur Eingang (VN)',
}

/**
 * Get GPIO description/tooltip
 */
export function getGpioDescription(gpio: number): string {
  return GPIO_DESCRIPTIONS[gpio] ?? `GPIO ${gpio}`
}

/**
 * Check if GPIO is safe for general use
 */
export function isGpioSafe(gpio: number): boolean {
  const unsafeGpios = [0, 1, 3, 6, 7, 8, 9, 10, 11, 12, 15]
  return !unsafeGpios.includes(gpio)
}

// =============================================================================
// UNIT EXPLANATIONS
// =============================================================================

export const UNIT_EXPLANATIONS: Record<string, string> = {
  '°C': 'Grad Celsius - Temperatureinheit',
  'pH': 'pH-Wert - Maß für Säure/Base (0-14)',
  '% RH': 'Relative Luftfeuchtigkeit in Prozent',
  'µS/cm': 'Mikrosiemens pro Zentimeter - Elektrische Leitfähigkeit',
  'hPa': 'Hektopascal - Luftdruckeinheit',
  'ppm': 'Parts per Million - Konzentration',
  'lux': 'Lux - Beleuchtungsstärke',
  'L/min': 'Liter pro Minute - Durchflussrate',
  'raw': 'Rohwert ohne Einheit',
}

/**
 * Get explanation for a unit
 */
export function getUnitExplanation(unit: string): string {
  return UNIT_EXPLANATIONS[unit] ?? unit
}

// =============================================================================
// GENERIC HELPER FUNCTIONS
// =============================================================================

/**
 * Get a label from any label map
 * @param value - The key to look up
 * @param labelMap - The label map to search
 * @returns The translated label or the original value
 */
export function getLabel(
  value: string, 
  labelMap: Record<string, string>
): string {
  return labelMap[value] ?? value
}

/**
 * Get quality label
 */
export function getQualityLabel(quality: string): string {
  return QUALITY_LABELS[quality] ?? quality
}

/**
 * Get state label
 */
export function getStateLabel(state: string): string {
  return STATE_LABELS[state] ?? state
}

/**
 * Get actuator type label
 */
export function getActuatorTypeLabel(type: string): string {
  return ACTUATOR_TYPE_LABELS[type] ?? type
}

/**
 * Get connection label
 */
export function getConnectionLabel(status: string): string {
  return CONNECTION_LABELS[status] ?? status
}

/**
 * Get device type label
 */
export function getDeviceTypeLabel(type: string): string {
  return DEVICE_TYPE_LABELS[type] ?? type
}

// =============================================================================
// SETTINGS LABELS
// =============================================================================

/**
 * Settings-Texte als zentrale Keys (i18n-faehige Struktur ohne vue-i18n Runtime).
 * Kann spaeter 1:1 auf echte i18n-Keys gemappt werden.
 */
export const SETTINGS_LABELS = {
  logout: 'Abmelden',
  logoutAllDevices: 'Auf allen Geraeten abmelden',
  sheetsExportTitle: 'Sheets-Export',
  sheetsExportSpreadsheetId: 'Spreadsheet-ID',
  sheetsExportOpenLink: 'Spreadsheet in Google Sheets oeffnen',
  sheetsExportHint:
    'Server-seitiger Export schreibt Sensor- und Aktor-Daten in dieses Spreadsheet.',
} as const

// =============================================================================
// ACTION LABELS
// =============================================================================

export const ACTION_LABELS: Record<string, string> = {
  'create': 'Erstellen',
  'edit': 'Bearbeiten',
  'delete': 'Löschen',
  'save': 'Speichern',
  'cancel': 'Abbrechen',
  'refresh': 'Aktualisieren',
  'add': 'Hinzufügen',
  'remove': 'Entfernen',
  'view': 'Anzeigen',
  'details': 'Details',
  'back': 'Zurück',
  'next': 'Weiter',
  'submit': 'Absenden',
  'confirm': 'Bestätigen',
  'retry': 'Erneut versuchen',
}

// =============================================================================
// MESSAGE LABELS
// =============================================================================

export const MESSAGE_LABELS: Record<string, string> = {
  'loading': 'Lädt...',
  'saving': 'Speichert...',
  'deleting': 'Löscht...',
  'error': 'Ein Fehler ist aufgetreten',
  'success': 'Erfolgreich',
  'no_data': 'Keine Daten vorhanden',
  'no_results': 'Keine Ergebnisse gefunden',
  'confirm_delete': 'Wirklich löschen?',
}





















