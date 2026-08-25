<script setup lang="ts">
/**
 * PlanTimelineView — konsolidierter Zonen-Zeitstrahl
 *
 * Display-only (AUT-1386): Zone selector, Phasenachse oben, Datumticks unten,
 * Operator-Zeilen Luft / Wasser / Boden / Licht / Pflanze.
 * EC/pH-Sollwerte werden im Nährlösung-Tab gesetzt.
 */

import { ref, computed, watch, onMounted } from 'vue'
import { CalendarRange, RefreshCw } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { useZoneStore } from '@/shared/stores/zone.store'
import { usePlanSegmentsStore } from '@/shared/stores/planSegments.store'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useToast } from '@/composables/useToast'
import { appliedSetpointLogsApi } from '@/api/appliedSetpointLogs'
import { sensorsApi } from '@/api/sensors'
import type { PlantLifecycleEvent } from '@/types'
import type { AppliedSetpointLog } from '@/types/planSegment'
import type {
  PlanMeasureCreatePayload,
  PlanMeasureMarker,
} from '@/components/plan-timeline/planMeasureMarkers'
import PlanMeasureMarkerRow from '@/components/plan-timeline/PlanMeasureMarkerRow.vue'
import {
  buildPastOverlayDelta,
  pastWindowSlice,
  sensorTypeForPlanMeasure,
  type PastOverlayDelta,
} from '@/components/plan-timeline/planPastOverlay'
import BaseToggle from '@/shared/design/primitives/BaseToggle.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import { getPlantEventTypeLabel } from '@/components/plants/plantLabels'
import PlanTimelineAxis from '@/components/plan-timeline/PlanTimelineAxis.vue'
import PlanPhaseAxis from '@/components/plan-timeline/PlanPhaseAxis.vue'
import PlanDomainTrackGrid from '@/components/plan-timeline/PlanDomainTrackGrid.vue'
import PlanMeasureDetailModal from '@/components/plan-timeline/PlanMeasureDetailModal.vue'
import {
  buildFullPlanTimelineWindow,
  buildPlanDomainRows,
} from '@/components/plan-timeline/planTimelineTracks'
import {
  buildPlanCohorts,
  buildCohortPhaseTracks,
} from '@/components/plan-timeline/planCohorts'
import { buildPlannedMeasureMarkers } from '@/components/plan-timeline/planMeasureMarkers'
import { buildVpdOverlayBands } from '@/components/plan-timeline/planVpdOverlay'

const zoneStore = useZoneStore()
const planStore = usePlanSegmentsStore()
const plantsStore = usePlantsStore()
const toast = useToast()

// =============================================================================
// Window — full data range (no preset selector)
// =============================================================================
const nowTick = ref(Date.now())

const timelineWindow = computed(() => {
  const zoneSegs = selectedZoneId.value
    ? planStore.segments.filter((s) => s.zone_id === selectedZoneId.value)
    : planStore.segments
  const eventTimestamps: string[] = []
  for (const events of eventsByPlantId.value.values()) {
    for (const e of events) eventTimestamps.push(e.event_timestamp)
  }
  const plantingDates = zonePlants.value
    .map((p) => p.planting_date)
    .filter((d): d is string => Boolean(d))

  return buildFullPlanTimelineWindow({
    nowMs: nowTick.value,
    segmentFromTs: zoneSegs.map((s) => s.from_ts),
    segmentToTs: zoneSegs.map((s) => s.to_ts),
    eventTimestamps,
    extraTimestamps: plantingDates,
  })
})

// =============================================================================
// Zone selection
// =============================================================================
const selectedZoneId = ref<string>('')

const zoneOptions = computed(() =>
  zoneStore.activeZones
    .slice()
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((z) => ({
      value: z.zone_id,
      label: z.name || z.zone_id,
    })),
)

const hasZones = computed(() => zoneOptions.value.length > 0)

const selectedZoneName = computed(() => {
  const z = zoneStore.activeZones.find((x) => x.zone_id === selectedZoneId.value)
  return z?.name || selectedZoneId.value
})

