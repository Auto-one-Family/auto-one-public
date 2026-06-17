<script setup lang="ts">
/**
 * ESPCard Component
 *
 * @legacy Nur noch für ZoneGroup verwendet. Dashboard nutzt ESPOrbitalLayout.
 * Links wurden auf /?openSettings=${espId} aktualisiert.
 *
 * Displays an ESP device card with:
 * - Mock/Real visual distinction (purple vs cyan border)
 * - Online/Offline status indicator
 * - Orphaned mock warning badge
 * - Quick stats (sensors, actuators)
 * - Different actions for Mock vs Real devices with loading states
 * - Zone information
 * - Last heartbeat time
 * - Inline name editing
 *
 * =============================================================================
 * DATA SOURCES DOCUMENTATION (Phase 1)
 * =============================================================================
 *
 * | Datum      | Mock-Quelle                          | Real-Quelle                      | Aktualisierung           |
 * |------------|--------------------------------------|----------------------------------|--------------------------|
 * | Name       | device.name (DB via Mock→normalized) | device.name (DB)                 | Bei Änderung via PATCH   |
 * | Status     | device.connected → 'online'/'offline'| device.status + last_seen        | WebSocket esp_health     |
 * | WiFi RSSI  | mock.wifi_rssi (Debug Store, -43dBm) | device.wifi_rssi (from heartbeat)| WebSocket esp_health     |
 * | Uptime     | mock.uptime (Debug Store)            | device.uptime (from heartbeat)   | WebSocket esp_health     |
 * | Heap       | mock.heap_free (Debug Store, 180KB)  | device.heap_free (from heartbeat)| WebSocket esp_health     |
 * | Last Seen  | mock.last_heartbeat                  | device.last_seen / last_heartbeat| WebSocket esp_health     |
 * | Sensors    | mock.sensors[] (Debug Store)         | device.sensor_count (DB)         | WebSocket sensor_data    |
 * | Actuators  | mock.actuators[] (Debug Store)       | device.actuator_count (DB)       | WebSocket actuator_status|
 *
 * Mock ESP Default Values (from server MockESPManager):
 * - wifi_rssi: -43 dBm (simulated excellent signal)
 * - heap_free: 180000 bytes (~176 KB)
 * - uptime: incremented every heartbeat
 *
 * Real ESP Data Flow:
 * 1. ESP sends heartbeat via MQTT with metrics (uptime, heap, rssi)
 * 2. Server heartbeat_handler stores in DB + broadcasts WebSocket esp_health
 * 3. Frontend esp.ts store receives esp_health and updates device in list
 * 4. ESPCard re-renders with updated props
 *
 * =============================================================================
 */

import { computed, ref, nextTick } from 'vue'
import { RouterLink } from 'vue-router'
import {
  Heart,
  AlertTriangle,
  Trash2,
  Settings,
  ExternalLink,
  AlertOctagon,
  Loader2,
  Thermometer,
  Zap,
  Clock,
  HardDrive,
  MapPin,
  Wifi,
  Database,
  MemoryStick,
  Radio,
  TimerOff,
  Pencil,
  Check,
  X,
  Power,
  Activity,
} from 'lucide-vue-next'
import { Badge } from '@/shared/design'
import { formatUptimeShort, formatHeapSize, getDataFreshness, type FreshnessLevel } from '@/utils/formatters'
import { getWifiStrength, type WifiStrengthInfo } from '@/utils/wifiStrength'
import type { ESPDevice } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { useESPStatus } from '@/composables/useESPStatus'
import { createLogger } from '@/utils/logger'

const log = createLogger('ESPCard')

interface Props {
  /** The ESP device data */
  esp: ESPDevice
  /** Loading state for heartbeat action */
  heartbeatLoading?: boolean
  /** Loading state for delete action */
  deleteLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  heartbeatLoading: false,
  deleteLoading: false,
})

const emit = defineEmits<{
  heartbeat: [espId: string]
  delete: [espId: string]
  nameUpdated: [espId: string, newName: string | null]
}>()

// ESP Store for name updates
const espStore = useEspStore()

// =============================================================================
// Name Editing State
// =============================================================================
const isEditingName = ref(false)
const editedName = ref('')
const isSavingName = ref(false)
const saveError = ref('')
const nameInputRef = ref<HTMLInputElement | null>(null)

// Computed: Display name or fallback
const displayName = computed(() => props.esp.name || null)

/**
 * Start inline editing of the device name
 */
function startEditName() {
  editedName.value = props.esp.name || ''
  isEditingName.value = true
  saveError.value = ''
  // Focus the input after DOM update
  nextTick(() => {
    nameInputRef.value?.focus()
    nameInputRef.value?.select()
  })
}

/**
 * Cancel name editing, reset to original value
 */
function cancelEditName() {
  isEditingName.value = false
  editedName.value = ''
  saveError.value = ''
}

/**
 * Save the new name via API
 */
async function saveName() {
  if (isSavingName.value) return

  const newName = editedName.value.trim() || null
  const deviceId = espId.value

  log.debug('saveName called', {
    deviceId,
    currentName: props.esp.name,
    newName,
    editedNameValue: editedName.value,
  })

  // No change? Just close
  if (newName === (props.esp.name || null)) {
    log.debug('No change detected, cancelling')
    cancelEditName()
    return
  }

  isSavingName.value = true
  saveError.value = ''

  try {
    log.debug('Calling espStore.updateDevice', { name: newName || undefined })
    const result = await espStore.updateDevice(deviceId, { name: newName })
    log.debug('updateDevice returned', result)
    isEditingName.value = false
    emit('nameUpdated', deviceId, newName)
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { detail?: string } } }
    saveError.value = axiosError.response?.data?.detail || 'Fehler beim Speichern'
    // Keep edit mode open on error
    setTimeout(() => {
      saveError.value = ''
    }, 3000)
  } finally {
    isSavingName.value = false
  }
}

/**
 * Handle keyboard events in name input
 */
function handleNameKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault()
    saveName()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    cancelEditName()
  }
}

