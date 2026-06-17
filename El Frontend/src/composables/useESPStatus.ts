/**
 * useESPStatus Composable
 *
 * Single source of truth for ESP device status calculation.
 * Replaces duplicated status logic in DeviceMiniCard, DeviceSummaryCard,
 * ESPHealthWidget, and ESPOrbitalLayout.
 *
 * Status priority:
 * 1. Server-provided status field (primary source)
 * 2. MQTT connected flag (secondary)
 * 3. Heartbeat-based timing (fallback for stale detection)
 */

import { computed, ref, type ComputedRef, toValue, type MaybeRefOrGetter } from 'vue'
import type { ESPDevice } from '@/api/esp'
import type { ConfigLastReject } from '@/types'
import { formatRelativeTime } from '@/utils/formatters'

/** Possible ESP status values */
export type ESPStatus = 'online' | 'stale' | 'offline' | 'error' | 'safemode' | 'unknown'

/** Status display configuration */
interface StatusDisplay {
  color: string
  text: string
  icon: string
  pulse: boolean
}

/** Status color mapping — uses CSS custom properties from tokens.css */
const STATUS_DISPLAY: Record<ESPStatus, StatusDisplay> = {
  online: {
    color: 'var(--color-success)',
    text: 'Online',
    icon: 'check-circle',
    pulse: true,
  },
  stale: {
    color: 'var(--color-warning)',
    text: 'Verzögert',
    icon: 'clock',
    pulse: false,
  },
  offline: {
    color: 'var(--color-text-muted)',
    text: 'Offline',
    icon: 'wifi-off',
    pulse: false,
  },
  error: {
    color: 'var(--color-error)',
    text: 'Fehler',
    icon: 'alert-triangle',
    pulse: false,
  },
  safemode: {
    color: 'var(--color-warning)',
    text: 'SafeMode',
    icon: 'shield-alert',
    pulse: false,
  },
  unknown: {
    color: 'var(--color-text-muted)',
    text: 'Unbekannt',
    icon: 'help-circle',
    pulse: false,
  },
}

/** Heartbeat timing thresholds */
const HEARTBEAT_STALE_MS = 120_000  // 2x default 60s interval — buffer for one missed heartbeat
const HEARTBEAT_OFFLINE_MS = 210_000 // 3.5 minutes (faster offline fallback)
const STATUS_REEVALUATION_TICK_MS = 1_000

/**
 * Global reactive tick to force periodic status reevaluation.
 * Without this, computed() values that call getESPStatus() do not re-run
 * because Date.now() is not reactive.
 */
const statusReevaluationTick = ref(0)

let statusTickTimerId: ReturnType<typeof setInterval> | null = null
let visibilityListenerRegistered = false

function startStatusTickTimer(): void {
  if (statusTickTimerId !== null) return
  if (typeof globalThis.setInterval !== 'function') return
  statusTickTimerId = globalThis.setInterval(() => {
    statusReevaluationTick.value += 1
  }, STATUS_REEVALUATION_TICK_MS)
}

function ensureStatusTickTimer(): void {
  startStatusTickTimer()
  if (visibilityListenerRegistered || typeof document === 'undefined') return
  visibilityListenerRegistered = true
  // Browser throttles setInterval in background tabs (~1/min instead of 1/s).
  // On tab focus: fire an immediate tick and restart the timer to clear drift.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      statusReevaluationTick.value += 1
      if (statusTickTimerId !== null) {
        clearInterval(statusTickTimerId)
        statusTickTimerId = null
      }
      startStatusTickTimer()
    }
  })
}

function statusFromHeartbeatAge(ts: string | null | undefined): ESPStatus | null {
  if (!ts) return null
  const age = Date.now() - new Date(ts).getTime()
  if (age < HEARTBEAT_STALE_MS) return 'online'
  if (age < HEARTBEAT_OFFLINE_MS) return 'stale'
  return 'offline'
}

/**
 * Pure function: calculate ESP status from device data.
 * Use this in list iterations (v-for) where the composable can't be called per-item.
 */
export function getESPStatus(device: ESPDevice): ESPStatus {
  ensureStatusTickTimer()
  // Reactive dependency for computed() callers: rerun every tick.
  void statusReevaluationTick.value

  // Priority 1: Server-provided status + connected flag
  // Mock ESPs use system_state instead of status for error/safemode detection
  const systemState = (device as any).system_state as string | undefined
  if (device.status === 'error' || systemState === 'ERROR') return 'error'
  if (device.status === 'safemode' || systemState === 'SAFE_MODE') return 'safemode'
  if (device.status === 'offline') return 'offline'

  // Priority 1.5: pending_approval — never show as 'online' via heartbeat fallback
  // Device awaits admin approval; last_seen may be updated by heartbeats but
  // status must remain 'unknown' until explicitly approved (BUG-06 fix)
  if (device.status === 'pending_approval') return 'unknown'

  const ts = device.last_seen || device.last_heartbeat

  // Priority 2: explicit online/connected — but still heartbeat-age aware.
  // This prevents "stuck online" badges when the server status has not
  // switched to offline yet (e.g. no LWT, timeout still pending).
  if (device.status === 'online' || device.connected === true) {
    const agedStatus = statusFromHeartbeatAge(ts)
    return agedStatus ?? 'online'
  }

  // Priority 3: "approved" status — device approved but no heartbeat yet
  // Treat as online if last_seen is recent, otherwise offline.
  if (device.status === 'approved') {
    const agedStatus = statusFromHeartbeatAge(ts)
    if (agedStatus === 'offline') return 'offline'
    return 'online'
  }

  // Priority 4: Heartbeat-based timing (for devices without explicit status)
  const agedStatus = statusFromHeartbeatAge(ts)
  if (agedStatus) return agedStatus

  return 'unknown'
}

