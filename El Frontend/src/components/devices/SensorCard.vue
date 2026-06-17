<script setup lang="ts">
/**
 * SensorCard — Unified sensor card for config and monitor views
 *
 * Config mode: Name, type, ESP-ID, GPIO, settings hint
 * Monitor mode: Name, live value, quality dot, sparkline, ESP-ID
 */
import { computed, ref, watch, onUnmounted, type Component } from 'vue'
import { Settings, ChevronRight, WifiOff, Clock, BellOff, Thermometer, Droplets, Wind, Sun, Gauge, Leaf, Activity, CircleDot, Info, Loader2, Scan, Check, X, AlertTriangle } from 'lucide-vue-next'
import { isMockEspId } from '@/composables/useZoneGrouping'
import type { SensorWithContext } from '@/composables/useZoneGrouping'
import type { TrendDirection } from '@/utils/trendUtils'
import { qualityToStatus, sensorStatusToLevel, getDataFreshness, formatRelativeTime } from '@/utils/formatters'
import StatusBadge from '@/components/base/StatusBadge.vue'
import { getSensorLabel, getSensorUnit, getSensorDisplayName, getSensorConfig, VIRTUAL_SENSOR_META } from '@/utils/sensorDefaults'
import { useDeviceContextStore } from '@/shared/stores/deviceContext.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { sensorsApi } from '@/api/sensors'
import { useToast } from '@/composables/useToast'

/** Default fallback icon for unknown sensor types */
const DEFAULT_SENSOR_ICON = CircleDot

/** Map SENSOR_TYPE_CONFIG icon names to Lucide components */
const ICON_MAP: Record<string, Component> = {
  Thermometer, Droplets, Wind, Sun, Gauge, Leaf, Activity,
  Droplet: Droplets,
  Zap: Activity,
}

interface Props {
  sensor: SensorWithContext
  mode: 'monitor' | 'config'
  dataMode?: 'Live' | 'Hybrid' | 'Snapshot'
  trend?: TrendDirection
  /** AUT-255: When true, shows 🔕 paused pill in monitor mode footer. */
  isSuppressed?: boolean
  /** AUT-255: Tooltip text for the suppression pill. */
  suppressionTooltip?: string
  /** AUT-609: Time range label above sparkline, e.g. "letzte 15 Min" */
  sparklineTimeLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  dataMode: 'Hybrid',
})

const emit = defineEmits<{
  configure: [sensor: SensorWithContext]
  click: [sensor: SensorWithContext]
}>()

const displayName = computed(() =>
  getSensorDisplayName({ sensor_type: props.sensor.sensor_type, name: props.sensor.name }) || `GPIO ${props.sensor.gpio}`
)

const sensorLabel = computed(() =>
  getSensorLabel(props.sensor.sensor_type) || props.sensor.sensor_type
)

// Data freshness indicator (stale after 120s, or server-flagged as stale)
const freshness = computed(() => getDataFreshness(props.sensor.last_read))
const isStale = computed(() => freshness.value === 'stale' || props.sensor.is_stale === true)
// Value present but no timestamp known
const isTimestampUnknown = computed(() =>
  freshness.value === 'unknown' && props.sensor.raw_value != null
)
// No data at all: no value and no valid timestamp
const hasNoData = computed(() =>
  props.sensor.raw_value == null && !props.sensor.last_read
)

// Effective quality status: defense-in-depth via timestamp age check
const effectiveQualityStatus = computed(() => {
  // AUT-300: On-demand sensors in normal waiting state are not "offline" or "stale"
  if (isOnDemand.value) {
    if (hasNoData.value) return 'good'
    if (props.sensor.is_stale === true) return 'warning'
    return qualityToStatus(props.sensor.quality, { lastRead: props.sensor.last_read })
  }
  if (hasNoData.value) return 'offline'
  if (isStale.value) return 'stale'
  return qualityToStatus(props.sensor.quality, { lastRead: props.sensor.last_read })
})


// ESP offline indicator
const isEspOffline = computed(() =>
  props.sensor.esp_state !== undefined && props.sensor.esp_state !== 'OPERATIONAL'
)

// Sensor type icon — 3-tier fallback: exact match → base-type suffix → default
const sensorIcon = computed(() => {
  const sType = props.sensor.sensor_type
  // 1. Exact match (case-insensitive via getSensorConfig)
  const exactIcon = getSensorConfig(sType)?.icon
  if (exactIcon && ICON_MAP[exactIcon]) return ICON_MAP[exactIcon]
  // 2. Base-type suffix (e.g. "bme280_pressure" → "pressure")
  const suffix = sType.includes('_') ? sType.split('_').pop() : null
  if (suffix) {
    const suffixIcon = getSensorConfig(suffix)?.icon
    if (suffixIcon && ICON_MAP[suffixIcon]) return ICON_MAP[suffixIcon]
  }
  // 3. Default fallback
  return DEFAULT_SENSOR_ICON
})

