<script setup lang="ts">
/**
 * ESPHorizontalLayout Component (formerly ESPOrbitalLayout)
 *
 * Displays sensors and actuators in a horizontal 3-column layout:
 * - Left column: Sensors (vertically stacked)
 * - Center column: ESP Card
 * - Right column: Actuators (vertically stacked)
 *
 * Features:
 * - Side-by-side layout: no overlap, all elements always visible
 * - Responsive: mobile = vertical stack, tablet/desktop = horizontal
 * - Drag & drop for adding sensors from sidebar
 * - Click to select/highlight satellites
 * - Chart panel expands within center card (not overlaying satellites)
 */

import { ref, computed, onMounted, onUnmounted, watch, watchEffect } from 'vue'
import { X, Heart, Settings2, Loader2, Pencil, Check, Database } from 'lucide-vue-next'
import ESPCard from './ESPCard.vue'
import SensorSatellite from './SensorSatellite.vue'
import ActuatorSatellite from './ActuatorSatellite.vue'
import AddSensorModal from './AddSensorModal.vue'
import AddActuatorModal from './AddActuatorModal.vue'
import AnalysisDropZone from './AnalysisDropZone.vue'
import { Badge } from '@/shared/design/primitives'
import ZoneAssignmentDropdown from './ZoneAssignmentDropdown.vue'
import type { ESPDevice } from '@/api/esp'
import type { MockSensor, MockActuator, ChartSensor } from '@/types'
import { useEspStore } from '@/stores/esp'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { useLogicStore } from '@/shared/stores/logic.store'
import { useZoneDragDrop } from '@/composables/useZoneDragDrop'
import { useDeviceActions } from '@/composables/useDeviceActions'
import { useGpioStatus } from '@/composables/useGpioStatus'
import { useOrbitalDragDrop } from '@/composables/useOrbitalDragDrop'

interface Props {
  /** The ESP device data */
  device: ESPDevice
  /** Whether to show connection lines (default: true) */
  showConnections?: boolean
  /** Compact mode for dashboard view (default: false) */
  compactMode?: boolean
  /** Actuator layout mode: stacked (default) or 2-column grid */
  actuatorLayout?: 'stack' | 'grid'
}

const props = withDefaults(defineProps<Props>(), {
  showConnections: true,
  compactMode: false,
  actuatorLayout: 'stack',
})

const espStore = useEspStore()
const dragStore = useDragStateStore()
const logicStore = useLogicStore()
const { handleDeviceDrop, handleRemoveFromZone, getAvailableZones } = useZoneDragDrop()

const emit = defineEmits<{
  sensorClick: [payload: { configId?: string; gpio: number; sensorType: string }]
  actuatorClick: [gpio: number]
  sensorDropped: [sensor: ChartSensor]
  /** Heartbeat request (Mock ESPs only) */
  heartbeat: [device: ESPDevice]
  /** Delete request - opens confirmation dialog */
  delete: [device: ESPDevice]
  /** Settings popover request */
  settings: [device: ESPDevice]
  /** Name was updated via inline edit */
  'name-updated': [payload: { deviceId: string; name: string | null }]
}>()

/** Live device from esp.store — props alone can lag behind WS patches (AUT-580 L2). */
const liveDevice = computed(() => {
  void espStore.devicesLiveTick
  const id = espStore.getDeviceId(props.device)
  return espStore.devices.find((entry) => espStore.getDeviceId(entry) === id) ?? props.device
})

// ── Device Actions (shared composable) ───────────────────────────────
const actions = useDeviceActions(() => liveDevice.value)
const {
  espId, isMock, displayName, isOnline, systemState, stateInfo,
  wifiInfo, wifiColorClass, wifiDisplayLabel, wifiTooltip,
  heartbeatLoading, isHeartbeatFresh, heartbeatTooltip, heartbeatText,
  isEditingName, editedName, isSavingName, saveError, nameInputRef,
  startEditName, cancelEditName, handleNameKeydown,
} = actions

// GPIO Status for dynamic GPIO selection (Phase 5)
useGpioStatus(espId)

// ── Drag & Drop (extracted composable) ───────────────────────────────
const {
  onDragEnter, onDragOver, onDragLeave, onDrop,
  isDragOver,
  showAddSensorModal, showAddActuatorModal,
  droppedSensorType, droppedActuatorType,
  analysisExpanded, wasAutoOpened,
} = useOrbitalDragDrop(espId)

// =============================================================================
// Zone Assignment (Dropdown alternative to drag)
// =============================================================================
const availableZones = computed(() => getAvailableZones(espStore.devices))

