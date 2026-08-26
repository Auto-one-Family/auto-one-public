/**
 * Formatting Utilities (German)
 *
 * Provides consistent formatting for dates, times, numbers, and other values
 * throughout the application. All formats are German-localized.
 */

import type { SensorOperatingMode } from '@/types'

// =============================================================================
// DATE & TIME FORMATTING
// =============================================================================

/**
 * Normalize a date string to ensure proper timezone handling.
 * Server sends timestamps without 'Z' suffix, but they are in UTC.
 * This function appends 'Z' to treat them as UTC.
 */
function normalizeTimestamp(date: string | Date): Date {
  if (date instanceof Date) {
    return date
  }
  // If no timezone info, assume UTC
  if (!date.endsWith('Z') && !date.includes('+') && !date.includes('-', 10)) {
    return new Date(date + 'Z')
  }
  return new Date(date)
}

/**
 * Format a date as relative time (German)
 * @example "Gerade eben", "vor 5 Minuten", "vor 2 Stunden"
 */
export function formatRelativeTime(date: string | Date | null | undefined): string {
  if (!date) return 'Nie'

  const now = new Date()
  const then = normalizeTimestamp(date)
  const diffMs = now.getTime() - then.getTime()
  const diffSec = Math.floor(diffMs / 1000)
  
  // Future dates
  if (diffSec < 0) {
    return formatDateTime(date)
  }
  
  // Past dates
  if (diffSec < 60) return 'vor < 1 Min.'
  
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin === 1) return 'vor 1 Minute'
  if (diffMin < 60) return `vor ${diffMin} Minuten`
  
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour === 1) return 'vor 1 Stunde'
  if (diffHour < 24) return `vor ${diffHour} Stunden`
  
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay === 1) return 'vor 1 Tag'
  if (diffDay < 7) return `vor ${diffDay} Tagen`
  
  // Older than a week: show full date
  return formatDateTime(date)
}

/**
 * Format a date as full date + time (German format)
 * @example "15.12.2024, 14:30"
 */
export function formatDateTime(date: string | Date | null | undefined): string {
  if (!date) return '-'

  try {
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(normalizeTimestamp(date))
  } catch {
    return '-'
  }
}

/**
 * Format a date only (without time)
 * @example "15.12.2024"
 */
export function formatDate(date: string | Date | null | undefined): string {
  if (!date) return '-'

  try {
    return new Intl.DateTimeFormat('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(normalizeTimestamp(date))
  } catch {
    return '-'
  }
}

/**
 * Format time only
 * @example "14:30:45"
 */
export function formatTime(date: string | Date | null | undefined, includeSeconds = false): string {
  if (!date) return '-'

  try {
    const options: Intl.DateTimeFormatOptions = {
      hour: '2-digit',
      minute: '2-digit',
    }

    if (includeSeconds) {
      options.second = '2-digit'
    }

    return new Intl.DateTimeFormat('de-DE', options).format(normalizeTimestamp(date))
  } catch {
    return '-'
  }
}

/**
 * Format ISO timestamp for display
 * @example "2024-12-15T14:30:00Z" → "15.12.2024, 15:30"
 */
export function formatTimestamp(timestamp: string | null | undefined): string {
  return formatDateTime(timestamp)
}

/**
 * Convert a Date to the local wall-clock string expected by
 * `<input type="datetime-local">` (format `YYYY-MM-DDTHH:mm`).
 *
 * AUT-1204: shared by all lifecycle-event dialogs that let an operator
 * pick a backdated `event_timestamp`.
 */
export function toDatetimeLocalValue(date: Date = new Date()): string {
  const pad = (n: number): string => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/**
 * Parse a `<input type="datetime-local">` value back into an ISO 8601 UTC
 * string for the `event_timestamp` API field. Returns `null` for empty or
 * unparsable input.
 *
 * AUT-1204: counterpart to {@link toDatetimeLocalValue}.
 */
export function datetimeLocalValueToIso(value: string): string | null {
  if (!value) return null
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

/**
 * Format last_seen timestamp with NULL and Epoch-0 guards (BUG-10 fix).
 *
 * - NULL → '—' (no data available)
 * - Epoch-0 / pre-2020 → 'Nie' (technically invalid timestamp)
 * - Valid timestamp → German-formatted date+time
 *
 * @example formatLastSeen(null) → '—'
 * @example formatLastSeen('1970-01-01T00:00:00Z') → 'Nie'
 * @example formatLastSeen('2026-03-08T14:30:00Z') → '08.03.2026, 14:30'
 */
export function formatLastSeen(lastSeen: string | Date | null | undefined): string {
  if (!lastSeen) return '\u2014'  // em-dash for NULL
  const date = normalizeTimestamp(lastSeen)
  if (isNaN(date.getTime()) || date.getFullYear() < 2020) return 'Nie'
  return formatDateTime(lastSeen)
}

// =============================================================================
// NUMBER FORMATTING
// =============================================================================

/**
 * Round a number to avoid floating-point display artifacts (e.g. 1.4000000000000001 → 1.4).
 * Used for threshold inputs in SensorConfigPanel (BUG-4).
 *
 * @param value - Number to round
 * @param decimals - Decimal places (default 2)
 */
export function roundToDecimals(value: number, decimals: number = 2): number {
  if (decimals <= 0) return Math.round(value)
  const factor = Math.pow(10, decimals)
  return Math.round(value * factor) / factor
}

/**
 * Format a number with specified decimal places
 * @example formatNumber(23.456, 2) → "23,46"
 */
export function formatNumber(
  value: number | null | undefined,
  decimals: number = 2,
  fallback: string = '-',
  useGrouping: boolean = true
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return fallback
  }

  // Round first so Chart.js float ticks (e.g. 63.400000000000006) never leak into labels.
  const rounded = roundToDecimals(value, decimals)

  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping,
  }).format(rounded)
}