// Resolved unit: sensor.unit → SENSOR_TYPE_CONFIG fallback
const resolvedUnit = computed(() => {
  const raw = props.sensor.unit
  if (raw && raw !== 'raw') return raw
  const configUnit = getSensorUnit(props.sensor.sensor_type)
  return configUnit !== 'raw' ? configUnit : ''
})

// Quality text label for accessibility (dual encoding: color + text)
const qualityLabel = computed(() => {
  const status = effectiveQualityStatus.value
  const labels: Record<string, string> = {
    good: 'OK',
    warning: 'Warnung',
    alarm: 'Kritisch',
    stale: 'Veraltet',
    offline: 'Offline',
  }
  return labels[status] ?? ''
})

const TREND_TITLES: Record<TrendDirection, string> = {
  rising: 'Steigend',
  stable: 'Stabil',
  falling: 'Fallend',
}

// Scope badge (T13-R3 WP4): only show for non-default scopes with DB config
const scopeBadge = computed(() => {
  const scope = props.sensor.device_scope
  if (!scope || scope === 'zone_local') return null
  if (scope === 'multi_zone') return { text: 'Multi-Zone', cls: 'sensor-card__scope-badge--multi-zone' }
  if (scope === 'mobile') return { text: 'Mobil', cls: 'sensor-card__scope-badge--mobile' }
  return null
})

const scopeTooltip = computed(() => {
  if (scopeBadge.value?.text !== 'Multi-Zone') return ''
  const zones = props.sensor.assigned_zones
  if (!zones?.length) return ''
  return `Bedient: ${zones.join(', ')}`
})

// Virtual sensor info (V19-F03): tooltip for server-computed sensors
const virtualMeta = computed(() => VIRTUAL_SENSOR_META[props.sensor.sensor_type] ?? null)
const showVirtualInfo = ref(false)

function toggleVirtualInfo(event: Event): void {
  event.stopPropagation()
  showVirtualInfo.value = !showVirtualInfo.value
}

// Subzone badge (Phase 2.2): canonical fallback "Zone-weit" when null/empty
const isFromMockDevice = computed(() => {
  return isMockEspId(props.sensor.esp_id ?? '')
})

const sourceBadge = computed(() => {
  if (isFromMockDevice.value) {
    return { text: 'Mock', cls: 'sensor-card__source-badge--mock' }
  }
  return { text: 'Real', cls: 'sensor-card__source-badge--real' }
})

const subzoneLabel = computed(() => {
  const name = props.sensor.subzone_name ?? ''
  const id = props.sensor.subzone_id ?? ''
  if (typeof name === 'string' && name.trim()) return name
  if (typeof id === 'string' && id.trim()) return id
  return 'Zone-weit'
})

// Mobile sensor context (6.7)
const deviceContextStore = useDeviceContextStore()
const zoneStore = useZoneStore()
const isChangingContext = ref(false)

const isMobile = computed(() => props.sensor.device_scope === 'mobile')

const activeContext = computed(() => {
  if (!isMobile.value) return null
  const configId = (props.sensor as SensorWithContext & { config_id?: string }).config_id
  if (!configId) return null
  return deviceContextStore.getContext(configId)
})

const activeZoneName = computed(() => {
  const zoneId = activeContext.value?.active_zone_id
  if (!zoneId) return null
  const entity = zoneStore.zoneEntities.find(z => z.zone_id === zoneId)
  return entity?.name ?? zoneId
})

/** Zones available for context switch (mobile sensors) */
const availableZones = computed(() => {
  if (!isMobile.value) return []
  const assignedZones = props.sensor.assigned_zones
  if (assignedZones && assignedZones.length > 0) {
    return zoneStore.activeZones.filter(z => assignedZones.includes(z.zone_id))
  }
  return zoneStore.activeZones
})

async function handleZoneContextChange(event: Event): Promise<void> {
  const select = event.target as HTMLSelectElement
  const newZoneId = select.value || null
  const configId = (props.sensor as SensorWithContext & { config_id?: string }).config_id
  if (!configId) return

  isChangingContext.value = true
  try {
    if (newZoneId) {
      await deviceContextStore.setContext('sensor', configId, newZoneId)
    } else {
      await deviceContextStore.clearContext('sensor', configId)
    }
  } catch {
    // Toast already shown by store
  } finally {
    isChangingContext.value = false
  }
}

function formatValue(value: number | null | undefined): string {
  if (value === null || value === undefined) return '--'
  const dec = getSensorConfig(props.sensor.sensor_type)?.decimals ?? 2
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  }).format(Number(value))
}

// AUT-299: ATC fallback warning badge
// Show when: EC/pH sensor + temp_sensor_config_id set + last metadata.temp_source === "default_25"
const atcFallbackWarning = computed<boolean>(() => {
  const sType = props.sensor.sensor_type.toLowerCase()
  if (sType !== 'ec' && sType !== 'ph') return false
  if (!props.sensor.temp_sensor_config_id) return false
  const meta = props.sensor.metadata
  if (!meta || typeof meta !== 'object') return false
  return meta.temp_source === 'default_25'
})

