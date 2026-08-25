<script setup lang="ts">
/**
 * TankIstSollPanel — Ist/Soll/Delta cockpit for a single tank (AUT-1225 Q4).
 *
 * Soll = plan_segment@now via GET /v1/tanks/{id}/targets (server-resolved,
 * NEVER derived from Tank fields — Tank carries no target_ec/target_ph
 * columns). Ist + membership = live `device.tank_id` via deviceIdsForTank
 * (AUT-1537 — same SSOT as NutrientSolutionView, not the 30s targets snapshot).
 *
 * A missing/stale value is NEVER rendered as "0" — always "—".
 *
 * KPI layout inspired by ClimateRuleHealthWidget.vue (Soll / IST / Δ row),
 * reimplemented with Tailwind + design tokens — no ruleHealth store import.
 *
 * AUT-1326: optional `variant="monitor-compact"` — Ist + Verlauf only
 * (Soll/Delta structurally retained for later additive enablement; not shown in V1).
 * Compact metrics reuse MonitorExpanded1hChart (same expand as SensorCard).
 *
 * AUT-1358 (E6): Soll re-fetches without remount — quiet poll + `refreshToken`
 * (plan edit). Ist remains live from espStore.
 */

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ChevronRight, Droplets, ExternalLink, Gauge } from 'lucide-vue-next'
import { tanksApi } from '@/api/tanks'
import { useEspStore } from '@/stores/esp'
import type { TankMeasureTarget, TankTargetsResponse } from '@/types'
import ErrorState from '@/shared/design/patterns/ErrorState.vue'
import EmptyState from '@/shared/design/patterns/EmptyState.vue'
import BaseSpinner from '@/shared/design/primitives/BaseSpinner.vue'
import LiveLineChart, { type ThresholdConfig } from '@/components/charts/LiveLineChart.vue'
import MonitorExpanded1hChart, {
  type ExpandedLivePoint,
} from '@/components/monitor/MonitorExpanded1hChart.vue'
import type { ChartDataPoint } from '@/components/charts/types'
import {
  computeDelta,
  findIstSensorValue,
  formatDelta,
  formatIstSollValue,
  measureKeyFromTarget,
  measureLabel,
  resolvedViaLabel,
  tankDetailHref,
  type IstSollMeasureKey,
} from './tankIstSollFormat'
import {
  deviceIdsForTank,
  resolveTankMeasureSensor,
  type TankEcPhSensorRef,
  type ZoneTankSensorLike,
} from '@/utils/zoneTankEcPh'
import { getSensorUnit } from '@/utils/sensorDefaults'
import { createLogger } from '@/utils/logger'
import { formatDateTime } from '@/utils/formatters'
import { formatMeasuredFreshWaterOrigin } from '@/utils/volumeZugabeSourceDisplay'

/** Quiet re-fetch interval for plan_segment@now (segment boundary / external edits). */
const TARGETS_POLL_MS = 30_000

const logger = createLogger('TankIstSollPanel')

// =============================================================================
// Props
// =============================================================================

export type TankIstSollVariant = 'full' | 'monitor-compact'

interface Props {
  tankId: string
  /** Default `full` preserves /plants + /domains mounts. */
  variant?: TankIstSollVariant
  /** Shown in monitor-compact header when provided. */
  tankName?: string
  /** Optional zone-sensor snapshots for sparkline identity (Monitor). */
  zoneSensors?: ZoneTankSensorLike[]
  getSparkline?: (sensor: TankEcPhSensorRef) => ChartDataPoint[] | undefined
  getThresholds?: (sensorType: string) => ThresholdConfig | undefined
  /** Override detail link (defaults to tankDetailHref). */
  detailTo?: string
  /**
   * Bump after plan_segment edits to re-fetch Soll without remounting
   * (AUT-1358 — replaces NutrientSolutionView :key remount hack).
   */
  refreshToken?: number
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'full',
  tankName: '',
  zoneSensors: () => [],
  detailTo: undefined,
  refreshToken: 0,
})