async function handleZoneChanged(_deviceId: string, zoneId: string | null) {
  if (zoneId === null) {
    await handleRemoveFromZone(liveDevice.value)
  } else {
    await handleDeviceDrop({
      device: liveDevice.value,
      fromZoneId: liveDevice.value.zone_id || null,
      toZoneId: zoneId,
    })
  }
}

// Handle sensor dropped into analysis zone
function handleSensorDrop(sensor: ChartSensor) {
  emit('sensorDropped', sensor)
}

// =============================================================================
// Refs
// =============================================================================
const containerRef = ref<HTMLElement | null>(null)
const centerRef = ref<HTMLElement | null>(null)

// Selected satellite state
const selectedGpio = ref<number | null>(null)
const selectedType = ref<'sensor' | 'actuator' | null>(null)

// =============================================================================
// Computed: Device Data
// =============================================================================
const sensors = computed<MockSensor[]>(() => {
  return (liveDevice.value.sensors as MockSensor[]) || []
})

const actuators = computed<MockActuator[]>(() => {
  return (liveDevice.value.actuators as MockActuator[]) || []
})

const actuatorRuntimeMap = computed(() => {
  const map: Record<number, { lastTriggeredAt?: string | null; triggerReason?: string | null; triggerRuleName?: string | null }> = {}
  for (const actuator of actuators.value) {
    const lastExecution = logicStore.getLastExecutionForActuator(espId.value, actuator.gpio)
    if (!lastExecution) continue
    map[actuator.gpio] = {
      lastTriggeredAt: lastExecution.triggered_at,
      triggerReason: lastExecution.trigger_reason ?? null,
      triggerRuleName: lastExecution.rule_name ?? null,
    }
  }
  return map
})

const totalItems = computed(() => {
  return sensors.value.length + actuators.value.length
})

/** Merged sorted satellite list: sensors (sorted) followed by actuators */
const sortedSatellites = computed(() => {
  const sensorItems = [...sensors.value]
    .sort((a, b) => {
      const typeCompare = (a.sensor_type || '').localeCompare(b.sensor_type || '')
      if (typeCompare !== 0) return typeCompare
      return (a.i2c_address ?? 0) - (b.i2c_address ?? 0)
    })
    .map(s => ({ ...s, kind: 'sensor' as const, key: s.config_id || `sensor-${s.gpio}-${s.sensor_type}` }))

  const actuatorItems = [...actuators.value]
    .map(a => ({ ...a, kind: 'actuator' as const, key: `actuator-${a.gpio}` }))

  return [...sensorItems, ...actuatorItems]
})

/** Normalized (cos/sin) orbit positions per satellite — CSS handles pixel calculation via --orbit-radius */
const orbitPositions = computed(() => {
  const total = sortedSatellites.value.length
  if (total === 0) return []
  return sortedSatellites.value.map((sat, index) => {
    const angle = (2 * Math.PI * index) / total - Math.PI / 2
    return {
      ...sat,
      txNorm: Math.round(Math.cos(angle) * 10000) / 10000,
      tyNorm: Math.round(Math.sin(angle) * 10000) / 10000,
      transitionDelay: `${index * 0.07}s`,
    }
  })
})

const visibleSatellites = ref(false)
const containerW = ref(720)
const containerH = ref(420)
// CSS-derived base orbit radii (from --orbit-radius breakpoints, NOT sat-count adjusted)
const orbitRadiusX = ref(270)
const orbitRadiusY = ref(210)
let orbitalResizeObserver: ResizeObserver | null = null

// Minimum orbit rx so adjacent satellites don't overlap (card width 150px + 10px gap).
// Computed from the tightest pair on an N-satellite ellipse with given aspect ratio.
function computeMinOrbitRX(n: number, rxBase: number, ryBase: number): number {
  if (n <= 2) return rxBase
  const angleStep = (2 * Math.PI) / n
  const k = ryBase / Math.max(rxBase, 1)
  const dFactor = Math.sqrt(
    Math.pow(1 - Math.cos(angleStep), 2) +
    Math.pow(k * Math.sin(angleStep), 2),
  )
  return dFactor > 0 ? 160 / dFactor : rxBase
}

// Effective orbit radii: scale up uniformly when satellite count demands it
const effectiveRX = computed(() => {
  const minRX = computeMinOrbitRX(sortedSatellites.value.length, orbitRadiusX.value, orbitRadiusY.value)
  return Math.max(orbitRadiusX.value, minRX)
})

const effectiveRY = computed(() => {
  if (orbitRadiusX.value <= 0) return orbitRadiusY.value
  return orbitRadiusY.value * (effectiveRX.value / orbitRadiusX.value)
})