/**
 * Format a number as integer
 * @example formatInteger(1234) → "1.234"
 */
export function formatInteger(value: number | null | undefined, fallback: string = '-'): string {
  if (value === null || value === undefined || isNaN(value)) {
    return fallback
  }
  
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(value))
}

/**
 * Format a sensor value with its unit
 * @example formatSensorValue(23.5, "°C", 1) → "23,5 °C"
 */
export function formatSensorValue(
  value: number | null | undefined, 
  unit: string = '',
  decimals: number = 2
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }
  
  const formattedValue = formatNumber(value, decimals)
  return unit ? `${formattedValue} ${unit}` : formattedValue
}

/**
 * AUT-837 E2: Chart-label unit is the last parenthetical, not the first.
 * `VPD (berechnet) (kPa)` → `kPa`. Dataset-unit callers should prefer that field first.
 */
export function unitFromChartLabel(
  label: string | undefined | null,
  fallback = '',
): string {
  if (!label) return fallback
  const matches = [...label.matchAll(/\(([^)]*)\)/g)]
  const last = matches[matches.length - 1]?.[1]?.trim()
  return last || fallback
}

/** AUT-1555 first-class mount fields already loaded on the view config. */
export interface MountChartFields {
  mount_height_cm?: number | null
  mount_medium?: string | null
  mount_angle_deg?: number | null
}

/**
 * AUT-1557: Montage-Suffix for the existing Monitor-L3 dataset label.
 * Empty when the loaded config has no mount fields — never invents values.
 * Example: ` · 30cm canopy`
 */
export function formatMountChartSuffix(
  config: MountChartFields | null | undefined,
): string {
  if (!config) return ''
  const parts: string[] = []
  if (config.mount_height_cm != null && Number.isFinite(config.mount_height_cm)) {
    parts.push(`${config.mount_height_cm}cm`)
  }
  if (config.mount_medium) {
    parts.push(config.mount_medium)
  }
  if (config.mount_angle_deg != null && Number.isFinite(config.mount_angle_deg)) {
    parts.push(`${config.mount_angle_deg}°`)
  }
  return parts.length > 0 ? ` · ${parts.join(' ')}` : ''
}

/**
 * AUT-837 E2: keep one tooltip row per dataset (mode:'x' otherwise hits neighbor buckets).
 */
export function isFirstTooltipItemForDataset<T extends { datasetIndex: number }>(
  item: T,
  index: number,
  items: readonly T[],
): boolean {
  return items.findIndex((other) => other.datasetIndex === item.datasetIndex) === index
}

/**
 * Format percentage
 * @example formatPercent(0.85) → "85%"
 */
export function formatPercent(
  value: number | null | undefined, 
  decimals: number = 0
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }
  
  // If value is already in percentage (0-100), use directly
  // If value is a ratio (0-1), multiply by 100
  const percentValue = value > 1 ? value : value * 100
  
  return `${formatNumber(percentValue, decimals)}%`
}