const emit = defineEmits<{
  /** Monitor L3 — same payload shape as SensorCard "Zeitreihe anzeigen". */
  'sensor-detail': [sensor: {
    esp_id: string
    gpio: number
    sensor_type: string
    name: string | null
    unit: string
  }]
}>()

// =============================================================================
// Store
// =============================================================================

const espStore = useEspStore()

// =============================================================================
// State
// =============================================================================

const targets = ref<TankTargetsResponse | null>(null)
const isLoading = ref(false)
const error = ref<string | null>(null)

/** Per-measure expand keys for monitor-compact (EC/PH independent; default collapsed). */
const expandedMeasures = ref<Set<string>>(new Set())

/** AUT-1398: last measured Frischwasser from Assist/ledger (M-3/M-5 path). */
const lastMeasuredFreshWater = ref<{
  volumeL: number
  label: string | null
  occurredAt: string | null
} | null>(null)

const measuredFreshWaterOrigin = computed(() => {
  const m = lastMeasuredFreshWater.value
  if (!m) return null
  return formatMeasuredFreshWaterOrigin({
    ruleName: m.label,
    occurredAt: m.occurredAt,
    volumeL: m.volumeL,
  })
})

// =============================================================================
// Computed
// =============================================================================

/** Live membership — Clear tank_id flips immediately (AUT-1537). Soll still polls. */
const assignedDeviceIds = computed<string[]>(() =>
  deviceIdsForTank(espStore.devices, props.tankId),
)
const hasAssignedDevices = computed<boolean>(() => assignedDeviceIds.value.length > 0)
const isCompact = computed(() => props.variant === 'monitor-compact')

/** Visible membership labels — name primary (AUT-1331 / AUT-1339); id only if unnamed. */
const assignedDeviceLabels = computed<string[]>(() => {
  return assignedDeviceIds.value.map((id) => {
    const device = espStore.devices.find(
      (d) => d.device_id === id || d.esp_id === id,
    )
    const name = device?.name?.trim()
    return name && name.length > 0 ? name : id
  })
})

const detailHref = computed(() => props.detailTo ?? tankDetailHref(props.tankId))

interface IstSollRow {
  /** `tank_temp` is compact-only (AUT-1537) — not a TankTargetMeasure. */
  measure: TankMeasureTarget['measure'] | 'tank_temp'
  measureKey: IstSollMeasureKey | null
  label: string
  unit: string
  sollDisplay: string
  istDisplay: string
  deltaDisplay: string
  deltaStatus: 'ok' | 'warn' | 'unknown'
  resolvedLabel: string
  /** Sensor identity for sparkline (compact); null when unresolved. */
  sensorRef: TankEcPhSensorRef | null
}

function isMeasureExpanded(measure: string): boolean {
  return expandedMeasures.value.has(measure)
}

function toggleMeasureExpand(measure: string): void {
  const next = new Set(expandedMeasures.value)
  if (next.has(measure)) next.delete(measure)
  else next.add(measure)
  expandedMeasures.value = next
}

function unitForSensor(sensor: TankEcPhSensorRef): string {
  const unit = getSensorUnit(sensor.sensor_type)
  return unit !== 'raw' ? unit : ''
}

function liveSampleFor(row: IstSollRow): ExpandedLivePoint | null {
  const sensor = row.sensorRef
  if (!sensor || sensor.value == null || !Number.isFinite(sensor.value)) return null
  const tsMs = sensor.last_read ? new Date(sensor.last_read).getTime() : Number.NaN
  if (!Number.isFinite(tsMs)) return null
  return { x: tsMs, y: Number(sensor.value) }
}

function emitSensorDetail(row: IstSollRow): void {
  const sensor = row.sensorRef
  if (!sensor) return
  emit('sensor-detail', {
    esp_id: sensor.esp_id,
    gpio: sensor.gpio,
    sensor_type: sensor.sensor_type,
    name: row.label || sensor.sensor_type,
    unit: unitForSensor(sensor) || row.unit,
  })
}