const zonePlants = computed(() =>
  plantsStore.plants.filter(
    (p) => p.parent_zone_id === selectedZoneId.value && !p.deleted_at,
  ),
)

// =============================================================================
// Lifecycle events per plant (for cohorts + measures)
// =============================================================================
const eventsByPlantId = ref<Map<string, PlantLifecycleEvent[]>>(new Map())
const isLoadingContext = ref(false)

async function loadZonePlantEvents(): Promise<void> {
  const plants = zonePlants.value
  if (!selectedZoneId.value || plants.length === 0) {
    eventsByPlantId.value = new Map()
    return
  }
  isLoadingContext.value = true
  try {
    const next = new Map<string, PlantLifecycleEvent[]>()
    await Promise.all(
      plants.map(async (p) => {
        try {
          const result = await plantsStore.fetchLifecycleEvents(p.plant_id)
          next.set(p.plant_id, result.events ?? [])
        } catch {
          next.set(p.plant_id, [])
        }
      }),
    )
    eventsByPlantId.value = next
  } finally {
    isLoadingContext.value = false
  }
}

const phaseTracks = computed(() => {
  const cohorts = buildPlanCohorts(zonePlants.value, eventsByPlantId.value)
  return buildCohortPhaseTracks(cohorts, eventsByPlantId.value, timelineWindow.value)
})

const allZoneEvents = computed(() => {
  const out: PlantLifecycleEvent[] = []
  for (const events of eventsByPlantId.value.values()) {
    out.push(...events)
  }
  return out
})

const plannedMarkers = computed(() =>
  buildPlannedMeasureMarkers(
    allZoneEvents.value,
    timelineWindow.value,
    getPlantEventTypeLabel,
  ),
)

// =============================================================================
// Past overlay (Ist vs historically applied Soll)
// =============================================================================
const showPastOverlay = ref(true)
const appliedLogs = ref<AppliedSetpointLog[]>([])
const pastDeltaByKey = ref<Map<string, PastOverlayDelta>>(new Map())
const isLoadingOverlay = ref(false)

const domainRows = computed(() => {
  if (!selectedZoneId.value) return []
  return buildPlanDomainRows({
    zoneId: selectedZoneId.value,
    zoneName: selectedZoneName.value,
    segments: planStore.segments,
    window: timelineWindow.value,
    appliedLogs: showPastOverlay.value ? appliedLogs.value : [],
    pastDeltaByKey: showPastOverlay.value ? pastDeltaByKey.value : new Map(),
  })
})

const vpdBands = computed(() => {
  if (!selectedZoneId.value) return []
  return buildVpdOverlayBands(
    planStore.segments,
    selectedZoneId.value,
    timelineWindow.value,
  )
})

// =============================================================================
// Measure detail dialog
// =============================================================================
const detailOpen = ref(false)
const selectedMarker = ref<PlanMeasureMarker | null>(null)

const selectedMarkerPlantLabel = computed(() => {
  if (!selectedMarker.value) return null
  const plant = plantsStore.plants.find(
    (p) => p.plant_id === selectedMarker.value?.plantId,
  )
  if (!plant) return null
  return plant.genotype_label || plant.qr_code || plant.plant_id
})

const selectedMarkerBatchLabel = computed(() => {
  if (!selectedMarker.value) return null
  const plant = plantsStore.plants.find(
    (p) => p.plant_id === selectedMarker.value?.plantId,
  )
  return plant?.batch_label || plant?.batch || null
})

function onSelectMeasure(marker: PlanMeasureMarker): void {
  selectedMarker.value = marker
  detailOpen.value = true
}

const measurePlantId = computed(() => zonePlants.value[0]?.plant_id ?? '')

const measurePlantOptions = computed(() =>
  zonePlants.value.map((p) => ({
    plantId: p.plant_id,
    label: p.genotype_label || p.qr_code || p.plant_id,
  })),
)

