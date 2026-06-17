<script setup lang="ts">
/**
 * SensorValueCard Component
 * 
 * Displays a sensor's value with:
 * - Human-readable sensor type label
 * - Correct unit from SENSOR_TYPE_CONFIG
 * - Quality indicator
 * - Technical details (collapsible)
 * - Edit/Remove actions
 */

import { computed, ref, watch, onUnmounted } from 'vue'
import { Gauge, Info, Edit, Trash2, AlertTriangle, Activity, Clock, Calendar, Pause, HelpCircle, Play, Beaker, Timer } from 'lucide-vue-next'
import { sensorsApi } from '@/api/sensors'
import { useToast } from '@/composables/useToast'
import { Badge } from '@/shared/design'
import {
  SENSOR_TYPE_CONFIG,
  getSensorLabel,
} from '@/utils/sensorDefaults'
import { getQualityInfo, getGpioDescription } from '@/utils/labels'
import { formatRelativeTime, formatNumber, formatSensorStatus, getModeLabel, getMeasurementFreshness, formatStaleReason } from '@/utils/formatters'
import type { SensorOperatingMode, SensorKind } from '@/types'
import { createLogger } from '@/utils/logger'

const log = createLogger('SensorValueCard')

interface Sensor {
  gpio: number
  sensor_type: string
  name?: string
  subzone_id?: string
  raw_value: number
  processed_value?: number
  unit: string
  quality: string
  updated_at?: string
  // Phase 2E: Health-Status fields
  operating_mode?: SensorOperatingMode
  timeout_seconds?: number
  is_stale?: boolean
  stale_reason?: string
  last_reading_at?: string | null
  // Sensor-Lifecycle fields
  measurement_freshness_hours?: number | null
  freshness_hours?: number | null
  calibration_interval_days?: number | null
  calibration_data?: Record<string, unknown> | null
  // Wave 1: Snapshot-Sensor Kennzeichnung (MultispeQ etc.)
  sensor_kind?: SensorKind | null
  // AUT-313: Finality-Watch field (WS sensor_data event)
  last_read?: string | null
  // Frontend-local marker updated on each sensor_data event.
  last_event_at?: string | null
}

interface Props {
  /** The sensor data */
  sensor: Sensor
  /** ESP device ID - required for triggering measurements */
  espId: string
  /** Whether editing is enabled */
  editable?: boolean
  /** Whether to show compact view */
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  editable: false,
  compact: false,
})

// Toast notifications
const toast = useToast()

// AUT-313: Finality-Pattern (mirroring SensorCard.vue:285-303 as canonical source)
const isMeasuring = ref(false)
type MeasureState = 'idle' | 'success' | 'error'
const measureState = ref<MeasureState>('idle')
let measureTriggerTime = 0
let preMeasureTriggerValue: number | null = null
let preMeasureLastRead: string | null = null
let preMeasureLastEventAt: string | null = null
let measureTimeoutId: ReturnType<typeof setTimeout> | null = null