// Unified status from composable (single source of truth)
const {
  isOnline,
  isMock,
  deviceId: espId,
  lastSeenText,
} = useESPStatus(() => props.esp)

const hasEmergencyStopped = computed(() => {
  if (!props.esp.actuators) return false
  return props.esp.actuators.some((a: any) => a.emergency_stopped)
})

// Orphaned mock detection - Mock ESP exists in DB but not in debug store
const isOrphanedMock = computed(() => {
  if (!isMock.value) return false
  // Check if metadata contains orphaned_mock flag (set by esp.ts API)
  const metadata = props.esp.metadata as Record<string, unknown> | undefined
  return metadata?.orphaned_mock === true
})

// Check if any action is currently loading
const isAnyActionLoading = computed(() =>
  props.heartbeatLoading || props.deleteLoading
)

// System state (FSM) for Mock ESPs - only shown when relevant (SAFE_MODE, ERROR)
const systemState = computed(() => {
  if (isMock.value && 'system_state' in props.esp) {
    return (props.esp as any).system_state
  }
  return null
})

// Connection status - consistent for ALL devices (online/offline)
const connectionStatus = computed(() => {
  // Use 'status' field if available (Mock ESPs now include this)
  if ('status' in props.esp && props.esp.status) {
    return props.esp.status
  }
  // Fallback to 'connected' for Mock ESPs
  if ('connected' in props.esp) {
    return props.esp.connected ? 'online' : 'offline'
  }
  return props.esp.status || 'unknown'
})

// Primary status info - ALWAYS shows connection/approval status
// Extended for Phase 3C: Pending-Mode Integration
const stateInfo = computed(() => {
  const status = connectionStatus.value

  // Status-to-UI mapping (consistent with server status values)
  const statusMap: Record<string, { label: string; variant: string }> = {
    // Approval-Flow Status (Phase 3C)
    pending_approval: { label: 'Wartet auf Freigabe', variant: 'warning' },
    approved: { label: 'Freigegeben', variant: 'info' },
    rejected: { label: 'Abgelehnt', variant: 'danger' },
    // Connection Status
    online: { label: 'Online', variant: 'success' },
    offline: { label: 'Offline', variant: 'gray' },
    error: { label: 'Fehler', variant: 'danger' },
  }

  return statusMap[status] ?? { label: 'Unbekannt', variant: 'gray' }
})

// Secondary state info for Mock ESPs - only shown for notable states (SAFE_MODE, ERROR)
const mockStateInfo = computed(() => {
  if (!isMock.value || !systemState.value) return null
  // Only show system_state badge for notable states, not for OPERATIONAL
  const state = systemState.value
  if (state === 'SAFE_MODE') {
    return { label: 'Sicherheitsmodus', variant: 'warning' }
  } else if (state === 'ERROR') {
    return { label: 'Fehler', variant: 'danger' }
  } else if (state === 'BOOT' || state === 'WIFI_SETUP' || state === 'MQTT_CONNECTING') {
    return { label: 'Startet...', variant: 'info' }
  }
  // Don't show badge for OPERATIONAL - connection status is sufficient
  return null
})

// Card classes based on mock/real and online/offline
const cardClasses = computed(() => {
  const classes = ['esp-card']

  if (isMock.value) {
    classes.push('esp-card--mock')
  } else {
    classes.push('esp-card--real')
  }

  if (!isOnline.value) {
    classes.push('esp-card--offline')
  }

  if (hasEmergencyStopped.value) {
    classes.push('esp-card--emergency')
  }

  if (isOrphanedMock.value) {
    classes.push('esp-card--orphaned')
  }

  return classes
})

// Status bar color based on state
const statusBarClasses = computed(() => {
  if (isOrphanedMock.value) return 'esp-card__status-bar--orphaned'
  if (hasEmergencyStopped.value) return 'esp-card__status-bar--emergency'
  if (!isOnline.value) return 'esp-card__status-bar--offline'
  if (systemState.value === 'SAFE_MODE') return 'esp-card__status-bar--warning'
  if (systemState.value === 'ERROR' || connectionStatus.value === 'error') return 'esp-card__status-bar--error'
  if (isMock.value) return 'esp-card__status-bar--mock'
  return 'esp-card__status-bar--real'
})

// =============================================================================
// Data Source & Freshness Indicators
// =============================================================================

// Data source: where is this data coming from?
// Mock ESPs from debug store have rich data (sensors array, system_state, etc.)
// Orphaned mocks or real ESPs from DB may have less data
const dataSource = computed<'memory' | 'database'>(() => {
  // If it has sensors array with full data, it's from memory (debug store)
  if (isMock.value && !isOrphanedMock.value && props.esp.sensors && Array.isArray(props.esp.sensors)) {
    return 'memory'
  }
  // If it's a real ESP or orphaned mock, it's from database
  return 'database'
})

const dataSourceInfo = computed(() => {
  if (dataSource.value === 'memory') {
    return { label: 'Live-Speicher', icon: 'memory', colorClass: 'text-success' }
  }
  return { label: 'Datenbank', icon: 'database', colorClass: 'text-info' }
})

// Data freshness based on last heartbeat
const dataFreshness = computed<FreshnessLevel>(() => {
  const timestamp = props.esp.last_heartbeat || props.esp.last_seen
  return getDataFreshness(timestamp)
})

const freshnessInfo = computed(() => {
  switch (dataFreshness.value) {
    case 'live':
      return { label: 'Live', colorClass: 'freshness--live', title: 'Daten sind aktuell (< 30s)' }
    case 'recent':
      return { label: 'Aktuell', colorClass: 'freshness--recent', title: 'Daten sind aktuell (< 2min)' }
    case 'stale':
      return { label: 'Veraltet', colorClass: 'freshness--stale', title: 'Daten sind veraltet (> 2min)' }
    default:
      return { label: 'Unbekannt', colorClass: 'freshness--unknown', title: 'Kein Heartbeat empfangen' }
  }
})

