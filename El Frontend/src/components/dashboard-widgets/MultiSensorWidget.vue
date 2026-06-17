<script setup lang="ts">
/**
 * MultiSensorWidget — Multi-sensor chart widget for dashboard
 *
 * Two modes:
 * - Manual: user picks individual sensors via chip-based UI
 * - Compare: user picks sensorType + zone, system auto-fills
 *   all matching subzone sensors as overlay chart with subzone labels
 */
import { ref, computed, watch, shallowRef, onMounted, onUnmounted, nextTick } from 'vue'
import { useEspStore } from '@/stores/esp'
import { useZoneStore } from '@/shared/stores/zone.store'
import MultiSensorChart from '@/components/charts/MultiSensorChart.vue'
import type { ActuatorOverlay, ActuatorOverlayBlock, ActuatorOverlayEvent } from '@/components/charts/MultiSensorChart.vue'
import { BarChart3, Plus, X, Download, GitCompareArrows, Zap } from 'lucide-vue-next'
import { CHART_COLORS, getChartColors } from '@/utils/chartColors'
import { SENSOR_TYPE_CONFIG } from '@/utils/sensorDefaults'
import { useSensorOptions } from '@/composables/useSensorOptions'
import { useExportCsv } from '@/composables/useExportCsv'
import { useToast } from '@/composables/useToast'
import { parseSensorId } from '@/composables/useSensorId'
import { getAutoResolution, TIME_RANGE_MINUTES } from '@/utils/autoResolution'
import { tokens } from '@/utils/cssTokens'
import { actuatorsApi } from '@/api/actuators'
import type { ActuatorHistoryEntry } from '@/api/actuators'
import {
  ACTUATOR_TIME_RANGE_MS,
  ACTUATOR_TIME_RANGE_LIMITS,
  isActuatorOn,
  isActuatorOff,
} from '@/composables/useActuatorHistory'
import type { MockSensor, MockActuator, ChartSensor } from '@/types'

interface Props {
  /** Comma-separated sensor IDs: "espId:gpio:sensorType,espId:gpio:sensorType" */
  dataSources?: string
  zoneId?: string
  title?: string
  timeRange?: '1h' | '6h' | '24h' | '7d'
  /** Compare mode: auto-fill sensors by sensorType + zone */
  compareMode?: boolean
  /** Sensor type to compare across subzones (e.g. "sht31_temp") */
  compareSensorType?: string
  /** Zone filter for compare mode; empty = use dashboard zoneId */
  compareZoneId?: string
  /** Comma-separated actuator IDs: "espId:gpio:actuatorType" (max 2, P8-A6c) */
  actuatorIds?: string
}

const props = withDefaults(defineProps<Props>(), {
  timeRange: '24h',
})

const emit = defineEmits<{
  'update:config': [config: Record<string, any>]
}>()

const espStore = useEspStore()
const zoneStore = useZoneStore()
const { exportSensorCsv, isExporting } = useExportCsv()
const toast = useToast()
const resolvedChartColors = getChartColors()
const chartColorPalette = resolvedChartColors.length > 0 ? resolvedChartColors : [...CHART_COLORS]

// Local state — survives render() one-shot props (Bug 1b pattern)
const localDataSources = ref(props.dataSources || '')
const localTimeRange = ref(props.timeRange)
const localZoneId = ref<string | undefined>(props.zoneId)
const localCompareMode = ref(props.compareMode ?? false)
const localCompareSensorType = ref(props.compareSensorType || '')
const localCompareZoneId = ref(props.compareZoneId || '')

const localActuatorIds = ref(props.actuatorIds || '')

watch(() => props.dataSources, (v) => { if (v) localDataSources.value = v })
watch(() => props.timeRange, (v) => { if (v) localTimeRange.value = v })
watch(() => props.zoneId, (v) => { localZoneId.value = v })
watch(() => props.compareMode, (v) => { if (v != null) localCompareMode.value = v })
watch(() => props.compareSensorType, (v) => { if (v) localCompareSensorType.value = v })
watch(() => props.compareZoneId, (v) => { if (v) localCompareZoneId.value = v })
watch(() => props.actuatorIds, (v) => { if (v != null) localActuatorIds.value = v })

// --- Manual mode sensor options ---
const { groupedSensorOptions, flatSensorOptions } = useSensorOptions(localZoneId)

