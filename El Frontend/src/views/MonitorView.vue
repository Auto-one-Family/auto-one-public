<script setup lang="ts">
defineOptions({ name: 'MonitorView' })

/**
 * MonitorView — Sensor & Actuator Live Monitoring
 *
 * Route: /monitor, /monitor/:zoneId
 *
 * Live data view with 3 levels (read-only, no configuration):
 * L1 /monitor — Zone tiles with KPI aggregation + cross-zone dashboard links
 * L2 /monitor/:zoneId — Subzone accordion with sensor/actuator cards (read-only)
 * L3 BaseModal — Sensor detail with historical time series
 */

import { ref, computed, onMounted, onUnmounted, watch, nextTick, defineAsyncComponent, type ComponentPublicInstance } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import type { RouteLocationRaw } from 'vue-router'
import { useKeyboardShortcuts } from '@/composables/useKeyboardShortcuts'
import { useSwipeNavigation } from '@/composables/useSwipeNavigation'
import { useEspStore } from '@/stores/esp'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useTankStore } from '@/shared/stores/tank.store'
import { useDeviceContextStore } from '@/shared/stores/deviceContext.store'
import { useZoneGrouping, isMockEspId } from '@/composables/useZoneGrouping'
import { useZoneKPIs } from '@/composables/useZoneKPIs'
import type { ZoneHealthStatus } from '@/composables/useZoneKPIs'
import { useSubzoneResolver } from '@/composables/useSubzoneResolver'
import { useSparklineCache } from '@/composables/useSparklineCache'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  createMonitorRecoveryOrchestrator,
  resolveMonitorConnectivityState,
  resolveMonitorDataMode,
} from '@/composables/monitorConnectivity'
import {
  getSensorLabel,
  getSensorUnit,
  getSensorDisplayName,
  getSensorAggCategory,
  getSensorConfig,
  formatSubzoneKpiLine,
} from '@/utils/sensorDefaults'
import { getActuatorTypeInfo } from '@/utils/labels'
import { storeToRefs } from 'pinia'
import { useDashboardStore } from '@/shared/stores/dashboard.store'
import { useLogicStore } from '@/shared/stores/logic.store'
import { useAuthStore } from '@/shared/stores/auth.store'
import { formatDateTime, formatRelativeTime, formatSensorValue, unitFromChartLabel, formatMountChartSuffix, isFirstTooltipItemForDataset, qualityToStatus, sensorStatusToLevel, DATA_STALE_THRESHOLD_S } from '@/utils/formatters'
import StatusBadge from '@/components/base/StatusBadge.vue'
import { calculateTrend } from '@/utils/trendUtils'
import type { TrendDirection } from '@/utils/trendUtils'
import { getAutoResolutionForWindow } from '@/utils/autoResolution'
import {
  type GapDataPoint,
  calculateMedianInterval,
  computeExpectedInterval,
  insertGapMarkers,
  lastFiniteSampleX,
} from '@/utils/gapDetection'
import { sensorsApi } from '@/api/sensors'
import { zonesApi } from '@/api/zones'
import type { MockSensor, SensorReading, SensorStats, SensorDataResolution } from '@/types'
import type { ZoneMonitorData } from '@/types/monitor'
import type { SensorWithContext, ActuatorWithContext } from '@/composables/useZoneGrouping'
import {
  Download,
  Clock,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowLeft,
  Activity,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-vue-next'
import ZoneTileCard from '@/components/monitor/ZoneTileCard.vue'
import ZoneTileInsightBlock from '@/components/monitor/ZoneTileInsightBlock.vue'
import ZoneTankEcPhBar from '@/components/monitor/ZoneTankEcPhBar.vue'
import MonitorExpanded1hChart, {
  type ExpandedLivePoint,
} from '@/components/monitor/MonitorExpanded1hChart.vue'
import TankIstSollPanel from '@/components/plants/TankIstSollPanel.vue'
import {
  filterOutEcPhSensors,
  type TankEcPhSensorRef,
} from '@/utils/zoneTankEcPh'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import ExportDialog from '@/components/export/ExportDialog.vue'
import TimeRangeSelector, { type TimePreset } from '@/components/charts/TimeRangeSelector.vue'
import { Line } from 'vue-chartjs'
import LiveLineChart, { type ThresholdConfig } from '@/components/charts/LiveLineChart.vue'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  Filler,
} from 'chart.js'
import type { TooltipItem } from 'chart.js'
import 'chartjs-adapter-date-fns'
import SensorCard from '@/components/devices/SensorCard.vue'
import ActuatorCard from '@/components/devices/ActuatorCard.vue'
import SharedSensorRefCard from '@/components/devices/SharedSensorRefCard.vue'
import DashboardViewer from '@/components/dashboard/DashboardViewer.vue'
import InlineDashboardPanel from '@/components/dashboard/InlineDashboardPanel.vue'
import BaseSkeleton from '@/shared/design/primitives/BaseSkeleton.vue'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'
import ZoneRulesSection from '@/components/monitor/ZoneRulesSection.vue'
import { getChartColors } from '@/utils/chartColors'
import { tokens } from '@/utils/cssTokens'
import { getZoneTileRenderableWidgets } from '@/utils/zoneTileWidgets'
import {
  collectStoreSensors,
  resolveMonitorDeepLink,
} from '@/utils/sensorConfigLookup'

ChartJS.register(
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, TimeScale, Filler,
)

/** Async load breaks dev-time circular import / HMR edges that left the component undefined under KeepAlive */
const ViewTabBar = defineAsyncComponent(() => import('@/components/common/ViewTabBar.vue'))

const router = useRouter()
const route = useRoute()
const espStore = useEspStore()
const zoneStore = useZoneStore()
const tankStore = useTankStore()
const deviceContextStore = useDeviceContextStore()
const dashStore = useDashboardStore()
const { sideMonitorPanels, bottomMonitorPanels } = storeToRefs(dashStore)
const logicStore = useLogicStore()
// TODO replace isViewer with capability check
const authStore = useAuthStore()
const monitorWs = useWebSocket({ autoConnect: true, autoReconnect: true })

// =============================================================================
// L1 Zone KPIs (extracted composable)
// =============================================================================

const {
  zoneKPIs,
  filteredZoneKPIs,
  isZoneStale,
  allZones,
  zoneApiDegraded,
  lastZoneApiSuccessAt,
} = useZoneKPIs({})

// =============================================================================
// L2 Subzones (all subzones; filter UI removed — always show all)
// =============================================================================

type MonitorSourceType = 'real' | 'mock'

const filteredSubzones = computed(() =>
  zoneDeviceGroup.value.filter(
    subzone => subzone.sensors.length > 0 || subzone.actuators.length > 0,
  ),
)

const selectedZoneId = computed(() => (route.params.zoneId as string) || null)
const selectedSensorId = computed(() => (route.params.sensorId as string) || null)
const selectedDashboardId = computed(() => (route.params.dashboardId as string) || null)
const isDashboardView = computed(() => !!selectedDashboardId.value)
const isZoneDetail = computed(() => !!selectedZoneId.value)

// Expanded sensor card state (for inline 1h chart)
const expandedSensorKey = ref<string | null>(null)

// Sensor key helper (from sparkline cache composable)
const { sparklineCache, getSensorKey, loadInitialData: loadSparklineHistory, getSparklineForDisplay } = useSparklineCache()


// Zone monitor data (API primary, fallback via useZoneGrouping)
const zoneMonitorData = ref<ZoneMonitorData | null>(null)
const zoneMonitorLoading = ref(false)
const zoneMonitorError = ref<string | null>(null)
const zoneMonitorAbort = ref<AbortController | null>(null)
const lastZoneMonitorApiSuccessAt = ref<number | null>(null)
const lastDetailApiSuccessAt = ref<number | null>(null)

// Subzone resolver for fallback (GPIO → subzone map) — lazy: only triggered on API error
const subzoneResolver = useSubzoneResolver(selectedZoneId, { lazy: true })

// Zone grouping composable (fallback when API fails)
const { sensorsByZone, actuatorsByZone, allSensors } = useZoneGrouping({
  subzoneResolver: subzoneResolver.resolverMap,
})

const zoneMockSensorCounts = computed(() => {
  const counts = new Map<string, number>()
  for (const sensor of allSensors.value) {
    const zId = sensor.zone_id
    if (!zId || !isMockEspId(sensor.esp_id)) continue
    counts.set(zId, (counts.get(zId) ?? 0) + 1)
  }
  return counts
})

const SOURCE_SORT_PRIORITY: Record<MonitorSourceType, number> = {
  real: 0,
  mock: 1,
}

const sensorCardElementMap = new Map<string, HTMLElement>()

function registerSensorCardElement(sensorKey: string, element: Element | ComponentPublicInstance | null): void {
  const host = element instanceof Element
    ? element
    : (element as ComponentPublicInstance | null)?.$el instanceof Element
      ? (element as ComponentPublicInstance).$el
      : null

  if (host instanceof HTMLElement) {
    sensorCardElementMap.set(sensorKey, host)
  } else {
    sensorCardElementMap.delete(sensorKey)
  }
}

function resolveSourceType(espId: string): MonitorSourceType {
  return isMockEspId(espId) ? 'mock' : 'real'
}

function resolveSensorDisplayName(sensor: Pick<SensorWithContext, 'sensor_type' | 'name' | 'gpio'>): string {
  return getSensorDisplayName({ sensor_type: sensor.sensor_type, name: sensor.name }) || sensor.sensor_type || 'Sensor'
}

function resolveActuatorDisplayName(actuator: Pick<ActuatorWithContext, 'name' | 'gpio' | 'actuator_type' | 'hardware_type'>): string {
  const name = typeof actuator.name === 'string' ? actuator.name.trim() : ''
  if (name.length > 0) return name
  const typeLabel = getActuatorTypeInfo(actuator.actuator_type, actuator.hardware_type).label
  return `${typeLabel} GPIO ${actuator.gpio}`
}

function compareSensorsMetricFirst(a: SensorWithContext, b: SensorWithContext): number {
  const metricA = getSensorAggCategory(a.sensor_type)
  const metricB = getSensorAggCategory(b.sensor_type)
  if (metricA !== metricB) return metricA.localeCompare(metricB)

  const sourceA = SOURCE_SORT_PRIORITY[resolveSourceType(a.esp_id)]
  const sourceB = SOURCE_SORT_PRIORITY[resolveSourceType(b.esp_id)]
  if (sourceA !== sourceB) return sourceA - sourceB

  const nameCmp = resolveSensorDisplayName(a).localeCompare(resolveSensorDisplayName(b), 'de')
  if (nameCmp !== 0) return nameCmp

  return `${a.esp_id}:${a.gpio}:${a.sensor_type}`.localeCompare(`${b.esp_id}:${b.gpio}:${b.sensor_type}`)
}

function compareActuatorsStable(a: ActuatorWithContext, b: ActuatorWithContext): number {
  const sourceA = SOURCE_SORT_PRIORITY[resolveSourceType(a.esp_id)]
  const sourceB = SOURCE_SORT_PRIORITY[resolveSourceType(b.esp_id)]
  if (sourceA !== sourceB) return sourceA - sourceB

  const nameCmp = resolveActuatorDisplayName(a).localeCompare(resolveActuatorDisplayName(b), 'de')
  if (nameCmp !== 0) return nameCmp

  return `${a.esp_id}:${a.gpio}:${a.actuator_type}`.localeCompare(`${b.esp_id}:${b.gpio}:${b.actuator_type}`)
}

function sortSensorsMetricFirst(sensors: SensorWithContext[]): SensorWithContext[] {
  return [...sensors].sort(compareSensorsMetricFirst)
}

function sortActuatorsStable(actuators: ActuatorWithContext[]): ActuatorWithContext[] {
  return [...actuators].sort(compareActuatorsStable)
}

function toggleExpanded(sensorKey: string) {
  const wasExpanded = expandedSensorKey.value === sensorKey
  expandedSensorKey.value = wasExpanded ? null : sensorKey
  if (!wasExpanded) {
    nextTick(() => {
      const cardElement = sensorCardElementMap.get(sensorKey)
      cardElement?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    })
  }
}

function resolveSensorUnit(sensor: Pick<SensorWithContext, 'sensor_type' | 'unit'>): string {
  return getSensorUnit(sensor.sensor_type) !== 'raw'
    ? getSensorUnit(sensor.sensor_type)
    : (sensor.unit || '')
}

/** Live sample for the expanded 1h chart (same source as former expandedLiveSample). */
function getExpandedLiveSample(sensor: SensorWithContext): ExpandedLivePoint | null {
  if (sensor.raw_value == null || !Number.isFinite(sensor.raw_value)) return null
  const tsMs = sensor.last_read ? new Date(sensor.last_read).getTime() : Number.NaN
  if (!Number.isFinite(tsMs)) return null
  return {
    x: tsMs,
    y: Number(sensor.raw_value),
  }
}

// =============================================================================
// Sparkline: Default thresholds from SENSOR_TYPE_CONFIG
// =============================================================================

function getDefaultThresholds(sensorType: string): ThresholdConfig | undefined {
  const config = getSensorConfig(sensorType)
  if (config == null || config.min == null || config.max == null) return undefined

  const range = config.max - config.min
  return {
    alarmLow: config.min + range * 0.1,
    warnLow: config.min + range * 0.2,
    warnHigh: config.max - range * 0.2,
    alarmHigh: config.max - range * 0.1,
  }
}

// =============================================================================
// Trend calculation from sparkline data
// =============================================================================

const MIN_TREND_POINTS = 5

function getSensorTrend(espId: string, gpio: number, sensorType?: string): TrendDirection | undefined {
  const key = getSensorKey(espId, gpio, sensorType)
  const points = sparklineCache.value.get(key)
  if (!points || points.length < MIN_TREND_POINTS) return undefined
  return calculateTrend(points, sensorType).direction
}