// Check if important data might be stale or missing
const hasIncompleteData = computed(() => {
  // Check if uptime/heap/rssi are undefined (might indicate stale DB data)
  return props.esp.uptime === undefined &&
         props.esp.heap_free === undefined &&
         props.esp.wifi_rssi === undefined
})

// =============================================================================
// Satellite Dots - Compact sensor/actuator indicators
// =============================================================================

const sensorCount = computed(() => {
  if (Array.isArray(props.esp.sensors)) return props.esp.sensors.length
  return props.esp.sensor_count ?? 0
})
const actuatorCount = computed(() => {
  if (Array.isArray(props.esp.actuators)) return props.esp.actuators.length
  return props.esp.actuator_count ?? 0
})
const hasSatellites = computed(() => sensorCount.value > 0 || actuatorCount.value > 0)

// Limit displayed dots to 5 max
const limitedSensors = computed(() => {
  const sensors = (props.esp.sensors || []) as Array<{ gpio: number; quality?: string; data_quality?: string; sensor_type?: string; name?: string; raw_value?: number }>
  return sensors.slice(0, 5)
})

const limitedActuators = computed(() => {
  const actuators = (props.esp.actuators || []) as Array<{ gpio: number; state?: boolean; pwm_value?: number; actuator_type?: string; name?: string; emergency_stopped?: boolean }>
  return actuators.slice(0, 5)
})

// Get quality class for sensor dot
function getSensorDotClass(sensor: any): string {
  const quality = sensor.quality || sensor.data_quality
  if (quality === 'excellent' || quality === 'good') return 'esp-card__satellite-dot--good'
  if (quality === 'fair' || quality === 'degraded') return 'esp-card__satellite-dot--fair'
  if (quality === 'poor' || quality === 'bad' || quality === 'emergency') return 'esp-card__satellite-dot--poor'
  return 'esp-card__satellite-dot--unknown'
}

// Get state class for actuator dot
function getActuatorDotClass(actuator: any): string {
  if (actuator.emergency_stopped) return 'esp-card__satellite-dot--emergency'
  if (actuator.state === true || actuator.current_state === true) return 'esp-card__satellite-dot--on'
  if (actuator.state === false || actuator.current_state === false) return 'esp-card__satellite-dot--off'
  return 'esp-card__satellite-dot--unknown'
}

// Format sensor value for tooltip
function formatSensorTooltip(sensor: any): string {
  const type = sensor.sensor_type || 'Sensor'
  const value = sensor.processed_value ?? sensor.raw_value ?? '?'
  const unit = sensor.unit || ''
  return `${type} (GPIO ${sensor.gpio}): ${value}${unit}`
}

// Format actuator tooltip
function formatActuatorTooltip(actuator: any): string {
  const type = actuator.actuator_type || 'Actuator'
  const state = actuator.emergency_stopped ? 'E-STOP' : (actuator.state ? 'AN' : 'AUS')
  return `${type} (GPIO ${actuator.gpio}): ${state}`
}

// =============================================================================
// WiFi Signal Strength
// =============================================================================

const wifiInfo = computed<WifiStrengthInfo>(() => getWifiStrength(props.esp.wifi_rssi))

// WiFi color class based on signal quality
const wifiColorClass = computed(() => {
  switch (wifiInfo.value.quality) {
    case 'excellent':
    case 'good':
      return 'text-emerald-400'
    case 'fair':
      return 'text-yellow-400'
    case 'poor':
      return 'text-orange-400'
    case 'none':
      return 'text-red-400'
    default:
      return 'text-slate-500'
  }
})

// WiFi tooltip with detailed info (shows technical dBm value for experts)
const wifiTooltip = computed(() => {
  if (props.esp.wifi_rssi === undefined || props.esp.wifi_rssi === null) {
    return 'WiFi-Signalstärke: Keine Daten verfügbar'
  }
  const simNote = isMock.value ? ' (simuliert)' : ''
  return `WiFi: ${props.esp.wifi_rssi} dBm${simNote}`
})

// =============================================================================
// Heartbeat Indicator (Phase 1)
// =============================================================================

/**
 * Check if heartbeat is "fresh" (< 30 seconds ago)
 * Used for pulse animation on heartbeat icon
 */
const isHeartbeatFresh = computed(() => {
  const timestamp = props.esp.last_heartbeat || props.esp.last_seen
  if (!timestamp) return false

  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  return diffSec >= 0 && diffSec < 30
})

/**
 * Heartbeat click handler
 * - Mock ESP: Triggers manual heartbeat
 * - Real ESP: Shows info that heartbeats are automatic
 */
function handleHeartbeatClick() {
  if (isMock.value) {
    emit('heartbeat', espId.value)
  } else {
    // Show browser alert for Real ESPs
    alert('Real ESPs senden Heartbeats automatisch alle 60 Sekunden.\n\nDiese Funktion ist nur für Mock ESPs verfügbar.')
  }
}

/**
 * Heartbeat tooltip based on device type
 */
const heartbeatTooltip = computed(() => {
  if (isMock.value) {
    return `Letzter Heartbeat: ${lastSeenText.value}\nKlicken um Heartbeat auszulösen`
  }
  return `Letzter Heartbeat: ${lastSeenText.value}\nReal ESPs senden automatisch alle 60s`
})

// =============================================================================
// Offline Info Display (Phase 1 - LWT & Heartbeat Timeout)
// =============================================================================

/**
 * Icon for offline reason.
 */
const offlineIcon = computed(() => {
  if (!props.esp.offlineInfo) return null

  switch (props.esp.offlineInfo.reason) {
    case 'lwt':
      return Zap  // ⚡ Lightning for sudden disconnect
    case 'heartbeat_timeout':
      return Clock  // ⏱️ Clock for timeout
    case 'shutdown':
      return Power  // 🔌 Power for intentional shutdown
    default:
      return null
  }
})

/**
 * Color class for offline reason.
 */
const offlineColor = computed(() => {
  if (!props.esp.offlineInfo) return 'text-gray-400'

  switch (props.esp.offlineInfo.reason) {
    case 'lwt':
      return 'text-red-500'  // Red for crash/power-loss
    case 'heartbeat_timeout':
      return 'text-orange-500'  // Orange for timeout
    case 'shutdown':
      return 'text-blue-400'  // Blue for intentional shutdown
    default:
      return 'text-gray-400'
  }
})