// AUT-322: ATC cached temperature badge (yellow)
// Show when: EC/pH sensor + metadata.temp_source === "cached_temp"
const atcCachedTemp = computed<boolean>(() => {
  const sType = props.sensor.sensor_type.toLowerCase()
  if (sType !== 'ec' && sType !== 'ph') return false
  const meta = props.sensor.metadata
  if (!meta || typeof meta !== 'object') return false
  return meta.temp_source === 'cached_temp'
})

// AUT-322: ATC temp read failed badge (red)
// Show when: EC/pH sensor + metadata.temp_source === "read_failed" or "temp_read_failed"
const atcReadFailed = computed<boolean>(() => {
  const sType = props.sensor.sensor_type.toLowerCase()
  if (sType !== 'ec' && sType !== 'ph') return false
  const meta = props.sensor.metadata
  if (!meta || typeof meta !== 'object') return false
  return meta.temp_source === 'read_failed' || meta.temp_source === 'temp_read_failed'
})

const stabilityBadge = computed<{
  level: 'good' | 'warning'
  label: string
  detail?: string
} | null>(() => {
  const sType = props.sensor.sensor_type.toLowerCase()
  if (!sType.includes('ec') && !sType.includes('ph')) return null
  const meta = props.sensor.metadata
  if (!meta || typeof meta !== 'object' || meta.sample_count == null) return null
  const ecStddev = typeof meta.ec_stddev === 'number' ? meta.ec_stddev : null
  const adcStddev = typeof meta.adc_stddev === 'number' ? meta.adc_stddev : null
  if (meta.stable === true) {
    return {
      level: 'good',
      label: 'Stabil',
      detail: ecStddev != null ? `σ ${ecStddev} µS/cm` : undefined,
    }
  }
  return {
    level: 'warning',
    label: 'Instabil',
    detail: ecStddev != null
      ? `σ ${ecStddev} µS/cm`
      : adcStddev != null
        ? `ADC σ ${adcStddev}`
        : undefined,
  }
})

// On-demand measurement (AUT-298)
const isOnDemand = computed(() => props.sensor.operating_mode === 'on_demand')
// AUT-300: Stale-due uses server flag (measurement_freshness_hours threshold), not frontend 120s threshold
const isOnDemandStaleDue = computed(() => isOnDemand.value && props.sensor.is_stale === true && !isEspOffline.value)
// AUT-314: Analog probe sensors need settling time — show hint before measuring
const isAnalogProbeSensor = computed(() => {
  const t = props.sensor.sensor_type.toLowerCase()
  return t.includes('ph') || t.includes('ec')
})
const isMeasuring = ref(false)
const measureState = ref<'idle' | 'success' | 'error'>('idle')
let measureTriggerTime = 0
let preMeasureTriggerValue: number | null = null
let preMeasureLastRead: string | null = null
let preMeasureLastEventAt: string | null = null
let measureTimeoutId: ReturnType<typeof setTimeout> | null = null
const { success: toastSuccess, error: toastError, warning: toastWarning } = useToast()

function clearMeasureTimeout(): void {
  if (measureTimeoutId !== null) {
    clearTimeout(measureTimeoutId)
    measureTimeoutId = null
  }
}

function resolveMeasureSuccess(): void {
  clearMeasureTimeout()
  isMeasuring.value = false
  measureState.value = 'success'
  measureTriggerTime = 0
  preMeasureTriggerValue = null
  preMeasureLastRead = null
  preMeasureLastEventAt = null
  toastSuccess('Messwert empfangen')
  setTimeout(() => { measureState.value = 'idle' }, 2000)
}

// AUT-298 Finalitätsmodell: wait for WS sensor_data after trigger.
// Primary: last_read timestamp newer than trigger time, or any change in last_read.
// Fallback: raw_value changed (covers ESP payloads with null timestamp — sensor_handler.py
// broadcasts esp32_timestamp_raw which can be null, causing normalizeRawTimestamp → null).
// Bug fixes: lastReadChanged detects any new timestamp; valueMutated without null-guard
// detects null→value (first measurement) correctly.
watch(
  () => [props.sensor.last_read, props.sensor.raw_value, props.sensor.last_event_at] as const,
  ([newLastRead, newRawValue, newLastEventAt]) => {
    if (!measureTriggerTime) return
    if (!isMeasuring.value && measureState.value !== 'error') return
    const timestampFresh = newLastRead != null && new Date(newLastRead).getTime() > measureTriggerTime
    const lastReadChanged = newLastRead !== preMeasureLastRead
    const valueMutated = newRawValue !== preMeasureTriggerValue
    const eventArrived = newLastEventAt != null && newLastEventAt !== preMeasureLastEventAt
    if (timestampFresh || lastReadChanged || valueMutated || eventArrived) {
      resolveMeasureSuccess()
    }
  }
)

onUnmounted(clearMeasureTimeout)