/** Delta thresholds are intentionally loose — this is a display cue, not a control loop.
 * EC in µS/cm (AUT-1268 / E1), same as plan segments + live sensors. */
const DELTA_OK_THRESHOLD: Record<string, number> = {
  target_ec: 300,
  target_ph: 0.3,
}

const rows = computed<IstSollRow[]>(() => {
  const list = targets.value?.targets ?? []
  const targetRows: IstSollRow[] = list.map((target) => {
    const measureKey = measureKeyFromTarget(target.measure)
    const ist = measureKey
      ? findIstSensorValue(espStore.devices, assignedDeviceIds.value, measureKey)
      : null
    const delta = computeDelta(ist, target.value)
    const okThreshold = DELTA_OK_THRESHOLD[target.measure] ?? 0.3
    const deltaStatus: IstSollRow['deltaStatus'] =
      delta === null ? 'unknown' : Math.abs(delta) <= okThreshold ? 'ok' : 'warn'

    const sensorRef =
      measureKey != null
        ? resolveTankMeasureSensor(
            props.zoneSensors,
            espStore.devices,
            assignedDeviceIds.value,
            measureKey,
          )
        : null

    return {
      measure: target.measure,
      measureKey,
      label: measureLabel(target.measure),
      unit: target.unit ?? '',
      sollDisplay: formatIstSollValue(target.value),
      // Keep default decimals for full mounts (/plants, /domains); compact may refine later.
      istDisplay: formatIstSollValue(ist),
      deltaDisplay: formatDelta(delta),
      deltaStatus,
      resolvedLabel: resolvedViaLabel(target.resolved_via),
      sensorRef,
    }
  })

  // AUT-1537: Messbox temp on compact tile only — not a TankTargetMeasure, not on full mounts.
  if (isCompact.value && assignedDeviceIds.value.length > 0) {
    const sensorRef = resolveTankMeasureSensor(
      props.zoneSensors,
      espStore.devices,
      assignedDeviceIds.value,
      'temperature',
    )
    if (sensorRef) {
      // Ist must come from the same sensor as sparkline / expand chart (AUT-1537:
      // sht31_temp and ds18b20 can both match AggCategory temperature).
      targetRows.push({
        measure: 'tank_temp',
        measureKey: 'temperature',
        label: 'Temp',
        unit: unitForSensor(sensorRef),
        sollDisplay: '—',
        istDisplay: formatIstSollValue(sensorRef.value, 1),
        deltaDisplay: '—',
        deltaStatus: 'unknown',
        resolvedLabel: '',
        sensorRef,
      })
    }
  }

  return targetRows
})

const evaluatedAtDisplay = computed<string>(() =>
  targets.value?.at ? formatDateTime(targets.value.at) : '—',
)

// =============================================================================
// Load
// =============================================================================

async function loadMeasuredFreshWater(): Promise<void> {
  const ecTarget = targets.value?.targets.find((t) => t.measure === 'target_ec')
  const targetEc =
    ecTarget?.value != null && Number.isFinite(Number(ecTarget.value))
      ? Number(ecTarget.value)
      : null
  const istEc = findIstSensorValue(
    espStore.devices,
    assignedDeviceIds.value,
    'ec',
  )
  if (targetEc == null || istEc == null) {
    lastMeasuredFreshWater.value = null
    return
  }
  try {
    // volume_zugabe_l=0 → server resolves latest fresh_water_refill (AUT-1385/1398).
    const assist = await tanksApi.computeDoseExpectation(props.tankId, {
      current_ec_us_cm: istEc,
      target_ec_us_cm: targetEc,
      volume_zugabe_l: 0,
    })
    if (
      assist.volume_zugabe_source === 'measured' &&
      assist.volume_zugabe_l > 0
    ) {
      lastMeasuredFreshWater.value = {
        volumeL: assist.volume_zugabe_l,
        label: assist.volume_zugabe_label ?? null,
        occurredAt: assist.volume_zugabe_occurred_at ?? null,
      }
    } else {
      lastMeasuredFreshWater.value = null
    }
  } catch (e) {
    // Fail-soft: Ist/Soll stays usable without measured strip.
    logger.warn('AUT-1398: measured freshwater probe failed', e)
    lastMeasuredFreshWater.value = null
  }
}