// --- Compare mode ---
const effectiveCompareZoneId = computed(() =>
  localCompareZoneId.value || localZoneId.value || ''
)
const compareZoneIdRef = computed(() => effectiveCompareZoneId.value || undefined)
const { groupedSensorOptions: compareGroupedOptions } = useSensorOptions(compareZoneIdRef)

/** Available sensor types within the selected compare zone */
const availableCompareSensorTypes = computed(() => {
  const typeMap = new Map<string, string>()
  for (const zone of compareGroupedOptions.value) {
    for (const subgroup of zone.subgroups) {
      for (const opt of subgroup.options) {
        if (!typeMap.has(opt.sensorType)) {
          typeMap.set(opt.sensorType, SENSOR_TYPE_CONFIG[opt.sensorType]?.label || opt.sensorType)
        }
      }
    }
  }
  return [...typeMap.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label))
})

/** Auto-filled sensors for compare mode (max 4, sorted alphabetically by subzone) */
const compareSensors = computed(() => {
  if (!localCompareMode.value || !localCompareSensorType.value) return []

  const raw = compareGroupedOptions.value
    .flatMap(zone => zone.subgroups)
    .flatMap(subzone =>
      subzone.options
        .filter(opt => opt.sensorType === localCompareSensorType.value)
        .map(opt => ({
          sensorId: opt.value,
          subzoneName: subzone.label || 'Zone-weit',
          subzoneId: subzone.subzoneId,
        }))
    )

  return [...raw]
    .sort((a, b) => a.subzoneName.localeCompare(b.subzoneName))
    .slice(0, 4)
})

// Parse selected sensor IDs from comma-separated string (manual mode)
const selectedSensorIds = computed(() => {
  if (!localDataSources.value) return []
  return localDataSources.value.split(',').filter(Boolean)
})

// Build ChartSensor[] for MultiSensorChart
const chartSensors = computed<ChartSensor[]>(() => {
  if (localCompareMode.value) {
    // Compare mode: build from auto-filled compareSensors
    return compareSensors.value
      .map((cs, index) => {
        const parsed = parseSensorId(cs.sensorId)
        if (!parsed.isValid || !parsed.espId || parsed.gpio === null) return null

        const device = espStore.devices.find(d => espStore.getDeviceId(d) === parsed.espId)
        const sensor = device
          ? ((device.sensors as MockSensor[]) || []).find(s =>
              s.gpio === parsed.gpio && (!parsed.sensorType || s.sensor_type === parsed.sensorType)
            )
          : null
        const sensorType = parsed.sensorType || 'unknown'

        return {
          id: `${parsed.espId}_${parsed.gpio}_${sensorType}`,
          espId: parsed.espId,
          gpio: parsed.gpio,
          sensorType,
          name: cs.subzoneName,
          unit: sensor?.unit || SENSOR_TYPE_CONFIG[sensorType]?.unit || '',
          color: chartColorPalette[index % chartColorPalette.length] as string,
        }
      })
      .filter((s): s is ChartSensor => s !== null)
  }

  // Manual mode: parse from dataSources via parseSensorId (filter invalid)
  const result: ChartSensor[] = []
  selectedSensorIds.value.forEach((sId, idx) => {
    const parsed = parseSensorId(sId)
    if (!parsed.isValid || !parsed.espId || parsed.gpio === null) return

    const device = espStore.devices.find(d => espStore.getDeviceId(d) === parsed.espId)
    const sensor = device
      ? ((device.sensors as MockSensor[]) || []).find(s =>
          s.gpio === parsed.gpio && (!parsed.sensorType || s.sensor_type === parsed.sensorType)
        )
      : null
    const sensorType = parsed.sensorType || sensor?.sensor_type || 'unknown'
    result.push({
      id: `${parsed.espId}_${parsed.gpio}_${sensorType}`,
      espId: parsed.espId,
      gpio: parsed.gpio,
      sensorType,
      name: sensor?.name || sensor?.sensor_type || `GPIO ${parsed.gpio}`,
      unit: sensor?.unit || SENSOR_TYPE_CONFIG[sensorType]?.unit || '',
      color: chartColorPalette[idx % chartColorPalette.length] as string,
    })
  })
  return result
})

// Available sensors excluding already selected ones (manual mode)
const availableSensors = computed(() =>
  flatSensorOptions.value.filter(s => !selectedSensorIds.value.includes(s.id))
)

const showAddDropdown = ref(false)
const chartHostRef = ref<HTMLElement | null>(null)
const chartHostHeight = ref(300)
let chartResizeObserver: ResizeObserver | null = null

