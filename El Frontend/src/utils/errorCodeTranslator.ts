/**
 * Error Code UI Helpers (German)
 *
 * WICHTIG: Diese Datei enthält NUR UI-Helper-Funktionen.
 *
 * SERVER-CENTRIC ARCHITECTURE:
 * - Error-Code-Interpretation erfolgt auf dem Server (100+ Mappings)
 * - Server liefert: message, severity, troubleshooting
 * - Frontend zeigt nur an, interpretiert nicht!
 *
 * Diese Datei enthält:
 * - Severity/Category Label-Übersetzungen (für UI)
 * - Icon-Mappings (für UI)
 * - Category-Detection (Fallback für API-Events ohne category)
 *
 * @see El Servador/god_kaiser_server/src/core/esp32_error_mapping.py - 100+ Error Codes
 */

// =============================================================================
// TYPES
// =============================================================================

export type ErrorSeverity = 'info' | 'warning' | 'error' | 'critical'
export type ErrorCategory = 'hardware' | 'service' | 'communication' | 'application' | 'server' | 'unknown'

// =============================================================================
// CATEGORY DETECTION (Fallback for API events without category)
// =============================================================================

/**
 * Detect error category from numeric code.
 *
 * Used as FALLBACK when API/WebSocket doesn't include category.
 * Server should ideally always provide category in the payload.
 *
 * Error Code Ranges:
 * - 1000-1999: Hardware (GPIO, I2C, OneWire, Sensors, Actuators)
 * - 2000-2999: Service (NVS, Config, Storage)
 * - 3000-3999: Communication (WiFi, MQTT, HTTP)
 * - 4000-4999: Application (State, Commands, Watchdog)
 * - 5000-5999: Server
 */
export function detectCategory(code: number | string): ErrorCategory {
  const num = typeof code === 'string' ? parseInt(code, 10) : code

  if (isNaN(num)) return 'unknown'

  if (num >= 1000 && num < 2000) return 'hardware'
  if (num >= 2000 && num < 3000) return 'service'
  if (num >= 3000 && num < 4000) return 'communication'
  if (num >= 4000 && num < 5000) return 'application'
  if (num >= 5000 && num < 6000) return 'server'

  return 'unknown'
}

// =============================================================================
// UI HELPER FUNCTIONS
// =============================================================================

/**
 * Get Lucide icon name for severity level
 */
export function getErrorIcon(severity: ErrorSeverity): string {
  const icons: Record<ErrorSeverity, string> = {
    info: 'Info',
    warning: 'AlertTriangle',
    error: 'AlertCircle',
    critical: 'AlertOctagon'
  }
  return icons[severity] ?? 'AlertCircle'
}

/**
 * Get CSS color class for severity level
 */
export function getErrorColor(severity: ErrorSeverity): string {
  const colors: Record<ErrorSeverity, string> = {
    info: 'text-info',
    warning: 'text-warning',
    error: 'text-error',
    critical: 'text-error' // Uses same color but with animation
  }
  return colors[severity] ?? 'text-muted'
}

/**
 * Get badge variant for severity level
 */
export function getErrorBadgeVariant(severity: ErrorSeverity): string {
  const variants: Record<ErrorSeverity, string> = {
    info: 'info',
    warning: 'warning',
    error: 'danger',
    critical: 'danger'
  }
  return variants[severity] ?? 'gray'
}

/**
 * Check if severity requires pulsing animation (critical only)
 */
export function shouldPulse(severity: ErrorSeverity): boolean {
  return severity === 'critical'
}

// =============================================================================
// LABEL TRANSLATIONS (German)
// =============================================================================

/**
 * Get category label in German
 */
export function getCategoryLabel(category: ErrorCategory): string {
  const labels: Record<ErrorCategory, string> = {
    hardware: 'Hardware',
    service: 'Dienste',
    communication: 'Kommunikation',
    application: 'Anwendung',
    server: 'Server',
    unknown: 'Unbekannt'
  }
  return labels[category] ?? 'Unbekannt'
}

/**
 * Get severity label in German
 */
export function getSeverityLabel(severity: ErrorSeverity): string {
  const labels: Record<ErrorSeverity, string> = {
    info: 'Information',
    warning: 'Warnung',
    error: 'Fehler',
    critical: 'Kritisch'
  }
  return labels[severity] ?? 'Unbekannt'
}