async function triggerMeasure(): Promise<void> {
  if (isMeasuring.value || isEspOffline.value) return
  isMeasuring.value = true
  measureState.value = 'idle'
  measureTriggerTime = Date.now()
  preMeasureTriggerValue = props.sensor.raw_value ?? null
  preMeasureLastRead = props.sensor.last_read ?? null
  preMeasureLastEventAt = props.sensor.last_event_at ?? null
  try {
    await sensorsApi.triggerMeasurement(props.sensor.esp_id, props.sensor.gpio, {
      sensor_type: props.sensor.sensor_type,
      ...(isAnalogProbeSensor.value
        ? { sample_count: 30, sample_delay_ms: 100, timeout_ms: 15000 }
        : {}),
    })
    // Command published to ESP — wait for WS sensor_data (finality via watch above)
    measureTimeoutId = setTimeout(() => {
      isMeasuring.value = false
      measureState.value = 'error'
      // Keep measureTriggerTime + preMeasureTriggerValue — watch can still catch late data in 2s grace window
      toastError('Kein Messwert erhalten (Timeout)')
      setTimeout(() => {
        if (measureState.value !== 'success') {
          measureTriggerTime = 0
          preMeasureTriggerValue = null
          preMeasureLastRead = null
          preMeasureLastEventAt = null
        }
        measureState.value = 'idle'
      }, 2000)
    }, 10_000)
  } catch (err: unknown) {
    clearMeasureTimeout()
    isMeasuring.value = false
    // HTTP 429 (legacy: 409): MeasurementBusyError — sensor cooldown active
    const axiosErr = err as { response?: { status?: number; data?: { retry_after_seconds?: number } } }
    if (axiosErr?.response?.status === 429 || axiosErr?.response?.status === 409) {
      const retryAfter = axiosErr.response.data?.retry_after_seconds ?? 3
      toastWarning(`Sensor misst gerade — bitte ${retryAfter}s warten`)
      measureState.value = 'idle'
      return
    }
    measureState.value = 'error'
    measureTriggerTime = 0
    preMeasureTriggerValue = null
    preMeasureLastRead = null
    preMeasureLastEventAt = null
    toastError('Messung fehlgeschlagen')
    setTimeout(() => { measureState.value = 'idle' }, 2000)
  }
}

function handleClick() {
  if (props.mode === 'config') {
    emit('configure', props.sensor)
  } else {
    emit('click', props.sensor)
  }
}
</script>