async function onCreateMeasure(payload: PlanMeasureCreatePayload): Promise<void> {
  try {
    await plantsStore.addLifecycleEvent(payload.plantId, {
      event_type: payload.eventType,
      note: payload.note,
      event_status: payload.eventStatus,
      event_timestamp: payload.windowStart,
      linked_sensor_window_start: payload.windowStart,
      linked_sensor_window_end: payload.windowEnd,
    })
    await loadZonePlantEvents()
  } catch (e) {
    toast.error(
      e instanceof Error ? e.message : 'Maßnahme konnte nicht gespeichert werden',
    )
  }
}

// =============================================================================
// Load
// =============================================================================
async function loadPastOverlay(): Promise<void> {
  if (!showPastOverlay.value) {
    appliedLogs.value = []
    pastDeltaByKey.value = new Map()
    return
  }
  const slice = pastWindowSlice(timelineWindow.value)
  if (!slice) {
    appliedLogs.value = []
    pastDeltaByKey.value = new Map()
    return
  }

  isLoadingOverlay.value = true
  try {
    const fromIso = new Date(slice.fromMs).toISOString()
    const toIso = new Date(slice.toMs).toISOString()
    appliedLogs.value = await appliedSetpointLogsApi.list({
      from_ts: fromIso,
      to_ts: toIso,
      limit: 2000,
      zone_id: selectedZoneId.value || undefined,
    })

    const keys = new Set<string>()
    for (const seg of planStore.segments) {
      if (selectedZoneId.value && seg.zone_id !== selectedZoneId.value) continue
      keys.add(`${seg.zone_id}::${seg.domain}::${seg.measure}`)
    }
    for (const log of appliedLogs.value) {
      keys.add(`${log.zone_id}::${log.domain}::${log.measure}`)
    }

    const next = new Map<string, PastOverlayDelta>()
    await Promise.all(
      [...keys].map(async (key) => {
        const [zoneId, domain, measure] = key.split('::')
        const sensorType = sensorTypeForPlanMeasure(measure)
        let istReadings: Array<number | null | undefined> = []
        if (sensorType) {
          try {
            const res = await sensorsApi.queryData({
              zone_id: zoneId,
              sensor_type: sensorType,
              start_time: fromIso,
              end_time: toIso,
              limit: 200,
              resolution: '1h',
            })
            istReadings = (res.readings ?? []).map(
              (r) => r.processed_value ?? r.raw_value,
            )
          } catch {
            istReadings = []
          }
        }
        next.set(
          key,
          buildPastOverlayDelta({
            logs: appliedLogs.value,
            zoneId,
            domain,
            measure,
            fromMs: slice.fromMs,
            toMs: slice.toMs,
            istReadings,
          }),
        )
      }),
    )
    pastDeltaByKey.value = next
  } catch (e) {
    appliedLogs.value = []
    pastDeltaByKey.value = new Map()
    toast.error(
      e instanceof Error
        ? e.message
        : 'Anwendungs-Protokoll konnte nicht geladen werden',
    )
  } finally {
    isLoadingOverlay.value = false
  }
}

async function reload(): Promise<void> {
  nowTick.value = Date.now()
  // Load full zone plan (no time filter) — window is derived from data.
  await planStore.fetchSegments({
    zone_id: selectedZoneId.value || undefined,
  })
  await loadZonePlantEvents()
  nowTick.value = Date.now()
  await loadPastOverlay()
}

function ensureZoneSelection(): void {
  if (
    selectedZoneId.value &&
    zoneOptions.value.some((z) => z.value === selectedZoneId.value)
  ) {
    return
  }
  selectedZoneId.value = zoneOptions.value[0]?.value ?? ''
}

onMounted(async () => {
  if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
    await zoneStore.fetchZoneEntities()
  }
  if (plantsStore.plants.length === 0 && !plantsStore.isLoading) {
    await plantsStore.fetchPlants()
  }
  ensureZoneSelection()
  await reload()
})

watch(showPastOverlay, () => {
  void loadPastOverlay()
})

watch(selectedZoneId, () => {
  void reload()
})

watch(
  () => zoneStore.activeZones.map((z) => z.zone_id).join(','),
  () => {
    ensureZoneSelection()
  },
)
</script>