function getDisplaySparkline(sensor: { esp_id: string; gpio: number; sensor_type?: string; operating_mode?: string | null }) {
  const key = getSensorKey(sensor.esp_id, sensor.gpio, sensor.sensor_type)
  return getSparklineForDisplay(key, sensor.operating_mode)
}

function getTankStripSparkline(sensor: TankEcPhSensorRef) {
  return getDisplaySparkline(sensor) ?? undefined
}

// AUT-609: Time range label derived from sparkline data timestamps
function getSparklineTimeLabel(sensor: { esp_id: string; gpio: number; sensor_type?: string }): string {
  const key = getSensorKey(sensor.esp_id, sensor.gpio, sensor.sensor_type)
  const points = sparklineCache.value.get(key)
  if (!points || points.length < 2) return ''
  const diffMin = Math.round(
    (new Date(points[points.length - 1].timestamp).getTime() - new Date(points[0].timestamp).getTime()) / 60000
  )
  if (diffMin < 1) return 'letzte Min'
  if (diffMin < 60) return `letzte ${diffMin} Min`
  return `letzte ${Math.round(diffMin / 60)} Std`
}

// =============================================================================
// Chart colors (shared between expanded panel + L3 overlay)
// =============================================================================

function getChartColor(index: number): string {
  const palette = getChartColors()
  if (palette.length === 0) return tokens.accent || tokens.info
  return palette[index % palette.length] || tokens.accent || tokens.info
}

// =============================================================================
// Level 3: Sensor Detail Modal
// =============================================================================

interface DetailSensor {
  espId: string
  gpio: number
  sensorType: string
  name: string
  unit: string
  configId?: string
}

const showSensorDetail = ref(false)
const selectedDetailSensor = ref<DetailSensor | null>(null)
const detailPreset = ref<TimePreset>('24h')
const detailStartTime = ref(new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString())
const detailEndTime = ref(new Date().toISOString())
const detailReadings = ref<SensorReading[]>([])
const detailLoading = ref(false)
const detailError = ref('')

// Multi-sensor overlay state
const overlaySensorIds = ref<string[]>([])
const overlaySensorReadings = ref<Map<string, SensorReading[]>>(new Map())
const overlayLoading = ref<Set<string>>(new Set())
const MAX_OVERLAY_SENSORS = 4

function openSensorDetail(sensor: {
  esp_id: string
  gpio: number
  sensor_type: string
  name: string | null
  unit: string
  config_id?: string
}) {
  const sensorName = getSensorDisplayName({ sensor_type: sensor.sensor_type, name: sensor.name })
    || sensor.sensor_type
    || 'Sensor'
  selectedDetailSensor.value = {
    espId: sensor.esp_id,
    gpio: sensor.gpio,
    sensorType: sensor.sensor_type,
    name: sensorName,
    unit: getSensorUnit(sensor.sensor_type) !== 'raw' ? getSensorUnit(sensor.sensor_type) : (sensor.unit || ''),
    configId: sensor.config_id,
  }
  showSensorDetail.value = true
  fetchDetailData()

  // AUT-1533: Deep-link identity is config_id. gpio is not written as SSOT.
  if (selectedZoneId.value && sensor.config_id) {
    dashStore.breadcrumb.sensorName = sensorName
    router.replace({
      name: 'monitor-sensor',
      params: { zoneId: selectedZoneId.value, sensorId: sensor.config_id },
    })
  }
}

function closeSensorDetail() {
  showSensorDetail.value = false

  // URL-sync: go back to /monitor/:zoneId
  if (selectedZoneId.value) {
    dashStore.breadcrumb.sensorName = ''
    router.replace({ name: 'monitor-zone', params: { zoneId: selectedZoneId.value } })
  }

  setTimeout(() => {
    selectedDetailSensor.value = null
    detailReadings.value = []
    // Clear overlay state
    overlaySensorIds.value = []
    overlaySensorReadings.value = new Map()
    overlayLoading.value = new Set()
  }, 300)
}

function onDetailRangeChange(payload: { start: string; end: string }) {
  detailStartTime.value = payload.start
  detailEndTime.value = payload.end
  fetchDetailData()
  // Re-fetch overlay sensor data for new time range
  for (const key of overlaySensorIds.value) {
    fetchOverlaySensorData(key)
  }
}

/** Same SSOT as HistoricalChart / MultiSensorChart — derived from the actual window. */
function getDetailResolution(): SensorDataResolution | undefined {
  return getAutoResolutionForWindow(detailStartTime.value, detailEndTime.value)
}

async function fetchDetailData() {
  if (!selectedDetailSensor.value) return
  detailLoading.value = true
  detailError.value = ''
  try {
    const resolution = getDetailResolution()
    const response = await sensorsApi.queryData({
      ...(selectedDetailSensor.value.configId
        ? { sensor_config_id: selectedDetailSensor.value.configId }
        : {
            esp_id: selectedDetailSensor.value.espId,
            gpio: selectedDetailSensor.value.gpio,
            sensor_type: selectedDetailSensor.value.sensorType || undefined,
          }),
      start_time: detailStartTime.value,
      end_time: detailEndTime.value,
      limit: 1000,
      ...(resolution ? { resolution } : {}),
    })
    detailReadings.value = response.readings ?? []
    lastDetailApiSuccessAt.value = Date.now()
  } catch (err) {
    detailError.value = err instanceof Error ? err.message : 'Fehler beim Laden'
    detailReadings.value = []
  } finally {
    detailLoading.value = false
  }
}

// =============================================================================
// Multi-Sensor Overlay (L3)
// =============================================================================

/** All sensors in current zone except the primary detail sensor (includes sensor_type for multi-value separation) */
const availableOverlaySensors = computed(() => {
  if (zoneDeviceGroup.value.length === 0 || !selectedDetailSensor.value) return []
  const result: {
    key: string
    name: string
    type: string
    unit: string
    espId: string
    gpio: number
    subzoneName: string
    mount_height_cm?: number | null
    mount_medium?: string | null
    mount_angle_deg?: number | null
  }[] = []
  for (const sz of zoneDeviceGroup.value) {
    for (const s of sz.sensors) {
      // Exclude the primary detail sensor (match by espId + gpio + sensorType)
      if (s.esp_id === selectedDetailSensor.value.espId &&
          s.gpio === selectedDetailSensor.value.gpio &&
          s.sensor_type === selectedDetailSensor.value.sensorType) continue
      const key = s.config_id || `${s.esp_id}-${s.gpio}-${s.sensor_type}`
      result.push({
        key,
        name: getSensorDisplayName({ sensor_type: s.sensor_type, name: s.name }) || getSensorLabel(s.sensor_type) || s.sensor_type,
        type: s.sensor_type,
        unit: getSensorUnit(s.sensor_type) !== 'raw' ? getSensorUnit(s.sensor_type) : (s.unit || ''),
        espId: s.esp_id,
        gpio: s.gpio,
        // L2 accordion name only when a named subzone exists — not "Zone-weit"
        subzoneName: sz.subzoneId ? sz.subzoneName : '',
        mount_height_cm: s.mount_height_cm ?? null,
        mount_medium: s.mount_medium ?? null,
        mount_angle_deg: s.mount_angle_deg ?? null,
      })
    }
  }
  return result
})

async function toggleOverlaySensor(sensorKey: string) {
  const idx = overlaySensorIds.value.indexOf(sensorKey)
  if (idx >= 0) {
    overlaySensorIds.value.splice(idx, 1)
    overlaySensorReadings.value.delete(sensorKey)
    overlayLoading.value.delete(sensorKey)
    return
  }
  if (overlaySensorIds.value.length >= MAX_OVERLAY_SENSORS) return
  overlaySensorIds.value.push(sensorKey)
  await fetchOverlaySensorData(sensorKey)
}

async function fetchOverlaySensorData(sensorKey: string) {
  const parts = sensorKey.split('-')
  if (parts.length < 2) return

  // Extract sensor_type from key if present (last part, non-numeric)
  let sensorType: string | undefined
  const lastPart = parts[parts.length - 1]
  if (parts.length >= 3 && isNaN(parseInt(lastPart, 10))) {
    sensorType = lastPart
    parts.pop()
  }
  const gpio = parseInt(parts[parts.length - 1], 10)
  const espId = parts.slice(0, -1).join('-')
  if (isNaN(gpio)) return

  overlayLoading.value.add(sensorKey)
  try {
    const resolution = getDetailResolution()
    const response = await sensorsApi.queryData({
      esp_id: espId,
      gpio,
      sensor_type: sensorType || undefined,
      start_time: detailStartTime.value,
      end_time: detailEndTime.value,
      limit: 1000,
      ...(resolution ? { resolution } : {}),
    })
    overlaySensorReadings.value.set(sensorKey, response.readings ?? [])
  } catch {
    overlaySensorReadings.value.set(sensorKey, [])
  } finally {
    overlayLoading.value.delete(sensorKey)
  }
}

/** Get the chart color for an overlay sensor by its index in overlaySensorIds */
function getOverlayColor(sensorKey: string): string {
  const idx = overlaySensorIds.value.indexOf(sensorKey)
  return getChartColor(idx + 1)
}

const detailChartData = computed(() => {
  const hasMain = detailReadings.value.length > 0
  const hasOverlay = overlaySensorIds.value.length > 0
  if (!hasMain && !hasOverlay) return { datasets: [] }

  const sensor = selectedDetailSensor.value
  // AUT-1543: L1/L2 view context — not sample-join. AUT-1557 appends mount from the same loaded config.
  const zoneName = selectedZoneName.value
  const primaryGroup = sensor
    ? zoneDeviceGroup.value.find(sz =>
        sz.sensors.some(s =>
          s.esp_id === sensor.espId &&
          s.gpio === sensor.gpio &&
          s.sensor_type === sensor.sensorType
        )
      )
    : undefined
  const primaryConfig = sensor
    ? primaryGroup?.sensors.find(s =>
        s.esp_id === sensor.espId &&
        s.gpio === sensor.gpio &&
        s.sensor_type === sensor.sensorType
      )
    : undefined
  const primarySubzone = primaryGroup?.subzoneId ? primaryGroup.subzoneName : ''
  const primaryLocation = zoneName
    ? (primarySubzone ? ` · ${zoneName} / ${primarySubzone}` : ` · ${zoneName}`)
    : ''
  const primaryMount = formatMountChartSuffix(primaryConfig)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const datasets: any[] = []

  // Primary sensor dataset (API returns DESC — sort ASC for Chart.js line path)
  if (hasMain) {
    const mainPoints = detailReadings.value
      .map(r => ({
        x: new Date(r.timestamp).getTime(),
        y: r.processed_value ?? r.raw_value,
      }))
      .sort((a, b) => a.x - b.x)
    // AUT-1545: same insertGapMarkers path as MonitorExpanded1hChart.chartData
    const mainGapPoints: GapDataPoint[] = mainPoints.map((p) => ({
      timestamp: new Date(p.x),
      value: p.y ?? null,
    }))
    const mainMedianMs = calculateMedianInterval(mainGapPoints)
    const mainExpectedMs = computeExpectedInterval(mainMedianMs, null, mainGapPoints.length)
    const mainWithGaps = insertGapMarkers(mainGapPoints, mainExpectedMs)
    const mainData = mainWithGaps.map((p) => ({ x: p.timestamp.getTime(), y: p.value }))
    datasets.push({
      label: `${sensor?.name ?? 'Sensor'} (${sensor?.unit ?? ''})${primaryLocation}${primaryMount}`,
      unit: sensor?.unit ?? '',
      data: mainData,
      borderColor: getChartColor(0),
      backgroundColor: `${getChartColor(0)}20`,
      borderWidth: 2,
      pointRadius: mainPoints.length > 200 ? 0 : 2,
      pointHoverRadius: 4,
      tension: 0.3,
      fill: true,
      spanGaps: false,
      yAxisID: 'y',
    })
  }

  // Overlay sensor datasets
  for (let i = 0; i < overlaySensorIds.value.length; i++) {
    const key = overlaySensorIds.value[i]
    const readings = overlaySensorReadings.value.get(key)
    if (!readings?.length) continue

    const overlaySensor = availableOverlaySensors.value.find(s => s.key === key)
    const color = getChartColor(i + 1)
    const sameUnit = overlaySensor?.unit === sensor?.unit
    const overlaySubzone = overlaySensor?.subzoneName ?? ''
    const overlayLocation = zoneName
      ? (overlaySubzone ? ` · ${zoneName} / ${overlaySubzone}` : ` · ${zoneName}`)
      : ''
    const overlayMount = formatMountChartSuffix(overlaySensor)

    const overlayPoints = readings
      .map(r => ({
        x: new Date(r.timestamp).getTime(),
        y: r.processed_value ?? r.raw_value,
      }))
      .sort((a, b) => a.x - b.x)
    const overlayGapPoints: GapDataPoint[] = overlayPoints.map((p) => ({
      timestamp: new Date(p.x),
      value: p.y ?? null,
    }))
    const overlayMedianMs = calculateMedianInterval(overlayGapPoints)
    const overlayExpectedMs = computeExpectedInterval(overlayMedianMs, null, overlayGapPoints.length)
    const overlayWithGaps = insertGapMarkers(overlayGapPoints, overlayExpectedMs)
    const overlayData = overlayWithGaps.map((p) => ({ x: p.timestamp.getTime(), y: p.value }))

    datasets.push({
      label: `${overlaySensor?.name ?? key} (${overlaySensor?.unit ?? ''})${overlayLocation}${overlayMount}`,
      unit: overlaySensor?.unit ?? '',
      data: overlayData,
      borderColor: color,
      backgroundColor: `${color}10`,
      borderWidth: 1.5,
      pointRadius: 0,
      pointHoverRadius: 3,
      tension: 0.3,
      fill: false,
      spanGaps: false,
      yAxisID: sameUnit ? 'y' : 'y1',
    })
  }

  return { datasets }
})

