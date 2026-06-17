<script setup lang="ts">
/**
 * ESPSettingsSheet Component
 *
 * Reines Informations-Panel (Level 1). Keine Konfiguration, keine Links zu
 * SensorConfigPanel/ActuatorConfigPanel. Konfiguration ausschliesslich ueber
 * Level 2 (Orbital → Sensor-/Aktor-Card klicken).
 *
 * Layout: Einheitlich mit Design-Tokens, kompakt, Geräte nach Subzone gruppiert.
 */

import { ref, computed, onUnmounted, watch, nextTick } from 'vue'
import {
  X,
  Heart,
  Wifi,
  HardDrive,
  Clock,
  MapPin,
  Trash2,
  Loader2,
  AlertTriangle,
  Bell,
  Info,
  Settings2,
  Pencil,
  Check,
  Timer,
  Tag,
  Activity,
  Thermometer,
  ChevronRight,
} from 'lucide-vue-next'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import { Badge, AccordionSection } from '@/shared/design/primitives'
import ZoneAssignmentPanel from '@/components/zones/ZoneAssignmentPanel.vue'
import ZoneSwitchDialog from '@/components/zones/ZoneSwitchDialog.vue'
import DeviceAlertConfigSection from '@/components/devices/DeviceAlertConfigSection.vue'
import type { ESPDevice } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { useUiStore } from '@/shared/stores'
import { useESPStatus, getESPStatus } from '@/composables/useESPStatus'
import { useIntentSignalsStore } from '@/shared/stores/intentSignals.store'
import { espHealthPresentation } from '@/domain/esp/espHealth'
import { useToast } from '@/composables/useToast'
import { getWifiStrength, type WifiStrengthInfo } from '@/utils/wifiStrength'
import { formatUptimeShort, formatHeapSize } from '@/utils/formatters'
import { getSensorLabel, getSensorUnit, getSensorDisplayName, getSensorConfig } from '@/utils/sensorDefaults'
import { createLogger } from '@/utils/logger'

const log = createLogger('ESPSettings')

interface Props {
  /** The ESP device data */
  device: ESPDevice
  /** Whether the sheet is open */
  isOpen: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  'update:isOpen': [value: boolean]
  'name-updated': [payload: { deviceId: string; name: string }]
  'zone-updated': [payload: { deviceId: string; zoneId: string; zoneName: string }]
  deleted: [payload: { deviceId: string }]
  'heartbeat-triggered': [payload: { deviceId: string }]
  /** AUT-251: Drilldown to subzone (consumer should open SubzoneContextEditor when available) */
  'subzone-drilldown': [payload: { subzoneId: string; subzoneName: string }]
}>()

/**
 * AUT-251: Subzone-Drilldown aus der "Subzonen-Übersicht".
 * Emittiert Event nach oben — Consumer kann SubzoneContextEditor öffnen, falls vorhanden.
 */
function handleSubzoneDrilldown(subzoneId: string, subzoneName: string) {
  emit('subzone-drilldown', { subzoneId, subzoneName })
}

// =============================================================================
// REFS & STORE
// =============================================================================

const espStore = useEspStore()
const uiStore = useUiStore()
const intentSignalsStore = useIntentSignalsStore()
const { success: showSuccess, error: showError } = useToast()

// Status via useESPStatus (single source of truth)
const { statusColor, statusText, statusPulse, isMock, lastSeenText, configLastReject, hasConfigReject } = useESPStatus(() => props.device)

// AUT-134 PKG-04: Config-Reject Reason-Code → menschenlesbares Label
const configRejectReasonLabel = computed(() => {
  const r = configLastReject.value
  if (!r) return ''
  switch (r.reason_code) {
    case 'config_oversize':
    case 'PAYLOAD_TOO_LARGE':
      return 'Konfiguration zu groß'
    default:
      return r.reason_code
  }
})

const configRejectSizeText = computed(() => {
  const r = configLastReject.value
  if (!r) return ''
  if (r.payload_size_bytes !== null && r.budget_bytes !== null) {
    return `${r.payload_size_bytes} / ${r.budget_bytes} Bytes`
  }
  if (r.payload_size_bytes !== null) {
    return `${r.payload_size_bytes} Bytes`
  }
  return ''
})

const configRejectSourceLabel = computed(() => {
  const r = configLastReject.value
  if (!r) return ''
  return r.source === 'config_failed' ? 'Server' : 'Gerät'
})

// Loading states
const heartbeatLoading = ref(false)
const deleteLoading = ref(false)

// Name editing state
const isEditingName = ref(false)
const editedName = ref('')
const isSavingName = ref(false)
const saveError = ref('')
const nameInputRef = ref<HTMLInputElement | null>(null)

// Zone error state
const zoneError = ref('')

// Zone switch dialog state
const showZoneSwitchDialog = ref(false)
const pendingZoneAssign = ref<{ zoneId: string; zoneName: string } | null>(null)
const activeSubzoneStrategy = ref<'transfer' | 'copy' | 'reset' | undefined>(undefined)

// Auto-Heartbeat state
const autoHeartbeatEnabled = ref(false)
const autoHeartbeatInterval = ref(60)
const autoHeartbeatLoading = ref(false)

// =============================================================================
// COMPUTED
// =============================================================================

const espId = computed(() => props.device?.device_id || props.device?.esp_id || '')

const healthPresentation = computed(() => {
  const vm = props.device?.runtime_health_view
  if (!vm) return null
  const st = getESPStatus(props.device)
  const onlineLike = st === 'online' || st === 'stale'
  return espHealthPresentation(vm, onlineLike)
})
const runtimeHealthDetails = computed(() => {
  const lines = healthPresentation.value?.tooltipLines ?? []
  return lines.filter(line => line !== 'Keine Degradations-Marker gesetzt')
})