function clearMeasureTimeout(): void {
  if (measureTimeoutId) {
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
  toast.success('Messwert empfangen')
  setTimeout(() => { measureState.value = 'idle' }, 2000)
}

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

// Computed: Button nur für nicht-continuous Modi anzeigen
const showMeasureButton = computed(() => {
  const mode = props.sensor.operating_mode
  return mode && mode !== 'continuous'
})

// AUT-314: Analog probe sensors need settling time
const isAnalogProbeSensor = computed(() => {
  const t = props.sensor.sensor_type.toLowerCase()
  return t.includes('ph') || t.includes('ec')
})

async function handleTriggerMeasurement(): Promise<void> {
  if (isMeasuring.value) return
  isMeasuring.value = true
  measureState.value = 'idle'
  measureTriggerTime = Date.now()
  preMeasureTriggerValue = props.sensor.raw_value ?? null
  preMeasureLastRead = props.sensor.last_read ?? null
  preMeasureLastEventAt = props.sensor.last_event_at ?? null
  try {
    await sensorsApi.triggerMeasurement(props.espId, props.sensor.gpio)
    log.info('Measurement command sent, waiting for WS finality', { gpio: props.sensor.gpio })
    measureTimeoutId = setTimeout(() => {
      isMeasuring.value = false
      measureState.value = 'error'
      toast.error('Kein Messwert erhalten (Timeout)')
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
    measureState.value = 'error'
    measureTriggerTime = 0
    preMeasureTriggerValue = null
    preMeasureLastRead = null
    preMeasureLastEventAt = null
    log.error('Measurement trigger failed', err)
    const errorMessage = (err as { response?: { data?: { detail?: string } } })
      .response?.data?.detail || 'Messung konnte nicht gestartet werden'
    toast.error(errorMessage)
    setTimeout(() => { measureState.value = 'idle' }, 2000)
  }
}

const emit = defineEmits<{
  edit: [gpio: number]
  remove: [gpio: number]
}>()

// Get sensor configuration
const sensorConfig = computed(() => SENSOR_TYPE_CONFIG[props.sensor.sensor_type])

// Use the correct unit from config, fallback to sensor's unit
const displayUnit = computed(() => 
  sensorConfig.value?.unit ?? props.sensor.unit ?? 'raw'
)

// Get display value (processed if available, otherwise raw)
const displayValue = computed(() => 
  props.sensor.processed_value ?? props.sensor.raw_value
)

// Format the value with correct decimals from config
const formattedValue = computed(() => {
  const decimals = sensorConfig.value?.decimals ?? 2
  return formatNumber(displayValue.value, decimals)
})

// Get quality info for badge
const qualityInfo = computed(() => getQualityInfo(props.sensor.quality))

// Human-readable name
const sensorName = computed(() => 
  props.sensor.name || getSensorLabel(props.sensor.sensor_type) || `GPIO ${props.sensor.gpio}`
)

// Sensor type label
const typeLabel = computed(() => getSensorLabel(props.sensor.sensor_type))

// GPIO description for tooltip
const gpioTooltip = computed(() => getGpioDescription(props.sensor.gpio))

// Phase 2E: Modus-basierter Sensor-Status für Anzeige
const sensorStatus = computed(() => {
  return formatSensorStatus({
    operating_mode: props.sensor.operating_mode,
    is_stale: props.sensor.is_stale,
    stale_reason: props.sensor.stale_reason,
    last_reading_at: props.sensor.last_reading_at || props.sensor.updated_at,
    timeout_seconds: props.sensor.timeout_seconds,
  })
})

// Sensor-Lifecycle: Measurement freshness for on-demand/scheduled sensors
const effectiveFreshnessHours = computed(() =>
  props.sensor.freshness_hours ?? props.sensor.measurement_freshness_hours ?? null
)

const measurementFreshness = computed(() => {
  const mode = props.sensor.operating_mode
  if (!mode || mode === 'continuous' || mode === 'paused') return null
  return getMeasurementFreshness(
    props.sensor.last_reading_at || props.sensor.updated_at,
    effectiveFreshnessHours.value,
  )
})

const showFreshnessIndicator = computed(() =>
  measurementFreshness.value !== null && measurementFreshness.value.level !== 'unknown'
)

// Sensor-Lifecycle: Calibration status
const calibrationStatus = computed(() => {
  const calData = props.sensor.calibration_data
  if (!calData || typeof calData !== 'object') return null

  const calibratedAt = calData.calibrated_at as string | undefined
  if (!calibratedAt) return null

  const interval = props.sensor.calibration_interval_days
  if (!interval || interval <= 0) return { isDue: false, label: null, daysAgo: 0 }

  const calDate = new Date(calibratedAt as string)
  const ageDays = Math.floor((Date.now() - calDate.getTime()) / 86400000)
  const isDue = ageDays > interval

  return {
    isDue,
    label: isDue
      ? `Kalibrierung fällig (vor ${ageDays} Tagen)`
      : `Kalibriert vor ${ageDays} Tagen`,
    daysAgo: ageDays,
  }
})

// Map icon names to components
const statusIconMap: Record<string, typeof AlertTriangle> = {
  'Activity': Activity,
  'AlertTriangle': AlertTriangle,
  'Clock': Clock,
  'Calendar': Calendar,
  'Pause': Pause,
  'HelpCircle': HelpCircle,
}

// Map SensorStatusVariant to BadgeVariant ('error' → 'danger')
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'gray'
const badgeVariant = computed((): BadgeVariant => {
  const variant = sensorStatus.value.variant
  return variant === 'error' ? 'danger' : variant
})

// Wave 1: Snapshot sensor (MultispeQ) — suppress live freshness/timeout warnings,
// show "Letzte Messung" label instead of relative-live timing.
const isSnapshot = computed(() => props.sensor.sensor_kind === 'snapshot')
</script>

<template>
  <div :class="['sensor-value-card', { 'sensor-value-card--compact': compact }]">
    <!-- Icon -->
    <div class="sensor-value-card__icon">
      <Gauge class="w-5 h-5" />
    </div>
    
    <!-- Main content -->
    <div class="sensor-value-card__content">
      <!-- Name and type -->
      <div class="sensor-value-card__header">
        <span class="sensor-value-card__name">{{ sensorName }}</span>
        <span class="sensor-value-card__type">{{ typeLabel }}</span>
      </div>
      
      <!-- Value display -->
      <div class="sensor-value-card__value-row">
        <span class="sensor-value-card__value">{{ formattedValue }}</span>
        <span class="sensor-value-card__unit">{{ displayUnit }}</span>
      </div>
      
      <!-- Quality and status badges -->
      <div class="sensor-value-card__badges">
        <!-- Quality Badge (bestehend) -->
        <Badge
          :variant="qualityInfo.label === 'Gut' || qualityInfo.label === 'Ausgezeichnet' ? 'success' : 'warning'"
          size="sm"
        >
          {{ qualityInfo.label }}
        </Badge>

        <!-- Wave 1: Snapshot Badge (MultispeQ etc.) -->
        <Badge
          v-if="isSnapshot"
          variant="warning"
          size="sm"
          title="Snapshot-Sensor: Punktmessung, kein Live-Stream"
        >
          Snapshot
        </Badge>

        <!-- Phase 2E: Operating Mode Badge (nur wenn nicht continuous) -->
        <Badge
          v-if="sensor.operating_mode && sensor.operating_mode !== 'continuous'"
          :variant="badgeVariant"
          size="sm"
          :title="sensorStatus.label"
        >
          <component
            :is="statusIconMap[sensorStatus.icon]"
            class="w-3 h-3 mr-1"
          />
          {{ getModeLabel(sensor.operating_mode) }}
        </Badge>

        <!-- Phase 2E: Stale-Warnung (nur bei continuous + stale, nicht für Snapshot) -->
        <Badge
          v-if="!isSnapshot && sensor.operating_mode === 'continuous' && sensor.is_stale"
          variant="danger"
          size="sm"
          :title="sensorStatus.label"
        >
          <AlertTriangle class="w-3 h-3 mr-1" />
          Stale
        </Badge>

        <!-- Sensor-Lifecycle: Freshness-Indikator für On-Demand/Scheduled (nicht für Snapshot) -->
        <Badge
          v-if="!isSnapshot && showFreshnessIndicator && measurementFreshness"
          :variant="measurementFreshness.variant === 'error' ? 'danger' : measurementFreshness.variant"
          size="sm"
          :title="measurementFreshness.label"
        >
          <Timer class="w-3 h-3 mr-1" />
          {{ measurementFreshness.ageLabel }}
        </Badge>

        <!-- Sensor-Lifecycle: Freshness exceeded stale badge -->
        <Badge
          v-if="sensor.is_stale && sensor.stale_reason === 'freshness_exceeded'"
          variant="danger"
          size="sm"
          :title="formatStaleReason(sensor.stale_reason)"
        >
          <AlertTriangle class="w-3 h-3 mr-1" />
          Messung empfohlen
        </Badge>

        <!-- Sensor-Lifecycle: Kalibrierungs-Indikator -->
        <Badge
          v-if="calibrationStatus?.isDue"
          variant="warning"
          size="sm"
          :title="calibrationStatus.label"
        >
          <Beaker class="w-3 h-3 mr-1" />
          Kalibrierung fällig
        </Badge>

        <!-- Subzone Badge -->
        <Badge v-if="sensor.subzone_id" variant="gray" size="sm">
          {{ sensor.subzone_id }}
        </Badge>
      </div>

      <!-- AUT-314: Settling hint for analog probe sensors -->
      <span v-if="showMeasureButton && isAnalogProbeSensor && !isMeasuring" class="sensor-value-card__measure-hint">
        Sonde ≥5s eintauchen lassen
      </span>

      <!-- Phase 2D: Messung starten Button (nur für nicht-continuous Modi) -->
      <button
        v-if="showMeasureButton"
        class="sensor-value-card__measure-btn"
        :disabled="isMeasuring"
        @click="handleTriggerMeasurement"
      >
        <!-- Loading Spinner -->
        <svg
          v-if="isMeasuring"
          class="sensor-value-card__spinner"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            class="opacity-25"
            cx="12" cy="12" r="10"
            stroke="currentColor"
            stroke-width="4"
          />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>

        <!-- Error Icon (Timeout/Fehler-Zustand) -->
        <AlertTriangle v-else-if="measureState === 'error'" class="w-4 h-4 text-red-400" />

        <!-- Play Icon (Normalzustand) -->
        <Play v-else class="w-4 h-4" />

        <span>{{ isMeasuring ? 'Messe...' : measureState === 'error' ? 'Fehler' : 'Messung starten' }}</span>
      </button>

      <!-- Technical details (expandable) -->
      <details v-if="!compact" class="sensor-value-card__details">
        <summary class="sensor-value-card__details-toggle">
          <Info class="w-3 h-3" />
          Technische Details
        </summary>
        <div class="sensor-value-card__details-content">
          <div class="sensor-value-card__detail-row">
            <span>Typ</span>
            <span>{{ sensor.sensor_type }}</span>
          </div>
          <div class="sensor-value-card__detail-row" :title="gpioTooltip">
            <span>GPIO</span>
            <span>{{ sensor.gpio }}</span>
          </div>
          <div class="sensor-value-card__detail-row">
            <span>Rohwert</span>
            <span>{{ formatNumber(sensor.raw_value, 4) }}</span>
          </div>
          <div v-if="sensor.updated_at || sensor.last_reading_at" class="sensor-value-card__detail-row">
            <span>{{ isSnapshot ? 'Letzte Messung' : 'Aktualisiert' }}</span>
            <span>{{ formatRelativeTime(sensor.last_reading_at || sensor.updated_at) }}</span>
          </div>
          <!-- Phase 2E: Operating Mode -->
          <div v-if="sensor.operating_mode" class="sensor-value-card__detail-row">
            <span>Modus</span>
            <span>{{ getModeLabel(sensor.operating_mode) }}</span>
          </div>
          <div v-if="sensor.timeout_seconds && sensor.timeout_seconds > 0" class="sensor-value-card__detail-row">
            <span>Timeout</span>
            <span>{{ sensor.timeout_seconds }}s</span>
          </div>
          <div v-if="effectiveFreshnessHours" class="sensor-value-card__detail-row">
            <span>Freshness-Limit</span>
            <span>{{ effectiveFreshnessHours }}h</span>
          </div>
          <div v-if="calibrationStatus && calibrationStatus.daysAgo > 0" class="sensor-value-card__detail-row">
            <span>Kalibrierung</span>
            <span>vor {{ calibrationStatus.daysAgo }} Tagen</span>
          </div>
          <div v-if="sensor.calibration_interval_days" class="sensor-value-card__detail-row">
            <span>Kalibrier-Intervall</span>
            <span>{{ sensor.calibration_interval_days }} Tage</span>
          </div>
          <div v-if="sensorConfig?.description" class="sensor-value-card__description">
            {{ sensorConfig.description }}
          </div>
        </div>
      </details>
    </div>
    
    <!-- Actions -->
    <div v-if="editable" class="sensor-value-card__actions">
      <button
        class="sensor-value-card__action-btn"
        @click="emit('edit', sensor.gpio)"
        title="Bearbeiten"
      >
        <Edit class="w-4 h-4" />
      </button>
      <button
        class="sensor-value-card__action-btn sensor-value-card__action-btn--danger"
        @click="emit('remove', sensor.gpio)"
        title="Entfernen"
      >
        <Trash2 class="w-4 h-4" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.sensor-value-card {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  transition: background-color 0.2s;
}

.sensor-value-card:hover {
  background-color: var(--color-bg-hover);
}

.sensor-value-card--compact {
  padding: 0.75rem;
}

.sensor-value-card__icon {
  width: clamp(1.5rem, 4vw, 2.5rem);
  height: clamp(1.5rem, 4vw, 2.5rem);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  background-color: rgba(167, 139, 250, 0.2);
  color: var(--color-mock);
  flex-shrink: 0;
}

.sensor-value-card__content {
  flex: 1;
  min-width: 0;
}

.sensor-value-card__header {
  margin-bottom: 0.25rem;
}

.sensor-value-card__name {
  font-weight: 600;
  color: var(--color-text-primary);
  display: block;
}

.sensor-value-card__type {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.sensor-value-card__value-row {
  display: flex;
  align-items: baseline;
  gap: 0.25rem;
  margin: 0.5rem 0;
  min-width: 0;
  overflow: hidden;
}

.sensor-value-card__value {
  font-size: 1.5rem;
  font-weight: 700;
  font-family: 'JetBrains Mono', monospace;
  color: var(--color-text-primary);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sensor-value-card__unit {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  flex-shrink: 0;
  white-space: nowrap;
}

.sensor-value-card__badges {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.sensor-value-card__details {
  margin-top: 0.75rem;
  font-size: 0.75rem;
}

.sensor-value-card__details-toggle {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--color-text-muted);
  cursor: pointer;
  user-select: none;
}

.sensor-value-card__details-toggle:hover {
  color: var(--color-text-secondary);
}

.sensor-value-card__details-content {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background-color: var(--color-bg-secondary);
  border-radius: var(--radius-xs);
}

.sensor-value-card__detail-row {
  display: flex;
  justify-content: space-between;
  padding: 0.25rem 0;
  border-bottom: 1px solid var(--glass-border);
}

.sensor-value-card__detail-row:last-child {
  border-bottom: none;
}

.sensor-value-card__detail-row span:first-child {
  color: var(--color-text-muted);
}

.sensor-value-card__detail-row span:last-child {
  color: var(--color-text-primary);
  font-family: 'JetBrains Mono', monospace;
}

.sensor-value-card__description {
  margin-top: 0.5rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
  font-style: italic;
}

.sensor-value-card__actions {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.sensor-value-card__action-btn {
  padding: 0.5rem;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}

.sensor-value-card__action-btn:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-secondary);
}

.sensor-value-card__action-btn--danger:hover {
  color: var(--color-error);
  background-color: rgba(248, 113, 113, 0.1);
}

/* Phase 2D: Measure Button Styles */
.sensor-value-card__measure-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  width: 100%;
  margin-top: 0.75rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: var(--radius-md);
  transition: all 0.2s;
  background-color: color-mix(in srgb, var(--color-accent) 20%, transparent);
  color: var(--color-accent-bright);
  border: 1px solid color-mix(in srgb, var(--color-accent) 30%, transparent);
  cursor: pointer;
}

.sensor-value-card__measure-btn:hover:not(:disabled) {
  background-color: color-mix(in srgb, var(--color-accent) 30%, transparent);
  border-color: color-mix(in srgb, var(--color-accent) 50%, transparent);
}

.sensor-value-card__measure-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sensor-value-card__spinner {
  width: 1rem;
  height: 1rem;
  animation: spin 1s linear infinite;
}

</style>





