const detailChartOptions = computed(() => {
  const unit = selectedDetailSensor.value?.unit ?? ''
  const hasOverlays = overlaySensorIds.value.length > 0

  // Check if any overlay sensor has a different unit → needs secondary y-axis
  const needsSecondaryAxis = overlaySensorIds.value.some(key => {
    const s = availableOverlaySensors.value.find(os => os.key === key)
    return s && s.unit !== unit
  })
  const secondaryOverlay = needsSecondaryAxis
    ? availableOverlaySensors.value.find(s => overlaySensorIds.value.includes(s.key) && s.unit !== unit)
    : undefined
  const secondaryUnit = secondaryOverlay?.unit ?? ''
  const primaryDecimals = detailSensorTypeConfig.value?.decimals ?? 2
  const secondaryDecimals = secondaryOverlay?.type
    ? (getSensorConfig(secondaryOverlay.type)?.decimals ?? 2)
    : 2
  const sampleMaxX = lastFiniteSampleX(detailChartData.value.datasets)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const scales: any = {
    x: {
      type: 'time' as const,
      min: new Date(detailStartTime.value).getTime(),
      ...(sampleMaxX != null ? { max: sampleMaxX } : {}),
      time: {
        displayFormats: { second: 'HH:mm:ss', minute: 'HH:mm', hour: 'HH:mm', day: 'dd.MM' },
      },
      grid: { color: tokens.glassBorder },
      ticks: { color: tokens.textMuted, font: { family: 'JetBrains Mono', size: 10 }, maxTicksLimit: 8 },
      border: { display: false },
    },
    y: {
      grid: { color: tokens.glassBorder },
      ticks: {
        color: getChartColor(0),
        font: { family: 'JetBrains Mono', size: 10 },
        callback: (val: string | number) => {
          const num = typeof val === 'number' ? val : Number(val)
          return formatSensorValue(num, unit, primaryDecimals)
        },
      },
      border: { display: false },
      ...(detailDynamicYBounds.value
        ? { suggestedMin: detailDynamicYBounds.value.min, suggestedMax: detailDynamicYBounds.value.max }
        : detailSensorTypeConfig.value
          ? { suggestedMin: detailSensorTypeConfig.value.min, suggestedMax: detailSensorTypeConfig.value.max }
          : {}),
    },
  }

  if (needsSecondaryAxis) {
    scales.y1 = {
      position: 'right',
      grid: { drawOnChartArea: false },
      ticks: {
        color: getChartColor(1),
        font: { family: 'JetBrains Mono', size: 10 },
        callback: (val: string | number) => {
          const num = typeof val === 'number' ? val : Number(val)
          return formatSensorValue(num, secondaryUnit, secondaryDecimals)
        },
      },
      border: { display: false },
    }
  }

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    interaction: { mode: 'x' as const, intersect: false },
    plugins: {
      legend: {
        display: hasOverlays,
        labels: {
          color: tokens.textSecondary,
          font: { family: 'JetBrains Mono', size: 10 },
          boxWidth: 12,
          boxHeight: 2,
          padding: 8,
        },
      },
      tooltip: {
        mode: 'x' as const,
        intersect: false,
        filter: (item: TooltipItem<'line'>, index: number, items: TooltipItem<'line'>[]) =>
          isFirstTooltipItemForDataset(item, index, items),
        backgroundColor: tokens.backdropColor,
        borderColor: tokens.glassBorder,
        borderWidth: 1,
        titleFont: { family: 'JetBrains Mono', size: 11 },
        bodyFont: { family: 'JetBrains Mono', size: 12 },
        titleColor: tokens.textSecondary,
        bodyColor: tokens.textPrimary,
        padding: 10,
        callbacks: {
          title: (items: TooltipItem<'line'>[]) => {
            if (!items.length) return ''
            return formatDateTime(new Date(items[0].parsed.x ?? 0))
          },
          label: (item: TooltipItem<'line'>) => {
            const datasetUnit = (item.dataset as { unit?: string }).unit
            const dsUnit = datasetUnit || unitFromChartLabel(item.dataset.label, unit)
            const y = item.parsed.y
            if (typeof y !== 'number' || !Number.isFinite(y)) return ` — ${dsUnit}`
            const dec = dsUnit === secondaryUnit ? secondaryDecimals : primaryDecimals
            return ` ${formatSensorValue(y, dsUnit, dec)}`
          },
        },
      },
    },
    scales,
  }
})

const exportWizardOpen = ref(false)

const exportWizardSensorContext = computed(() =>
  selectedDetailSensor.value
    ? {
        espId: selectedDetailSensor.value.espId,
        gpio: selectedDetailSensor.value.gpio,
        sensorType: selectedDetailSensor.value.sensorType,
        sensorName: selectedDetailSensor.value.name,
      }
    : undefined
)

function openExportWizard(): void {
  exportWizardOpen.value = true
}

// =============================================================================
// Level 3: Sensor Detail — Live Value, Stats, Trend (Block 1 Polishing)
// =============================================================================

/** Current live value from store (reactive) */
const detailLiveValue = computed(() => {
  if (!selectedDetailSensor.value) return null
  const device = espStore.devices.find(d =>
    espStore.getDeviceId(d) === selectedDetailSensor.value!.espId
  )
  if (!device) return null
  const sensors = (device.sensors as MockSensor[] | undefined) ?? []
  const sensor = selectedDetailSensor.value.configId
    ? sensors.find(s => s.config_id === selectedDetailSensor.value!.configId)
    : sensors.find(
        s => s.gpio === selectedDetailSensor.value!.gpio &&
             s.sensor_type === selectedDetailSensor.value!.sensorType
      )
  if (!sensor) return null
  return {
    value: sensor.raw_value,
    quality: sensor.quality ?? 'unknown',
    lastUpdate: sensor.last_reading_at ?? sensor.last_read ?? null,
  }
})

/** SENSOR_TYPE_CONFIG for the detail sensor */
const detailSensorTypeConfig = computed(() => {
  if (!selectedDetailSensor.value) return null
  return getSensorConfig(selectedDetailSensor.value.sensorType)
})

/** Data-range-based Y-axis bounds for the L3 detail chart (AUT-29) */
const detailDynamicYBounds = computed(() => {
  const readings = detailReadings.value
  if (readings.length === 0) return null

  const values = readings
    .map(r => r.processed_value ?? r.raw_value)
    .filter((v): v is number => Number.isFinite(v))
  if (values.length === 0) return null

  const dataMin = Math.min(...values)
  const dataMax = Math.max(...values)
  const dataSpan = dataMax - dataMin

  const cfg = detailSensorTypeConfig.value
  const rangeSpan = cfg ? Math.max(cfg.max - cfg.min, 0) : 0

  const minVisualSpan = Math.max(rangeSpan * 0.03, 0.5)
  const targetSpan = Math.max(dataSpan, minVisualSpan)
  const padding = targetSpan * 0.10

  let min = dataMin - padding
  let max = dataMax + padding

  if (dataSpan < minVisualSpan) {
    const extra = (minVisualSpan - dataSpan) / 2
    min -= extra
    max += extra
  }

  if (cfg) {
    min = Math.max(min, cfg.min)
    max = Math.min(max, cfg.max)
  }

  if (max <= min) {
    const center = values[values.length - 1] ?? dataMin
    min = center - minVisualSpan / 2
    max = center + minVisualSpan / 2
  }

  return { min, max }
})

/** Stale indicator: no update within DATA_STALE_THRESHOLD_S */
const detailIsStale = computed(() => {
  const lastUpdate = detailLiveValue.value?.lastUpdate
  if (!lastUpdate) return false
  return Date.now() - new Date(lastUpdate).getTime() > DATA_STALE_THRESHOLD_S * 1000
})

const detailHistoryLatestAt = computed<string | null>(() => {
  if (detailReadings.value.length === 0) return null
  // Server returns DESC order — index 0 is the most recent point/bucket
  const newest = detailReadings.value[0]
  return newest?.timestamp ?? null
})

const detailHistoryIsStale = computed(() => {
  if (!lastDetailApiSuccessAt.value) return true
  return Date.now() - lastDetailApiSuccessAt.value > DATA_STALE_THRESHOLD_S * 1000
})

const overlayHistoryLatest = computed(() => {
  const latest = new Map<string, string | null>()
  for (const key of overlaySensorIds.value) {
    const readings = overlaySensorReadings.value.get(key) ?? []
    // Server returns DESC — index 0 is the newest reading
    latest.set(key, readings.length > 0 ? readings[0].timestamp : null)
  }
  return latest
})

/** Trend calculation from readings (last 10% vs first 10%) */
const detailTrend = computed<'up' | 'down' | 'stable'>(() => {
  const readings = detailReadings.value
  if (readings.length < 4) return 'stable'
  const chunkSize = Math.max(2, Math.floor(readings.length * 0.1))
  // Server returns DESC — oldest buckets at end, newest at start
  const firstChunk = readings.slice(-chunkSize)
  const lastChunk = readings.slice(0, chunkSize)
  const avgFirst = firstChunk.reduce((sum, r) => sum + (r.processed_value ?? r.raw_value), 0) / chunkSize
  const avgLast = lastChunk.reduce((sum, r) => sum + (r.processed_value ?? r.raw_value), 0) / chunkSize
  const diff = avgLast - avgFirst
  const range = detailSensorTypeConfig.value
    ? (detailSensorTypeConfig.value.max - detailSensorTypeConfig.value.min)
    : Math.abs(avgFirst) || 1
  const threshold = range * 0.02
  if (diff > threshold) return 'up'
  if (diff < -threshold) return 'down'
  return 'stable'
})

/** Stats fetched from server API */
const detailStats = ref<SensorStats | null>(null)

async function fetchDetailStats() {
  if (!selectedDetailSensor.value) return
  try {
    const resp = await sensorsApi.getStats(
      selectedDetailSensor.value.espId,
      selectedDetailSensor.value.gpio,
      {
        start_time: detailStartTime.value,
        end_time: detailEndTime.value,
        sensor_type: selectedDetailSensor.value.sensorType,
      },
    )
    detailStats.value = resp.stats
  } catch (e) {
    console.warn('[MonitorView] Failed to fetch sensor stats:', selectedDetailSensor.value?.espId, 'GPIO', selectedDetailSensor.value?.gpio, e)
    detailStats.value = null
  }
}

/** Format a stat value with the detail sensor's unit and decimals */
function formatStatValue(value: number | null): string {
  if (value == null) return '—'
  const dec = detailSensorTypeConfig.value?.decimals ?? 2
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  }).format(value)
}

/** Find timestamp of min/max values from readings (client-side fallback) */
const detailMinMaxTimestamps = computed(() => {
  const readings = detailReadings.value
  if (readings.length === 0) return { minAt: null as string | null, maxAt: null as string | null }
  let minVal = Infinity
  let maxVal = -Infinity
  let minAt: string | null = null
  let maxAt: string | null = null
  for (const r of readings) {
    const val = r.processed_value ?? r.raw_value
    if (val < minVal) { minVal = val; minAt = r.timestamp }
    if (val > maxVal) { maxVal = val; maxAt = r.timestamp }
  }
  return { minAt, maxAt }
})

/** Format a timestamp to short time (HH:mm) */
function formatShortTime(ts: string | null): string {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })
  } catch { return '' }
}

/** Sensor config link removed — Monitor is read-only + Subzone-CRUD only */

// Fetch stats whenever detail data is loaded
watch(detailReadings, (readings) => {
  if (readings.length > 0) {
    fetchDetailStats()
  } else {
    detailStats.value = null
  }
})

/**
 * Load device contexts for all mobile/multi_zone sensors (6.7).
 * Iterates over espStore.devices, finds non-zone_local sensors with config_id,
 * and loads their active context from the API.
 */
async function loadMobileDeviceContexts(): Promise<void> {
  if (deviceContextStore.isLoaded) return
  const devices: Array<{ configType: 'sensor' | 'actuator'; configId: string }> = []
  for (const esp of espStore.devices) {
    const sensors = (esp.sensors as MockSensor[]) || []
    for (const sensor of sensors) {
      const s = sensor as MockSensor & { config_id?: string; device_scope?: string }
      if (s.device_scope && s.device_scope !== 'zone_local' && s.config_id) {
        devices.push({ configType: 'sensor', configId: s.config_id })
      }
    }
  }
  if (devices.length > 0) {
    await deviceContextStore.loadContextsForDevices(devices)
  }
}

// Fetch data on mount + deep-link support
onMounted(() => {
  if (espStore.devices.length === 0) {
    espStore.fetchAll()
  }

  // allZones fetch handled by useZoneKPIs composable (onMounted + guarded)

  // Fetch zone entities for filter dropdown (active + archived)
  if (zoneStore.zoneEntities.length === 0) {
    zoneStore.fetchZoneEntities()
  }

  // AUT-1324: Zone→Tank wiring for L2 EC/pH strip (existing tank store; not value API)
  tankStore.fetchTanks().catch(() => {
    // Offline cache in tank store remains usable; strip hides when empty.
  })

  // Fetch logic rules + execution history for ActuatorCard context
  logicStore.fetchRules()
  logicStore.loadExecutionHistory()
  logicStore.subscribeToWebSocket()

  // Load device contexts for mobile/multi_zone sensors (6.7)
  loadMobileDeviceContexts()

  // Update breadcrumb zone name
  if (selectedZoneId.value) {
    dashStore.breadcrumb.zoneName = selectedZoneName.value
  }
})