const configuredActuatorCount = computed(() =>
  localActuatorIds.value.split(',').map(id => id.trim()).filter(Boolean).length
)

const chartMinHeight = computed(() => {
  const sensorCount = chartSensors.value.length
  let minHeight = 170

  if (sensorCount > 2) {
    minHeight += Math.min((sensorCount - 2) * 14, 56)
  }
  if (configuredActuatorCount.value > 0) {
    minHeight += 20
  }
  if (localCompareMode.value) {
    minHeight += 12
  }

  return Math.min(minHeight, 280)
})

const effectiveChartHeight = computed(() =>
  Math.max(chartMinHeight.value, Math.round(chartHostHeight.value))
)

function updateChartHostHeight(): void {
  const host = chartHostRef.value
  if (!host) return
  const nextHeight = Math.floor(host.getBoundingClientRect().height)
  if (nextHeight > 0) {
    chartHostHeight.value = nextHeight
  }
}

function addSensor(sensorId: string) {
  const ids = [...selectedSensorIds.value, sensorId]
  localDataSources.value = ids.join(',')
  emit('update:config', { dataSources: localDataSources.value })
  showAddDropdown.value = false
}

function removeSensor(sensorId: string) {
  const ids = selectedSensorIds.value.filter(id => id !== sensorId)
  localDataSources.value = ids.join(',')
  emit('update:config', { dataSources: localDataSources.value })
}

function toggleCompareMode() {
  localCompareMode.value = !localCompareMode.value
  emit('update:config', { compareMode: localCompareMode.value })
}

function updateCompareSensorType(value: string) {
  localCompareSensorType.value = value
  emit('update:config', { compareSensorType: value })
}

function updateCompareZoneId(value: string) {
  localCompareZoneId.value = value
  emit('update:config', { compareZoneId: value })
}

// --- CSV Export ---
function getZoneName(): string | undefined {
  if (!localZoneId.value) return undefined
  return zoneStore.zoneEntities.find(z => z.zone_id === localZoneId.value)?.name
}

async function handleExportAll() {
  const sensors = chartSensors.value
  if (sensors.length === 0) return

  const rangeMinutes = TIME_RANGE_MINUTES[localTimeRange.value] ?? 1440
  const resolution = getAutoResolution(rangeMinutes) ?? 'raw'
  const endTime = new Date()
  const startTime = new Date(endTime.getTime() - rangeMinutes * 60 * 1000)
  const zoneName = getZoneName()

  let downloadCount = 0
  for (let i = 0; i < sensors.length; i++) {
    const sensor = sensors[i]
    const parsed = parseSensorId(`${sensor.espId}:${sensor.gpio}:${sensor.sensorType}`)
    if (!parsed.isValid || parsed.espId === null || parsed.gpio === null) continue

    // 200ms delay between downloads so the browser doesn't block them
    if (i > 0) await new Promise(r => setTimeout(r, 200))

    await exportSensorCsv({
      espId: parsed.espId,
      gpio: parsed.gpio,
      sensorType: parsed.sensorType ?? '',
      sensorName: sensor.name,
      zoneName,
      startTime,
      endTime,
      resolution,
    })
    downloadCount++
  }

  if (downloadCount > 0) {
    toast.show({ message: `${downloadCount} CSV-Dateien heruntergeladen`, type: 'success' })
  }
}

// =============================================================================
// Actuator Correlation (P8-A6c)
// =============================================================================

const MAX_ACTUATORS = 2
const ACTUATOR_OVERLAY_COLORS = [tokens.success || tokens.info, tokens.info || tokens.accent]

/** Parsed actuator IDs from comma-separated string */
const selectedActuatorIds = computed(() => {
  if (!localActuatorIds.value) return [] as string[]
  return localActuatorIds.value.split(',').filter(Boolean)
})

/** Available actuators from ESP store, grouped by device */
interface ActuatorOption {
  id: string  // espId:gpio:actuatorType
  label: string
  type: string
}
interface EspActuatorGroup {
  name: string
  actuators: ActuatorOption[]
}