const intentDisplay = computed(() => intentSignalsStore.getDisplayForEsp(espId.value))

const displayName = computed(() => props.device?.name || espId.value)

const deviceType = computed(() => {
  if (isMock.value) {
    return (props.device as any).hardware_type || 'MOCK_ESP32_WROOM'
  }
  return props.device?.hardware_type || 'ESP32'
})

const wifiInfo = computed<WifiStrengthInfo>(() => getWifiStrength(props.device?.wifi_rssi))

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

const isHeartbeatFresh = computed(() => {
  const timestamp = props.device?.last_heartbeat || props.device?.last_seen
  if (!timestamp) return false
  const now = Date.now()
  const then = new Date(timestamp).getTime()
  const diffSec = Math.floor((now - then) / 1000)
  return diffSec >= 0 && diffSec < 30
})

const uptimeDisplay = computed(() => {
  if (props.device?.uptime === undefined) return null
  return formatUptimeShort(props.device.uptime)
})

const heapDisplay = computed(() => {
  if (props.device?.heap_free === undefined) return null
  return formatHeapSize(props.device.heap_free)
})

const zoneDisplay = computed(() => {
  return props.device?.zone_name || props.device?.zone_id || null
})

// =============================================================================
// DEVICE LIST BY SUBZONE (read-only, no config links)
// =============================================================================

interface SubzoneGroup {
  subzoneId: string | null
  subzoneName: string
  items: Array<{
    type: 'sensor' | 'actuator'
    name: string
    gpio: number
    typeLabel: string
    value?: string
    unit?: string
    state?: boolean
  }>
}

function formatSensorValue(sensor: any): string {
  const val = sensor.raw_value ?? sensor.value
  if (val === null || val === undefined) return '--'
  const num = Number(val)
  if (isNaN(num)) return String(val)
  const dec = getSensorConfig(sensor.sensor_type ?? sensor.type ?? '')?.decimals ?? 2
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  }).format(num)
}

/**
 * Resolve effective subzone for a device (sensor or actuator).
 *
 * Priority:
 * 1. Direct subzone_id FK (if set)
 * 2. GPIO match against subzone assigned_gpios (gpio > 0 only, I2C excluded)
 * 3. Fallback to null ("Keine Subzone")
 *
 * GPIO 0 is an I2C placeholder and must not match assigned_gpios.
 */
function getEffectiveSubzoneId(
  device: { gpio: number; subzone_id?: string | null },
  subzones: Array<{ subzone_id: string; assigned_gpios: number[] }>,
): string | null {
  if (device.subzone_id) {
    return device.subzone_id
  }
  if (device.gpio > 0) {
    for (const sz of subzones) {
      if (sz.assigned_gpios?.includes(device.gpio)) {
        return sz.subzone_id
      }
    }
  }
  return null
}

const devicesBySubzone = computed<SubzoneGroup[]>(() => {
  const d = props.device as any
  const deviceSensors = d?.sensors ?? []
  const deviceActuators = d?.actuators ?? []
  const deviceSubzones = props.device?.subzones ?? []

  // Build subzone name lookup from device.subzones (SubzoneSummary[])
  const subzoneNameMap = new Map<string, string>()
  for (const sz of deviceSubzones) {
    if (sz.subzone_id && sz.subzone_name) {
      subzoneNameMap.set(sz.subzone_id, sz.subzone_name)
    }
  }

  function resolveSubzoneName(szId: string | null): string {
    if (szId === null) return 'Keine Subzone'
    return subzoneNameMap.get(szId) || szId
  }

  const map = new Map<string | null, { subzoneName: string; items: SubzoneGroup['items'] }>()

  function getOrCreateGroup(szId: string | null) {
    if (!map.has(szId)) {
      map.set(szId, {
        subzoneName: resolveSubzoneName(szId),
        items: [],
      })
    }
    return map.get(szId)!
  }

  for (const sensor of deviceSensors) {
    const szId = getEffectiveSubzoneId(sensor, deviceSubzones)
    const g = getOrCreateGroup(szId)
    g.items.push({
      type: 'sensor',
      name: getSensorDisplayName({ sensor_type: sensor.sensor_type || sensor.type || '', name: sensor.name }) || getSensorLabel(sensor.sensor_type || sensor.type || ''),
      gpio: sensor.gpio,
      typeLabel: getSensorLabel(sensor.sensor_type || sensor.type || ''),
      value: formatSensorValue(sensor),
      unit: sensor.unit || getSensorUnit(sensor.sensor_type || sensor.type || ''),
    })
  }

  for (const actuator of deviceActuators) {
    const szId = getEffectiveSubzoneId(actuator, deviceSubzones)
    const g = getOrCreateGroup(szId)
    g.items.push({
      type: 'actuator',
      name: actuator.name || actuator.actuator_type || actuator.type || 'Aktor',
      gpio: actuator.gpio,
      typeLabel: actuator.actuator_type || actuator.type || 'Relay',
      state: actuator.state,
    })
  }

  const groups: SubzoneGroup[] = []
  for (const [szId, { subzoneName, items }] of map) {
    groups.push({
      subzoneId: szId,
      subzoneName,
      items,
    })
  }

  groups.sort((a, b) => {
    if (a.subzoneId === null) return 1
    if (b.subzoneId === null) return -1
    return (a.subzoneName ?? '').localeCompare(b.subzoneName ?? '')
  })

  return groups
})

// =============================================================================
// METHODS
// =============================================================================

function close() {
  emit('update:isOpen', false)
  emit('close')
}