onUnmounted(() => {
  dashStore.breadcrumb.sensorName = ''
  deactivateScope('monitor-zone')
  unregisterLeft?.()
  unregisterRight?.()
  logicStore.unsubscribeFromWebSocket()
  // Abort any in-flight zone monitor request
  zoneMonitorAbort.value?.abort()
  // KPI debounce timer cleanup handled by useZoneKPIs composable
})

const monitorRecovery = createMonitorRecoveryOrchestrator(async () => {
  await espStore.fetchAll()
  if (selectedZoneId.value) {
    await fetchZoneMonitorData()
  }
  if (showSensorDetail.value && selectedDetailSensor.value) {
    await fetchDetailData()
  }
})

async function runMonitorRecovery(): Promise<void> {
  await monitorRecovery.trigger()
}

watch(
  () => monitorWs.connectionStatus.value,
  (status, prevStatus) => {
    if (status === 'connected' && prevStatus && prevStatus !== 'connected') {
      runMonitorRecovery().catch(() => {
        // Recovery errors surface via existing store/API error channels.
      })
    }
  },
)

// Graceful fallback: redirect to L1 if zone does not exist
// Check both device zones and allZones (includes empty zones from ZoneContext)
watch(
  [selectedZoneId, () => espStore.devices.length, allZones],
  ([zoneId, deviceCount]) => {
    if (!zoneId) return
    const zoneInDevices = espStore.devices.some(d => d.zone_id === zoneId)
    const zoneInApi = allZones.value.some(z => z.zone_id === zoneId)
    if (!zoneInDevices && !zoneInApi && deviceCount > 0) {
      router.replace({ name: 'monitor' })
    }
  },
  { immediate: true },
)

// Deep-link: open sensor detail from URL /monitor/:zoneId/sensor/:sensorId
watch(
  [selectedSensorId, () => espStore.devices.length],
  ([sensorId, deviceCount]) => {
    if (!sensorId || deviceCount === 0 || showSensorDetail.value) return

    // AUT-1533: config_id first. Legacy gpio URL only if that pin is unique.
    const storeSensors = collectStoreSensors(espStore.devices)
    const resolved = resolveMonitorDeepLink(sensorId, storeSensors)
    if (resolved.kind !== 'hit') return

    const sensor = resolved.sensor
    const host = espStore.devices.find((device) =>
      ((device.sensors as MockSensor[] | undefined) ?? []).some((candidate) =>
        sensor.config_id
          ? candidate.config_id === sensor.config_id
          : candidate === sensor,
      ),
    )
    if (!host) return

    openSensorDetail({
      esp_id: espStore.getDeviceId(host),
      gpio: sensor.gpio,
      sensor_type: sensor.sensor_type ?? '',
      name: sensor.name ?? null,
      unit: sensor.unit ?? '',
      config_id: sensor.config_id,
    })
  },
  { immediate: true },
)

// Zone KPI types + logic: see @/composables/useZoneKPIs

const monitorLastApiSuccessAt = computed(() => {
  const candidates = [
    lastZoneApiSuccessAt.value,
    lastZoneMonitorApiSuccessAt.value,
    lastDetailApiSuccessAt.value,
  ].filter((value): value is number => value != null)
  if (candidates.length === 0) return null
  return Math.max(...candidates)
})

const monitorConnectivityState = computed(() => resolveMonitorConnectivityState({
  wsStatus: monitorWs.connectionStatus.value,
  hasZoneApiError: zoneApiDegraded.value || zoneMonitorError.value != null,
  hasDetailApiError: showSensorDetail.value && detailError.value.length > 0,
  lastApiSuccessAt: monitorLastApiSuccessAt.value,
}))


const monitorSensorCardDataMode = computed(() => resolveMonitorDataMode({
  hasSnapshotBase: !zoneMonitorError.value,
  hasLiveOverlay: true,
  monitorState: monitorConnectivityState.value,
}))

const monitorActuatorCardDataMode = computed(() => resolveMonitorDataMode({
  hasSnapshotBase: !zoneMonitorError.value,
  hasLiveOverlay: true,
  monitorState: monitorConnectivityState.value,
}))

const showActuatorSnapshotWarning = computed(() =>
  monitorConnectivityState.value === 'disconnected' || monitorConnectivityState.value === 'degraded_api',
)

// =============================================================================
// L1 Zone Mini-Widgets (Phase 3)
// =============================================================================

/**
 * Returns the first zone-tile dashboard (empty shell or tile-compatible widgets).
 * Filters on scope='zone-tile' to avoid collision with full zone dashboards.
 */
function getZoneMiniPanelId(zoneId: string): string | undefined {
  return dashStore.getCanonicalZoneTileLayout(zoneId)?.id
}

function hasZoneTileRenderableWidgets(zoneId: string): boolean {
  const layout = dashStore.getCanonicalZoneTileLayout(zoneId)
  if (!layout) return false
  return getZoneTileRenderableWidgets(layout.widgets).length > 0
}

function getZoneTileEditorRoute(zoneId: string): RouteLocationRaw | null {
  const layoutId = getZoneMiniPanelId(zoneId)
  if (!layoutId) return null
  const layout = dashStore.getLayoutById(layoutId)
  if (!layout) return null
  return {
    name: 'editor-dashboard',
    params: { dashboardId: layout.serverId || layoutId },
  }
}

// =============================================================================
// Level 2: Unified subzone-first device grouping
// =============================================================================

interface ZoneDeviceSubzone {
  subzoneId: string | null
  subzoneName: string
  sensors: SensorWithContext[]
  actuators: ActuatorWithContext[]
}

const zoneDeviceGroup = computed<ZoneDeviceSubzone[]>(() => {
  if (!selectedZoneId.value) return []

  // Primary path: API data (server delivers subzones with sensors + actuators together)
  const data = zoneMonitorData.value
  if (data && !zoneMonitorError.value) {
    // Read espStore.devices to establish reactivity — live values override API snapshot
    const devices = espStore.devices
    return data.subzones.map(sz => ({
      subzoneId: sz.subzone_id,
      subzoneName: sz.subzone_id === null ? 'Zone-weit' : sz.subzone_name,
      sensors: sortSensorsMetricFirst(sz.sensors.map(s => {
        const device = devices.find(d => espStore.getDeviceId(d) === s.esp_id)
        const liveSensor = (device?.sensors as MockSensor[] | undefined)?.find(
          (sens) => sens.gpio === s.gpio && sens.sensor_type === s.sensor_type
        )
        const raw_value = liveSensor?.raw_value ?? s.raw_value ?? 0
        const quality = (liveSensor?.quality ?? s.quality) as SensorWithContext['quality']
        // AUT-298 fix: use most recent of all timestamp sources so sensor_data WS events
        // propagate to SensorCard.last_read even when sensor_health already set last_reading_at.
        const last_read = [liveSensor?.last_reading_at, liveSensor?.last_read, s.last_read]
          .filter((t): t is string => Boolean(t))
          .reduce<string | null>((best, ts) => !best || ts > best ? ts : best, null)
        return {
          ...s,
          raw_value,
          quality,
          last_read,
          // AUT-1533 leftover: server SubzoneSensorEntry has no config_id; hydrate from store.
          config_id: liveSensor?.config_id ?? (s as Partial<SensorWithContext>).config_id,
          interface_type: liveSensor?.interface_type ?? null,
          zone_id: data.zone_id,
          zone_name: data.zone_name,
          subzone_id: sz.subzone_id,
          subzone_name: sz.subzone_name,
          esp_state: device?.system_state,
          device_scope: liveSensor?.device_scope ?? (s as Partial<SensorWithContext>).device_scope ?? null,
          assigned_zones: liveSensor?.assigned_zones ?? (s as Partial<SensorWithContext>).assigned_zones ?? [],
          // AUT-298: operating_mode is config, not live data — API is authoritative.
          // Store value is fallback only (sensor_health WS may not cover all sensors).
          // Never let a store value from a sibling sensor (same GPIO) override the API config.
          operating_mode: (s as Partial<SensorWithContext>).operating_mode ?? liveSensor?.operating_mode ?? null,
          is_stale: liveSensor?.is_stale ?? (s as Partial<SensorWithContext>).is_stale ?? false,
          // AUT-1544: SubzoneSensorEntry has no calibration blob; hydrate from store (same leftover as config_id).
          calibration: liveSensor?.calibration ?? (s as Partial<SensorWithContext>).calibration ?? null,
          // AUT-1557: zone-monitor payload has no mount_*; leftover from store (A1 config).
          mount_height_cm: liveSensor?.mount_height_cm ?? (s as Partial<SensorWithContext>).mount_height_cm ?? null,
          mount_medium: liveSensor?.mount_medium ?? (s as Partial<SensorWithContext>).mount_medium ?? null,
          mount_angle_deg: liveSensor?.mount_angle_deg ?? (s as Partial<SensorWithContext>).mount_angle_deg ?? null,
        }
      }) as SensorWithContext[]),
      actuators: sortActuatorsStable(sz.actuators.map(a => ({
        ...a,
        state: (() => {
          const liveDevice = devices.find(d => espStore.getDeviceId(d) === a.esp_id)
          const liveActuator = (liveDevice?.actuators as ActuatorWithContext[] | undefined)?.find(
            candidate => candidate.gpio === a.gpio,
          )
          return liveActuator?.state ?? a.state
        })(),
        pwm_value: (() => {
          const liveDevice = devices.find(d => espStore.getDeviceId(d) === a.esp_id)
          const liveActuator = (liveDevice?.actuators as ActuatorWithContext[] | undefined)?.find(
            candidate => candidate.gpio === a.gpio,
          )
          return liveActuator?.pwm_value ?? a.pwm_value
        })(),
        emergency_stopped: (() => {
          const liveDevice = devices.find(d => espStore.getDeviceId(d) === a.esp_id)
          const liveActuator = (liveDevice?.actuators as ActuatorWithContext[] | undefined)?.find(
            candidate => candidate.gpio === a.gpio,
          )
          return liveActuator?.emergency_stopped ?? a.emergency_stopped
        })(),
        last_command_at: (() => {
          const liveDevice = devices.find(d => espStore.getDeviceId(d) === a.esp_id)
          const liveActuator = (liveDevice?.actuators as ActuatorWithContext[] | undefined)?.find(
            candidate => candidate.gpio === a.gpio,
          )
          return liveActuator?.last_command_at ?? (a as Partial<ActuatorWithContext>).last_command_at ?? null
        })(),
        esp_state: (() => {
          const liveDevice = devices.find(d => espStore.getDeviceId(d) === a.esp_id)
          return liveDevice?.system_state ?? (a as Partial<ActuatorWithContext>).esp_state
        })(),
        last_seen: (() => {
          const liveDevice = devices.find(d => espStore.getDeviceId(d) === a.esp_id)
          return liveDevice?.last_seen ?? (a as Partial<ActuatorWithContext>).last_seen ?? null
        })(),
        zone_id: data.zone_id,
        zone_name: data.zone_name,
        subzone_id: sz.subzone_id,
        subzone_name: sz.subzone_name,
      })) as ActuatorWithContext[]),
    })).sort((a, b) => {
      // Named subzones first (alphabetical), "Zone-weit" (null) at end
      if (a.subzoneId === null) return 1
      if (b.subzoneId === null) return -1
      return (a.subzoneName ?? '').localeCompare(b.subzoneName ?? '')
    })
  }

  // Fallback path: useZoneGrouping + useSubzoneResolver (merge sensors + actuators)
  const sensorGroup = sensorsByZone.value.find(z => z.zoneId === selectedZoneId.value)
  const actuatorGroup = actuatorsByZone.value.find(z => z.zoneId === selectedZoneId.value)
  if (!sensorGroup && !actuatorGroup) return []

  const subzoneMap = new Map<string | null, ZoneDeviceSubzone>()

  for (const sz of sensorGroup?.subzones ?? []) {
    subzoneMap.set(sz.subzoneId, {
      subzoneId: sz.subzoneId,
      subzoneName: sz.subzoneId === null ? 'Zone-weit' : (sz.subzoneName || 'Zone-weit'),
      sensors: sortSensorsMetricFirst(sz.sensors as SensorWithContext[]),
      actuators: [],
    })
  }

  for (const sz of actuatorGroup?.subzones ?? []) {
    const existing = subzoneMap.get(sz.subzoneId)
    if (existing) {
      existing.actuators = sortActuatorsStable(sz.actuators as ActuatorWithContext[])
    } else {
      subzoneMap.set(sz.subzoneId, {
        subzoneId: sz.subzoneId,
        subzoneName: sz.subzoneId === null ? 'Zone-weit' : (sz.subzoneName || 'Zone-weit'),
        sensors: [],
        actuators: sortActuatorsStable(sz.actuators as ActuatorWithContext[]),
      })
    }
  }

  return Array.from(subzoneMap.values()).sort((a, b) => {
    if (a.subzoneId === null) return 1
    if (b.subzoneId === null) return -1
    return (a.subzoneName ?? '').localeCompare(b.subzoneName ?? '')
  })
})

/** AUT-1324: Zone→Tank EC/pH strip — tanks via existing store, values from zoneDeviceGroup */
const tanksInSelectedZone = computed(() => {
  if (!selectedZoneId.value) return []
  return tankStore.tanksForZone(selectedZoneId.value)
})

const flattenedZoneSensors = computed(() =>
  zoneDeviceGroup.value.flatMap((sz) => sz.sensors),
)

const selectedZoneName = computed(() => {
  if (!selectedZoneId.value) return ''
  const device = espStore.devices.find(d => d.zone_id === selectedZoneId.value)
  return device?.zone_name || selectedZoneId.value
})