// =============================================================================
// UPTIME / DURATION FORMATTING
// =============================================================================

/**
 * Format uptime in seconds to human-readable format
 * @example formatUptime(3661) → "1h 1m 1s"
 */
export function formatUptime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || isNaN(seconds)) {
    return '-'
  }
  
  if (seconds < 0) seconds = 0
  
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  
  if (days > 0) {
    return `${days}d ${hours}h ${minutes}m`
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`
  }
  if (minutes > 0) {
    return `${minutes}m ${secs}s`
  }
  return `${secs}s`
}

/**
 * Format uptime as short format (for compact displays)
 * @example formatUptimeShort(3661) → "1h 1m"
 */
export function formatUptimeShort(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || isNaN(seconds)) {
    return '-'
  }
  
  if (seconds < 0) seconds = 0
  
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  
  if (days > 0) {
    return `${days}d ${hours}h`
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  return `${minutes}m`
}

/**
 * Format duration in milliseconds
 * @example formatDuration(1500) → "1.5s"
 */
export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined || isNaN(milliseconds)) {
    return '-'
  }
  
  if (milliseconds < 1000) {
    return `${milliseconds}ms`
  }
  
  const seconds = milliseconds / 1000
  if (seconds < 60) {
    return `${formatNumber(seconds, 1)}s`
  }
  
  return formatUptime(Math.floor(seconds))
}

// =============================================================================
// BYTE SIZE FORMATTING
// =============================================================================

/**
 * Format bytes to human-readable size
 * @example formatBytes(1536) → "1.5 KB"
 */
export function formatBytes(bytes: number | null | undefined, decimals: number = 1): string {
  if (bytes === null || bytes === undefined || isNaN(bytes)) {
    return '-'
  }
  
  if (bytes === 0) return '0 B'
  if (bytes < 0) return '-'
  
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  
  if (i >= sizes.length) {
    return `${formatNumber(bytes / Math.pow(k, sizes.length - 1), decimals)} ${sizes[sizes.length - 1]}`
  }
  
  return `${formatNumber(bytes / Math.pow(k, i), decimals)} ${sizes[i]}`
}

/**
 * Format heap/memory size (commonly in bytes)
 * @example formatHeapSize(131072) → "128 KB"
 */
export function formatHeapSize(bytes: number | null | undefined): string {
  return formatBytes(bytes, 0)
}

// =============================================================================
// SIGNAL STRENGTH FORMATTING
// =============================================================================

/**
 * Format WiFi RSSI to human-readable signal strength
 * @example formatRssi(-65) → "-65 dBm (Gut)"
 */
export function formatRssi(rssi: number | null | undefined): string {
  if (rssi === null || rssi === undefined || isNaN(rssi)) {
    return '-'
  }
  
  let quality: string
  if (rssi >= -50) {
    quality = 'Ausgezeichnet'
  } else if (rssi >= -60) {
    quality = 'Sehr gut'
  } else if (rssi >= -70) {
    quality = 'Gut'
  } else if (rssi >= -80) {
    quality = 'Akzeptabel'
  } else {
    quality = 'Schwach'
  }
  
  return `${rssi} dBm (${quality})`
}

/**
 * Get RSSI quality level
 */
export function getRssiQuality(rssi: number | null | undefined): 'excellent' | 'good' | 'fair' | 'poor' | 'unknown' {
  if (rssi === null || rssi === undefined || isNaN(rssi)) {
    return 'unknown'
  }
  
  if (rssi >= -50) return 'excellent'
  if (rssi >= -60) return 'good'
  if (rssi >= -80) return 'fair'
  return 'poor'
}

// =============================================================================
// ID / IDENTIFIER FORMATTING
// =============================================================================

/**
 * Truncate a long ID for display
 * @example truncateId("ESP_ABCDEF123456", 8) → "ESP_ABCD..."
 */
export function truncateId(id: string | null | undefined, maxLength: number = 12): string {
  if (!id) return '-'
  if (id.length <= maxLength) return id
  return `${id.substring(0, maxLength)}...`
}

/**
 * Format ESP ID with MOCK indicator
 */
export function formatEspId(espId: string, isMock: boolean): string {
  return isMock ? `${espId} (Mock)` : espId
}

// =============================================================================
// RANGE / VALUE VALIDATION
// =============================================================================

/**
 * Clamp a value to a range and format
 */
export function formatClampedValue(
  value: number | null | undefined,
  min: number,
  max: number,
  unit: string = '',
  decimals: number = 2
): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }
  
  const clamped = Math.max(min, Math.min(max, value))
  return formatSensorValue(clamped, unit, decimals)
}

// =============================================================================
// BOOLEAN FORMATTING
// =============================================================================

/**
 * Format boolean as German text
 */
export function formatBoolean(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return value ? 'Ja' : 'Nein'
}

/**
 * Format on/off state
 */
export function formatOnOff(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return value ? 'Ein' : 'Aus'
}

/**
 * Format enabled/disabled state
 */
export function formatEnabled(value: boolean | null | undefined): string {
  if (value === null || value === undefined) return '-'
  return value ? 'Aktiviert' : 'Deaktiviert'
}

// =============================================================================
// LIST FORMATTING
// =============================================================================

/**
 * Format a count with singular/plural German text
 * @example formatCount(1, "Sensor", "Sensoren") → "1 Sensor"
 * @example formatCount(5, "Sensor", "Sensoren") → "5 Sensoren"
 */
export function formatCount(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`
}