<template>
  <div
    :class="[
      'sensor-card',
      `sensor-card--${mode}`,
      mode === 'monitor' ? `sensor-card--${effectiveQualityStatus}` : '',
      mode === 'monitor' && isStale && !isOnDemand ? 'sensor-card--stale' : '',
      mode === 'monitor' && isOnDemandStaleDue ? 'sensor-card--on-demand-stale' : '',
      mode === 'monitor' && isEspOffline ? 'sensor-card--esp-offline' : '',
      mode === 'monitor' && isFromMockDevice ? 'sensor-card--mock' : '',
    ]"
    @click="handleClick"
  >
    <!-- Config Mode -->
    <template v-if="mode === 'config'">
      <div class="sensor-card__header">
        <div class="sensor-card__icon sensor-card__icon--config">
          <Settings class="w-5 h-5 text-purple-400" />
        </div>
        <div class="sensor-card__info">
          <p class="sensor-card__name">{{ displayName }}</p>
          <p class="sensor-card__meta">{{ sensor.esp_id }} · {{ sensorLabel }}</p>
          <span class="sensor-card__subzone-badge">{{ subzoneLabel }}</span>
          <span v-if="scopeBadge" :class="['sensor-card__scope-badge', scopeBadge.cls]" :title="scopeTooltip">{{ scopeBadge.text }}</span>
        </div>
        <ChevronRight class="w-4 h-4 text-dark-500 flex-shrink-0" />
      </div>
    </template>

    <!-- Monitor Mode -->
    <template v-else>
      <div class="sensor-card__header">
        <component :is="sensorIcon" class="sensor-card__type-icon" />
        <span class="sensor-card__name" :title="displayName">{{ displayName }}</span>
        <span v-if="virtualMeta" class="sensor-card__virtual-info-trigger" @click="toggleVirtualInfo" @mouseenter="showVirtualInfo = true" @mouseleave="showVirtualInfo = false">
          <Info :size="14" />
          <div v-show="showVirtualInfo" class="sensor-card__virtual-tooltip">
            <p v-if="virtualMeta.description" class="sensor-card__virtual-tooltip-desc">{{ virtualMeta.description }}</p>
            <p class="sensor-card__virtual-tooltip-heading">Berechnet aus:</p>
            <ul class="sensor-card__virtual-tooltip-list">
              <li v-for="src in virtualMeta.sources" :key="src">{{ src }}</li>
            </ul>
            <p class="sensor-card__virtual-tooltip-formula">Formel: {{ virtualMeta.formula }}</p>
          </div>
        </span>
        <div class="sensor-card__quality">
          <span v-if="sourceBadge.text !== 'Real'" :class="['sensor-card__source-badge', sourceBadge.cls]">{{ sourceBadge.text }}</span>
          <span v-if="dataMode !== 'Live'" :class="['sensor-card__mode-badge', `sensor-card__mode-badge--${dataMode.toLowerCase()}`]">
            {{ dataMode }}
          </span>
          <StatusBadge
            v-if="effectiveQualityStatus !== 'good'"
            :level="sensorStatusToLevel(effectiveQualityStatus)"
            :label-override="qualityLabel || undefined"
            :show-icon="false"
          />
        </div>
      </div>
      <div class="sensor-card__value">
        <template v-if="hasNoData">
          <span class="sensor-card__number sensor-card__number--no-data">Keine Daten</span>
        </template>
        <template v-else>
          <span class="sensor-card__number">{{ formatValue(sensor.raw_value) }}</span>
          <span class="sensor-card__unit">{{ resolvedUnit }}</span>
          <span
            v-if="trend"
            :class="['sensor-card__trend', `sensor-card__trend-char--${trend}`]"
            :title="TREND_TITLES[trend]"
          >{{ trend === 'rising' ? '↑' : trend === 'falling' ? '↓' : '→' }}</span>
        </template>
      </div>
      <!-- AUT-300: Always-visible timestamp below value — on_demand shows hours, live confirms freshness -->
      <div v-if="sensor.last_read" class="sensor-card__last-seen">
        {{ formatRelativeTime(sensor.last_read) }}
      </div>
      <!-- AUT-609: Sparkline time range label above the chart -->
      <div v-if="sparklineTimeLabel && $slots.sparkline" class="sensor-card__sparkline-header">
        <span class="sensor-card__sparkline-timerange">{{ sparklineTimeLabel }}</span>
      </div>
      <!-- Sparkline slot: parent can inject a mini chart -->
      <div v-if="$slots.sparkline" class="sensor-card__sparkline">
        <slot name="sparkline" />
      </div>
      <div class="sensor-card__footer">
        <span class="sensor-card__esp">{{ sensor.esp_id }}</span>
        <div class="sensor-card__footer-badges">
          <span class="sensor-card__subzone-badge">{{ subzoneLabel }}</span>
          <span v-if="scopeBadge" :class="['sensor-card__scope-badge', scopeBadge.cls]" :title="scopeTooltip">{{ scopeBadge.text }}</span>
          <span
            v-if="isSuppressed"
            class="sensor-card__badge sensor-card__badge--suppressed"
            :title="suppressionTooltip || 'Alerts unterdrückt'"
          >
            <BellOff class="w-3 h-3" /> paused
          </span>
          <span v-if="isEspOffline" class="sensor-card__badge sensor-card__badge--offline">
            <WifiOff class="w-3 h-3" /> ESP offline
          </span>
          <!-- AUT-300: On-demand sensor states (only when ESP online) -->
          <span
            v-else-if="isOnDemandStaleDue"
            class="sensor-card__badge sensor-card__badge--on-demand-stale"
            title="Messung überfällig — Sensor wartet auf manuellen Abruf"
          >
            <AlertTriangle class="w-3 h-3" /> Messung veraltet
          </span>
          <span
            v-else-if="isOnDemand && hasNoData"
            class="sensor-card__badge sensor-card__badge--on-demand-waiting"
            title="Noch keine Messung — Sensor wartet auf ersten Abruf"
          >
            <Clock class="w-3 h-3" /> Noch keine Messung
          </span>
          <span
            v-else-if="isOnDemand"
            class="sensor-card__badge sensor-card__badge--on-demand-waiting"
            title="Wartet auf nächste Messung — on-demand-Sensor"
          >
            <Clock class="w-3 h-3" /> Wartet auf Messung
          </span>
          <!-- Non-on-demand fallback states -->
          <span v-else-if="hasNoData" class="sensor-card__badge sensor-card__badge--no-data">
            <Clock class="w-3 h-3" /> Keine Daten
          </span>
          <span v-else-if="isStale" class="sensor-card__badge sensor-card__badge--stale">
            <Clock class="w-3 h-3" /> Zuletzt: {{ formatRelativeTime(sensor.last_read) }}
          </span>
          <span v-else-if="isTimestampUnknown" class="sensor-card__badge sensor-card__badge--unknown" title="Zeitpunkt des Messwerts unbekannt">
            <Clock class="w-3 h-3" /> Zuletzt: unbekannt
          </span>
          <!-- AUT-299: ATC fallback badge — shown when temp sensor linked but default 25°C used -->
          <span
            v-if="atcFallbackWarning"
            class="sensor-card__badge sensor-card__badge--atc-fallback"
            title="Kein frischer Temperaturwert vom verknüpften Sensor — Standardwert 25°C verwendet."
          >
            <AlertTriangle class="w-3 h-3" /> ATC: Fallback 25°C
          </span>
          <!-- AUT-322: ATC cached temperature badge — approximated temp from cache -->
          <span
            v-if="atcCachedTemp"
            class="sensor-card__badge sensor-card__badge--atc-cached"
            title="Temperatur aus Cache (< 60 s) — Messung basiert auf gecachtem Temperaturwert."
          >
            ~T
          </span>
          <!-- AUT-322: ATC temp read failed badge — measurement aborted -->
          <span
            v-if="atcReadFailed"
            class="sensor-card__badge sensor-card__badge--atc-read-failed"
            title="Temp-Read fehlgeschlagen — Messung wurde abgebrochen. Temperaturerfassung prüfen."
          >
            <AlertTriangle class="w-3 h-3" />
          </span>
          <span
            v-if="stabilityBadge"
            :class="[
              'sensor-card__badge',
              stabilityBadge.level === 'good'
                ? 'sensor-card__badge--stability-good'
                : 'sensor-card__badge--stability-warn',
            ]"
            :title="stabilityBadge.detail
              ? `${stabilityBadge.label} (${stabilityBadge.detail})`
              : stabilityBadge.label"
          >
            <Activity class="w-3 h-3" />
            {{ stabilityBadge.label }}
            <span v-if="stabilityBadge.detail" class="sensor-card__badge-detail">
              {{ stabilityBadge.detail }}
            </span>
          </span>
        </div>
      </div>
      <!-- On-Demand Measure Button (AUT-298) -->
      <div
        v-if="isOnDemand"
        class="sensor-card__measure-row"
        @click.stop
      >
        <span v-if="isAnalogProbeSensor && !isMeasuring" class="sensor-card__measure-hint">
          Sonde ≥5s eintauchen lassen
        </span>
        <button
          :class="[
            'sensor-card__measure-btn',
            measureState === 'success' && 'sensor-card__measure-btn--success',
            measureState === 'error' && 'sensor-card__measure-btn--error',
          ]"
          :disabled="isMeasuring || isEspOffline"
          :title="isEspOffline ? 'ESP offline — Messung nicht möglich' : 'Manuelle Messung auslösen'"
          @click.stop="triggerMeasure"
        >
          <Loader2 v-if="isMeasuring" :size="11" class="sensor-card__measure-spinner" />
          <Check v-else-if="measureState === 'success'" :size="11" />
          <X v-else-if="measureState === 'error'" :size="11" />
          <Scan v-else :size="11" />
          <span>{{ isMeasuring ? 'Messen…' : measureState === 'success' ? 'Ausgelöst' : measureState === 'error' ? 'Fehler' : 'Messen' }}</span>
        </button>
      </div>
      <!-- Mobile sensor context hint (6.7) -->
      <div
        v-if="mode === 'monitor' && isMobile && activeContext"
        class="sensor-card__context-hint"
      >
        Aktiv in {{ activeZoneName }} seit {{ formatRelativeTime(activeContext.context_since) }}
      </div>
      <!-- Mobile sensor zone switch (6.7) -->
      <div
        v-if="mode === 'monitor' && isMobile"
        class="sensor-card__context-controls"
      >
        <select
          :value="activeContext?.active_zone_id ?? ''"
          :disabled="isChangingContext"
          class="sensor-card__zone-select"
          @change="handleZoneContextChange($event)"
          @click.stop
        >
          <option value="">Keine Zone</option>
          <option
            v-for="zone in availableZones"
            :key="zone.zone_id"
            :value="zone.zone_id"
          >
            {{ zone.name }}
          </option>
        </select>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sensor-card {
  cursor: pointer;
  transition: all var(--transition-fast);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
}