// Keep CSS custom properties in sync so satellite transforms stay correct
watchEffect(() => {
  const el = containerRef.value
  if (!el) return
  el.style.setProperty('--orbit-radius-x', `${Math.round(effectiveRX.value)}px`)
  el.style.setProperty('--orbit-radius-y', `${Math.round(effectiveRY.value)}px`)
})

onMounted(() => {
  requestAnimationFrame(() => { visibleSatellites.value = true })
  if (containerRef.value) {
    orbitalResizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (!entry) return
      containerW.value = entry.contentRect.width
      containerH.value = entry.contentRect.height
      // Read the RAW --orbit-radius base (not the JS-overridden --orbit-radius-x/y)
      const cs = window.getComputedStyle(entry.target)
      const base = parseFloat(cs.getPropertyValue('--orbit-radius').trim()) || 280
      orbitRadiusX.value = Math.max(270, base * 1.3)
      orbitRadiusY.value = Math.max(150, base * 0.75)
    })
    orbitalResizeObserver.observe(containerRef.value)
  }
})

watch(
  () => sortedSatellites.value.length,
  () => {
    visibleSatellites.value = false
    requestAnimationFrame(() => { visibleSatellites.value = true })
  },
)

onUnmounted(() => {
  orbitalResizeObserver?.disconnect()
  orbitalResizeObserver = null
})

// =============================================================================
// Event Handlers
// =============================================================================

/** Heartbeat click: trigger + emit */
async function handleHeartbeatClick() {
  await actions.triggerHeartbeat()
  emit('heartbeat', props.device)
}

/** Settings click -> emit to parent */
function handleSettingsClick() {
  emit('settings', props.device)
}

/** Save name + emit */
async function saveName() {
  const result = await actions.saveName()
  if (result) emit('name-updated', result)
}

function handleSensorClick(payload: { configId?: string; gpio: number; sensorType: string }) {
  // Emit to parent (HardwareView) -> opens SensorConfigPanel in SlideOver
  emit('sensorClick', payload)
}

function handleActuatorClick(gpio: number) {
  if (selectedGpio.value === gpio && selectedType.value === 'actuator') {
    selectedGpio.value = null
    selectedType.value = null
  } else {
    selectedGpio.value = gpio
    selectedType.value = 'actuator'
  }
  emit('actuatorClick', gpio)
}
</script>