// =============================================================================
// DATA FRESHNESS UTILITIES
// =============================================================================

/** Sensor data considered "live" within this many seconds */
export const DATA_LIVE_THRESHOLD_S = 30

/** Sensor data considered "stale" after this many seconds (2 min) */
// AUT-837 A5: harmonisiert mit Server-Default timeout_seconds=180
// (sensor_health.py compute_effective_config, continuous). Server-WS-Event
// is_stale ist die primaere Wahrheit; diese Schwelle ist der FE-Fallback.
export const DATA_STALE_THRESHOLD_S = 180

/** Zone considered stale if no sensor event for this many ms (1 min) */
export const ZONE_STALE_THRESHOLD_MS = 60_000

/**
 * Freshness level for data
 */
export type FreshnessLevel = 'live' | 'recent' | 'stale' | 'unknown'

/**
 * Get data freshness level based on timestamp
 * - live: < DATA_LIVE_THRESHOLD_S seconds ago
 * - recent: < DATA_STALE_THRESHOLD_S seconds ago
 * - stale: > DATA_STALE_THRESHOLD_S seconds ago
 * - unknown: no timestamp
 */
export function getDataFreshness(
  timestamp: string | Date | null | undefined,
  thresholds: { live?: number; recent?: number } = {}
): FreshnessLevel {
  if (!timestamp) return 'unknown'

  const { live = DATA_LIVE_THRESHOLD_S, recent = DATA_STALE_THRESHOLD_S } = thresholds
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 0) return 'live' // Future = just received
  if (diffSec <= live) return 'live'
  if (diffSec <= recent) return 'recent'
  return 'stale'
}

/**
 * Get freshness info with label and color class
 */
export function getFreshnessInfo(freshness: FreshnessLevel): {
  label: string
  colorClass: string
  icon: 'live' | 'recent' | 'stale' | 'unknown'
} {
  switch (freshness) {
    case 'live':
      return { label: 'Live', colorClass: 'text-success', icon: 'live' }
    case 'recent':
      return { label: 'Aktuell', colorClass: 'text-info', icon: 'recent' }
    case 'stale':
      return { label: 'Veraltet', colorClass: 'text-warning', icon: 'stale' }
    default:
      return { label: 'Unbekannt', colorClass: 'text-muted', icon: 'unknown' }
  }
}

/**
 * Calculate age in seconds from timestamp
 */
export function getAgeSeconds(timestamp: string | Date | null | undefined): number | null {
  if (!timestamp) return null
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  return Math.floor((now - then) / 1000)
}

// =============================================================================
// SENSOR STATUS FORMATTING (Phase 2E)
// =============================================================================

/**
 * Badge variant types for UI components.
 */
export type SensorStatusVariant = 'success' | 'warning' | 'error' | 'info' | 'gray'

/**
 * Sensor status information for display.
 */
export interface SensorStatusInfo {
  label: string
  variant: SensorStatusVariant
  icon: 'Activity' | 'AlertTriangle' | 'Clock' | 'Calendar' | 'Pause' | 'HelpCircle'
  showLastReading: boolean
}