const espActuatorOptions = computed<EspActuatorGroup[]>(() => {
  const groups: EspActuatorGroup[] = []
  for (const device of espStore.devices) {
    const deviceId = espStore.getDeviceId(device)
    const acts = (device.actuators as MockActuator[]) || []
    if (acts.length === 0) continue

    const options: ActuatorOption[] = acts
      .filter(a => !selectedActuatorIds.value.includes(`${deviceId}:${a.gpio}:${a.actuator_type}`))
      .map(a => ({
        id: `${deviceId}:${a.gpio}:${a.actuator_type}`,
        label: a.name || `GPIO ${a.gpio}`,
        type: a.actuator_type,
      }))

    if (options.length > 0) {
      groups.push({
        name: device.name || deviceId,
        actuators: options,
      })
    }
  }
  return groups
})

const showActuatorDropdown = ref(false)

function addActuatorId(actuatorId: string) {
  const ids = [...selectedActuatorIds.value, actuatorId]
  localActuatorIds.value = ids.join(',')
  emit('update:config', { actuatorIds: localActuatorIds.value })
  showActuatorDropdown.value = false
}

function removeActuatorId(actuatorId: string) {
  const ids = selectedActuatorIds.value.filter(id => id !== actuatorId)
  localActuatorIds.value = ids.join(',')
  emit('update:config', { actuatorIds: localActuatorIds.value })
}

function formatActuatorLabel(actuatorId: string): string {
  const parts = actuatorId.split(':')
  if (parts.length < 3) return actuatorId
  const [espId, gpioStr, actType] = parts
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === espId)
  const acts = (device?.actuators as MockActuator[]) || []
  const act = acts.find(a => String(a.gpio) === gpioStr && a.actuator_type === actType)
  return act?.name || `${actType} (GPIO ${gpioStr})`
}

/** Actuator history data — fetched from API */
const actuatorHistoryMap = shallowRef<Map<string, ActuatorHistoryEntry[]>>(new Map())
const isLoadingActuators = ref(false)
let actuatorRefreshTimer: ReturnType<typeof setInterval> | null = null
let actuatorAbortController: AbortController | null = null

async function fetchActuatorHistory(): Promise<void> {
  // Abort any running fetch before starting a new one
  actuatorAbortController?.abort()
  actuatorAbortController = new AbortController()
  const signal = actuatorAbortController.signal

  const ids = selectedActuatorIds.value
  if (ids.length === 0) {
    actuatorHistoryMap.value = new Map()
    return
  }

  isLoadingActuators.value = true
  const now = new Date()
  const rangeMs = ACTUATOR_TIME_RANGE_MS[localTimeRange.value as keyof typeof ACTUATOR_TIME_RANGE_MS] ?? ACTUATOR_TIME_RANGE_MS['24h']
  const startTime = new Date(now.getTime() - rangeMs)
  const limit = ACTUATOR_TIME_RANGE_LIMITS[localTimeRange.value as keyof typeof ACTUATOR_TIME_RANGE_LIMITS] ?? 300

  try {
    const results = await Promise.all(
      ids.map(async (id) => {
        const parts = id.split(':')
        if (parts.length < 3) return { id, entries: [] as ActuatorHistoryEntry[] }
        const [espId, gpioStr] = parts
        const gpio = parseInt(gpioStr, 10)
        if (isNaN(gpio)) return { id, entries: [] as ActuatorHistoryEntry[] }

        try {
          const response = await actuatorsApi.getHistory(espId, gpio, {
            start_time: startTime.toISOString(),
            end_time: now.toISOString(),
            limit,
          }, signal)
          return { id, entries: response.entries }
        } catch {
          return { id, entries: [] as ActuatorHistoryEntry[] }
        }
      })
    )

    // Discard results if this fetch was superseded
    if (signal.aborted) return

    const newMap = new Map<string, ActuatorHistoryEntry[]>()
    for (const { id, entries } of results) {
      newMap.set(id, entries)
    }
    actuatorHistoryMap.value = newMap
  } finally {
    isLoadingActuators.value = false
  }
}

/** Convert history entries into overlay blocks for the chart */
function historyToOverlayBlocks(entries: ActuatorHistoryEntry[]): ActuatorOverlayBlock[] {
  if (entries.length === 0) return []

  const sorted = [...entries].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  const blocks: ActuatorOverlayBlock[] = []
  let onStart: number | null = null
  let onValue: number | null = null
  const rangeEnd = Date.now()

  for (const entry of sorted) {
    const ts = new Date(entry.timestamp).getTime()
    const on = isActuatorOn(entry)
    const off = isActuatorOff(entry)

    if (on) {
      if (onStart === null) {
        onStart = ts
        onValue = entry.value
      }
    } else if (off && onStart !== null) {
      blocks.push({ start: onStart, end: ts, value: onValue })
      onStart = null
      onValue = null
    }
  }

  // Still ON at end of range
  if (onStart !== null) {
    blocks.push({ start: onStart, end: rangeEnd, value: onValue })
  }

  return blocks
}