const selectedZoneKpi = computed(() =>
  zoneKPIs.value.find(zone => zone.zoneId === selectedZoneId.value) ?? null,
)

const zoneHealthLabelMap: Record<ZoneHealthStatus, string> = {
  ok: 'Stabil',
  warning: 'Warnung',
  alarm: 'Kritisch',
  empty: 'Leer',
}

const selectedZoneHealthStatus = computed<ZoneHealthStatus | null>(() =>
  selectedZoneKpi.value?.healthStatus ?? null,
)

const selectedZoneHealthLabel = computed(() => {
  const status = selectedZoneHealthStatus.value
  if (status == null) return 'Unbekannt'
  return zoneHealthLabelMap[status]
})

const selectedZoneHealthReason = computed(() =>
  selectedZoneKpi.value?.healthReason ?? null,
)

const filteredZoneSensorCount = computed(() =>
  filteredSubzones.value.reduce((sum, sz) => sum + sz.sensors.length, 0)
)
const filteredZoneActuatorCount = computed(() =>
  filteredSubzones.value.reduce((sum, sz) => sum + sz.actuators.length, 0)
)

/**
 * Shared sensor references for L2 (6.7):
 * Multi-zone sensors from OTHER zones whose assigned_zones includes the current zone.
 */
const sharedSensorRefs = computed(() => {
  if (!selectedZoneId.value) return []
  const zoneId = selectedZoneId.value
  const result: Array<MockSensor & { _homeZoneName: string; _homeZoneId: string; esp_id: string }> = []

  for (const esp of espStore.devices) {
    // Only look at ESPs NOT in the current zone (to avoid duplication)
    if (esp.zone_id === zoneId) continue
    const sensors = (esp.sensors as MockSensor[]) || []
    for (const sensor of sensors) {
      const s = sensor as MockSensor & { device_scope?: string; assigned_zones?: string[] }
      if (
        s.device_scope === 'multi_zone' &&
        s.assigned_zones?.includes(zoneId)
      ) {
        result.push({
          ...sensor,
          _homeZoneName: esp.zone_name || esp.zone_id || '',
          _homeZoneId: esp.zone_id || '',
          esp_id: espStore.getDeviceId(esp),
        })
      }
    }
  }
  return result
})

// Reactive breadcrumb update — when devices load after mount, zone_id → zone_name
watch(selectedZoneName, (name) => {
  if (name && selectedZoneId.value) {
    dashStore.breadcrumb.zoneName = name
  }
})

// Breadcrumb update for dashboard name (match by local ID or server UUID via store getter)
watch(selectedDashboardId, (dashId) => {
  if (dashId) {
    const layout = dashStore.getLayoutById(dashId)
    dashStore.breadcrumb.dashboardName = layout?.name || ''
  } else {
    dashStore.breadcrumb.dashboardName = ''
  }
}, { immediate: true })

// Fetch zone monitor data (API primary for L2) with AbortController for race-condition safety
async function fetchZoneMonitorData() {
  const zoneId = selectedZoneId.value
  if (!zoneId) {
    zoneMonitorData.value = null
    zoneMonitorError.value = null
    return
  }
  // Only fetch when zone exists in current devices (avoids 500 for invalid/deep-link zone slugs)
  const zoneExists = espStore.devices.some((d) => d.zone_id === zoneId)
  if (!zoneExists) {
    zoneMonitorData.value = null
    zoneMonitorError.value = null
    return
  }

  // Abort previous in-flight request (race-condition guard on fast zone switches)
  if (zoneMonitorAbort.value) {
    zoneMonitorAbort.value.abort()
  }
  const controller = new AbortController()
  zoneMonitorAbort.value = controller

  zoneMonitorLoading.value = true
  zoneMonitorError.value = null
  try {
    const data = await zonesApi.getZoneMonitorData(zoneId, controller.signal)
    zoneMonitorData.value = data
    lastZoneMonitorApiSuccessAt.value = Date.now()
  } catch (e) {
    // Ignore AbortError — expected when user switches zones quickly
    if (e instanceof DOMException && e.name === 'AbortError') return
    zoneMonitorError.value = e instanceof Error ? e.message : 'Fehler beim Laden'
    zoneMonitorData.value = null
  } finally {
    // Only clear loading if this controller is still current (not superseded)
    if (zoneMonitorAbort.value === controller) {
      zoneMonitorLoading.value = false
    }
  }
}

watch(selectedZoneId, (zoneId) => {
  if (zoneId) fetchZoneMonitorData()
  else {
    zoneMonitorData.value = null
    zoneMonitorError.value = null
  }
}, { immediate: true })

// Lazy Resolver: trigger only when primary monitor-data API fails
watch(zoneMonitorError, (err) => {
  if (err && selectedZoneId.value) {
    subzoneResolver.buildResolver()
  }
})

// Load initial sparkline history when zone device data becomes available
watch(zoneDeviceGroup, (subzones) => {
  if (!subzones.length) return
  const sensors: { esp_id: string; gpio: number; sensor_type?: string }[] = []
  for (const sz of subzones) {
    for (const s of sz.sensors) {
      sensors.push({ esp_id: s.esp_id, gpio: s.gpio, sensor_type: s.sensor_type })
    }
  }
  if (sensors.length > 0) {
    loadSparklineHistory(sensors)
  }
})

// =============================================================================
// Accordion State with localStorage persistence
// =============================================================================

const collapsedSubzones = ref<Set<string>>(new Set())

function loadAccordionState(zoneId: string) {
  try {
    const stored = localStorage.getItem(`ao-monitor-subzone-collapse-${zoneId}`)
    if (stored) {
      collapsedSubzones.value = new Set(JSON.parse(stored))
      return
    }
  } catch {
    // Fall through to smart defaults
  }

  applySmartDefaults(zoneId)
}

function applySmartDefaults(zoneId: string) {
  const subzones = zoneDeviceGroup.value

  // Collapse empty subzones (0 sensors + 0 actuators)
  const emptyKeys = new Set<string>()
  for (const sz of subzones) {
    if (sz.sensors.length === 0 && sz.actuators.length === 0) {
      emptyKeys.add(getSubzoneKey(zoneId, sz.subzoneId))
    }
  }

  // Count named subzones (exclude "Zone-weit")
  const namedSubzones = subzones.filter(sz => sz.subzoneId !== null)

  if (namedSubzones.length <= 4) {
    // <= 4 subzones: all open, except empty ones
    collapsedSubzones.value = emptyKeys
    return
  }

  // >4 named subzones: only first named + "Zone-weit" open
  const firstNamedId = namedSubzones[0]?.subzoneId

  const collapsed = new Set<string>(emptyKeys)
  for (const sz of namedSubzones) {
    if (sz.subzoneId === firstNamedId) continue
    collapsed.add(getSubzoneKey(zoneId, sz.subzoneId))
  }

  collapsedSubzones.value = collapsed
}

function saveAccordionState(zoneId: string) {
  try {
    localStorage.setItem(
      `ao-monitor-subzone-collapse-${zoneId}`,
      JSON.stringify([...collapsedSubzones.value])
    )
  } catch {
    // localStorage full or unavailable
  }
}

function isSubzoneExpanded(subzoneKey: string): boolean {
  return !collapsedSubzones.value.has(subzoneKey)
}

function toggleSubzone(subzoneKey: string) {
  const next = new Set(collapsedSubzones.value)
  if (next.has(subzoneKey)) {
    next.delete(subzoneKey)
  } else {
    next.add(subzoneKey)
  }
  collapsedSubzones.value = next
  if (selectedZoneId.value) {
    saveAccordionState(selectedZoneId.value)
  }
}

function shouldShowSubzoneAccordionHeader(subzoneId: string | null): boolean {
  return filteredSubzones.value.length > 1 || subzoneId !== null
}

// Apply smart defaults once data becomes available (zoneSensorGroup may be null on initial load)
const smartDefaultsApplied = ref(false)

// Load accordion state when zone changes (also handles Prev/Next nav via router.replace)
const prevZoneId = ref<string | null>(null)

watch(selectedZoneId, (zoneId) => {
  if (zoneId && zoneId !== prevZoneId.value) {
    loadAccordionState(zoneId)
    prevZoneId.value = zoneId
    smartDefaultsApplied.value = false
    // Close expanded sensor panel when switching zones
    expandedSensorKey.value = null
  }
}, { immediate: true })

watch(
  zoneDeviceGroup,
  () => {
    if (smartDefaultsApplied.value) return
    if (!selectedZoneId.value) return
    if (zoneDeviceGroup.value.length === 0) return

    const stored = localStorage.getItem(
      `ao-monitor-subzone-collapse-${selectedZoneId.value}`
    )
    if (stored) {
      smartDefaultsApplied.value = true
      return
    }

    applySmartDefaults(selectedZoneId.value)
    smartDefaultsApplied.value = true
  }
)

// =============================================================================
// Navigation
// =============================================================================

function goToZone(zoneId: string) {
  router.push({ name: 'monitor-zone', params: { zoneId } })
}

function goBack() {
  router.push({ name: 'monitor' })
}

// Zone-to-Zone navigation (Prev/Next on L2)
const sortedZoneIds = computed(() => zoneKPIs.value.map(z => z.zoneId))

const currentZoneIndex = computed(() => {
  if (!selectedZoneId.value) return -1
  return sortedZoneIds.value.indexOf(selectedZoneId.value)
})

const prevNavZoneId = computed(() => {
  const idx = currentZoneIndex.value
  return idx > 0 ? sortedZoneIds.value[idx - 1] : null
})

const nextNavZoneId = computed(() => {
  const idx = currentZoneIndex.value
  return idx >= 0 && idx < sortedZoneIds.value.length - 1
    ? sortedZoneIds.value[idx + 1]
    : null
})

/** L2 inline panels: cross-zone + zone-specific for selectedZoneId (E3) */
const inlineMonitorPanelsL2 = computed(() => {
  const cross = dashStore.inlineMonitorPanelsCrossZone
  const zoneId = selectedZoneId.value
  if (!zoneId) return cross
  const forZone = dashStore.inlineMonitorPanelsForZone(zoneId)
  const seen = new Set(cross.map(p => p.id))
  const combined = [...cross]
  for (const p of forZone) {
    if (!seen.has(p.id)) {
      seen.add(p.id)
      combined.push(p)
    }
  }
  return combined.sort((a, b) => (a.target?.order ?? 0) - (b.target?.order ?? 0))
})

function goToPrevZone() {
  if (prevNavZoneId.value) {
    router.replace({ name: 'monitor-zone', params: { zoneId: prevNavZoneId.value } })
  }
}

function goToNextZone() {
  if (nextNavZoneId.value) {
    router.replace({ name: 'monitor-zone', params: { zoneId: nextNavZoneId.value } })
  }
}

// =============================================================================
// Keyboard shortcuts: ArrowLeft/ArrowRight for zone navigation on L2
// =============================================================================

const { register: registerShortcut, activateScope, deactivateScope } = useKeyboardShortcuts()
let unregisterLeft: (() => void) | null = null
let unregisterRight: (() => void) | null = null

watch(selectedZoneId, (zoneId) => {
  if (zoneId) {
    activateScope('monitor-zone')
    unregisterLeft?.()
    unregisterRight?.()
    unregisterLeft = registerShortcut({
      key: 'ArrowLeft',
      handler: goToPrevZone,
      description: 'Vorherige Zone',
      scope: 'monitor-zone',
    })
    unregisterRight = registerShortcut({
      key: 'ArrowRight',
      handler: goToNextZone,
      description: 'Nächste Zone',
      scope: 'monitor-zone',
    })
  } else {
    deactivateScope('monitor-zone')
    unregisterLeft?.()
    unregisterRight?.()
    unregisterLeft = null
    unregisterRight = null
  }
})

// =============================================================================
// Swipe navigation: Left/Right swipe for zone navigation on L2
// =============================================================================

const monitorContentRef = ref<HTMLElement | null>(null)

useSwipeNavigation(monitorContentRef, {
  onSwipeLeft: () => { if (selectedZoneId.value) goToNextZone() },
  onSwipeRight: () => { if (selectedZoneId.value) goToPrevZone() },
  threshold: 50,
})

// =============================================================================
// Actuator control
// =============================================================================

async function toggleActuator(espId: string, gpio: number, currentState: boolean) {
  const command = currentState ? 'OFF' : 'ON'
  try {
    await espStore.sendActuatorCommand(espId, gpio, command)
  } catch {
    // Toast handled by store
  }
}

// AUT-995 Feld 6: one-shot dose — ActuatorCard computed the auto-off duration from dose_ml / flow_rate_ml_s.
async function doseActuator(espId: string, gpio: number, durationSeconds: number) {
  try {
    await espStore.sendActuatorCommand(espId, gpio, 'ON', undefined, durationSeconds)
  } catch {
    // Toast handled by store
  }
}

// Helpers
function getSubzoneKey(zoneId: string | null, subzoneId: string | null): string {
  return `${zoneId ?? '__u'}-${subzoneId ?? '__n'}`
}

/**
 * AUT-1537: sensors rendered as subzone cards (membership-aware).
 * Tank-assigned ESP: EC/pH + Messbox-T leave the card (strip/tile). Unassigned keeps them.
 * Raw `subzone.sensors` from the server is intentionally left unchanged.
 */
function subzoneCardSensors<T extends { sensor_type: string; esp_id?: string }>(sensors: T[]): T[] {
  return filterOutEcPhSensors(sensors, espStore.devices)
}

// Subzone KPI helper: same AggCategory semantics as aggregateZoneSensors (sensorDefaults.formatSubzoneKpiLine)
// AUT-1537: header mirrors visible cards (membership-aware, not type-hide).
function getSubzoneKPIs(sensors: { sensor_type: string; raw_value: number | null; unit: string; quality: string; esp_id?: string }[]): string {
  return formatSubzoneKpiLine(subzoneCardSensors(sensors))
}