.sensor-card:hover {
  border-color: var(--color-border-hover, rgba(255, 255, 255, 0.12));
}

/* Config Mode */
.sensor-card--config {
  padding: var(--space-3);
}

.sensor-card--config .sensor-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.sensor-card__icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.sensor-card__icon--config {
  background: var(--color-mock-bg);
}

.sensor-card__info {
  flex: 1;
  min-width: 0;
}

.sensor-card__name {
  font-weight: 500;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sensor-card__meta {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sensor-card__info .sensor-card__subzone-badge {
  margin-top: var(--space-1);
  display: inline-block;
}

/* Monitor Mode */
.sensor-card--monitor {
  padding: var(--space-3);
}

.sensor-card--monitor .sensor-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.sensor-card__type-icon {
  width: 14px;
  height: 14px;
  color: var(--color-iridescent-2);
  flex-shrink: 0;
}

.sensor-card--monitor .sensor-card__name {
  font-size: var(--text-sm);
  font-weight: 500;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sensor-card__quality {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.sensor-card__mode-badge {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  padding: 1px var(--space-2);
  font-size: var(--text-xxs);
  line-height: 1.1;
  color: var(--color-text-secondary);
}

.sensor-card__mode-badge--live {
  color: var(--color-success);
}

.sensor-card__mode-badge--hybrid {
  color: var(--color-info);
}

.sensor-card__mode-badge--snapshot {
  color: var(--color-warning);
}

.sensor-card__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.sensor-card__quality-text {
  font-size: var(--text-xxs);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.sensor-card__quality-text--good { color: var(--color-success); }
.sensor-card__quality-text--warning { color: var(--color-warning); }
.sensor-card__quality-text--alarm { color: var(--color-error); }
.sensor-card__quality-text--stale { color: var(--color-status-warning); }
.sensor-card__quality-text--offline { color: var(--color-text-muted); }

.sensor-card__sparkline {
  height: 32px;
  margin: 0 0 var(--space-1);
  overflow: hidden;
}

.sensor-card__dot--good {
  background: var(--color-success);
}

.sensor-card__dot--warning {
  background: var(--color-warning);
}

.sensor-card__dot--alarm {
  background: var(--color-error);
}

.sensor-card__dot--stale {
  background: var(--color-status-warning);
}

.sensor-card__dot--offline {
  background: var(--color-text-muted);
}

.sensor-card__value {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--space-1);
  margin-bottom: var(--space-1);
}

.sensor-card__number {
  font-size: clamp(1.125rem, 3vw, 1.5rem);
  font-weight: 700;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  color: var(--color-text-primary);
  overflow-wrap: break-word;
  word-break: break-all;
  min-width: 0;
}

.sensor-card__unit {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.sensor-card__trend {
  display: inline-flex;
  align-items: center;
  margin-left: var(--space-1);
  color: var(--color-text-muted);
}

.sensor-card__footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-1) var(--space-2);
  flex-wrap: wrap;
  min-width: 0;
}

.sensor-card__footer-badges {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  flex-wrap: wrap;
  min-width: 0;
  max-width: 100%;
}

.sensor-card__subzone-badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--text-xs);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  background: var(--color-bg-quaternary, rgba(255, 255, 255, 0.06));
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sensor-card__esp {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Status border in monitor mode */
.sensor-card--good { border-color: rgba(52, 211, 153, 0.15); }
.sensor-card--warning { border-color: rgba(251, 191, 36, 0.15); }
.sensor-card--alarm { border-color: rgba(248, 113, 113, 0.15); }
.sensor-card--stale { border-color: rgba(251, 146, 60, 0.15); }
.sensor-card--offline { border-color: var(--glass-border); }

/* Stale data indicator */
.sensor-card--stale {
  opacity: 0.7;
  border-color: rgba(251, 191, 36, 0.25);
  border-left: 3px solid var(--color-warning);
}

.sensor-card--stale .sensor-card__number {
  color: var(--color-text-secondary);
}

.sensor-card--stale .sensor-card__sparkline {
  opacity: 0.5;
  filter: saturate(0.3);
}

.sensor-card--stale .sensor-card__trend {
  opacity: 0.5;
}

/* ESP offline indicator */
.sensor-card--esp-offline {
  opacity: 0.5;
  border-color: var(--glass-border);
}

.sensor-card--esp-offline .sensor-card__number {
  color: var(--color-text-muted);
}

/* Badges */
.sensor-card__badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xxs);
  font-weight: 500;
  padding: 1px var(--space-1);
  border-radius: var(--radius-xs);
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 0;
}

.sensor-card__badge--stale {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
}

.sensor-card__badge--offline {
  color: var(--color-text-muted);
  background: rgba(112, 112, 128, 0.15);
}

.sensor-card__badge--unknown {
  color: var(--color-text-muted);
  background: rgba(112, 112, 128, 0.1);
}

.sensor-card__badge--no-data {
  color: var(--color-text-muted);
  background: rgba(112, 112, 128, 0.1);
}

/* AUT-255: Alert-Suppression-Indicator */
.sensor-card__badge--suppressed {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
}

/* AUT-299: ATC fallback warning */
.sensor-card__badge--atc-fallback {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
}

/* AUT-322: ATC cached temperature (yellow/warning — approximated value) */
.sensor-card__badge--atc-cached {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  letter-spacing: 0.03em;
}

/* AUT-322: ATC temp read failed (red/danger — measurement aborted) */
.sensor-card__badge--atc-read-failed {
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
}

.sensor-card__badge--stability-good {
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 35%, transparent);
}