/** Extract switch events from history entries */
function historyToOverlayEvents(entries: ActuatorHistoryEntry[], label: string): ActuatorOverlayEvent[] {
  if (entries.length === 0) return []

  const sorted = [...entries].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  )

  const events: ActuatorOverlayEvent[] = []
  let wasOn = false

  for (const entry of sorted) {
    const on = isActuatorOn(entry)
    const off = isActuatorOff(entry)

    if (on && !wasOn) {
      events.push({ timestamp: new Date(entry.timestamp).getTime(), label, isOn: true })
      wasOn = true
    } else if (off && wasOn) {
      events.push({ timestamp: new Date(entry.timestamp).getTime(), label, isOn: false })
      wasOn = false
    }
  }

  return events
}

/** Pre-processed overlay data for MultiSensorChart */
const actuatorOverlays = computed<ActuatorOverlay[]>(() => {
  return selectedActuatorIds.value.map((id, index) => {
    const entries = actuatorHistoryMap.value.get(id) || []
    const label = formatActuatorLabel(id)
    return {
      id,
      label,
      color: ACTUATOR_OVERLAY_COLORS[index % ACTUATOR_OVERLAY_COLORS.length],
      blocks: historyToOverlayBlocks(entries),
      events: historyToOverlayEvents(entries, label),
    }
  })
})

// Fetch actuator history when IDs or timeRange change
watch(
  [selectedActuatorIds, localTimeRange],
  () => { fetchActuatorHistory() },
  { immediate: true }
)

// Auto-refresh actuator history every 60s
function startActuatorRefresh() {
  stopActuatorRefresh()
  actuatorRefreshTimer = setInterval(fetchActuatorHistory, 60_000)
}

function stopActuatorRefresh() {
  if (actuatorRefreshTimer) {
    clearInterval(actuatorRefreshTimer)
    actuatorRefreshTimer = null
  }
}

onMounted(() => {
  updateChartHostHeight()
  if (typeof ResizeObserver !== 'undefined') {
    chartResizeObserver = new ResizeObserver(() => updateChartHostHeight())
    if (chartHostRef.value) {
      chartResizeObserver.observe(chartHostRef.value)
    }
  }
  startActuatorRefresh()
})

onUnmounted(() => {
  stopActuatorRefresh()
  actuatorAbortController?.abort()
  chartResizeObserver?.disconnect()
  chartResizeObserver = null
})

watch(
  () => [
    chartSensors.value.length,
    localCompareMode.value,
    configuredActuatorCount.value,
  ],
  async () => {
    await nextTick()
    updateChartHostHeight()
  }
)
</script>