// Worst-case quality status for a set of sensors (defense-in-depth via timestamp check)
function getWorstQualityStatus(sensors: { quality: string; last_read?: string | null }[]): 'good' | 'warning' | 'alarm' | 'stale' | 'offline' {
  let worst: 'good' | 'warning' | 'alarm' | 'stale' | 'offline' = 'good'
  for (const s of sensors) {
    const status = qualityToStatus(s.quality, { lastRead: s.last_read })
    if (status === 'alarm') return 'alarm'
    if (status === 'warning' && worst !== 'warning') worst = 'warning'
    if (status === 'stale' && worst === 'good') worst = 'stale'
    if (status === 'offline' && worst === 'good') worst = 'offline'
  }
  return worst
}
</script>

<template>
  <div class="monitor-view">
    <!-- View Tab Bar (Hardware / Monitor / Dashboard) -->
    <div class="monitor-view__head">
      <ViewTabBar class="monitor-view__head-tabs" />
    </div>

    <!-- L3 Dashboard View (Cross-Zone or Zone-specific) -->
    <template v-if="isDashboardView">
      <DashboardViewer :layoutId="selectedDashboardId!" showHeader />
    </template>

    <!-- L1/L2 with optional Side-Panel and Bottom-Panel -->
    <div v-else class="monitor-layout" :class="{ 'monitor-layout--has-side': sideMonitorPanels.length > 0 }">
      <div class="monitor-layout__main-col">
      <main class="monitor-layout__main">

    <!-- Level 1: Zone Overview -->
    <template v-if="!isZoneDetail">
      <!-- L1 Ready-Gate: Loading → Error → Content -->
      <BaseSkeleton v-if="espStore.isLoading" text="Lade Zonen..." full-height />
      <ErrorState
        v-else-if="espStore.error"
        :message="espStore.error"
        title="Fehler beim Laden der Geräte"
        show-retry
        @retry="espStore.fetchAll()"
      />
      <template v-else>


      <!-- Flapping Banner (PKG-20) -->
      <div v-if="espStore.hasFlappingDevices" class="monitor-flapping-banner">
        <AlertTriangle class="monitor-flapping-banner__icon" />
        <span class="monitor-flapping-banner__text">
          {{ espStore.flappingDeviceCount }} {{ espStore.flappingDeviceCount === 1 ? 'Gerät' : 'Geräte' }}
          mit instabiler Verbindung (Disconnect-Loop)
        </span>
        <span class="monitor-flapping-banner__hint">
          {{ espStore.flappingDeviceIds.slice(0, 3).join(', ') }}{{ espStore.flappingDeviceCount > 3 ? ` +${espStore.flappingDeviceCount - 3}` : '' }}
        </span>
      </div>

      <!-- Empty State (only when loading done + no error + truly empty) -->
      <div v-if="zoneKPIs.length === 0" class="monitor-view__empty">
        <Activity class="w-12 h-12" style="color: var(--color-text-muted)" />
        <p>Noch keine Zonen eingerichtet.</p>
        <p class="monitor-view__empty-hint">Weise Geräten Zonen zu unter Hardware.</p>
        <router-link to="/hardware" class="monitor-view__empty-cta">
          Zur Hardware-Ansicht
        </router-link>
      </div>

      <!-- Zone Tiles Grid -->
      <div v-else class="monitor-zone-grid">
        <ZoneTileCard
          v-for="zone in filteredZoneKPIs"
          :key="zone.zoneId"
          :zone="zone"
          :is-stale="isZoneStale(zone.lastActivity)"
          :mock-sensor-count="zoneMockSensorCounts.get(zone.zoneId) ?? 0"
          :flapping-count="espStore.getFlappingDevicesInZone(zone.zoneId).length"
          :rules="logicStore.getRulesForZone(zone.zoneId)"
          :total-rule-count="logicStore.getRulesForZone(zone.zoneId).length"
          :is-rule-active="logicStore.isRuleActive"
          :zone-tile-editor-to="getZoneTileEditorRoute(zone.zoneId)"
          @click="goToZone(zone.zoneId)"
        >
          <template #extra>
            <div class="monitor-zone-tile__extra-stack">
              <ZoneTileInsightBlock :zone="zone" />
              <InlineDashboardPanel
                v-if="getZoneMiniPanelId(zone.zoneId) && hasZoneTileRenderableWidgets(zone.zoneId)"
                :layout-id="getZoneMiniPanelId(zone.zoneId)!"
                :zone-id="zone.zoneId"
                :compact="true"
                mode="view"
                class="monitor-zone-tile__mini-widget"
              />
            </div>
          </template>
        </ZoneTileCard>
      </div>

      <!-- L1 Cross-Zone Rules Overview (AUT-663): Top-5 enabled rules across all zones -->
      <ZoneRulesSection
        v-if="logicStore.rules.some(r => r.enabled)"
        :aggregate-mode="true"
        class="monitor-zone-aggregate-rules"
      />

      </template>
    </template>

    <!-- Level 2: Zone Data Detail (Subzone Accordion) -->
    <template v-else>
      <!-- Ready-Gate: BaseSkeleton during load, ErrorState on API error -->
      <BaseSkeleton v-if="zoneMonitorLoading" text="Lade Zonendaten..." full-height />
      <ErrorState
        v-else-if="zoneMonitorError"
        :message="zoneMonitorError"
        show-retry
        @retry="fetchZoneMonitorData()"
      />
      <div v-else ref="monitorContentRef">
      <section
        class="monitor-zone-detail"
        :class="selectedZoneHealthStatus ? `monitor-zone-detail--${selectedZoneHealthStatus}` : ''"
        :aria-label="selectedZoneHealthLabel ? `${selectedZoneName}: ${selectedZoneHealthLabel}` : selectedZoneName"
      >
      <div
        class="monitor-view__header"
        :class="{ 'monitor-view__header--with-zone-nav': sortedZoneIds.length > 1 }"
      >
        <button class="monitor-view__back" aria-label="Zurück" title="Zurück" @click="goBack">
          <ArrowLeft class="w-4 h-4" />
        </button>

        <!-- Zone-to-Zone Navigation -->
        <div v-if="sortedZoneIds.length > 1" class="monitor-view__zone-nav">
          <button
            class="monitor-view__zone-nav-btn"
            :disabled="!prevNavZoneId"
            aria-label="Vorherige Zone"
            title="Vorherige Zone"
            @click="goToPrevZone"
          >
            <ChevronLeft class="w-4 h-4" />
          </button>
          <span class="monitor-view__zone-nav-label">
            {{ selectedZoneName }}
          </span>
          <button
            class="monitor-view__zone-nav-btn"
            :disabled="!nextNavZoneId"
            aria-label="Nächste Zone"
            title="Nächste Zone"
            @click="goToNextZone"
          >
            <ChevronRight class="w-4 h-4" />
          </button>
        </div>

        <div v-else class="monitor-view__header-info">
          <h2 class="monitor-view__title">{{ selectedZoneName }}</h2>
        </div>
      </div>
      <p v-if="selectedZoneHealthReason" class="monitor-view__header-reason">
        {{ selectedZoneHealthReason }}
      </p>

      <!-- AUT-1324: Zone/Tank EC+pH strip (Ist + Verlauf; before subzones) -->
      <ZoneTankEcPhBar
        v-if="tanksInSelectedZone.length > 0"
        :tanks="tanksInSelectedZone"
        :devices="espStore.devices"
        :zone-sensors="flattenedZoneSensors"
        :get-sparkline="getTankStripSparkline"
        :get-thresholds="getDefaultThresholds"
      />

      <!-- Unified Subzone-First Section (sensors + actuators per subzone) -->
      <section v-if="filteredSubzones.length > 0" class="monitor-section monitor-section--subzones">
        <div
          v-for="subzone in filteredSubzones"
          :key="subzone.subzoneId ?? '__zoneweit__'"
          class="monitor-subzone"
          :class="{ 'monitor-subzone--unassigned': subzone.subzoneId === null }"
        >
          <!-- Accordion-Header: only when >1 subzone OR named subzone -->
          <button
            v-if="shouldShowSubzoneAccordionHeader(subzone.subzoneId)"
            @click="toggleSubzone(getSubzoneKey(selectedZoneId, subzone.subzoneId))"
            class="monitor-subzone__header"
            :class="{ 'monitor-subzone__header--zoneweit': subzone.subzoneId === null }"
          >
            <ChevronRight
              :class="['monitor-subzone__chevron', { 'monitor-subzone__chevron--expanded': isSubzoneExpanded(getSubzoneKey(selectedZoneId, subzone.subzoneId)) }]"
            />
            <StatusBadge :level="sensorStatusToLevel(getWorstQualityStatus(subzoneCardSensors(subzone.sensors)))" compact />
            <span class="monitor-subzone__name" :title="subzone.subzoneName">{{ subzone.subzoneName }}</span>
            <span class="monitor-subzone__count">
              {{ subzoneCardSensors(subzone.sensors).length }}S · {{ subzone.actuators.length }}A
            </span>
            <span class="monitor-subzone__kpis" v-if="getSubzoneKPIs(subzone.sensors)">{{ getSubzoneKPIs(subzone.sensors) }}</span>
          </button>
          <div
            v-else
            class="monitor-subzone__header monitor-subzone__header--static monitor-subzone__header--zoneweit"
          >
            <StatusBadge :level="sensorStatusToLevel(getWorstQualityStatus(subzoneCardSensors(subzone.sensors)))" compact />
            <span class="monitor-subzone__name" :title="subzone.subzoneName">{{ subzone.subzoneName }}</span>
            <span class="monitor-subzone__count">
              {{ subzoneCardSensors(subzone.sensors).length }}S · {{ subzone.actuators.length }}A
            </span>
            <span class="monitor-subzone__kpis" v-if="getSubzoneKPIs(subzone.sensors)">{{ getSubzoneKPIs(subzone.sensors) }}</span>
            <span class="monitor-subzone__optional-hint">Keine Subzone konfiguriert</span>
          </div>

          <!-- Accordion-Body -->
          <Transition name="accordion">
          <div
            v-show="!shouldShowSubzoneAccordionHeader(subzone.subzoneId) || isSubzoneExpanded(getSubzoneKey(selectedZoneId, subzone.subzoneId))"
            class="monitor-subzone__content"
          >

            <!-- Sensors (AUT-1537: membership-aware hide of tank-routed EC/pH/T) -->
            <template v-if="subzoneCardSensors(subzone.sensors).length > 0">
              <div
                v-if="subzoneCardSensors(subzone.sensors).length > 0 && subzone.actuators.length > 0"
                class="monitor-subzone__type-label"
              >Sensoren</div>
              <div class="monitor-card-grid grid-auto-sm">
                <div
                  v-for="sensor in subzoneCardSensors(subzone.sensors)"
                  :key="`${sensor.esp_id}-${sensor.gpio}-${sensor.sensor_type}`"
                  :class="[
                    'monitor-sensor-card',
                    { 'monitor-sensor-card--expanded': expandedSensorKey === getSensorKey(sensor.esp_id, sensor.gpio, sensor.sensor_type) }
                  ]"
                  :ref="(el) => registerSensorCardElement(getSensorKey(sensor.esp_id, sensor.gpio, sensor.sensor_type), el)"
                >
                  <SensorCard
                    :sensor="sensor"
                    mode="monitor"
                    :data-mode="monitorSensorCardDataMode"
                    :trend="getSensorTrend(sensor.esp_id, sensor.gpio, sensor.sensor_type)"
                    :sparkline-time-label="getSparklineTimeLabel(sensor)"
                    @click="toggleExpanded(getSensorKey(sensor.esp_id, sensor.gpio, sensor.sensor_type))"
                  >
                    <template #sparkline>
                      <LiveLineChart
                        v-if="getDisplaySparkline(sensor)?.length"
                        :data="getDisplaySparkline(sensor)!"
                        compact
                        height="32px"
                        :max-data-points="30"
                        :sensor-type="sensor.sensor_type"
                        :thresholds="getDefaultThresholds(sensor.sensor_type)"
                        :show-thresholds="!!getDefaultThresholds(sensor.sensor_type)"
                      />
                      <span v-else class="sensor-card__sparkline-placeholder">Keine Daten</span>
                    </template>
                  </SensorCard>

                  <!-- Expanded Chart Panel (inline 1h chart) — shared MonitorExpanded1hChart -->
                  <Transition name="expand">
                    <MonitorExpanded1hChart
                      v-if="expandedSensorKey === getSensorKey(sensor.esp_id, sensor.gpio, sensor.sensor_type)"
                      :esp-id="sensor.esp_id"
                      :gpio="sensor.gpio"
                      :sensor-type="sensor.sensor_type"
                      :unit="resolveSensorUnit(sensor)"
                      :live-sample="getExpandedLiveSample(sensor)"
                      show-detail-action
                      @detail="openSensorDetail(sensor)"
                    />
                  </Transition>
                </div>
              </div>
            </template>

            <!-- Separator: only when BOTH types present -->
            <hr
              v-if="subzoneCardSensors(subzone.sensors).length > 0 && subzone.actuators.length > 0"
              class="monitor-subzone__separator"
            />

            <!-- Actuators -->
            <template v-if="subzone.actuators.length > 0">
              <div
                v-if="subzoneCardSensors(subzone.sensors).length > 0 && subzone.actuators.length > 0"
                class="monitor-subzone__type-label"
              >Aktoren</div>
              <div class="monitor-card-grid grid-auto-sm">
                <ActuatorCard
                  v-for="actuator in subzone.actuators"
                  :key="`${actuator.esp_id}-${actuator.gpio}`"
                  :actuator="actuator"
                  mode="monitor"
                  :data-mode="monitorActuatorCardDataMode"
                  :show-snapshot-warning="showActuatorSnapshotWarning"
                  :linked-rules="logicStore.getRulesForActuator(actuator.esp_id, actuator.gpio)"
                  :last-execution="logicStore.getLastExecutionForActuator(actuator.esp_id, actuator.gpio)"
                  @toggle="toggleActuator"
                  @dose-now="doseActuator"
                />
              </div>
            </template>

            <!-- Empty subzone -->
            <div
              v-if="subzoneCardSensors(subzone.sensors).length === 0 && subzone.actuators.length === 0"
              class="monitor-subzone__empty"
            >
              Keine Geräte zugeordnet
            </div>
          </div>
          </Transition>
        </div>
      </section>

      <!-- AUT-1326: compact tank tile after all subzones, before zone-wide rules -->
      <section
        v-if="tanksInSelectedZone.length > 0"
        class="monitor-section monitor-section--tanks"
        aria-label="Tank Ist und Verlauf"
      >
        <TankIstSollPanel
          v-for="tank in tanksInSelectedZone"
          :key="tank.id"
          :tank-id="tank.id"
          :tank-name="tank.name"
          variant="monitor-compact"
          :zone-sensors="flattenedZoneSensors"
          :get-sparkline="getTankStripSparkline"
          :get-thresholds="getDefaultThresholds"
          @sensor-detail="openSensorDetail"
        />
      </section>
      </section>

      <!-- Zonenweite Regeln (bewusst getrennt von Subzone-Bloecken) -->
      <div class="monitor-zonewide-rules">
        <ZoneRulesSection :zone-id="selectedZoneId" />
      </div>

      <!-- Shared Sensors from other zones (6.7) -->
      <section v-if="sharedSensorRefs.length > 0" class="monitor-shared-equipment">
        <h3 class="monitor-section__title">
          Shared Sensors
          <span class="monitor-section__count">{{ sharedSensorRefs.length }}</span>
        </h3>
        <div class="monitor-shared-equipment__grid grid-auto-sm">
          <SharedSensorRefCard
            v-for="sensor in sharedSensorRefs"
            :key="sensor.config_id || `${sensor.esp_id}-${sensor.gpio}`"
            :sensor="sensor"
            :home-zone-id="sensor._homeZoneId"
          />
        </div>
      </section>

      <!-- Inline Dashboard Panels for this zone (cross-zone + zone-specific, E3) -->
      <InlineDashboardPanel
        v-for="panel in inlineMonitorPanelsL2"
        :key="panel.id"
        :layoutId="panel.id"
        :zone-id="selectedZoneId ?? undefined"
        :mode="authStore.isViewer ? 'view' : 'manage'"
      />

      <div v-if="filteredZoneSensorCount === 0 && filteredZoneActuatorCount === 0" class="monitor-view__empty">
        <Activity class="w-12 h-12" style="color: var(--color-text-muted)" />
        <p>
          Keine Sensoren oder Aktoren in dieser Zone.
        </p>
      </div>
      </div><!-- /monitorContentRef -->
    </template>

      </main>

      <!-- Bottom-Panel (target.view='monitor', placement='bottom-panel') -->
      <div v-if="bottomMonitorPanels?.length > 0" class="monitor-layout__bottom">
        <InlineDashboardPanel
          v-for="panel in bottomMonitorPanels"
          :key="panel.id"
          :layoutId="panel.id"
          :mode="authStore.isViewer ? 'view' : 'manage'"
          :zone-id="selectedZoneId ?? undefined"
        />
      </div>
      </div>

      <!-- Side-Panel (target.view='monitor', placement='side-panel') -->
      <aside v-if="sideMonitorPanels.length > 0" class="monitor-layout__side">
        <InlineDashboardPanel
          v-for="panel in sideMonitorPanels"
          :key="panel.id"
          :layoutId="panel.id"
          mode="side-panel"
          :zone-id="selectedZoneId ?? undefined"
        />
      </aside>
    </div>

    <!-- Level 3: Sensor Detail Modal (5-Section Anatomy, BaseModal shell) -->
    <BaseModal
      :open="showSensorDetail"
      :title="selectedDetailSensor?.name || 'Sensor-Detail'"
      max-width="sensor-detail-modal-max"
      @close="closeSensorDetail"
    >
      <template v-if="selectedDetailSensor">
        <!-- ═══ Section 1: Header — Live Value + Trend + Stale ═══ -->
        <div class="sensor-detail__hero">
          <div class="sensor-detail__hero-identity">
            <div class="sensor-detail__hero-top">
              <span class="sensor-detail__sensor-type">{{ selectedDetailSensor.sensorType }}</span>
              <span class="sensor-detail__hero-sep">·</span>
              <span class="sensor-detail__esp-name">{{ selectedDetailSensor.espId }}</span>
              <template v-if="selectedZoneName">
                <span class="sensor-detail__hero-sep">·</span>
                <span class="sensor-detail__zone-name">{{ selectedZoneName }}</span>
              </template>
            </div>
            <div class="sensor-detail__hero-meta">
              <span v-if="detailIsStale" class="sensor-detail__stale-badge">
                <Clock :size="12" />
                Veraltet
              </span>
              <span class="sensor-detail__source-line">
                Live jetzt:
                <strong v-if="detailLiveValue?.lastUpdate">{{ formatRelativeTime(detailLiveValue.lastUpdate) }}</strong>
                <strong v-else>unbekannt</strong>
              </span>
              <span class="sensor-detail__source-line">
                Historie bis:
                <strong v-if="detailHistoryLatestAt">{{ formatRelativeTime(detailHistoryLatestAt) }}</strong>
                <strong v-else>keine Daten</strong>
                <span v-if="detailHistoryIsStale" class="sensor-detail__history-stale">Snapshot</span>
              </span>
            </div>
          </div>
          <div class="sensor-detail__hero-value">
            <span v-if="detailLiveValue?.value != null" class="sensor-detail__live-value">
              {{ formatStatValue(detailLiveValue.value) }}
              <span class="sensor-detail__live-unit">{{ selectedDetailSensor.unit }}</span>
            </span>
            <span v-else class="sensor-detail__live-value sensor-detail__live-value--no-data">—</span>
            <component
              :is="detailTrend === 'up' ? TrendingUp : detailTrend === 'down' ? TrendingDown : Minus"
              :class="['sensor-detail__trend-icon', `sensor-detail__trend-icon--${detailTrend}`]"
              :size="20"
            />
          </div>
        </div>

        <!-- ═══ Section 2: Controls — TimeRange + Overlay ═══ -->
        <div class="sensor-detail__controls">
          <TimeRangeSelector
            v-model="detailPreset"
            @range-change="onDetailRangeChange"
          />

          <!-- Multi-Sensor Overlay Selector -->
          <div v-if="availableOverlaySensors.length > 0" class="sensor-detail__overlay">
            <p class="sensor-detail__overlay-label">Vergleichen mit:</p>
            <div class="sensor-detail__overlay-chips">
              <button
                v-for="s in availableOverlaySensors"
                :key="s.key"
                :class="[
                  'sensor-detail__overlay-chip',
                  { 'sensor-detail__overlay-chip--active': overlaySensorIds.includes(s.key) },
                  { 'sensor-detail__overlay-chip--loading': overlayLoading.has(s.key) },
                ]"
                :disabled="!overlaySensorIds.includes(s.key) && overlaySensorIds.length >= MAX_OVERLAY_SENSORS"
                @click="toggleOverlaySensor(s.key)"
              >
                <span
                  class="sensor-detail__overlay-dot"
                  :style="{ background: overlaySensorIds.includes(s.key) ? getOverlayColor(s.key) : 'var(--color-text-muted)' }"
                />
                {{ s.name }}
                <span class="sensor-detail__overlay-unit">{{ s.unit }}</span>
              </button>
            </div>
          </div>
        </div>

        <!-- ═══ Section 3: Chart ═══ -->
        <!-- Loading -->
        <div v-if="detailLoading" class="sensor-detail__status">
          <div class="sensor-detail__spinner" />
          <span>Lade Sensordaten...</span>
        </div>

        <!-- Error -->
        <div v-else-if="detailError" class="sensor-detail__status sensor-detail__status--error">
          {{ detailError }}
        </div>

        <!-- No data -->
        <div v-else-if="detailReadings.length === 0" class="sensor-detail__status">
          Keine Daten für den gewählten Zeitraum.
        </div>

        <!-- Chart + Stats -->
        <template v-else>
          <div class="sensor-detail__chart-wrap">
            <div class="sensor-detail__chart-header">
              <span class="sensor-detail__point-count">
                {{ detailReadings.length }} Datenpunkte
              </span>
              <span class="sensor-detail__point-count">
                Stand: {{ detailHistoryLatestAt ? formatRelativeTime(detailHistoryLatestAt) : 'unbekannt' }}
              </span>
            </div>
            <div v-if="overlaySensorIds.length > 0" class="sensor-detail__overlay-stand">
              <span
                v-for="sensorKey in overlaySensorIds"
                :key="sensorKey"
                class="sensor-detail__overlay-stand-chip"
              >
                Overlay: {{ overlayHistoryLatest.get(sensorKey) ? formatRelativeTime(overlayHistoryLatest.get(sensorKey)!) : 'keine Daten' }}
              </span>
            </div>
            <div class="sensor-detail__chart">
              <Line :data="detailChartData" :options="detailChartOptions" />
            </div>
          </div>

          <!-- ═══ Section 4: Statistics Row ═══ -->
          <div v-if="detailStats" class="sensor-detail__stats">
            <div class="sensor-detail__stat">
              <span class="sensor-detail__stat-label">Min</span>
              <span class="sensor-detail__stat-value">{{ formatStatValue(detailStats.min_value) }}</span>
              <span class="sensor-detail__stat-unit">{{ selectedDetailSensor.unit }}</span>
              <span v-if="detailMinMaxTimestamps.minAt" class="sensor-detail__stat-time">({{ formatShortTime(detailMinMaxTimestamps.minAt) }})</span>
            </div>
            <div class="sensor-detail__stat">
              <span class="sensor-detail__stat-label">Max</span>
              <span class="sensor-detail__stat-value">{{ formatStatValue(detailStats.max_value) }}</span>
              <span class="sensor-detail__stat-unit">{{ selectedDetailSensor.unit }}</span>
              <span v-if="detailMinMaxTimestamps.maxAt" class="sensor-detail__stat-time">({{ formatShortTime(detailMinMaxTimestamps.maxAt) }})</span>
            </div>
            <div class="sensor-detail__stat">
              <span class="sensor-detail__stat-label">Ø</span>
              <span class="sensor-detail__stat-value">{{ formatStatValue(detailStats.avg_value) }}</span>
              <span class="sensor-detail__stat-unit">{{ selectedDetailSensor.unit }}</span>
            </div>
            <div class="sensor-detail__stat">
              <span class="sensor-detail__stat-label">Messungen</span>
              <span class="sensor-detail__stat-value">{{ detailStats.reading_count }}</span>
            </div>
          </div>
        </template>
      </template>

      <!-- ═══ Section 5: Quick-Actions (fixed footer) ═══ -->
      <template #footer v-if="selectedDetailSensor">
        <div class="sensor-detail__actions">
          <button class="sensor-detail__action-btn" @click="openExportWizard" :disabled="!selectedDetailSensor">
            <Download :size="14" />
            CSV Export
          </button>
        </div>
      </template>
    </BaseModal>

    <ExportDialog
      v-if="exportWizardSensorContext"
      mode="sensor"
      :open="exportWizardOpen"
      :esp-id="exportWizardSensorContext.espId"
      :gpio="exportWizardSensorContext.gpio"
      :sensor-type="exportWizardSensorContext.sensorType"
      :sensor-name="exportWizardSensorContext.sensorName"
      :default-start-time="detailStartTime"
      :default-end-time="detailEndTime"
      @update:open="exportWizardOpen = $event"
      @close="exportWizardOpen = false"
    />

  </div>