async function load(options?: { quiet?: boolean }): Promise<void> {
  const quiet = options?.quiet === true && targets.value !== null
  if (!quiet) {
    isLoading.value = true
  }
  if (!quiet) {
    error.value = null
  }
  try {
    targets.value = await tanksApi.getTargets(props.tankId)
    if (espStore.devices.length === 0) {
      await espStore.fetchAll()
    }
    await loadMeasuredFreshWater()
  } catch (e) {
    // Quiet polls keep last good Soll; only surface errors on initial/hard load.
    if (!quiet) {
      error.value = e instanceof Error ? e.message : 'Ist/Soll-Daten konnten nicht geladen werden'
    }
    logger.error(`Failed to load targets for tank ${props.tankId}`, e)
  } finally {
    if (!quiet) {
      isLoading.value = false
    }
  }
}

function sparklineFor(row: IstSollRow): ChartDataPoint[] | undefined {
  if (!row.sensorRef || !props.getSparkline) return undefined
  return props.getSparkline(row.sensorRef)
}

// =============================================================================
// Lifecycle
// =============================================================================

let pollTimer: ReturnType<typeof setInterval> | null = null

function startTargetsPoll(): void {
  stopTargetsPoll()
  pollTimer = setInterval(() => {
    if (props.tankId) void load({ quiet: true })
  }, TARGETS_POLL_MS)
}