<template>
  <div class="multi-sensor-widget">
    <!-- Mode toggle -->
    <div class="multi-sensor-widget__mode-toggle">
      <button
        class="multi-sensor-widget__toggle-btn"
        :class="{ 'multi-sensor-widget__toggle-btn--active': localCompareMode }"
        :title="localCompareMode ? 'Manueller Modus' : 'Vergleichs-Modus'"
        @click="toggleCompareMode"
      >
        <GitCompareArrows :size="14" />
        <span>Vergleich</span>
      </button>
    </div>

    <!-- Compare mode config -->
    <div v-if="localCompareMode" class="multi-sensor-widget__compare-config">
      <select
        class="multi-sensor-widget__select"
        :value="localCompareZoneId || localZoneId || ''"
        @change="updateCompareZoneId(($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>— Zone —</option>
        <option
          v-for="zone in zoneStore.activeZones"
          :key="zone.zone_id"
          :value="zone.zone_id"
        >{{ zone.name }}</option>
      </select>
      <select
        class="multi-sensor-widget__select"
        :value="localCompareSensorType"
        @change="updateCompareSensorType(($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>— Sensortyp —</option>
        <option
          v-for="st in availableCompareSensorTypes"
          :key="st.value"
          :value="st.value"
        >{{ st.label }}</option>
      </select>
    </div>

    <!-- Chart content -->
    <template v-if="chartSensors.length > 0">
      <!-- Sensor chips -->
      <div class="multi-sensor-widget__chips">
        <span
          v-for="(sensor, idx) in chartSensors"
          :key="sensor.id"
          class="multi-sensor-widget__chip"
          :style="{ borderColor: chartColorPalette[idx % chartColorPalette.length] }"
        >
          <span
            class="multi-sensor-widget__chip-dot"
            :style="{ background: chartColorPalette[idx % chartColorPalette.length] }"
          />
          {{ sensor.name }}
          <button
            v-if="!localCompareMode"
            class="multi-sensor-widget__chip-remove"
            @click="removeSensor(selectedSensorIds[idx])"
          >
            <X :size="10" />
          </button>
        </span>
        <!-- Add button (manual mode only) -->
        <button
          v-if="!localCompareMode && availableSensors.length > 0"
          class="multi-sensor-widget__add-btn"
          @click="showAddDropdown = !showAddDropdown"
        >
          <Plus :size="12" />
        </button>
        <button
          class="multi-sensor-widget__export-btn"
          title="Alle Sensoren als CSV exportieren"
          :disabled="isExporting"
          @click="handleExportAll"
        >
          <Download :size="12" />
        </button>
        <div v-if="!localCompareMode && showAddDropdown" class="multi-sensor-widget__dropdown">
          <template v-for="zoneGroup in groupedSensorOptions" :key="zoneGroup.zoneId ?? '__unassigned'">
            <template v-for="subgroup in zoneGroup.subgroups" :key="`${zoneGroup.zoneId}_${subgroup.subzoneId ?? '__nosub'}`">
              <div class="multi-sensor-widget__dropdown-group">
                {{ subgroup.label ? `${zoneGroup.label} / ${subgroup.label}` : zoneGroup.label }}
              </div>
              <template v-for="opt in subgroup.options" :key="opt.value">
                <div
                  v-if="!selectedSensorIds.includes(opt.value)"
                  class="multi-sensor-widget__dropdown-item"
                  @click="addSensor(opt.value)"
                >{{ opt.label }}</div>
              </template>
            </template>
          </template>
        </div>
      </div>

      <!-- Actuator chips (P8-A6c) -->
      <div v-if="!localCompareMode" class="multi-sensor-widget__actuator-section">
        <div class="multi-sensor-widget__actuator-chips">
          <span
            v-for="actId in selectedActuatorIds"
            :key="actId"
            class="multi-sensor-widget__chip multi-sensor-widget__chip--actuator"
          >
            <Zap :size="10" class="multi-sensor-widget__chip-icon" />
            {{ formatActuatorLabel(actId) }}
            <button class="multi-sensor-widget__chip-remove" @click="removeActuatorId(actId)">
              <X :size="10" />
            </button>
          </span>
          <button
            v-if="selectedActuatorIds.length < MAX_ACTUATORS && espActuatorOptions.length > 0"
            class="multi-sensor-widget__add-btn multi-sensor-widget__add-btn--actuator"
            title="Aktor hinzufügen"
            @click="showActuatorDropdown = !showActuatorDropdown"
          >
            <Zap :size="10" />
          </button>
        </div>
        <div v-if="showActuatorDropdown" class="multi-sensor-widget__dropdown">
          <template v-for="espGroup in espActuatorOptions" :key="espGroup.name">
            <div class="multi-sensor-widget__dropdown-group">{{ espGroup.name }}</div>
            <div
              v-for="act in espGroup.actuators"
              :key="act.id"
              class="multi-sensor-widget__dropdown-item"
              @click="addActuatorId(act.id)"
            >
              {{ act.label }} ({{ act.type }})
            </div>
          </template>
        </div>
      </div>

      <!-- Chart -->
      <div ref="chartHostRef" class="multi-sensor-widget__chart">
        <MultiSensorChart
          :sensors="chartSensors"
          :time-range="localTimeRange"
          :enable-live-updates="true"
          :height="effectiveChartHeight"
          :actuator-overlays="actuatorOverlays"
        />
      </div>
    </template>

    <!-- Empty state -->
    <div v-else class="multi-sensor-widget__empty">
      <BarChart3 class="w-8 h-8" style="opacity: 0.3" />
      <template v-if="localCompareMode">
        <p v-if="!effectiveCompareZoneId">Bitte Zone auswählen</p>
        <p v-else-if="!localCompareSensorType">Bitte Sensortyp auswählen</p>
        <p v-else>Keine passenden Sensoren in dieser Zone</p>
      </template>
      <template v-else>
        <p>Sensoren für Multi-Chart auswählen{{ props.title ? ` für ${props.title}` : '' }}:</p>
        <select
          class="multi-sensor-widget__select"
          @change="addSensor(($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''"
        >
          <option value="" disabled selected>— Sensor hinzufügen —</option>
          <template v-for="zoneGroup in groupedSensorOptions" :key="zoneGroup.zoneId ?? '__unassigned'">
            <template v-for="subgroup in zoneGroup.subgroups" :key="`${zoneGroup.zoneId}_${subgroup.subzoneId ?? '__nosub'}`">
              <optgroup :label="subgroup.label ? `${zoneGroup.label} / ${subgroup.label}` : zoneGroup.label">
                <option
                  v-for="opt in subgroup.options"
                  :key="opt.value"
                  :value="opt.value"
                >{{ opt.label }}</option>
              </optgroup>
            </template>
          </template>
        </select>
      </template>
    </div>
  </div>