</template>

<style scoped>
.monitor-view {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  max-width: 100%;
  overflow-x: hidden;
}

/* Kopfzeile: Tabs + WS-Status (AUT-200) */
.monitor-view__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.monitor-view__head-tabs {
  flex: 1 1 240px;
  min-width: 0;
}


.monitor-view :deep(.view-tab-bar) {
  margin-bottom: 0;
}

.monitor-archived-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-md);
  color: var(--color-warning);
  font-size: var(--text-sm);
}

/* Flapping Banner (PKG-20) */
.monitor-flapping-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.25);
  border-radius: var(--radius-md);
  color: var(--color-warning);
  font-size: var(--text-sm);
  animation: flapping-banner-pulse 3s ease-in-out infinite;
}

.monitor-flapping-banner__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.monitor-flapping-banner__text {
  font-weight: 600;
}

.monitor-flapping-banner__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

@keyframes flapping-banner-pulse {
  0%, 100% { border-color: rgba(251, 191, 36, 0.25); }
  50% { border-color: rgba(251, 191, 36, 0.5); }
}

@media (prefers-reduced-motion: reduce) {
  .monitor-flapping-banner {
    animation: none;
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   LAYOUT — Main + optional Side-Panel (Block 7d)
   ═══════════════════════════════════════════════════════════════════════════ */

.monitor-layout {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
}

.monitor-layout--has-side {
  display: grid;
  grid-template-columns: 1fr 300px;
  gap: var(--space-4);
}

.monitor-layout__main-col {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.monitor-layout__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.monitor-zone-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border: 1px solid var(--glass-border);
  border-left: 3px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-tertiary);
  margin-bottom: var(--space-2);
}

.monitor-zone-detail--ok { border-left-color: var(--color-success); }
.monitor-zone-detail--warning { border-left-color: var(--color-warning); }
.monitor-zone-detail--alarm { border-left-color: var(--color-error); }
.monitor-zone-detail--empty { border-left-color: var(--color-text-muted); opacity: 0.9; }

.monitor-layout__bottom {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  flex-shrink: 0;
  max-height: 400px;
  overflow-y: auto;
}

.monitor-layout__side {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-y: auto;
  max-height: calc(100vh - 120px);
  position: sticky;
  top: 0;
}

@media (max-width: 768px) {
  .monitor-layout--has-side {
    grid-template-columns: 1fr;
  }
  .monitor-layout__side {
    position: static;
    max-height: none;
  }
}

.monitor-view__title {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.monitor-view__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: nowrap;
  justify-content: space-between;
  margin-bottom: 0;
  padding: 0 0 var(--space-2);
  border-bottom: 1px solid var(--glass-border);
}

.monitor-view__header--with-zone-nav {
  justify-content: flex-start;
}

/* Zone-to-Zone Navigation (Prev/Next on L2) */
.monitor-view__zone-nav {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex: 1 1 auto;
  min-width: 0;
  justify-content: center;
}

.monitor-view__zone-nav-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--color-text-primary);
  transition: all var(--transition-fast);
  padding: 0;
}