<template>
  <div class="plan-view">
    <header class="plan-toolbar glass-panel">
      <div class="plan-toolbar__brand">
        <CalendarRange class="plan-toolbar__icon" aria-hidden="true" />
        <div class="plan-toolbar__titles">
          <h1 class="plan-toolbar__title">Planungs-Zeitstrahl</h1>
          <p class="plan-toolbar__sub">Gesamter Planungszeitraum der Zone</p>
        </div>
      </div>

      <BaseSelect
        v-model="selectedZoneId"
        :options="zoneOptions"
        placeholder="Zone wählen"
        aria-label="Zone für Zeitstrahl"
        class="plan-toolbar__zone"
      />

      <div
        v-if="selectedZoneId"
        class="plan-toolbar__meta"
        aria-label="Zonen-Zusammenfassung"
      >
        <span class="plan-toolbar__chip">{{ zonePlants.length }} Pflanzen</span>
        <span class="plan-toolbar__chip">
          {{ phaseTracks.length }} Phasen-Spur{{ phaseTracks.length === 1 ? '' : 'en' }}
        </span>
        <span
          v-if="showPastOverlay"
          class="plan-toolbar__chip plan-toolbar__chip--muted"
        >
          hist. {{ appliedLogs.length }}
          <template v-if="isLoadingOverlay">…</template>
        </span>
        <span
          v-if="planStore.segments.length === 0"
          class="plan-toolbar__chip plan-toolbar__chip--warn"
        >
          keine Segmente
        </span>
      </div>

      <div class="plan-toolbar__actions">
        <RouterLink
          :to="{ name: 'nutrient-solution' }"
          class="plan-toolbar__link"
        >
          Nährlösung
        </RouterLink>

        <label
          class="plan-overlay-toggle"
          title="Ist-Telemetrie gegen den damals geltenden Sollwert aus dem Anwendungs-Protokoll"
        >
          <BaseToggle
            :model-value="showPastOverlay"
            size="sm"
            aria-label="Vergangenheits-Überlagerung"
            @update:model-value="(v: boolean) => { showPastOverlay = v }"
          />
          <span class="plan-overlay-toggle__label">Vergangenheit</span>
        </label>

        <button
          type="button"
          class="plan-btn plan-btn--ghost"
          aria-label="Daten neu laden"
          @click="reload"
        >
          <RefreshCw
            class="w-4 h-4"
            :class="{
              'plan-spin':
                planStore.isLoading ||
                planStore.isMutating ||
                isLoadingOverlay ||
                isLoadingContext,
            }"
          />
          <span class="plan-btn__text">Aktualisieren</span>
        </button>
      </div>
    </header>

    <div v-if="planStore.isLoading && domainRows.length === 0" class="plan-state">
      Lade Planungs-Zeitstrahl...
    </div>
    <div v-else-if="planStore.error" class="plan-state plan-state--warn">
      Plan-Segmente: {{ planStore.error }}
    </div>

    <template v-if="!hasZones">
      <div class="plan-state">
        <CalendarRange class="w-8 h-8 plan-state__icon" aria-hidden="true" />
        <p>Keine aktiven Zonen vorhanden.</p>
        <p class="plan-state__sub">
          Lege zuerst Zonen an — der Zeitstrahl zeigt die Planung einer Zone.
        </p>
      </div>
    </template>

    <template v-else-if="selectedZoneId">
      <section class="plan-chart glass-panel" aria-label="Zonen-Zeitstrahl">
        <div v-if="isLoadingContext" class="plan-state plan-state--inline">
          Lade Phasen und Maßnahmen...
        </div>
        <template v-else>
          <PlanPhaseAxis
            :tracks="phaseTracks"
            :window="timelineWindow"
            :empty-hint="
              zonePlants.length === 0
                ? 'Keine Pflanzen in dieser Zone'
                : 'keine Licht-/Wachstumsphasen erfasst'
            "
          />

          <PlanMeasureMarkerRow
            :markers="plannedMarkers"
            :window="timelineWindow"
            :plant-id="measurePlantId"
            :plants="measurePlantOptions"
            :disabled="zonePlants.length === 0"
            @create="onCreateMeasure"
            @select="onSelectMeasure"
          />

          <PlanDomainTrackGrid
            :rows="domainRows"
            :window="timelineWindow"
            :markers="plannedMarkers"
            :vpd-bands="vpdBands"
            @select-measure="onSelectMeasure"
          />

          <div class="plan-chart__axis">
            <div class="plan-chart__gutter" aria-hidden="true" />
            <PlanTimelineAxis :window="timelineWindow" />
          </div>
        </template>
      </section>
    </template>

    <PlanMeasureDetailModal
      v-model:open="detailOpen"
      :marker="selectedMarker"
      :plant-label="selectedMarkerPlantLabel"
      :batch-label="selectedMarkerBatchLabel"
    />
  </div>