/**
 * Formatiert Sensor-Status basierend auf Operating Mode.
 *
 * @param sensor - Sensor mit operating_mode, is_stale, last_reading_at
 * @returns Object mit label, variant, icon für Badge-Anzeige
 */
export function formatSensorStatus(sensor: {
  operating_mode?: SensorOperatingMode
  is_stale?: boolean
  stale_reason?: string
  last_reading_at?: string | null
  timeout_seconds?: number
}): SensorStatusInfo {
  const mode = sensor.operating_mode || 'continuous'

  switch (mode) {
    case 'continuous':
      if (sensor.is_stale) {
        return {
          label: sensor.last_reading_at
            ? `Keine Daten seit ${formatRelativeTime(sensor.last_reading_at)}`
            : 'Noch keine Daten empfangen',
          variant: 'error',
          icon: 'AlertTriangle',
          showLastReading: false,
        }
      }
      return {
        label: 'Aktiv',
        variant: 'success',
        icon: 'Activity',
        showLastReading: true,
      }

    case 'on_demand':
      if (sensor.is_stale && sensor.stale_reason === 'freshness_exceeded') {
        return {
          label: sensor.last_reading_at
            ? `Messung veraltet: ${formatRelativeTime(sensor.last_reading_at)}`
            : 'Messung dringend empfohlen',
          variant: 'error',
          icon: 'AlertTriangle',
          showLastReading: false,
        }
      }
      return {
        label: sensor.last_reading_at
          ? `Letzte Messung: ${formatRelativeTime(sensor.last_reading_at)}`
          : 'Noch keine Messung durchgeführt',
        variant: 'info',
        icon: 'Clock',
        showLastReading: false,
      }

    case 'scheduled':
      return {
        label: 'Geplant',
        variant: 'info',
        icon: 'Calendar',
        showLastReading: true,
      }

    case 'paused':
      return {
        label: 'Pausiert',
        variant: 'gray',
        icon: 'Pause',
        showLastReading: false,
      }

    default:
      return {
        label: 'Unbekannt',
        variant: 'gray',
        icon: 'HelpCircle',
        showLastReading: false,
      }
  }
}

/**
 * Übersetzt Operating Mode in lesbares Label.
 */
export function getModeLabel(mode: SensorOperatingMode | undefined): string {
  switch (mode) {
    case 'continuous': return 'Kontinuierlich'
    case 'on_demand': return 'Auf Abruf'
    case 'scheduled': return 'Geplant'
    case 'paused': return 'Pausiert'
    default: return 'Unbekannt'
  }
}

// =============================================================================
// MEASUREMENT FRESHNESS (Sensor-Lifecycle)
// =============================================================================

export type MeasurementFreshnessLevel = 'fresh' | 'aging' | 'stale' | 'unknown'

export interface MeasurementFreshnessInfo {
  level: MeasurementFreshnessLevel
  label: string
  variant: SensorStatusVariant
  ageLabel: string
}

/**
 * Berechnet Mess-Alter-Status für On-Demand/Scheduled Sensoren.
 *
 * @param lastReadingAt - Zeitpunkt der letzten Messung
 * @param freshnessHours - Konfiguriertes Freshness-Limit in Stunden
 * @returns Freshness-Info mit Level, Label und Variante
 */
export function getMeasurementFreshness(
  lastReadingAt: string | null | undefined,
  freshnessHours: number | null | undefined,
): MeasurementFreshnessInfo {
  if (!lastReadingAt) {
    return {
      level: 'unknown',
      label: 'Noch keine Messung',
      variant: 'gray',
      ageLabel: '—',
    }
  }

  const ageSeconds = getAgeSeconds(lastReadingAt)
  if (ageSeconds === null) {
    return {
      level: 'unknown',
      label: 'Unbekannt',
      variant: 'gray',
      ageLabel: '—',
    }
  }

  const ageLabel = formatRelativeTime(lastReadingAt) ?? '—'

  if (!freshnessHours || freshnessHours <= 0) {
    return {
      level: 'fresh',
      label: `Letzte Messung: ${ageLabel}`,
      variant: 'info',
      ageLabel,
    }
  }

  const freshnessSeconds = freshnessHours * 3600
  const halfFreshnessSeconds = freshnessSeconds / 2

  if (ageSeconds > freshnessSeconds) {
    return {
      level: 'stale',
      label: `Messung veraltet (${ageLabel})`,
      variant: 'error',
      ageLabel,
    }
  }

  if (ageSeconds > halfFreshnessSeconds) {
    return {
      level: 'aging',
      label: `Messung wird alt (${ageLabel})`,
      variant: 'warning',
      ageLabel,
    }
  }

  return {
    level: 'fresh',
    label: `Letzte Messung: ${ageLabel}`,
    variant: 'success',
    ageLabel,
  }
}