async function handleHeartbeat() {
  if (!isMock.value || heartbeatLoading.value) return

  heartbeatLoading.value = true
  try {
    await espStore.triggerHeartbeat(espId.value)
    emit('heartbeat-triggered', { deviceId: espId.value })
  } catch (err) {
    log.error('Failed to trigger heartbeat', err)
  } finally {
    setTimeout(() => {
      heartbeatLoading.value = false
    }, 500)
  }
}

async function handleDelete() {
  const confirmed = await uiStore.confirm({
    title: 'Gerät löschen',
    message: `Möchtest du "${displayName.value}" wirklich löschen? ${isMock.value ? 'Der simulierte ESP wird vollständig entfernt.' : 'Das Gerät und alle zugehörigen Sensoren/Aktoren werden aus der Datenbank entfernt.'}`,
    variant: 'danger',
    confirmText: 'Löschen',
  })
  if (!confirmed) return

  deleteLoading.value = true
  try {
    await espStore.deleteDevice(espId.value)
    showSuccess(`"${displayName.value}" wurde gelöscht`)
    emit('deleted', { deviceId: espId.value })
    close()
  } catch (err) {
    showError(err instanceof Error ? err.message : 'Gerät konnte nicht gelöscht werden')
    log.error('Failed to delete device', err)
  } finally {
    deleteLoading.value = false
  }
}

// =============================================================================
// NAME EDITING
// =============================================================================

function startEditName() {
  editedName.value = props.device?.name || ''
  isEditingName.value = true
  saveError.value = ''
  nextTick(() => {
    nameInputRef.value?.focus()
    nameInputRef.value?.select()
  })
}

function cancelEditName() {
  isEditingName.value = false
  editedName.value = ''
  saveError.value = ''
}

async function saveName() {
  if (isSavingName.value) return

  const newName = editedName.value.trim() || null
  const deviceId = espId.value

  if (newName === (props.device?.name || null)) {
    cancelEditName()
    return
  }

  isSavingName.value = true
  saveError.value = ''

  try {
    await espStore.updateDevice(deviceId, { name: newName })
    isEditingName.value = false
    emit('name-updated', { deviceId, name: newName || '' })
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { detail?: string } } }
    saveError.value = axiosError.response?.data?.detail || 'Fehler beim Speichern'
    setTimeout(() => {
      saveError.value = ''
    }, 3000)
  } finally {
    isSavingName.value = false
  }
}

function handleNameKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter') {
    event.preventDefault()
    saveName()
  } else if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    cancelEditName()
  }
}

// =============================================================================
// ZONE MANAGEMENT
// =============================================================================

/**
 * Intercept zone changes: if device already has a zone, open ZoneSwitchDialog.
 * ZoneAssignmentPanel emits 'zone-before-save' with the pending zone data.
 */
function handleZoneBeforeSave(zoneData: { zone_id: string; zone_name: string }) {
  const hasExistingZone = !!(props.device?.zone_id)
  if (hasExistingZone && zoneData.zone_id !== props.device?.zone_id) {
    // Device already in a zone — ask user for subzone strategy
    pendingZoneAssign.value = { zoneId: zoneData.zone_id, zoneName: zoneData.zone_name }
    showZoneSwitchDialog.value = true
  } else {
    // No existing zone or same zone — proceed directly
    activeSubzoneStrategy.value = undefined
  }
}

function handleZoneSwitchConfirm(strategy: 'transfer' | 'copy' | 'reset') {
  activeSubzoneStrategy.value = strategy
  showZoneSwitchDialog.value = false
  pendingZoneAssign.value = null
}

function handleZoneSwitchClose() {
  showZoneSwitchDialog.value = false
  pendingZoneAssign.value = null
}

function handleZoneUpdated(zoneData: { zone_id: string; zone_name?: string; master_zone_id?: string }) {
  zoneError.value = ''
  activeSubzoneStrategy.value = undefined
  emit('zone-updated', {
    deviceId: espId.value,
    zoneId: zoneData.zone_id,
    zoneName: zoneData.zone_name || zoneData.zone_id,
  })
}

function handleZoneError(error: string) {
  zoneError.value = error
  setTimeout(() => {
    zoneError.value = ''
  }, 5000)
}

// =============================================================================
// AUTO-HEARTBEAT MANAGEMENT
// =============================================================================

async function handleAutoHeartbeatToggle() {
  if (!isMock.value || autoHeartbeatLoading.value) return

  autoHeartbeatLoading.value = true
  const newEnabled = !autoHeartbeatEnabled.value

  try {
    await espStore.setAutoHeartbeat(
      espId.value,
      newEnabled,
      autoHeartbeatInterval.value
    )
    autoHeartbeatEnabled.value = newEnabled
  } catch (err) {
    log.error('Failed to toggle auto-heartbeat', err)
    autoHeartbeatEnabled.value = !newEnabled
  } finally {
    autoHeartbeatLoading.value = false
  }
}

async function handleIntervalChange() {
  if (!isMock.value || !autoHeartbeatEnabled.value || autoHeartbeatLoading.value) return

  const interval = Math.max(10, Math.min(300, autoHeartbeatInterval.value))
  autoHeartbeatInterval.value = interval

  autoHeartbeatLoading.value = true

  try {
    await espStore.setAutoHeartbeat(espId.value, true, interval)
  } catch (err) {
    log.error('Failed to update interval', err)
  } finally {
    autoHeartbeatLoading.value = false
  }
}

// =============================================================================
// LIFECYCLE & WATCHERS
// =============================================================================