</template>

<style scoped>
.plan-view {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  width: 100%;
  max-width: none;
  margin: 0;
  box-sizing: border-box;
}

.plan-toolbar {
  display: grid;
  grid-template-columns: auto minmax(220px, 1.2fr) minmax(0, 1.4fr) auto;
  align-items: center;
  gap: var(--space-3) var(--space-4);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  animation: plan-toolbar-in 280ms ease-out;
}

@keyframes plan-toolbar-in {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.plan-toolbar__brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.plan-toolbar__icon {
  width: 1.35rem;
  height: 1.35rem;
  color: var(--color-iridescent-1);
  flex-shrink: 0;
}

.plan-toolbar__titles {
  display: flex;
  flex-direction: column;
  gap: 1px;
  min-width: 0;
}

.plan-toolbar__title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--color-text-primary);
  line-height: 1.2;
  white-space: nowrap;
}

.plan-toolbar__sub {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.plan-toolbar__zone {
  width: 100%;
  min-width: 0;
}

.plan-toolbar__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.plan-toolbar__chip {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(96, 165, 250, 0.06);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.plan-toolbar__chip--muted {
  background: transparent;
  color: var(--color-text-muted);
}

.plan-toolbar__chip--warn {
  border-color: rgba(251, 191, 36, 0.35);
  background: rgba(251, 191, 36, 0.08);
  color: var(--color-warning);
}

.plan-toolbar__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-2);
}

.plan-toolbar__link {
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(96, 165, 250, 0.35);
  background: rgba(96, 165, 250, 0.08);
  color: var(--color-accent);
  font-size: var(--text-xs);
  font-weight: 600;
  text-decoration: none;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.plan-toolbar__link:hover {
  border-color: var(--color-accent);
  background: rgba(96, 165, 250, 0.14);
}

.plan-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  border-radius: var(--radius-md);
  cursor: pointer;
  border: 1px solid var(--glass-border);
  min-height: 44px;
}

.plan-btn--ghost {
  background: transparent;
  color: var(--color-text-secondary);
}

.plan-btn--ghost:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.03);
}

.plan-overlay-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
  min-height: 44px;
}

.plan-spin {
  animation: plan-spin 0.8s linear infinite;
}

@keyframes plan-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 1100px) {
  .plan-toolbar {
    grid-template-columns: 1fr 1fr;
  }

  .plan-toolbar__brand {
    grid-column: 1 / -1;
  }

  .plan-toolbar__actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .plan-toolbar {
    grid-template-columns: 1fr;
  }
}

.plan-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-6);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
}

.plan-state--inline {
  padding: var(--space-4);
}

.plan-state--warn {
  color: var(--color-warning);
  border-color: rgba(251, 191, 36, 0.35);
  background: rgba(251, 191, 36, 0.06);
}

.plan-state__icon {
  opacity: 0.4;
}

.plan-state__sub {
  font-size: var(--text-xs);
  max-width: 420px;
}

.plan-chart {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-md);
}

.plan-chart__axis {
  display: grid;
  grid-template-columns: minmax(88px, 120px) 1fr;
  gap: var(--space-3);
  align-items: center;
  margin-top: var(--space-1);
}

.plan-chart__gutter {
  min-width: 0;
}
</style>