.monitor-view__zone-nav-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.monitor-view__zone-nav-btn:not(:disabled):hover {
  background: var(--color-surface-hover);
  border-color: var(--glass-border-hover);
}

.monitor-view__zone-nav-label {
  display: inline-flex;
  align-items: center;
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: 700;
  line-height: 1;
  padding: 0 var(--space-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: min(72vw, 480px);
  justify-content: center;
}

@media (max-width: 640px) {
  .monitor-view__zone-nav {
    gap: var(--space-1);
  }
}

.monitor-view__back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  flex-shrink: 0;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.monitor-view__back:hover {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  background: var(--glass-bg-light);
  transform: translateX(-2px);
}

.monitor-view__header-info {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 0;
  flex: 1 1 auto;
  min-width: 0;
}

.monitor-view__header-reason {
  margin: calc(-1 * var(--space-1)) 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Defensive: falls alter Markup-Stand aktiv ist, KPI-Zeile/Back-Text ausblenden */
.monitor-view__zone-kpis,
.monitor-view__zone-kpi,
.monitor-view__back span {
  display: none;
}

.monitor-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-12);
  text-align: center;
  color: var(--color-text-muted);
  margin-bottom: var(--space-10);
}

.monitor-view__empty-hint {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-top: calc(-1 * var(--space-2));
}

.monitor-view__empty-cta {
  display: inline-flex;
  align-items: center;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  text-decoration: none;
  transition: all var(--transition-fast);
}

.monitor-view__empty-cta:hover {
  border-color: var(--color-iridescent-2);
  color: var(--color-text-primary);
  background: color-mix(in srgb, var(--color-text-inverse) 4%, transparent);
}

/* ═══════════════════════════════════════════════════════════════════════════
   ZONE TILES (Level 1)
   ═══════════════════════════════════════════════════════════════════════════ */

.monitor-zone-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: var(--space-4);
  align-items: start;
  margin-bottom: var(--space-10);
  max-width: 100%;
  overflow: hidden;
  --monitor-separator-color: var(--glass-border-hover);
}

@media (min-width: 1024px) {
  .monitor-zone-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (min-width: 1600px) {
  .monitor-zone-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

.monitor-zone-grid :deep(.monitor-zone-tile) {
  position: relative;
  min-width: 0;
}

.monitor-zone-tile__extra-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* Phase 3: Mini-widget inside zone tile (extra-slot) — height controlled by InlineDashboardPanel rowHeightPx */
.monitor-zone-tile__mini-widget {
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--glass-bg);
  padding: var(--space-1);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SUBZONE ACCORDION (Level 2)
   ═══════════════════════════════════════════════════════════════════════════ */

.monitor-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-10);
}

.monitor-section--subzones {
  margin-bottom: var(--space-4);
}

.monitor-section__title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

.monitor-subzone {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--glass-bg);
}

.monitor-subzone--unassigned {
  border-style: dashed;
}

.monitor-subzone--unassigned .monitor-subzone__header {
  color: var(--color-text-secondary);
}

.monitor-subzone__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  width: 100%;
  text-align: left;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.monitor-subzone__header--static {
  cursor: default;
}

.monitor-subzone__header:hover {
  border-color: var(--glass-border-hover);
}

.monitor-subzone__chevron {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  transition: transform var(--transition-fast);
  flex-shrink: 0;
}

.monitor-subzone__chevron--expanded {
  transform: rotate(90deg);
}

.monitor-subzone__name {
  font-weight: 600;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* AUT-250: Subzone status dots now rendered by StatusBadge compact. */

.monitor-subzone__kpis {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  margin-left: auto;
  margin-right: var(--space-2);
  white-space: nowrap;
}

.monitor-subzone__optional-hint {
  margin-left: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.monitor-subzone__count {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.monitor-subzone__separator {
  border: none;
  border-top: 1px dashed var(--monitor-separator-color);
  margin: var(--space-3) 0;
}

.monitor-subzone__type-label {
  font-size: var(--text-xs, 0.75rem);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
}

.monitor-subzone__header--zoneweit {
  border-style: dashed;
}

.monitor-subzone__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.monitor-zonewide-rules {
  margin-bottom: var(--space-4);
  padding-top: 0;
  border-top: 1px dashed var(--monitor-separator-color);
}

.monitor-subzone__empty {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: var(--space-3);
}

/* Subzone CRUD elements */
.monitor-subzone__toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
  min-width: 0;
  background: none;
  border: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
  padding: 0;
  text-align: left;
}

.monitor-subzone__actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.monitor-subzone__header:hover .monitor-subzone__actions {
  opacity: 1;
}

.monitor-subzone__empty-hint {
  font-size: var(--text-xs, 11px);
  color: var(--color-text-muted);
  padding: var(--space-3) var(--space-4);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  text-align: center;
  grid-column: 1 / -1;
}

.monitor-subzone__empty-link {
  color: var(--color-iridescent-2);
  text-decoration: none;
}

.monitor-subzone__empty-link:hover {
  text-decoration: underline;
}

.monitor-subzone__action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.monitor-subzone__action-btn:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border);
  color: var(--color-text-primary);
}

.monitor-subzone__action-btn--danger:hover {
  background: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error);
}

.monitor-subzone__action-btn--confirm {
  color: var(--color-success);
}

.monitor-subzone__action-btn--confirm:hover {
  background: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success);
}

.monitor-subzone__action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.monitor-subzone__rename-input {
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  min-width: 120px;
  max-width: 200px;
}

.monitor-subzone__rename-input:focus {
  outline: none;
  border-color: var(--color-accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-accent) 15%, transparent);
}

.monitor-subzone__create-form {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
}

.monitor-subzone__add-btn {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  width: 100%;
}

.monitor-subzone__add-btn:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--color-accent);
  color: var(--color-text-secondary);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SENSOR/ACTUATOR CARDS (Level 2)
   ═══════════════════════════════════════════════════════════════════════════ */

.monitor-card-grid {
  gap: var(--space-3);
  max-width: 100%;
}

/* AUT-25: Widescreen breakpoints — 4 columns at 1600px, 5 columns at 1920px */
@media (min-width: 1600px) {
  .monitor-card-grid.grid-auto-sm {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (min-width: 1920px) {
  .monitor-card-grid.grid-auto-sm {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

/* Sensor Card wrapper (SensorCard handles its own visual styling) */
.monitor-sensor-card--expanded {
  grid-column: 1 / -1;
  scroll-margin-top: var(--space-8);
}

/* Expand transition */
.expand-enter-active {
  transition: all var(--duration-base) var(--ease-out);
}

.expand-leave-active {
  transition: all var(--duration-fast) var(--ease-in-out);
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.expand-enter-to,
.expand-leave-from {
  max-height: 600px;
}

/* Accordion transition */
.accordion-enter-active {
  transition: all var(--duration-base) var(--ease-out);
}

.accordion-leave-active {
  transition: all var(--duration-fast) var(--ease-in-out);
}

.accordion-enter-from,
.accordion-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.accordion-enter-to,
.accordion-leave-from {
  max-height: 2000px;
}

/* ═══════════════════════════════════════════════════════════════════════════
   DASHBOARD LINKS
   ═══════════════════════════════════════════════════════════════════════════ */

/* Zone Dashboards section (L2) */
/* Shared Equipment section (6.7) */
.monitor-shared-equipment {
  margin-bottom: var(--space-10);
}

.monitor-shared-equipment__grid {
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.monitor-section__count {
  font-size: var(--text-xs);
  font-weight: 400;
  color: var(--color-text-muted);
  margin-left: var(--space-2);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SENSOR DETAIL MODAL CONTENT (5-Section Anatomy, reflow for centered shell)
   ═══════════════════════════════════════════════════════════════════════════ */

/* Section 1: Hero Header — identity left, live value right */
.sensor-detail__hero {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3) var(--space-6);
  margin-bottom: var(--space-4);
}

.sensor-detail__hero-identity {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
  flex: 1 1 16rem;
}

.sensor-detail__hero-top {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.sensor-detail__sensor-type {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-iridescent-2);
  background: color-mix(in srgb, var(--color-iridescent-2) 10%, transparent);
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
}

.sensor-detail__esp-name {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.sensor-detail__hero-sep {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.sensor-detail__zone-name {
  font-size: var(--text-xs);
  color: var(--color-iridescent-2);
  font-weight: 500;
}

.sensor-detail__hero-value {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  flex: 0 0 auto;
}

.sensor-detail__live-value {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  font-family: var(--font-mono);
  line-height: 1.1;
}

.sensor-detail__live-value--no-data {
  color: var(--color-text-muted);
}

.sensor-detail__live-unit {
  font-size: var(--text-base);
  font-weight: 400;
  color: var(--color-text-secondary);
}

.sensor-detail__trend-icon {
  flex-shrink: 0;
}

.sensor-detail__trend-icon--up {
  color: var(--color-error);
}

.sensor-detail__trend-icon--down {
  color: var(--color-info);
}

.sensor-detail__trend-icon--stable {
  color: var(--color-text-muted);
}

.sensor-detail__hero-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Section 2: Controls (time range + compare chips) */
.sensor-detail__controls {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.sensor-detail__stale-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-warning);
  font-weight: 600;
  animation: breathe 2s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.sensor-detail__last-update {
  color: var(--color-text-muted);
}

.sensor-detail__source-line {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}

.sensor-detail__source-line strong {
  color: var(--color-text-secondary);
}

.sensor-detail__history-stale {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  padding: 1px var(--space-2);
  color: var(--color-warning);
}

/* Section 4: Statistics Row */
.sensor-detail__stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-4);
  padding: var(--space-4);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
}

.sensor-detail__stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
}

.sensor-detail__stat-label {
  font-size: var(--text-xxs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.sensor-detail__stat-value {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--color-text-primary);
  font-family: var(--font-mono);
}

.sensor-detail__stat-unit {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.sensor-detail__stat-time {
  font-size: var(--text-xxs);
  color: var(--color-text-secondary);
  font-family: var(--font-mono);
}

/* Section 5: Quick-Actions (footer) */
.sensor-detail__actions {
  display: flex;
  gap: var(--space-2);
}

.sensor-detail__action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
  white-space: nowrap;
}

.sensor-detail__action-btn:hover:not(:disabled) {
  border-color: var(--color-iridescent-1);
  color: var(--color-text-primary);
}

.sensor-detail__action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.sensor-detail__status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-8);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  text-align: center;
}

.sensor-detail__status--error {
  color: var(--color-error);
}

.sensor-detail__spinner {
  width: 1.25rem;
  height: 1.25rem;
  border: 2px solid var(--color-bg-tertiary);
  border-top-color: var(--color-iridescent-1);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.sensor-detail__chart-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.sensor-detail__chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.sensor-detail__point-count {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}

.sensor-detail__overlay-stand {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.sensor-detail__overlay-stand-chip {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-full);
  border: 1px solid var(--glass-border);
  padding: 2px var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.sensor-detail__chart {
  position: relative;
  width: 100%;
  height: 360px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}

/* ═══════════════════════════════════════════════════════════════════════════
   MULTI-SENSOR OVERLAY (L3)
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-detail__overlay {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sensor-detail__overlay-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
  font-weight: 500;
}

.sensor-detail__overlay-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.sensor-detail__overlay-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.sensor-detail__overlay-chip:hover:not(:disabled) {
  border-color: var(--glass-border-hover);
  color: var(--color-text-primary);
}

.sensor-detail__overlay-chip--active {
  background: color-mix(in srgb, var(--color-iridescent-3) 10%, transparent);
  border-color: color-mix(in srgb, var(--color-iridescent-3) 30%, transparent);
  color: var(--color-text-primary);
}

.sensor-detail__overlay-chip--loading {
  opacity: 0.6;
}

.sensor-detail__overlay-chip:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.sensor-detail__overlay-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sensor-detail__overlay-unit {
  color: var(--color-text-muted);
  font-size: var(--text-xxs);
}
</style>

<!--
  BaseModal teleports to <body>; scoped :deep() does not cross Teleport.
  Global forms.css `.modal-content { max-width: 28rem }` would otherwise win
  (same pattern as ConfigWizardModal `.cwm-modal-max`).
  Size = Tailwind max-w-4xl (56rem), capped to viewport.
-->
<style>
.modal-content.sensor-detail-modal-max {
  max-width: min(94vw, 56rem);
}
</style>