/**
 * Übersetzt stale_reason in lesbares Label.
 */
export function formatStaleReason(reason: string | undefined): string {
  switch (reason) {
    case 'timeout_exceeded': return 'Timeout überschritten'
    case 'no_data': return 'Keine Daten empfangen'
    case 'sensor_error': return 'Sensor-Fehler'
    case 'freshness_exceeded': return 'Messung veraltet'
    default: return reason ?? 'Unbekannt'
  }
}

/**
 * Maps sensor quality level to a simplified status category.
 * Used for status-dot coloring in MonitorView and similar views.
 *
 * Defense-in-depth: when `opts.lastRead` is provided, data age is checked
 * independently of the quality flag. This catches cases where the server's
 * quality field is stale/incorrect but the timestamp reveals old data.
 *
 * Backward-compatible: calling without opts preserves original behaviour.
 */
export type SensorStatus = 'good' | 'warning' | 'alarm' | 'stale' | 'offline'

export interface QualityToStatusOpts {
  lastRead?: string | Date | null
  staleThresholdS?: number
}

export function qualityToStatus(quality: string, opts?: QualityToStatusOpts): SensorStatus {
  if (opts?.lastRead != null) {
    const ageS = getAgeSeconds(opts.lastRead)
    const threshold = opts.staleThresholdS ?? DATA_STALE_THRESHOLD_S
    if (ageS !== null && ageS > threshold) return 'stale'
  }

  if (quality === 'good' || quality === 'excellent') return 'good'
  if (quality === 'fair' || quality === 'degraded') return 'warning'
  if (quality === 'poor' || quality === 'bad' || quality === 'error' || quality === 'critical') return 'alarm'
  if (quality === 'stale') return 'stale'
  return 'good'
}

// ─── AUT-250: Canonical 4-level status vocabulary ────────────────────────────

/** Canonical 4-level status used by StatusBadge. stale always → offline (AUT-27). */
export type StatusLevel = 'ok' | 'warning' | 'alarm' | 'offline'

/** Maps sensor quality string directly to 4-level StatusLevel. */
export function qualityToStatusLevel(quality: string, opts?: QualityToStatusOpts): StatusLevel {
  return sensorStatusToLevel(qualityToStatus(quality, opts))
}

/** Maps notification/alert severity string to 4-level StatusLevel. */
export function severityToStatus(severity: string): StatusLevel {
  if (severity === 'critical') return 'alarm'
  if (severity === 'warning') return 'warning'
  return 'ok'
}

/** Collapses the 5-level SensorStatus to 4-level StatusLevel. stale → offline per AUT-27. */
export function sensorStatusToLevel(status: SensorStatus): StatusLevel {
  if (status === 'good') return 'ok'
  if (status === 'warning') return 'warning'
  if (status === 'alarm') return 'alarm'
  return 'offline'  // stale | offline → offline
}

/** Maps ESPStatus to 4-level StatusLevel. */
export function espStatusToLevel(status: 'online' | 'offline' | 'stale' | 'safemode' | string): StatusLevel {
  if (status === 'online') return 'ok'
  if (status === 'stale') return 'warning'
  if (status === 'safemode') return 'alarm'
  return 'offline'
}

/** Maps zone health string to 4-level StatusLevel. */
export function zoneHealthToLevel(health: 'ok' | 'warning' | 'alarm' | 'empty' | string): StatusLevel {
  if (health === 'ok') return 'ok'
  if (health === 'warning') return 'warning'
  if (health === 'alarm') return 'alarm'
  return 'offline'  // empty | unknown → offline
}

// =============================================================================
// ALERT SUPPRESSION
// =============================================================================

export function formatSuppressionReason(reason: string | null | undefined): string {
  switch (reason) {
    case 'maintenance':
      return 'Wartung'
    case 'intentionally_offline':
      return 'Geplant offline'
    case 'calibration':
      return 'Kalibrierung'
    case 'custom':
      return 'Benutzerdefiniert'
    default:
      return reason ?? 'Unbekannt'
  }
}





