.sensor-card__badge--stability-warn {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
}

.sensor-card__badge-detail {
  margin-left: var(--space-1);
  opacity: 0.85;
  font-size: var(--text-xs);
}

/* AUT-300: On-demand sensor state badges */
.sensor-card__badge--on-demand-waiting {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--glass-border);
}

.sensor-card__badge--on-demand-stale {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.25);
}

/* AUT-300: On-demand stale card state (subtle, not full stale treatment) */
.sensor-card--on-demand-stale {
  border-color: rgba(251, 191, 36, 0.2);
  border-left: 3px solid rgba(251, 191, 36, 0.5);
}

/* AUT-300: Always-visible timestamp below the sensor value */
.sensor-card__last-seen {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-1);
  line-height: 1.3;
}

/* AUT-624: trend direction character (text, not icon-only) — color + symbol dual encoding */
.sensor-card__trend-char {
  margin-right: 2px;
  font-weight: 700;
}

.sensor-card__trend-char--rising {
  color: var(--color-warning);
}

.sensor-card__trend-char--stable {
  color: var(--color-text-muted);
}

.sensor-card__trend-char--falling {
  color: var(--color-info);
}

.sensor-card__number--no-data {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-muted);
  font-family: inherit;
}

/* AUT-609: Sparkline time range label */
.sensor-card__sparkline-header {
  display: flex;
  align-items: center;
  margin-bottom: 2px;
}