function syncAutoHeartbeatFromStore() {
  const currentDeviceId = espId.value
  if (!currentDeviceId) return

  const storeDevice = espStore.devices.find(
    d => (d.device_id || d.esp_id) === currentDeviceId
  )
  const deviceAutoHB = storeDevice?.auto_heartbeat ?? (props.device as any)?.auto_heartbeat

  autoHeartbeatEnabled.value = deviceAutoHB ?? false
}

watch(
  () => props.isOpen,
  (isOpen) => {
    if (isOpen) {
      syncAutoHeartbeatFromStore()
      uiStore.pushModal('esp-settings-sheet')
    } else {
      uiStore.popModal('esp-settings-sheet')
    }
  }
)

// Sync when device changes while sheet is open
watch(
  () => props.device?.device_id || props.device?.esp_id,
  (newId, oldId) => {
    if (newId && newId !== oldId && props.isOpen) {
      syncAutoHeartbeatFromStore()
    }
  }
)

// Watch store value for auto-heartbeat sync
watch(
  () => {
    const currentId = espId.value
    if (!currentId) return undefined
    const device = espStore.devices.find(d => (d.device_id || d.esp_id) === currentId)
    return device?.auto_heartbeat
  },
  (newVal) => {
    if (props.isOpen && newVal !== undefined) {
      if (autoHeartbeatEnabled.value !== newVal) {
        autoHeartbeatEnabled.value = newVal
      }
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  uiStore.popModal('esp-settings-sheet')
})
</script>

<template>
  <SlideOver
    :open="isOpen"
    title="Geräte-Einstellungen"
    width="lg"
    @close="close"
  >
    <div class="sheet-body">
      <!-- IDENTIFICATION Section -->
      <section class="sheet-section">
        <h4 class="sheet-section__title">
          <Tag class="w-3.5 h-3.5" />
          Identifikation
        </h4>
        <div class="sheet-section__content">
          <!-- Name (Editable) -->
          <div class="info-row info-row--name">
            <span class="info-row__label">Name</span>

            <!-- Edit Mode -->
            <template v-if="isEditingName">
              <div class="name-edit">
                <input
                  ref="nameInputRef"
                  v-model="editedName"
                  type="text"
                  class="name-edit__input"
                  placeholder="Gerätename eingeben..."
                  :disabled="isSavingName"
                  @keydown="handleNameKeydown"
                  @blur="saveName"
                />
                <div class="name-edit__actions">
                  <button
                    v-if="isSavingName"
                    class="name-edit__btn"
                    disabled
                  >
                    <Loader2 class="w-4 h-4 animate-spin" />
                  </button>
                  <template v-else>
                    <button
                      class="name-edit__btn name-edit__btn--save"
                      title="Speichern (Enter)"
                      @mousedown.prevent="saveName"
                    >
                      <Check class="w-4 h-4" />
                    </button>
                    <button
                      class="name-edit__btn name-edit__btn--cancel"
                      title="Abbrechen (Escape)"
                      @mousedown.prevent="cancelEditName"
                    >
                      <X class="w-4 h-4" />
                    </button>
                  </template>
                </div>
              </div>
            </template>

            <!-- Display Mode -->
            <template v-else>
              <div
                class="name-display"
                title="Klicken zum Bearbeiten"
                @click="startEditName"
              >
                <span :class="['info-row__value info-row__value--name', { 'info-row__value--empty': !displayName }]">
                  {{ displayName || 'Unbenannt' }}
                </span>
                <Pencil class="name-display__pencil w-4 h-4" />
              </div>
            </template>
          </div>

          <!-- Name Error Message -->
          <div v-if="saveError" class="name-edit__error">
            {{ saveError }}
          </div>

          <!-- ESP-ID -->
          <div class="info-row">
            <span class="info-row__label">ESP-ID</span>
            <code class="info-row__value info-row__value--mono">{{ espId }}</code>
          </div>

          <!-- Type -->
          <div class="info-row">
            <span class="info-row__label">Typ</span>
            <div class="info-row__value">
              <Badge :variant="isMock ? 'mock' : 'real'" size="sm">
                {{ isMock ? 'MOCK' : 'REAL' }}
              </Badge>
              <span class="text-muted text-sm ml-2">{{ deviceType }}</span>
            </div>
          </div>
        </div>
      </section>

      <!-- STATUS Section (uses useESPStatus) -->
      <section class="sheet-section">
        <h4 class="sheet-section__title">
          <Activity class="w-3.5 h-3.5" />
          Status
        </h4>
        <div class="sheet-section__content">
          <!-- Online Status with dot + text (like DeviceMiniCard) -->
          <div class="info-row">
            <span class="info-row__label">Verbindung</span>
            <div class="status-display">
              <span
                class="status-dot"
                :class="{ 'status-dot--pulse': statusPulse }"
                :style="{ backgroundColor: statusColor }"
              />
              <span class="status-text" :style="{ color: statusColor }">{{ statusText }}</span>
              <Badge
                v-if="healthPresentation?.showBadge"
                variant="warning"
                size="sm"
                class="ml-2"
                :title="healthPresentation.tooltipLines.join('\n')"
              >
                {{ healthPresentation.badgeLabel }}
              </Badge>
            </div>
          </div>

          <div v-if="intentDisplay && (intentDisplay.lifecycleSummary || intentDisplay.resultSummary || intentDisplay.correlationShort)" class="info-row info-row--stack">
            <span class="info-row__label">Vorgang</span>
            <div class="info-row__value esp-settings__intent-block">
              <p v-if="intentDisplay.lifecycleSummary" class="text-sm text-muted m-0">
                {{ intentDisplay.lifecycleSummary }}
              </p>
              <p v-if="intentDisplay.resultSummary" class="text-sm m-0">
                {{ intentDisplay.resultSummary }}
              </p>
              <p v-if="intentDisplay.firmwareCode" class="text-xs text-muted m-0 mt-1">
                Firmware-Code: {{ intentDisplay.firmwareCode }}
              </p>
              <p class="text-xs text-muted m-0 mt-1 font-mono">
                ID: {{ intentDisplay.correlationShort }}
              </p>
            </div>
          </div>

          <!-- Last Heartbeat (always visible) -->
          <div class="info-row">
            <span class="info-row__label">
              <Heart class="w-4 h-4 inline mr-1" />
              Heartbeat
            </span>
            <span :class="['info-row__value', isHeartbeatFresh ? 'text-success' : '']">
              {{ lastSeenText }}
            </span>
          </div>

          <!-- Details (accordion) -->
          <AccordionSection
            title="Status-Details"
            storage-key="esp-settings-status-details"
            :icon="Activity"
          >
            <!-- WiFi Signal -->
            <div class="info-row">
              <span class="info-row__label">
                <Wifi class="w-4 h-4 inline mr-1" />
                WiFi
              </span>
              <div class="info-row__value wifi-display">
                <div :class="['wifi-bars', wifiColorClass]">
                  <span :class="['wifi-bar', { active: wifiInfo.bars >= 1 }]" />
                  <span :class="['wifi-bar', { active: wifiInfo.bars >= 2 }]" />
                  <span :class="['wifi-bar', { active: wifiInfo.bars >= 3 }]" />
                  <span :class="['wifi-bar', { active: wifiInfo.bars >= 4 }]" />
                </div>
                <span :class="wifiColorClass">{{ wifiInfo.label }}</span>
                <span v-if="device.wifi_rssi" class="text-muted text-xs ml-1">
                  ({{ device.wifi_rssi }} dBm)
                </span>
              </div>
            </div>

            <!-- Heap Memory -->
            <div v-if="heapDisplay" class="info-row">
              <span class="info-row__label">
                <HardDrive class="w-4 h-4 inline mr-1" />
                Speicher
              </span>
              <span class="info-row__value">{{ heapDisplay }} frei</span>
            </div>

            <!-- Uptime -->
            <div v-if="uptimeDisplay" class="info-row">
              <span class="info-row__label">
                <Clock class="w-4 h-4 inline mr-1" />
                Uptime
              </span>
              <span class="info-row__value">{{ uptimeDisplay }}</span>
            </div>

            <!-- Geräte-Telemetrie (Heartbeat-Zusatzfelder) -->
            <template v-if="device.runtime_health_view">
              <p v-if="runtimeHealthDetails.length > 0" class="text-xs text-muted mt-2 mb-1">
                Laufzeit-Details (Geräte-Telemetrie)
              </p>
              <ul v-if="runtimeHealthDetails.length > 0" class="esp-settings__telemetry-list text-xs text-muted m-0 pl-4">
                <li v-for="line in runtimeHealthDetails" :key="line">
                  {{ line }}
                </li>
              </ul>
              <p
                v-if="healthPresentation?.recommendedAction"
                class="esp-settings__recommended-action text-xs m-0 mt-2"
              >
                <strong>Nächster Schritt:</strong> {{ healthPresentation.recommendedAction }}
              </p>
              <details v-if="Object.keys(device.runtime_health_view.rawTelemetry).length > 0" class="esp-settings__raw-tel mt-2">
                <summary class="text-xs cursor-pointer text-muted">Weitere Telemetrie-Schlüssel</summary>
                <ul class="text-xs font-mono m-0 mt-1 pl-4 max-h-32 overflow-y-auto">
                  <li v-for="(val, key) in device.runtime_health_view.rawTelemetry" :key="key">
                    {{ key }}: {{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}
                  </li>
                </ul>
              </details>
            </template>

            <!-- AUT-134 PKG-04: Letzter Config-Reject (terminale UI-Sichtbarkeit, separat von runtime_health) -->
            <div
              v-if="hasConfigReject && configLastReject"
              class="esp-settings__config-reject"
              :title="`Letzter Config-Reject — ${configRejectReasonLabel}`"
            >
              <div class="esp-settings__config-reject-header">
                <AlertTriangle class="w-3.5 h-3.5" />
                <span class="esp-settings__config-reject-title">Letzter Config-Reject</span>
                <Badge variant="warning" size="sm">{{ configRejectReasonLabel }}</Badge>
              </div>
              <ul class="esp-settings__config-reject-list text-xs text-muted m-0 mt-1 pl-4">
                <li v-if="configRejectSizeText">Größe: {{ configRejectSizeText }}</li>
                <li>Quelle: {{ configRejectSourceLabel }}</li>
                <li v-if="configLastReject.correlation_id">
                  Korrelation: <span class="font-mono">{{ configLastReject.correlation_id }}</span>
                </li>
                <li>Zeitpunkt: {{ configLastReject.timestamp }}</li>
              </ul>
              <p class="esp-settings__config-reject-hint text-xs m-0 mt-1">
                <strong>Hinweis:</strong> Konfiguration wurde abgelehnt. Reduziere Regelumfang
                oder prüfe das Server-Log. Kein automatischer Retry.
              </p>
            </div>
          </AccordionSection>
        </div>
      </section>

      <!-- ZONE Section -->
      <section class="sheet-section">
        <h4 class="sheet-section__title">
          <MapPin class="w-3.5 h-3.5" />
          Zone
        </h4>
        <div class="sheet-section__content">
          <div v-if="zoneDisplay" class="info-row info-row--compact">
            <span class="info-row__label">Aktuell</span>
            <Badge variant="success" size="sm">{{ zoneDisplay }}</Badge>
          </div>

          <ZoneAssignmentPanel
            :esp-id="espId"
            :current-zone-id="device.zone_id ?? undefined"
            :current-zone-name="device.zone_name ?? undefined"
            :current-master-zone-id="device.master_zone_id ?? undefined"
            :is-mock="isMock"
            :subzone-strategy="activeSubzoneStrategy"
            compact
            @zone-before-save="handleZoneBeforeSave"
            @zone-updated="handleZoneUpdated"
            @zone-error="handleZoneError"
          />

          <p class="sheet-hint">
            <Info class="w-3 h-3" />
            Zone kann auch via Drag &amp; Drop geändert werden.
          </p>
        </div>
      </section>

      <!-- Alert-Konfiguration (Gerät) -->
      <section v-if="espId" class="sheet-section">
        <AccordionSection
          title="Alert-Konfiguration (Gerät)"
          storage-key="esp-settings-alert-config"
          :icon="Bell"
        >
          <DeviceAlertConfigSection :esp-id="espId" />
        </AccordionSection>
      </section>

      <!-- Subzonen-Übersicht (read-only) — AUT-251 -->
      <section v-if="devicesBySubzone.length > 0" class="sheet-section">
        <h4 class="sheet-section__title">
          <Thermometer class="w-3.5 h-3.5" />
          Subzonen-Übersicht
        </h4>
        <p class="sheet-section__hint">
          Welche Subzonen mit Sensoren/Aktoren dieses Gerätes verknüpft sind. Read-only.
        </p>
        <div class="sheet-section__content">
          <div
            v-for="group in devicesBySubzone"
            :key="group.subzoneId ?? 'none'"
            class="device-group"
          >
            <button
              v-if="group.subzoneId"
              type="button"
              class="device-group__title device-group__title--clickable"
              :aria-label="`Subzone ${group.subzoneName} öffnen`"
              @click="handleSubzoneDrilldown(group.subzoneId, group.subzoneName)"
            >
              <span>{{ group.subzoneName }}</span>
              <ChevronRight class="device-group__drilldown-icon" />
            </button>
            <h5 v-else class="device-group__title">{{ group.subzoneName }}</h5>
            <ul class="device-list">
              <li
                v-for="(item, idx) in group.items"
                :key="`${item.type}-${item.gpio}-${idx}`"
                class="device-list__item"
              >
                <span class="device-list__name">{{ item.name }}</span>
                <span class="device-list__meta">{{ item.typeLabel }} · GPIO {{ item.gpio }}</span>
                <span v-if="item.type === 'sensor'" class="device-list__value">
                  {{ item.value }} {{ item.unit }}
                </span>
                <Badge
                  v-else
                  :variant="item.state ? 'success' : 'gray'"
                  size="sm"
                  dot
                >
                  {{ item.state ? 'AN' : 'AUS' }}
                </Badge>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- MOCK CONTROLS Section -->
      <section v-if="isMock" class="sheet-section sheet-section--mock">
        <AccordionSection
          title="Mock-Steuerung"
          storage-key="esp-settings-mock-controls"
          :icon="Settings2"
          default-open
        >
          <button
            class="action-btn action-btn--heartbeat"
            :disabled="heartbeatLoading"
            @click="handleHeartbeat"
          >
            <Loader2 v-if="heartbeatLoading" class="w-4 h-4 animate-spin" />
            <Heart v-else class="w-4 h-4" />
            <span>{{ heartbeatLoading ? 'Wird gesendet...' : 'Heartbeat senden' }}</span>
          </button>

          <!-- Auto-Heartbeat Toggle -->
          <div class="auto-heartbeat">
            <div class="auto-heartbeat__row">
              <div class="auto-heartbeat__label">
                <Timer class="w-4 h-4" />
                <span>Automatische Heartbeats</span>
              </div>
              <button
                :class="[
                  'auto-heartbeat__toggle',
                  { 'auto-heartbeat__toggle--active': autoHeartbeatEnabled }
                ]"
                :disabled="autoHeartbeatLoading"
                @click="handleAutoHeartbeatToggle"
              >
                <span class="auto-heartbeat__toggle-knob" />
              </button>
            </div>

            <Transition name="slide-fade">
              <div v-if="autoHeartbeatEnabled" class="auto-heartbeat__interval">
                <label class="auto-heartbeat__interval-label">
                  Intervall:
                  <input
                    v-model.number="autoHeartbeatInterval"
                    type="number"
                    min="10"
                    max="300"
                    class="auto-heartbeat__interval-input"
                    :disabled="autoHeartbeatLoading"
                    @change="handleIntervalChange"
                  />
                  <span class="auto-heartbeat__interval-unit">Sek.</span>
                </label>
                <Loader2 v-if="autoHeartbeatLoading" class="w-3 h-3 animate-spin text-muted" />
              </div>
            </Transition>
          </div>

          <p class="text-muted text-xs mt-2">
            <template v-if="autoHeartbeatEnabled">
              Heartbeats werden automatisch alle {{ autoHeartbeatInterval }} Sekunden gesendet.
            </template>
            <template v-else>
              Mock ESPs senden keine automatischen Heartbeats.
              Aktiviere diese Option fuer regelmaessige Updates.
            </template>
          </p>
        </AccordionSection>
      </section>

      <!-- Echt-ESP-Info -->
      <section v-if="!isMock" class="sheet-section sheet-section--info">
        <h4 class="sheet-section__title">Echt-ESP-Info</h4>
        <div class="sheet-section__content">
          <p class="text-muted text-sm">
            <Info class="w-4 h-4 inline mr-1" />
            Dieses Geraet sendet automatisch alle 60 Sekunden einen Heartbeat.
            Sensor- und Aktor-Daten werden in Echtzeit ueber MQTT synchronisiert.
          </p>
        </div>
      </section>

      <!-- DANGER ZONE (uses ConfirmDialog via uiStore.confirm) -->
      <section class="sheet-section sheet-section--danger">
        <h4 class="sheet-section__title">
          <AlertTriangle class="w-4 h-4 inline mr-1" />
          Gefahrenzone
        </h4>
        <div class="sheet-section__content">
          <button
            class="action-btn action-btn--danger-outline"
            :disabled="deleteLoading"
            @click="handleDelete"
          >
            <Loader2 v-if="deleteLoading" class="w-4 h-4 animate-spin" />
            <Trash2 v-else class="w-4 h-4" />
            <span>Gerät löschen</span>
          </button>
        </div>
      </section>
    </div>

    <!-- Zone Switch Strategy Dialog -->
    <ZoneSwitchDialog
      :is-open="showZoneSwitchDialog"
      :device-name="displayName"
      :current-zone-name="device.zone_name || device.zone_id || ''"
      :target-zone-name="pendingZoneAssign?.zoneName || ''"
      @close="handleZoneSwitchClose"
      @confirm="handleZoneSwitchConfirm"
    />
  </SlideOver>
</template>

<style scoped>
/* =============================================================================
   BODY (inside SlideOver content slot)
   ============================================================================= */

.sheet-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* =============================================================================
   SECTIONS
   ============================================================================= */

.sheet-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sheet-section__title {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
  margin: 0;
  padding-bottom: var(--space-1);
  border-bottom: 1px solid var(--glass-border);
}

.sheet-section__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* AUT-251: Hinweistext unterhalb Sektions-Titel */
.sheet-section__hint {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  margin: var(--space-1) 0;
  font-style: italic;
}

.sheet-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: var(--space-1) 0 0;
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.sheet-section--mock {
  background-color: rgba(168, 85, 247, 0.04);
  border: 1px solid rgba(168, 85, 247, 0.15);
  border-radius: var(--radius-md);
  padding: 0.875rem;
}

.sheet-section--mock .sheet-section__title {
  color: var(--color-mock);
  border-color: rgba(168, 85, 247, 0.2);
}

.sheet-section--info {
  background-color: rgba(96, 165, 250, 0.04);
  border: 1px solid rgba(96, 165, 250, 0.15);
  border-radius: var(--radius-md);
  padding: 0.875rem;
}

.sheet-section--info .sheet-section__title {
  color: var(--color-info);
  border-color: rgba(96, 165, 250, 0.2);
}

.sheet-section--danger {
  background-color: rgba(239, 68, 68, 0.04);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: var(--radius-md);
  padding: 0.875rem;
}

.sheet-section--danger .sheet-section__title {
  color: var(--color-error);
  border-color: rgba(239, 68, 68, 0.2);
}

/* =============================================================================
   INFO ROWS
   ============================================================================= */

.info-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  min-height: 28px;
}