/** Get status display config for a given status */
export function getESPStatusDisplay(status: ESPStatus): StatusDisplay {
  return STATUS_DISPLAY[status]
}

/** Operator-facing status label (e.g. stale → "Keine Live-Daten"). */
export function getESPStatusDetailLabel(status: ESPStatus): string {
  switch (status) {
    case 'stale':
      return 'Keine Live-Daten'
    case 'safemode':
      return 'Sicherheitsmodus'
    default:
      return getESPStatusDisplay(status).text
  }
}

/** Multi-line tooltip for header status dots (online/offline/stale + offline context). */
export function getESPStatusTooltip(device: ESPDevice): string {
  const status = getESPStatus(device)
  const lines: string[] = [`Status: ${getESPStatusDetailLabel(status)}`]

  if (status !== 'online') {
    const ts = device.last_seen || device.last_heartbeat
    if (ts) {
      lines.push(`Letztes Lebenszeichen: ${formatRelativeTime(ts)}`)
    }
  }

  const offlineInfo = device.offlineInfo
  if (offlineInfo) {
    lines.push(`Erkennung: ${offlineInfo.displayText}`)
    lines.push(`Quelle: ${offlineInfo.source}`)
    lines.push(`Grund: ${offlineInfo.reason}`)
  }

  return lines.join('\n')
}

/**
 * Calculate ESP device status from all available signals.
 *
 * @param esp - Reactive reference or getter to an ESPDevice
 * @returns Reactive status, color, text, icon, and utility computed refs
 */
export function useESPStatus(esp: MaybeRefOrGetter<ESPDevice>) {
  const status: ComputedRef<ESPStatus> = computed(() => getESPStatus(toValue(esp)))

  const statusColor = computed(() => STATUS_DISPLAY[status.value].color)
  const statusText = computed(() => STATUS_DISPLAY[status.value].text)
  const statusDetailLabel = computed(() => getESPStatusDetailLabel(status.value))
  const statusTooltip = computed(() => getESPStatusTooltip(toValue(esp)))
  const statusIcon = computed(() => STATUS_DISPLAY[status.value].icon)
  const statusPulse = computed(() => STATUS_DISPLAY[status.value].pulse)

  /** Whether the device is reachable (online or stale) */
  const isReachable = computed(() => status.value === 'online' || status.value === 'stale')

  /** Whether the device is fully online */
  const isOnline = computed(() => status.value === 'online')

  /** Mock vs Real distinction — consistent with espApi.isMockEsp() */
  const isMock = computed(() => {
    const device = toValue(esp)
    const id = device.device_id || device.esp_id || ''
    return id.startsWith('ESP_MOCK_') || id.startsWith('MOCK_') || (device.hardware_type === 'MOCK_ESP32')
  })

  /** Border color for mock/real visual distinction */
  const borderColor = computed(() =>
    isMock.value ? 'var(--color-mock)' : 'var(--color-real)'
  )

  /** Device display name (name or device_id fallback) */
  const displayName = computed(() => {
    const device = toValue(esp)
    return device.name || device.device_id || device.esp_id || 'Unbenannt'
  })

  /** Device ID (canonical) */
  const deviceId = computed(() => {
    const device = toValue(esp)
    return device.device_id || device.esp_id || ''
  })

  /** Relative time since last seen — updates every tick so the display stays live */
  const lastSeenText = computed(() => {
    void statusReevaluationTick.value
    const device = toValue(esp)
    const ts = device.last_seen || device.last_heartbeat
    if (!ts) return 'Nie'
    return formatRelativeTime(ts)
  })

  /**
   * AUT-134 PKG-04: Letztes terminales Config-Reject (Server config_failed
   * mit reason_code='config_oversize' ODER ESP32 intent_outcome mit
   * code='PAYLOAD_TOO_LARGE'). Read-only informational.
   *
   * SEPARATER Pfad zum runtime_health_view.degraded `Eingeschränkt`-Badge
   * (das ist Runtime-Health, NICHT Config-Reject).
   */
  const configLastReject = computed<ConfigLastReject | null>(() => {
    const device = toValue(esp)
    return device.config_last_reject ?? null
  })

  /** Boolescher Indikator für UI-Sichtbarkeitslogik (Card/Sheet) */
  const hasConfigReject = computed(() => configLastReject.value !== null)

  return {
    status,
    statusColor,
    statusText,
    statusDetailLabel,
    statusTooltip,
    statusIcon,
    statusPulse,
    isReachable,
    isOnline,
    isMock,
    borderColor,
    displayName,
    deviceId,
    lastSeenText,
    configLastReject,
    hasConfigReject,
  }
}