.sensor-card__sparkline-timerange {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  line-height: 1.2;
}

.sensor-card__sparkline-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

/* Mock device visual distinction */
.sensor-card--mock {
  border-color: color-mix(in srgb, var(--color-mock) 25%, var(--glass-border));
  background: color-mix(in srgb, var(--color-mock) 4%, var(--color-bg-tertiary));
}

.sensor-card--mock:hover {
  border-color: color-mix(in srgb, var(--color-mock) 40%, var(--glass-border));
}

.sensor-card__source-badge {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  padding: 1px var(--space-2);
  font-size: var(--text-xxs);
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: 0.03em;
}

.sensor-card__source-badge--mock {
  color: var(--color-mock);
  background: var(--color-mock-bg);
}

.sensor-card__source-badge--real {
  color: var(--color-real);
  background: color-mix(in srgb, var(--color-real) 16%, transparent);
}

/* Scope badges (T13-R3 WP4) */
.sensor-card__scope-badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--text-xxs);
  font-weight: 500;
  padding: 1px var(--space-2);
  border-radius: var(--radius-xs);
  white-space: nowrap;
  cursor: default;
}

.sensor-card__scope-badge--multi-zone {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.sensor-card__scope-badge--mobile {
  background: var(--color-accent-bg);
  color: var(--color-accent-bright);
}

/* Mobile sensor context hint (6.7) */
.sensor-card__context-hint {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-top: var(--space-1);
  padding-top: var(--space-1);
  border-top: 1px dashed var(--glass-border);
}

/* Mobile sensor zone switch (6.7) */
.sensor-card__context-controls {
  margin-top: var(--space-1);
}

.sensor-card__zone-select {
  width: 100%;
  font-size: var(--text-xs);
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  padding: var(--space-1) var(--space-2);
  min-height: 44px;
  cursor: pointer;
  transition: border-color var(--transition-fast);
}

.sensor-card__zone-select:hover {
  border-color: var(--color-iridescent-1);
}

.sensor-card__zone-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Virtual sensor info icon + tooltip (V19-F03) */
.sensor-card__virtual-info-trigger {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  min-height: 32px;
  color: var(--color-text-muted);
  cursor: help;
  flex-shrink: 0;
}

.sensor-card__virtual-tooltip {
  position: absolute;
  top: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-tooltip);
  min-width: 200px;
  padding: var(--space-3);
  background: var(--glass-bg, rgba(18, 18, 26, 0.92));
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md);
  backdrop-filter: blur(8px);
  pointer-events: none;
}

.sensor-card__virtual-tooltip-desc {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-bottom: var(--space-2);
  line-height: 1.4;
}

.sensor-card__virtual-tooltip-heading {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: var(--space-1);
}

.sensor-card__virtual-tooltip-list {
  list-style: disc;
  padding-left: 1rem;
  margin: 0 0 var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.sensor-card__virtual-tooltip-list li {
  margin-bottom: 2px;
}

.sensor-card__virtual-tooltip-formula {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
}

/* On-Demand Measure Button (AUT-298) */
.sensor-card__measure-row {
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px dashed var(--glass-border);
  display: flex;
  justify-content: flex-end;
}

.sensor-card__measure-hint {
  font-size: var(--text-xxs);
  color: var(--color-warning);
  opacity: 0.8;
  letter-spacing: 0.02em;
}

.sensor-card__measure-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xxs);
  font-weight: 500;
  padding: 3px var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-info-border);
  background: var(--color-info-bg);
  color: var(--color-info);
  cursor: pointer;
  white-space: nowrap;
  min-height: 22px;
  transition: border-color var(--transition-fast), background var(--transition-fast), color var(--transition-fast);
  letter-spacing: 0.02em;
}

.sensor-card__measure-btn:hover:not(:disabled) {
  border-color: var(--color-info-border);
  background: var(--color-info-bg-hover);
}

.sensor-card__measure-btn:disabled {
  opacity: 0.38;
  cursor: not-allowed;
}

.sensor-card__measure-btn--success {
  border-color: rgba(52, 211, 153, 0.4);
  background: rgba(52, 211, 153, 0.1);
  color: var(--color-success);
}

.sensor-card__measure-btn--error {
  border-color: rgba(248, 113, 113, 0.4);
  background: rgba(248, 113, 113, 0.1);
  color: var(--color-error);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
.sensor-card__measure-spinner {
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
</style>