<template>
  <div
    ref="containerRef"
    class="esp-horizontal-layout"
    :class="{
      'esp-horizontal-layout--has-items': totalItems > 0,
      'esp-horizontal-layout--can-drop': dragStore.isDraggingSensorType || dragStore.isDraggingActuatorType,
      'esp-horizontal-layout--drag-over': isDragOver
    }"
    :data-esp-id="espId"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
  >
    <!-- Orbital SVG Overlay: decorative orbit ellipse + radial connection lines (S6) -->
    <svg
      class="esp-orbital-svg"
      :width="containerW"
      :height="containerH"
      :viewBox="`0 0 ${containerW} ${containerH}`"
      aria-hidden="true"
    >
      <ellipse
        class="esp-orbital-svg__ring"
        :cx="containerW / 2"
        :cy="containerH / 2"
        :rx="effectiveRX"
        :ry="effectiveRY"
      />
      <line
        v-for="sat in orbitPositions"
        :key="`line-${sat.key}`"
        class="esp-orbital-svg__line"
        :class="{ 'esp-orbital-svg__line--visible': visibleSatellites }"
        :x1="containerW / 2"
        :y1="containerH / 2"
        :x2="containerW / 2 + sat.txNorm * effectiveRX"
        :y2="containerH / 2 + sat.tyNorm * effectiveRY"
        :style="{ 'transition-delay': sat.transitionDelay, 'animation-delay': sat.transitionDelay }"
      />
    </svg>

    <!-- Radial Satellites (Sensors + Actuators) -->
    <div
      v-for="sat in orbitPositions"
      :key="sat.kind === 'sensor'
        ? `${sat.key}-${sat.last_read ?? ''}-${sat.raw_value ?? ''}`
        : `${sat.key}-${sat.state}-${sat.pwm_value ?? 0}`"
      class="satellite-card"
      :class="{ 'satellite-card--visible': visibleSatellites }"
      :style="{ '--tx-norm': sat.txNorm, '--ty-norm': sat.tyNorm, 'transition-delay': sat.transitionDelay }"
    >
      <SensorSatellite
        v-if="sat.kind === 'sensor'"
        :esp-id="espId"
        :gpio="sat.gpio"
        :sensor-type="sat.sensor_type"
        :name="sat.name"
        :value="sat.processed_value ?? sat.raw_value ?? 0"
        :quality="sat.quality"
        :unit="sat.unit"
        :device-type="sat.device_type"
        :multi-values="sat.multi_values"
        :is-multi-value="sat.is_multi_value"
        :i2c-address="sat.i2c_address"
        :interface-type="sat.interface_type"
        :device-scope="sat.device_scope"
        :assigned-zones="sat.assigned_zones ?? undefined"
        :selected="selectedGpio === sat.gpio && selectedType === 'sensor'"
        :show-connections="showConnections"
        @click="() => handleSensorClick({ configId: sat.config_id, gpio: sat.gpio, sensorType: sat.sensor_type })"
      />
      <ActuatorSatellite
        v-else
        :esp-id="espId"
        :gpio="sat.gpio"
        :actuator-type="sat.actuator_type"
        :hardware-type="sat.hardware_type"
        :name="sat.name"
        :state="sat.state"
        :pwm-value="sat.pwm_value"
        :last-command-at="sat.last_command_at"
        :last-triggered-at="actuatorRuntimeMap[sat.gpio]?.lastTriggeredAt"
        :trigger-reason="actuatorRuntimeMap[sat.gpio]?.triggerReason"
        :trigger-rule-name="actuatorRuntimeMap[sat.gpio]?.triggerRuleName"
        :emergency-stopped="sat.emergency_stopped"
        :device-scope="sat.device_scope"
        :assigned-zones="sat.assigned_zones ?? undefined"
        :selected="selectedGpio === sat.gpio && selectedType === 'actuator'"
        :show-connections="showConnections"
        @click="handleActuatorClick(sat.gpio)"
      />
    </div>

    <!-- Center: ESP Card (orbital center) -->
    <div ref="centerRef" class="esp-orbital-center">
      <!-- Compact Mode: Simple Info Card -->
      <div
        v-if="compactMode"
        :class="['esp-info-compact', isMock ? 'esp-info-compact--mock' : 'esp-info-compact--real']"
      >
        <!-- Header is the drag handle for VueDraggable (esp-drag-handle class) -->
        <div class="esp-info-compact__header esp-drag-handle">
          <!-- Top Row: Name + Settings -->
          <div class="esp-info-compact__top-row">
            <!-- Name Editing (Phase 3) - Edit Mode -->
            <template v-if="isEditingName">
              <div class="esp-info-compact__name-edit" data-no-drag>
                <input
                  ref="nameInputRef"
                  v-model="editedName"
                  type="text"
                  class="esp-info-compact__name-input"
                  placeholder="Gerätename..."
                  :disabled="isSavingName"
                  @keydown="handleNameKeydown"
                  @blur="saveName"
                  @click.stop
                />
                <div class="esp-info-compact__name-actions">
                  <button
                    v-if="isSavingName"
                    class="esp-info-compact__name-btn"
                    disabled
                  >
                    <Loader2 class="w-3 h-3 animate-spin" />
                  </button>
                  <template v-else>
                    <button
                      class="esp-info-compact__name-btn esp-info-compact__name-btn--save"
                      title="Speichern (Enter)"
                      @mousedown.prevent="saveName"
                    >
                      <Check class="w-3 h-3" />
                    </button>
                    <button
                      class="esp-info-compact__name-btn esp-info-compact__name-btn--cancel"
                      title="Abbrechen (Escape)"
                      @mousedown.prevent="cancelEditName"
                    >
                      <X class="w-3 h-3" />
                    </button>
                  </template>
                </div>
              </div>
            </template>

            <!-- Name Display Mode (double-click to edit) -->
            <template v-else>
              <div
                class="esp-info-compact__name-display"
                :title="displayName ? `${displayName}\n(Doppelklick zum Bearbeiten)` : 'Doppelklick zum Bearbeiten'"
                @dblclick.stop="startEditName"
              >
                <h3 :class="['esp-info-compact__title', { 'esp-info-compact__title--empty': !displayName }]">
                  {{ displayName || 'Unbenannt' }}
                </h3>
                <Pencil class="esp-info-compact__name-pencil w-3 h-3" />
              </div>
            </template>

            <!-- Settings Icon - always top right -->
            <button
              class="esp-info-compact__settings-btn"
              title="Einstellungen"
              @click.stop="handleSettingsClick"
            >
              <Settings2 class="w-4 h-4" />
            </button>
          </div>

          <!-- Name Edit Error Message -->
          <span v-if="saveError" class="esp-info-compact__name-error">{{ saveError }}</span>

          <!-- Info Row: Type Badge, ESP-ID, Status, WiFi -->
          <div class="esp-info-compact__info-row">
            <Badge :variant="isMock ? 'mock' : 'real'" size="xs">
              {{ isMock ? 'Simuliert' : 'Hardware' }}
            </Badge>
            <span class="esp-info-compact__id">{{ espId }}</span>
            <Badge
              :variant="stateInfo.variant as any"
              :pulse="isOnline && (systemState === 'OPERATIONAL' || device.status === 'online')"
              dot
              size="xs"
            >
              {{ stateInfo.label }}
            </Badge>
            <!-- WiFi Signal Bars -->
            <div class="esp-info-compact__wifi" :title="wifiTooltip">
              <div :class="['esp-info-compact__wifi-bars', wifiColorClass]">
                <span :class="['esp-info-compact__wifi-bar', { active: wifiInfo.bars >= 1 }]" />
                <span :class="['esp-info-compact__wifi-bar', { active: wifiInfo.bars >= 2 }]" />
                <span :class="['esp-info-compact__wifi-bar', { active: wifiInfo.bars >= 3 }]" />
                <span :class="['esp-info-compact__wifi-bar', { active: wifiInfo.bars >= 4 }]" />
              </div>
              <span :class="['esp-info-compact__wifi-label', wifiColorClass]">{{ wifiDisplayLabel }}</span>
            </div>
            <!-- AUT-716: Offline-Spool pending badge -->
            <Badge
              v-if="(device.spool_pending_count ?? 0) > 0"
              variant="warning"
              size="xs"
              :title="`Offline-Spool: ${device.spool_pending_count} Einträge ausstehend (nach Reconnect synchronisiert)`"
            >
              <Database class="w-3 h-3 mr-0.5" />
              {{ device.spool_pending_count }}
            </Badge>
          </div>

          <!-- Zone Assignment Dropdown -->
          <ZoneAssignmentDropdown
            :device="device"
            :zones="availableZones"
            @zone-changed="handleZoneChanged"
          />

          <!-- Heartbeat Row -->
          <button
            :class="[
              'esp-info-compact__heartbeat',
              { 'esp-info-compact__heartbeat--fresh': isHeartbeatFresh },
              { 'esp-info-compact__heartbeat--mock': isMock }
            ]"
            :title="heartbeatTooltip"
            :disabled="heartbeatLoading"
            @click.stop="handleHeartbeatClick"
          >
            <Heart
              :class="[
                'w-3 h-3',
                isHeartbeatFresh ? 'esp-info-compact__heart-pulse' : ''
              ]"
            />
            <span class="esp-info-compact__heartbeat-text">
              {{ heartbeatText }}
            </span>
            <Loader2 v-if="heartbeatLoading" class="w-3 h-3 animate-spin" />
          </button>
        </div>

        <!--
          Analysis Drop Zone - Opens automatically on sensor drag.
          Always in DOM (no v-if!), only hidden/shown via CSS.
        -->
        <AnalysisDropZone
          :esp-id="espId"
          :max-sensors="4"
          :compact="true"
          :class="[
            'esp-info-compact__dropzone',
            {
              'esp-info-compact__dropzone--visible': analysisExpanded,
              'esp-info-compact__dropzone--overlay': wasAutoOpened && analysisExpanded
            }
          ]"
          @sensor-added="handleSensorDrop"
        />
      </div>

      <!-- Full Mode: Full ESP Card (for detail view) -->
      <ESPCard v-else :esp="device" />
    </div>

    <!-- Drop Indicator Overlay (Phase 2B: for all ESPs) -->
    <Transition name="fade">
      <div v-if="isDragOver" class="esp-horizontal-layout__drop-indicator">
        <span class="esp-horizontal-layout__drop-text">{{ dragStore.isDraggingActuatorType ? 'Aktor hinzufügen' : 'Sensor hinzufügen' }}</span>
      </div>
    </Transition>
  </div>

  <!-- Add Sensor Modal (extracted component) -->
  <AddSensorModal
    v-model="showAddSensorModal"
    :esp-id="espId"
    :initial-sensor-type="droppedSensorType"
    @added="() => { droppedSensorType = null; espStore.fetchDevice(espId); espStore.fetchGpioStatus(espId) }"
  />

  <!-- Add Actuator Modal (extracted component) -->
  <AddActuatorModal
    v-model="showAddActuatorModal"
    :esp-id="espId"
    :initial-actuator-type="droppedActuatorType"
    @added="() => { droppedActuatorType = null; espStore.fetchDevice(espId); espStore.fetchGpioStatus(espId) }"
  />
</template>

<style scoped src="./ESPOrbitalLayout.css"></style>