.info-row__label {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.info-row__value {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  font-weight: 500;
  text-align: right;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.info-row__value--name {
  font-weight: 600;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.info-row__value--empty {
  color: var(--color-text-muted);
  font-style: italic;
  font-weight: 400;
}

/* =============================================================================
   STATUS DISPLAY (dot + text, like DeviceMiniCard)
   ============================================================================= */

.status-display {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.status-dot--pulse {
  animation: status-pulse 2s ease-in-out infinite;
}

@keyframes status-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-size: 0.8125rem;
  font-weight: 500;
}

/* =============================================================================
   NAME EDITING
   ============================================================================= */

.info-row--name { flex-wrap: wrap; }

.name-display {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  margin: -0.25rem -0.5rem;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease;
}

.name-display:hover { background-color: var(--glass-bg); }
.name-display:hover .name-display__pencil { opacity: 1; }

.name-display__pencil {
  color: var(--color-text-muted);
  opacity: 0.3;
  transition: opacity 0.15s ease;
  flex-shrink: 0;
}

.name-edit {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex: 1;
  min-width: 0;
}

.name-edit__input {
  flex: 1;
  min-width: 0;
  padding: 0.375rem 0.5rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: var(--color-text-primary);
  background-color: transparent;
  border: none;
  border-bottom: 2px solid var(--color-iridescent-1);
  outline: none;
  font-family: inherit;
}

.name-edit__input::placeholder {
  color: var(--color-text-muted);
  font-weight: 400;
}

.name-edit__input:disabled { opacity: 0.6; }

.name-edit__actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}

.name-edit__btn {
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

.name-edit__btn:hover:not(:disabled) { background-color: var(--glass-bg); }
.name-edit__btn:disabled { cursor: not-allowed; }

.name-edit__btn--save:hover:not(:disabled) {
  color: var(--color-success);
  background-color: rgba(34, 197, 94, 0.1);
}

.name-edit__btn--cancel:hover:not(:disabled) {
  color: var(--color-error);
  background-color: rgba(239, 68, 68, 0.1);
}

.name-edit__error {
  width: 100%;
  font-size: 0.75rem;
  color: var(--color-error);
  margin-top: 0.25rem;
}

.info-row__value--mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  background-color: var(--color-bg-tertiary);
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
}

.info-row--compact {
  min-height: 24px;
}

.info-row--zone-current {
  padding-bottom: var(--space-2);
  margin-bottom: var(--space-1);
  border-bottom: 1px solid var(--glass-border);
}

/* =============================================================================
   DEVICE LIST (Geräte nach Subzone — read-only, compact)
   ============================================================================= */

.device-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.device-group__title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  margin: 0;
  padding: 0 var(--space-1);
}

/* AUT-251: Drilldown auf benannte Subzonen */
.device-group__title--clickable {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  color: var(--color-iridescent-1);
  text-decoration: underline;
  text-decoration-style: dotted;
  text-underline-offset: 2px;
  transition: color var(--transition-fast);
}

.device-group__title--clickable:hover {
  color: var(--color-text-primary);
}

.device-group__title--clickable:focus-visible {
  outline: 2px solid var(--color-iridescent-1);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

.device-group__drilldown-icon {
  width: 12px;
  height: 12px;
  opacity: 0.7;
}

.device-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.device-list__item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

.device-list__name {
  font-weight: 500;
  color: var(--color-text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-list__meta {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.device-list__value {
  font-family: 'JetBrains Mono', monospace;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  flex-shrink: 0;
}

/* =============================================================================
   WIFI DISPLAY
   ============================================================================= */

.wifi-display { display: flex; align-items: center; gap: 0.375rem; }

.wifi-bars { display: flex; align-items: flex-end; gap: 2px; height: 14px; }

.wifi-bar {
  width: 3px;
  background-color: var(--color-text-muted);
  border-radius: 1px;
  opacity: 0.25;
  transition: opacity 0.2s ease, background-color 0.2s ease;
}

.wifi-bar:nth-child(1) { height: 3px; }
.wifi-bar:nth-child(2) { height: 6px; }
.wifi-bar:nth-child(3) { height: 9px; }
.wifi-bar:nth-child(4) { height: 12px; }

.wifi-bar.active { opacity: 1; background-color: currentColor; }

/* =============================================================================
   ACTION BUTTONS
   ============================================================================= */

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.15s ease;
  border: none;
  width: 100%;
}

.action-btn:disabled { opacity: 0.6; cursor: not-allowed; }

.action-btn--heartbeat {
  background: linear-gradient(135deg, rgba(244, 114, 182, 0.15), rgba(168, 85, 247, 0.1));
  border: 1px solid rgba(244, 114, 182, 0.3);
  color: var(--color-iridescent-4);
}

.action-btn--heartbeat:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(244, 114, 182, 0.25), rgba(168, 85, 247, 0.15));
  border-color: rgba(244, 114, 182, 0.5);
  transform: translateY(-1px);
}

.action-btn--danger-outline {
  background: transparent;
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: var(--color-error);
}

.action-btn--danger-outline:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.5);
}