/**
 * Formatted timestamp for offline info.
 * Shows relative time (e.g., "vor 15 Minuten").
 */
const offlineTimeAgo = computed(() => {
  if (!props.esp.offlineInfo?.timestamp) return null

  const now = Date.now()
  const offlineAt = props.esp.offlineInfo.timestamp * 1000
  const diffMs = now - offlineAt
  const diffMin = Math.floor(diffMs / 60000)

  if (diffMin < 1) return 'gerade eben'
  if (diffMin < 60) return `vor ${diffMin} Min`

  const diffHours = Math.floor(diffMin / 60)
  if (diffHours < 24) return `vor ${diffHours} Std`

  const diffDays = Math.floor(diffHours / 24)
  return `vor ${diffDays} Tag${diffDays > 1 ? 'en' : ''}`
})

/**
 * Absolute timestamp for tooltip.
 */
const offlineTimeAbsolute = computed(() => {
  if (!props.esp.offlineInfo?.timestamp) return null

  const date = new Date(props.esp.offlineInfo.timestamp * 1000)
  return date.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
})
</script>

<template>
  <div :class="cardClasses">
    <!-- Status indicator bar (left border) -->
    <div :class="['esp-card__status-bar', statusBarClasses]" />
    
    <div class="esp-card__content">
      <!-- Header: Name (editable) + Badges -->
      <div class="esp-card__header">
        <div class="esp-card__name-group">
          <!-- Editable Name Section -->
          <div class="esp-card__name-row">
            <!-- Edit Mode: Input -->
            <template v-if="isEditingName">
              <div class="esp-card__name-edit">
                <input
                  ref="nameInputRef"
                  v-model="editedName"
                  type="text"
                  class="esp-card__name-input"
                  placeholder="Gerätename eingeben..."
                  :disabled="isSavingName"
                  @keydown="handleNameKeydown"
                  @blur="saveName"
                />
                <div class="esp-card__name-actions">
                  <button
                    v-if="isSavingName"
                    class="esp-card__name-btn"
                    disabled
                  >
                    <Loader2 class="w-4 h-4 animate-spin" />
                  </button>
                  <template v-else>
                    <button
                      class="esp-card__name-btn esp-card__name-btn--save"
                      title="Speichern (Enter)"
                      @mousedown.prevent="saveName"
                    >
                      <Check class="w-4 h-4" />
                    </button>
                    <button
                      class="esp-card__name-btn esp-card__name-btn--cancel"
                      title="Abbrechen (Escape)"
                      @mousedown.prevent="cancelEditName"
                    >
                      <X class="w-4 h-4" />
                    </button>
                  </template>
                </div>
              </div>
            </template>

            <!-- Display Mode: Name + Pencil -->
            <template v-else>
              <div
                class="esp-card__name-display"
                @click="startEditName"
                :title="displayName ? `${displayName}\n(Klicken zum Bearbeiten)` : 'Klicken zum Bearbeiten'"
              >
                <span :class="['esp-card__name', { 'esp-card__name--empty': !displayName }]">
                  {{ displayName || 'Unbenannt' }}
                </span>
                <Pencil class="esp-card__name-pencil w-4 h-4" />
              </div>
            </template>
          </div>

          <!-- Error Message -->
          <div v-if="saveError" class="esp-card__name-error">
            {{ saveError }}
          </div>

          <!-- ESP-ID (secondary, always visible) -->
          <div class="esp-card__id-row">
            <RouterLink
              :to="`/?openSettings=${espId}`"
              class="esp-card__id"
            >
              {{ espId }}
            </RouterLink>
            <Badge
              :variant="isMock ? 'mock' : 'real'"
              size="sm"
              :title="isMock ? 'Mock-Gerät (simuliert)' : 'Hardware-Gerät'"
            >
              {{ isMock ? 'MOCK' : 'REAL' }}
            </Badge>
          </div>
        </div>

        <div class="esp-card__status-badges">
          <!-- Orphaned Mock Warning - highest priority indicator -->
          <Badge
            v-if="isOrphanedMock"
            variant="warning"
            size="sm"
            :dot="true"
            title="Verwaist: Nur in Datenbank, nicht im Debug-Store"
          >
            <AlertOctagon class="w-3 h-3 mr-1" />
            Verwaist
          </Badge>

          <!-- Primary: Connection status (Online/Offline) - consistent for ALL devices -->
          <Badge
            v-if="!isOrphanedMock"
            :variant="stateInfo.variant as any"
            :pulse="isOnline"
            :dot="true"
            size="sm"
            :title="isOnline ? 'Online: Gerät verbunden' : 'Offline: Keine Verbindung'"
          >
            {{ stateInfo.label }}
          </Badge>

          <!-- Secondary: Mock ESP system state (only for SAFE_MODE, ERROR, etc.) -->
          <Badge
            v-if="mockStateInfo && !isOrphanedMock"
            :variant="mockStateInfo.variant as any"
            size="sm"
            :title="`Systemzustand: ${mockStateInfo.label}`"
          >
            {{ mockStateInfo.label }}
          </Badge>

          <Badge
            v-if="hasEmergencyStopped"
            variant="danger"
            size="sm"
            title="Notaus: Alle Aktoren dieses Geräts wurden gestoppt"
          >
            E-STOP
          </Badge>

          <!-- AUT-716: Offline-Spool pending badge -->
          <Badge
            v-if="(esp.spool_pending_count ?? 0) > 0"
            variant="warning"
            size="sm"
            :title="`Offline-Spool: ${esp.spool_pending_count} Einträge ausstehend (nach Reconnect wird synchronisiert)`"
          >
            <Database class="w-3 h-3 mr-1" />
            {{ esp.spool_pending_count }}
          </Badge>
        </div>
      </div>
      
      <!-- Zone info (prominent) - shows zone_name (human-readable), zone_id only in tooltip -->
      <div
        :class="['esp-card__zone', { 'esp-card__zone--empty': !esp.zone_name && !esp.zone_id }]"
        :title="esp.zone_id ? `Zone-ID: ${esp.zone_id}` : 'Keine Zone zugewiesen'"
      >
        <MapPin :class="['w-4 h-4', esp.zone_name || esp.zone_id ? 'text-accent' : 'text-muted']" />
        <span class="esp-card__zone-name">
          {{ esp.zone_name || esp.zone_id || 'Keine Zone' }}
        </span>
      </div>

      <!-- Offline Info Line (Phase 1 - LWT & Heartbeat Timeout) -->
      <div
        v-if="esp.status === 'offline' && esp.offlineInfo"
        class="esp-card__offline-info"
        :class="offlineColor"
        :title="offlineTimeAbsolute || undefined"
      >
        <component :is="offlineIcon" class="w-4 h-4" />
        <span class="esp-card__offline-text">{{ esp.offlineInfo.displayText }}</span>
        <span class="esp-card__offline-separator">•</span>
        <span class="esp-card__offline-time">{{ offlineTimeAgo }}</span>
      </div>

      <!-- Data Source & Freshness Indicators -->
      <div class="esp-card__data-info">
        <!-- Data Source -->
        <div :class="['esp-card__data-source', dataSourceInfo.colorClass]" :title="dataSource === 'memory' ? 'Daten aus Debug-Store (RAM)' : 'Daten aus PostgreSQL'">
          <MemoryStick v-if="dataSource === 'memory'" class="w-3.5 h-3.5" />
          <Database v-else class="w-3.5 h-3.5" />
          <span>{{ dataSourceInfo.label }}</span>
        </div>

        <!-- Separator -->
        <span class="esp-card__data-separator">•</span>

        <!-- Freshness -->
        <div :class="['esp-card__freshness', freshnessInfo.colorClass]" :title="freshnessInfo.title">
          <Radio v-if="dataFreshness === 'live'" class="w-3.5 h-3.5" />
          <Clock v-else-if="dataFreshness === 'recent'" class="w-3.5 h-3.5" />
          <TimerOff v-else class="w-3.5 h-3.5" />
          <span>{{ freshnessInfo.label }}</span>
        </div>

        <!-- Incomplete Data Warning -->
        <template v-if="hasIncompleteData && dataSource === 'database'">
          <span class="esp-card__data-separator">•</span>
          <div class="esp-card__incomplete-data" title="Keine Uptime/Heap/RSSI Daten - letzter Heartbeat fehlt">
            <AlertTriangle class="w-3.5 h-3.5" />
            <span>Unvollständig</span>
          </div>
        </template>
      </div>

      <!-- Quick stats (compact grid) -->
      <div class="esp-card__stats">
        <!-- Sensors -->
        <div class="esp-card__stat" title="Sensoren">
          <Thermometer class="w-4 h-4" />
          <span :class="{ 'text-muted': sensorCount === 0 }">{{ sensorCount }}</span>
        </div>
        <!-- Actuators -->
        <div class="esp-card__stat" title="Aktoren">
          <Zap class="w-4 h-4" />
          <span :class="{ 'text-muted': actuatorCount === 0 }">{{ actuatorCount }}</span>
        </div>
        <div v-if="esp.uptime !== undefined" class="esp-card__stat" title="Uptime">
          <Clock class="w-4 h-4" />
          <span>{{ formatUptimeShort(esp.uptime || 0) }}</span>
        </div>
        <div v-if="esp.heap_free !== undefined" class="esp-card__stat" title="Heap">
          <HardDrive class="w-4 h-4" />
          <span>{{ formatHeapSize(esp.heap_free || 0) }}</span>
        </div>
        <!-- WiFi Signal with bars indicator (Phase 1) -->
        <div v-if="esp.wifi_rssi !== undefined" class="esp-card__stat esp-card__wifi" :title="wifiTooltip">
          <!-- WiFi Bars Indicator -->
          <div :class="['esp-card__wifi-bars', wifiColorClass]">
            <span :class="['esp-card__wifi-bar', { active: wifiInfo.bars >= 1 }]" />
            <span :class="['esp-card__wifi-bar', { active: wifiInfo.bars >= 2 }]" />
            <span :class="['esp-card__wifi-bar', { active: wifiInfo.bars >= 3 }]" />
            <span :class="['esp-card__wifi-bar', { active: wifiInfo.bars >= 4 }]" />
          </div>
          <span :class="wifiColorClass">{{ wifiInfo.label }}</span>
        </div>
        <!-- WiFi Unknown state -->
        <div v-else class="esp-card__stat esp-card__wifi" title="WiFi-Signalstärke: Keine Daten verfügbar">
          <Wifi class="w-4 h-4 text-slate-500 opacity-40" />
          <span class="text-slate-500">Unbekannt</span>
        </div>
      </div>

      <!-- Satellite Dots - Compact sensor/actuator indicators -->
      <div v-if="hasSatellites" class="esp-card__satellites">
        <!-- Sensor Dots (circles) -->
        <div v-if="limitedSensors.length > 0" class="esp-card__satellite-group">
          <span class="esp-card__satellite-label">S</span>
          <div
            v-for="sensor in limitedSensors"
            :key="`sensor-${sensor.gpio}`"
            :class="['esp-card__satellite-dot esp-card__satellite-dot--sensor', getSensorDotClass(sensor)]"
            :title="formatSensorTooltip(sensor)"
          />
          <span v-if="sensorCount > 5" class="esp-card__satellite-more">
            +{{ sensorCount - 5 }}
          </span>
        </div>

        <!-- Actuator Dots (rounded squares) -->
        <div v-if="limitedActuators.length > 0" class="esp-card__satellite-group">
          <span class="esp-card__satellite-label">A</span>
          <div
            v-for="actuator in limitedActuators"
            :key="`actuator-${actuator.gpio}`"
            :class="['esp-card__satellite-dot esp-card__satellite-dot--actuator', getActuatorDotClass(actuator)]"
            :title="formatActuatorTooltip(actuator)"
          />
          <span v-if="actuatorCount > 5" class="esp-card__satellite-more">
            +{{ actuatorCount - 5 }}
          </span>
        </div>
      </div>

      <!-- Heartbeat Indicator (Phase 1: Clickable with pulse animation) -->
      <button
        v-if="esp.last_heartbeat || esp.last_seen || isMock"
        :class="[
          'esp-card__heartbeat-indicator',
          { 'esp-card__heartbeat-indicator--fresh': isHeartbeatFresh },
          { 'esp-card__heartbeat-indicator--mock': isMock }
        ]"
        :title="heartbeatTooltip"
        :disabled="heartbeatLoading || isOrphanedMock"
        @click="handleHeartbeatClick"
      >
        <Heart
          :class="[
            'w-4 h-4',
            isHeartbeatFresh ? 'esp-card__heart-pulse' : ''
          ]"
        />
        <span class="esp-card__heartbeat-text">
          {{ lastSeenText }}
        </span>
        <Loader2 v-if="heartbeatLoading" class="w-3 h-3 animate-spin ml-1" />
      </button>
      
      <!-- Auto-heartbeat indicator (Mock ESP only) -->
      <div v-if="isMock && 'auto_heartbeat' in esp" class="esp-card__auto-heartbeat">
        <span :class="['esp-card__auto-heartbeat-dot', (esp as any).auto_heartbeat ? 'active' : '']" />
        <span class="esp-card__auto-heartbeat-text">
          Auto-Heartbeat {{ (esp as any).auto_heartbeat ? 'aktiv' : 'inaktiv' }}
        </span>
      </div>
      
      <!-- Orphaned Mock Warning Message -->
      <div v-if="isOrphanedMock" class="esp-card__orphaned-warning">
        <AlertOctagon class="w-4 h-4 flex-shrink-0" />
        <span>
          Verwaist: Nur in DB, nicht im Debug-Store. Bitte löschen und neu erstellen.
        </span>
      </div>

      <!-- Actions -->
      <div class="esp-card__actions">
        <!-- Left group: Details + other actions -->
        <div class="esp-card__actions-left">
          <RouterLink
            :to="`/?openSettings=${espId}`"
            class="esp-card__details-btn"
          >
            <ExternalLink class="w-4 h-4" />
            Details
          </RouterLink>

          <!-- System Monitor: View Logs -->
          <RouterLink
            :to="{
              path: '/system-monitor',
              query: {
                tab: 'events',
                esp: espId,
                timeRange: '1h'
              }
            }"
            class="esp-card__action-btn esp-card__action-btn--logs"
            title="Logs anzeigen"
          >
            <Activity class="w-4 h-4" />
          </RouterLink>

          <!-- Mock ESP: Heartbeat -->
          <button
            v-if="isMock"
            class="esp-card__action-btn esp-card__action-btn--heartbeat"
            :disabled="heartbeatLoading || isOrphanedMock || isAnyActionLoading"
            :title="isOrphanedMock ? 'Nicht verfügbar für verwaiste Mocks' : 'Heartbeat auslösen'"
            @click="emit('heartbeat', espId)"
          >
            <Loader2 v-if="heartbeatLoading" class="w-4 h-4 animate-spin" />
            <Heart v-else class="w-4 h-4" />
          </button>

          <!-- Real ESP: Settings -->
          <button
            v-if="!isMock"
            class="esp-card__action-btn"
            title="Konfigurieren"
            @click="$router.push(`/?openSettings=${espId}`)"
          >
            <Settings class="w-4 h-4" />
          </button>
        </div>

        <!-- Right: Delete (always) -->
        <button
          class="esp-card__action-btn esp-card__action-btn--delete"
          :disabled="deleteLoading || isAnyActionLoading"
          title="Löschen"
          @click="emit('delete', espId)"
        >
          <Loader2 v-if="deleteLoading" class="w-4 h-4 animate-spin" />
          <Trash2 v-else class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.esp-card {
  position: relative;
  display: flex;
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  overflow: hidden;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  outline: none; /* Remove focus outline - prevents blue border after click */
}