</template>

<style scoped>
.multi-sensor-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.multi-sensor-widget__mode-toggle {
  display: flex;
  justify-content: flex-end;
  padding: var(--space-1) var(--space-2) 0;
  flex-shrink: 0;
}

.multi-sensor-widget__toggle-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 28px;
}

.multi-sensor-widget__toggle-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-text-secondary);
}

.multi-sensor-widget__toggle-btn--active {
  border-color: var(--color-accent);
  background: rgba(96, 165, 250, 0.1);
  color: var(--color-accent);
}

.multi-sensor-widget__compare-config {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  flex-shrink: 0;
}

.multi-sensor-widget__compare-config .multi-sensor-widget__select {
  flex: 1;
  min-width: 0;
  max-width: none;
}

.multi-sensor-widget__chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  flex-shrink: 0;
  position: relative;
}

.multi-sensor-widget__chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border: 1px solid;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-quaternary);
}

.multi-sensor-widget__chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.multi-sensor-widget__chip-remove {
  display: flex;
  align-items: center;
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  padding: 0;
}

.multi-sensor-widget__chip-remove:hover {
  color: var(--color-error);
}

.multi-sensor-widget__add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
}

.multi-sensor-widget__add-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.multi-sensor-widget__export-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  opacity: 0.5;
  transition: opacity 0.15s, color 0.15s;
}

.multi-sensor-widget__export-btn:hover {
  opacity: 1;
  border-color: var(--color-accent);
  color: var(--color-accent);
}

.multi-sensor-widget__export-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

@media (hover: none) {
  .multi-sensor-widget__export-btn {
    opacity: 0.8;
  }
}

.multi-sensor-widget__dropdown {
  position: absolute;
  top: 100%;
  left: var(--space-2);
  z-index: var(--z-dropdown);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  box-shadow: var(--elevation-floating);
  max-height: 200px;
  overflow-y: auto;
  min-width: 200px;
}

.multi-sensor-widget__dropdown-group {
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xxs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  border-top: 1px solid var(--glass-border);
}

.multi-sensor-widget__dropdown-group:first-child {
  border-top: none;
}

.multi-sensor-widget__dropdown-item {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.multi-sensor-widget__dropdown-item:hover {
  background: var(--glass-bg-light);
  color: var(--color-text-primary);
}

.multi-sensor-widget__chart {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.multi-sensor-widget__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.multi-sensor-widget__select {
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  max-width: 220px;
}

/* Actuator section (P8-A6c) */
.multi-sensor-widget__actuator-section {
  position: relative;
  padding: 0 var(--space-2) var(--space-1);
  flex-shrink: 0;
}

.multi-sensor-widget__actuator-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
}

.multi-sensor-widget__chip--actuator {
  border-color: color-mix(in srgb, var(--color-success) 50%, transparent);
  background: color-mix(in srgb, var(--color-success) 8%, transparent);
}

.multi-sensor-widget__chip-icon {
  flex-shrink: 0;
  color: color-mix(in srgb, var(--color-success) 80%, transparent);
}

.multi-sensor-widget__add-btn--actuator {
  border-color: color-mix(in srgb, var(--color-success) 30%, transparent);
  color: color-mix(in srgb, var(--color-success) 60%, transparent);
}

.multi-sensor-widget__add-btn--actuator:hover {
  border-color: color-mix(in srgb, var(--color-success) 70%, transparent);
  color: var(--color-success);
}
</style>