function stopTargetsPoll(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onMounted(() => {
  if (props.tankId) void load()
  startTargetsPoll()
})

onUnmounted(() => {
  stopTargetsPoll()
})

watch(
  () => props.tankId,
  (tankId, previous) => {
    if (tankId && tankId !== previous) {
      expandedMeasures.value = new Set()
      void load()
      startTargetsPoll()
    }
  },
)

watch(
  () => props.refreshToken,
  (token, previous) => {
    if (props.tankId && token !== previous) {
      void load({ quiet: true })
    }
  },
)
</script>

<template>
  <div
    class="flex flex-col gap-3 rounded-[var(--radius-md)] border border-[var(--glass-border)] bg-[var(--color-bg-card,var(--color-bg-secondary))] p-3"
    :class="{ 'tank-ist-soll-panel--compact': isCompact }"
    :data-variant="variant"
  >
    <!-- Loading -->
    <div v-if="isLoading" class="flex items-center justify-center gap-2 py-6 text-sm text-[var(--color-text-secondary)]">
      <BaseSpinner size="sm" />
      <span>{{ isCompact ? 'Lade Tank-Werte…' : 'Lade Ist/Soll…' }}</span>
    </div>

    <!-- Error -->
    <ErrorState
      v-else-if="error"
      :message="error"
      :title="isCompact ? 'Tank-Werte konnten nicht geladen werden' : 'Ist/Soll konnte nicht geladen werden'"
      @retry="load"
    />

    <!-- Empty: no device assigned -->
    <EmptyState
      v-else-if="!hasAssignedDevices"
      title="Kein Gerät zugeordnet"
      description="Diesem Tank ist kein ESP-Gerät zugeordnet. Ist-Werte können erst nach der Geräte-Zuordnung angezeigt werden."
      :show-action="false"
    />

    <!-- AUT-1326/1328: Monitor compact — Ist + Sparkline + expand to 1h chart; Details → full panel -->
    <template v-else-if="isCompact">
      <header class="flex items-center justify-between gap-2">
        <router-link
          :to="detailHref"
          class="flex min-w-0 items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)] hover:underline"
          :aria-label="`Zur vollständigen Tank-Ansicht: ${tankName || 'Tank'}`"
        >
          <Droplets class="h-4 w-4 shrink-0 text-[var(--color-iridescent-1)]" aria-hidden="true" />
          <span class="truncate">{{ tankName || 'Tank' }}</span>
        </router-link>
        <router-link
          :to="detailHref"
          class="inline-flex shrink-0 items-center gap-1 text-xs font-medium text-[var(--color-accent)] hover:underline"
          aria-label="Zur vollständigen Tank-Ansicht"
        >
          Details
          <ExternalLink class="h-3 w-3" aria-hidden="true" />
        </router-link>
      </header>

      <p
        class="text-xs text-[var(--color-text-secondary)]"
        :aria-label="`Zugeordnete Geräte: ${assignedDeviceLabels.join(', ')}`"
      >
        Geräte: {{ assignedDeviceLabels.join(' · ') }}
      </p>

      <div
        v-for="row in rows"
        :key="row.measure"
        class="flex flex-col gap-2 rounded-[var(--radius-sm)] border border-[var(--glass-border)] p-2"
        :class="{ 'tank-ist-soll-panel__metric--expanded': isMeasureExpanded(row.measure) }"
      >
        <div
          class="flex w-full flex-col gap-2 text-left"
          :class="{ 'cursor-pointer': !!row.sensorRef }"
          role="button"
          tabindex="0"
          :aria-expanded="isMeasureExpanded(row.measure)"
          :aria-disabled="!row.sensorRef"
          :aria-label="`${row.label} Verlauf ${isMeasureExpanded(row.measure) ? 'einklappen' : 'aufklappen'}`"
          @click="row.sensorRef && toggleMeasureExpand(row.measure)"
          @keydown.enter.prevent="row.sensorRef && toggleMeasureExpand(row.measure)"
          @keydown.space.prevent="row.sensorRef && toggleMeasureExpand(row.measure)"
        >
          <div class="flex items-baseline justify-between gap-2">
            <span class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">
              {{ row.label }}{{ row.unit ? ` (${row.unit})` : '' }}
            </span>
            <span class="flex items-center gap-1">
              <span
                class="font-mono text-lg font-bold text-[var(--color-text-primary)]"
                :aria-label="`Ist ${row.label}: ${row.istDisplay}`"
              >
                {{ row.istDisplay }}
              </span>
              <ChevronRight
                v-if="row.sensorRef"
                class="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform"
                :class="{ 'rotate-90': isMeasureExpanded(row.measure) }"
                aria-hidden="true"
              />
            </span>
          </div>

          <div class="h-10 min-h-[40px]">
            <LiveLineChart
              v-if="row.sensorRef && sparklineFor(row)?.length"
              :data="sparklineFor(row)!"
              compact
              height="40px"
              :max-data-points="30"
              :sensor-type="row.sensorRef.sensor_type"
              :thresholds="getThresholds?.(row.sensorRef.sensor_type)"
              :show-thresholds="!!getThresholds?.(row.sensorRef.sensor_type)"
            />
            <span v-else class="text-xs text-[var(--color-text-muted)]">Keine Verlaufsdaten</span>
          </div>
        </div>

        <Transition name="expand">
          <MonitorExpanded1hChart
            v-if="isMeasureExpanded(row.measure) && row.sensorRef"
            :esp-id="row.sensorRef.esp_id"
            :gpio="row.sensorRef.gpio"
            :sensor-type="row.sensorRef.sensor_type"
            :unit="unitForSensor(row.sensorRef)"
            :live-sample="liveSampleFor(row)"
            show-detail-action
            @detail="emitSensorDetail(row)"
          />
        </Transition>

        <!-- Structural hooks for later Soll/Delta (V1: unused / empty) -->
        <slot name="soll" :row="row" />
        <slot name="delta" :row="row" />
      </div>

      <p
        v-if="measuredFreshWaterOrigin"
        class="rounded-[var(--radius-sm)] border border-[var(--glass-border)] px-2 py-2 text-xs text-[var(--color-text-secondary)]"
        data-testid="tank-ist-soll-measured-freshwater"
        role="status"
      >
        <span class="font-semibold text-[var(--color-success)]">Messpunkt</span>
        · {{ measuredFreshWaterOrigin }}
      </p>
    </template>

    <!-- Full KPI rows (default — /plants, /domains) -->
    <template v-else>
      <header class="flex items-center justify-between gap-2">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
          <Gauge class="h-4 w-4 text-[var(--color-iridescent-1)]" aria-hidden="true" />
          Ist / Soll
        </h3>
        <span class="text-xs text-[var(--color-text-muted)]" :title="`Auswertungszeit: ${evaluatedAtDisplay}`">
          Stand: {{ evaluatedAtDisplay }}
        </span>
      </header>

      <p
        class="text-xs text-[var(--color-text-secondary)]"
        :aria-label="`Zugeordnete Geräte: ${assignedDeviceLabels.join(', ')}`"
      >
        Zugeordnete Geräte: {{ assignedDeviceLabels.join(' · ') }}
      </p>

      <div
        v-for="row in rows"
        :key="row.measure"
        class="flex flex-col gap-2 rounded-[var(--radius-sm)] border border-[var(--glass-border)] p-2"
      >
        <div class="flex items-center justify-between">
          <span class="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">
            <Droplets class="h-3.5 w-3.5" aria-hidden="true" />
            {{ row.label }}{{ row.unit ? ` (${row.unit})` : '' }}
          </span>
          <span class="text-xs text-[var(--color-text-muted)]">{{ row.resolvedLabel }}</span>
        </div>

        <div class="grid grid-cols-3 gap-2">
          <div class="flex flex-col items-center justify-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] px-2 py-2">
            <span class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Soll</span>
            <span
              class="font-mono text-lg font-bold text-[var(--color-text-primary)]"
              :aria-label="`Soll ${row.label}: ${row.sollDisplay}`"
            >
              {{ row.sollDisplay }}
            </span>
          </div>

          <div class="flex flex-col items-center justify-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] px-2 py-2">
            <span class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">IST</span>
            <span
              class="font-mono text-lg font-bold text-[var(--color-text-primary)]"
              :aria-label="`Ist ${row.label}: ${row.istDisplay}`"
            >
              {{ row.istDisplay }}
            </span>
          </div>

          <div class="flex flex-col items-center justify-center gap-1 rounded-[var(--radius-sm)] bg-[var(--color-bg-tertiary)] px-2 py-2">
            <span class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">Δ</span>
            <span
              class="font-mono text-lg font-bold"
              :class="{
                'text-[var(--color-success)]': row.deltaStatus === 'ok',
                'text-[var(--color-warning)]': row.deltaStatus === 'warn',
                'text-[var(--color-text-secondary)]': row.deltaStatus === 'unknown',
              }"
              :aria-label="`Delta ${row.label}: ${row.deltaDisplay}`"
            >
              {{ row.deltaDisplay }}
            </span>
          </div>
        </div>
      </div>

      <p
        v-if="measuredFreshWaterOrigin"
        class="rounded-[var(--radius-sm)] border border-[var(--glass-border)] px-2 py-2 text-xs leading-snug text-[var(--color-text-secondary)]"
        data-testid="tank-ist-soll-measured-freshwater"
        role="status"
        aria-label="Letzter abgeleiteter Messwert aus Mess-Bindung"
      >
        <span class="font-semibold text-[var(--color-success)]">Letzte Messung</span>
        · {{ measuredFreshWaterOrigin }}
      </p>
    </template>
  </div>
</template>

<style scoped>
/* Match MonitorView sensor-card expand transition */
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

.tank-ist-soll-panel__metric--expanded {
  border-color: color-mix(in srgb, var(--color-accent) 35%, var(--glass-border));
}
</style>