.esp-card:hover {
  border-color: rgba(96, 165, 250, 0.25);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* Focus only for keyboard navigation (accessibility) */
.esp-card:focus-visible {
  outline: 2px solid var(--color-iridescent-1);
  outline-offset: 2px;
}

/* Status bar (left border indicator) */
.esp-card__status-bar {
  width: 4px;
  flex-shrink: 0;
}

.esp-card__status-bar--mock {
  background-color: var(--color-mock);
}

.esp-card__status-bar--real {
  background-color: var(--color-real);
}

.esp-card__status-bar--offline {
  background-color: var(--color-text-muted);
}

.esp-card__status-bar--warning {
  background-color: var(--color-warning);
}

.esp-card__status-bar--error {
  background-color: var(--color-error);
}

.esp-card__status-bar--emergency {
  background-color: var(--color-error);
  animation: pulse-bar 1s infinite;
}

@keyframes pulse-bar {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* Offline state */
.esp-card--offline {
  opacity: 0.7;
}

/* Emergency state */
.esp-card--emergency {
  border-color: rgba(248, 113, 113, 0.3);
}

/* Orphaned mock state */
.esp-card--orphaned {
  border-color: rgba(251, 191, 36, 0.4);
  background-color: rgba(251, 191, 36, 0.03);
}

.esp-card__status-bar--orphaned {
  background-color: var(--color-warning);
  animation: pulse-bar 1.5s infinite;
}

/* Content area */
.esp-card__content {
  flex: 1;
  padding: 1rem 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
  min-width: 0;
}

/* Header */
.esp-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.esp-card__name-group {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  min-width: 0;
  flex: 1;
}

.esp-card__name-row {
  display: flex;
  align-items: center;
  min-height: 28px;
}

/* Name Display Mode */
.esp-card__name-display {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  margin: -0.25rem -0.5rem;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;
  min-width: 0; /* Erlaubt Text-Truncation in Flexbox */
  max-width: 100%;
  overflow: hidden;
}

.esp-card__name-display:hover {
  background-color: var(--glass-bg);
}

.esp-card__name-display:hover .esp-card__name-pencil {
  opacity: 1;
}

.esp-card__name {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.3;
  /* Fade-out für lange Namen */
  display: block;
  max-width: 180px; /* Begrenzt Namen-Breite */
  overflow: hidden;
  white-space: nowrap;
  position: relative;
  /* Gradient-Mask für smooth Fade-out */
  mask-image: linear-gradient(to right, black 80%, transparent 100%);
  -webkit-mask-image: linear-gradient(to right, black 80%, transparent 100%);
}

/* Responsive: Kürzere max-width auf kleineren Screens */
@media (max-width: 480px) {
  .esp-card__name {
    max-width: 120px;
  }
}

.esp-card__name--empty {
  color: var(--color-text-muted);
  font-style: italic;
  font-weight: 400;
}

.esp-card__name-pencil {
  color: var(--color-text-muted);
  opacity: 0.3;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

/* Name Edit Mode */
.esp-card__name-edit {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
}

.esp-card__name-input {
  flex: 1;
  min-width: 0;
  padding: 0.375rem 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
  background-color: transparent;
  border: none;
  border-bottom: 2px solid var(--color-iridescent-1);
  outline: none;
  font-family: inherit;
}

.esp-card__name-input::placeholder {
  color: var(--color-text-muted);
  font-weight: 400;
}

.esp-card__name-input:disabled {
  opacity: 0.6;
}

.esp-card__name-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.esp-card__name-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background-color: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.esp-card__name-btn:hover:not(:disabled) {
  background-color: var(--glass-bg);
}

.esp-card__name-btn:disabled {
  cursor: not-allowed;
}

.esp-card__name-btn--save:hover:not(:disabled) {
  color: var(--color-success);
  background-color: rgba(34, 197, 94, 0.1);
}

.esp-card__name-btn--cancel:hover:not(:disabled) {
  color: var(--color-error);
  background-color: rgba(239, 68, 68, 0.1);
}

/* Name Error */
.esp-card__name-error {
  font-size: 0.75rem;
  color: var(--color-error);
  padding-left: 0.5rem;
}

/* ESP-ID Row (secondary) */
.esp-card__id-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.esp-card__id {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  text-decoration: none;
  transition: color 0.2s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.esp-card__id:hover {
  color: var(--color-iridescent-1);
}

.esp-card__status-badges {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  flex-shrink: 0;
}

/* Zone info */
.esp-card__zone {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: 2rem;
  font-size: 0.8125rem;
  transition: all 0.15s ease;
}

.esp-card__zone:hover {
  background-color: rgba(96, 165, 250, 0.08);
  border-color: rgba(96, 165, 250, 0.2);
}

.esp-card__zone--empty {
  background-color: transparent;
  border-style: dashed;
}

.esp-card__zone--empty:hover {
  background-color: var(--color-bg-tertiary);
}

.esp-card__zone-name {
  color: var(--color-text-secondary);
  font-weight: 500;
}

.esp-card__zone--empty .esp-card__zone-name {
  color: var(--color-text-muted);
  font-style: italic;
  font-weight: 400;
}

.text-accent {
  color: var(--color-iridescent-1);
}

.text-muted {
  color: var(--color-text-muted);
}

/* Data Source & Freshness Indicators */
.esp-card__data-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.375rem;
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.esp-card__data-source,
.esp-card__freshness,
.esp-card__incomplete-data {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.esp-card__data-separator {
  color: var(--color-text-muted);
  opacity: 0.5;
}

/* Freshness color states */
.freshness--live {
  color: var(--color-success);
}

.freshness--recent {
  color: var(--color-info);
}

.freshness--stale {
  color: var(--color-warning);
}

.freshness--unknown {
  color: var(--color-text-muted);
}

.esp-card__incomplete-data {
  color: var(--color-warning);
}

.text-success {
  color: var(--color-success);
}

.text-info {
  color: var(--color-info);
}

/* Quick stats grid */
.esp-card__stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
}

.esp-card__stat {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

.esp-card__stat span {
  color: var(--color-text-secondary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.esp-card__stat span.text-muted {
  color: var(--color-text-muted);
  font-weight: 400;
}

/* =============================================================================
   WiFi Bars Indicator (Phase 1)
   ============================================================================= */

.esp-card__wifi {
  cursor: help;
}

.esp-card__wifi-bars {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 16px;
}

.esp-card__wifi-bar {
  width: 3px;
  background-color: var(--color-text-muted);
  border-radius: 1px;
  opacity: 0.25;
  transition: opacity 0.2s ease, background-color 0.2s ease;
}

/* Bar heights: increasing from left to right */
.esp-card__wifi-bar:nth-child(1) { height: 4px; }
.esp-card__wifi-bar:nth-child(2) { height: 7px; }
.esp-card__wifi-bar:nth-child(3) { height: 10px; }
.esp-card__wifi-bar:nth-child(4) { height: 14px; }

/* Active bars inherit color from parent and are fully opaque */
.esp-card__wifi-bar.active {
  opacity: 1;
  background-color: currentColor;
}

/* =============================================================================
   Heartbeat Indicator (Phase 1)
   ============================================================================= */

.esp-card__heartbeat-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  background-color: transparent;
  border: 1px solid var(--glass-border);
  border-radius: 2rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.esp-card__heartbeat-indicator:hover:not(:disabled) {
  background-color: var(--glass-bg);
  border-color: rgba(244, 114, 182, 0.3);
  color: var(--color-text-secondary);
}

.esp-card__heartbeat-indicator:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Mock ESP heartbeat button - more prominent */
.esp-card__heartbeat-indicator--mock {
  border-color: rgba(244, 114, 182, 0.2);
}

.esp-card__heartbeat-indicator--mock:hover:not(:disabled) {
  background-color: rgba(244, 114, 182, 0.08);
  border-color: rgba(244, 114, 182, 0.4);
}

/* Fresh heartbeat state - green tint */
.esp-card__heartbeat-indicator--fresh {
  color: var(--color-success);
  border-color: rgba(34, 197, 94, 0.25);
}

.esp-card__heartbeat-indicator--fresh:hover:not(:disabled) {
  background-color: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.4);
}

.esp-card__heartbeat-text {
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* Heart pulse animation */
.esp-card__heart-pulse {
  animation: heart-beat 1.5s ease-in-out infinite;
  color: var(--color-iridescent-4); /* Pink heart */
}

@keyframes heart-beat {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  25% {
    transform: scale(1.2);
    opacity: 1;
  }
  50% {
    transform: scale(1);
    opacity: 0.8;
  }
  75% {
    transform: scale(1.15);
    opacity: 1;
  }
}

/* Auto-heartbeat indicator */
.esp-card__auto-heartbeat {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.esp-card__auto-heartbeat-dot {
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background-color: var(--color-text-muted);
}

.esp-card__auto-heartbeat-dot.active {
  background-color: var(--color-success);
  animation: pulse-dot 2s infinite;
}

/* Orphaned mock warning message */
.esp-card__orphaned-warning {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.75rem;
  color: var(--color-warning);
  background-color: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.2);
  border-radius: var(--radius-sm);
}

.esp-card__orphaned-warning span {
  line-height: 1.4;
}

/* Actions */
.esp-card__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--glass-border);
  margin-top: auto;
}

.esp-card__actions-left {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* Details button - subtle iridescent accent */
.esp-card__details-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-primary);
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.12), rgba(139, 92, 246, 0.08));
  border: 1px solid rgba(96, 165, 250, 0.25);
  border-radius: var(--radius-md);
  text-decoration: none;
  transition: all 0.2s ease;
}

.esp-card__details-btn:hover {
  background: linear-gradient(135deg, rgba(96, 165, 250, 0.2), rgba(139, 92, 246, 0.15));
  border-color: rgba(96, 165, 250, 0.4);
  box-shadow: 0 0 12px rgba(96, 165, 250, 0.15);
  transform: translateY(-1px);
}

.esp-card__details-btn:active {
  transform: translateY(0);
}

/* Action buttons (icon-only) */
.esp-card__action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  color: var(--color-text-muted);
  background-color: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
}

.esp-card__action-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
  background-color: var(--glass-bg);
  border-color: rgba(96, 165, 250, 0.3);
}