/* =============================================================================
   AUTO-HEARTBEAT
   ============================================================================= */

.auto-heartbeat {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 0.75rem;
  background-color: rgba(168, 85, 247, 0.06);
  border: 1px solid rgba(168, 85, 247, 0.15);
  border-radius: var(--radius-md);
  margin-top: 0.5rem;
}

.auto-heartbeat__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.auto-heartbeat__label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.auto-heartbeat__toggle {
  position: relative;
  width: 48px;
  height: 26px;
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.auto-heartbeat__toggle:hover:not(:disabled) {
  border-color: rgba(168, 85, 247, 0.4);
  background-color: var(--color-bg-hover);
}

.auto-heartbeat__toggle:disabled { opacity: 0.5; cursor: not-allowed; }

.auto-heartbeat__toggle--active {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.4), rgba(139, 92, 246, 0.3));
  border-color: rgba(168, 85, 247, 0.5);
}

.auto-heartbeat__toggle-knob {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  background-color: var(--color-text-secondary);
  border-radius: 50%;
  transition: all 0.2s ease;
}

.auto-heartbeat__toggle--active .auto-heartbeat__toggle-knob {
  left: 25px;
  background-color: var(--color-mock);
  box-shadow: 0 0 8px rgba(167, 139, 250, 0.6);
}