.esp-card__action-btn:active:not(:disabled) {
  transform: scale(0.95);
}

/* Heartbeat button - pink/red accent */
.esp-card__action-btn--heartbeat:hover:not(:disabled) {
  color: var(--color-iridescent-4);
  background-color: rgba(244, 114, 182, 0.1);
  border-color: rgba(244, 114, 182, 0.3);
}

/* Logs button - blue accent */
.esp-card__action-btn--logs {
  text-decoration: none;
}

.esp-card__action-btn--logs:hover {
  color: var(--color-info);
  background-color: rgba(59, 130, 246, 0.1);
  border-color: rgba(59, 130, 246, 0.3);
}

/* Delete button - red accent */
.esp-card__action-btn--delete:hover:not(:disabled) {
  color: var(--color-error);
  background-color: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.3);
}

/* Disabled button state */
.esp-card__action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* =============================================================================
   Satellite Dots - Compact sensor/actuator indicators
   ============================================================================= */

.esp-card__satellites {
  display: flex;
  flex-wrap: wrap;
  gap: 1rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--glass-border);
}

.esp-card__satellite-group {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.esp-card__satellite-label {
  font-size: 0.625rem;
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
  color: var(--color-text-muted);
  text-transform: uppercase;
  margin-right: 0.25rem;
  opacity: 0.7;
}

.esp-card__satellite-dot {
  width: 10px;
  height: 10px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all 0.2s ease;
}

/* Sensor dots: circles */
.esp-card__satellite-dot--sensor {
  border-radius: 50%;
}

/* Actuator dots: rounded squares */
.esp-card__satellite-dot--actuator {
  border-radius: var(--radius-xs);
}

/* State-based colors */
.esp-card__satellite-dot--good,
.esp-card__satellite-dot--on {
  background: var(--color-success);
  border-color: var(--color-success);
}

.esp-card__satellite-dot--fair {
  background: var(--color-warning);
  border-color: var(--color-warning);
}

.esp-card__satellite-dot--poor,
.esp-card__satellite-dot--emergency {
  background: var(--color-error);
  border-color: var(--color-error);
}

.esp-card__satellite-dot--off,
.esp-card__satellite-dot--unknown {
  background: var(--color-text-muted);
  border-color: var(--color-text-muted);
  opacity: 0.5;
}

/* Hover effect */
.esp-card__satellite-dot:hover {
  transform: scale(1.5);
  box-shadow: 0 0 8px currentColor;
  z-index: var(--z-dropdown);
}

/* Emergency pulsing */
.esp-card__satellite-dot--emergency {
  animation: pulse-dot 1s infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* "+X more" indicator */
.esp-card__satellite-more {
  font-size: 0.625rem;
  font-family: 'JetBrains Mono', monospace;
  color: var(--color-text-muted);
  margin-left: 0.25rem;
}

/* =============================================================================
   Offline Info Display (Phase 1 - LWT & Heartbeat Timeout)
   ============================================================================= */

.esp-card__offline-info {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: var(--radius-sm);
  cursor: help;
}

.esp-card__offline-text {
  font-weight: 600;
}

.esp-card__offline-separator {
  opacity: 0.5;
}

.esp-card__offline-time {
  font-weight: 400;
  opacity: 0.8;
}

/* LWT: Red for crash/power-loss */
.esp-card__offline-info.text-red-500 {
  background-color: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
}

/* Heartbeat Timeout: Orange for timeout */
.esp-card__offline-info.text-orange-500 {
  background-color: rgba(249, 115, 22, 0.1);
  border: 1px solid rgba(249, 115, 22, 0.2);
}

/* Shutdown: Blue for intentional */
.esp-card__offline-info.text-blue-400 {
  background-color: rgba(96, 165, 250, 0.1);
  border: 1px solid rgba(96, 165, 250, 0.2);
}
</style>