.auto-heartbeat__interval { display: flex; align-items: center; gap: 0.5rem; }

.auto-heartbeat__interval-label {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.auto-heartbeat__interval-input {
  width: 60px;
  padding: 0.25rem 0.375rem;
  font-size: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xs);
  text-align: center;
}

.auto-heartbeat__interval-input:focus {
  outline: none;
  border-color: var(--color-iridescent-1);
}

.auto-heartbeat__interval-input:disabled { opacity: 0.5; cursor: not-allowed; }
.auto-heartbeat__interval-unit { color: var(--color-text-muted); }

/* Slide-fade transition */
.slide-fade-enter-active,
.slide-fade-leave-active { transition: all 0.2s ease; }

.slide-fade-enter-from,
.slide-fade-leave-to { opacity: 0; transform: translateY(-8px); }

/* =============================================================================
   COLOR UTILITIES
   ============================================================================= */

.text-iridescent { color: var(--color-iridescent-1); }
.text-success { color: var(--color-success); }
.text-muted { color: var(--color-text-muted); }

.text-emerald-400 { color: var(--color-success); }
.text-yellow-400 { color: var(--color-warning); }
.text-orange-400 { color: var(--color-warning); }
.text-red-400 { color: var(--color-error); }
.text-slate-500 { color: var(--color-text-muted); }

.text-sm { font-size: 0.8125rem; }
.text-xs { font-size: 0.75rem; }
.ml-1 { margin-left: 0.25rem; }
.ml-2 { margin-left: 0.5rem; }
.mt-2 { margin-top: 0.5rem; }

.esp-settings__recommended-action {
  color: var(--color-warning);
}

/* AUT-134 PKG-04: Config-Reject Block — terminales Operator-Ergebnis */
.esp-settings__config-reject {
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  border-left: 3px solid var(--color-warning);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md, 0.375rem);
}

.esp-settings__config-reject-header {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--color-warning);
}

.esp-settings__config-reject-title {
  font-size: 0.75rem;
  font-weight: 600;
}

.esp-settings__config-reject-list {
  list-style: disc;
}

.esp-settings__config-reject-hint {
  color: var(--color-text-secondary);
}
</style>
