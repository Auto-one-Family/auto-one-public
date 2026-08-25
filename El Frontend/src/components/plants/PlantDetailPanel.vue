<script setup lang="ts">
/**
 * PlantDetailPanel — SlideOver detail view for a single plant.
 *
 * Sections:
 *   1) Stammdaten + QR-Label download + Phase wechseln
 *   2) Lifecycle-Events Zeitstrahl + Notiz hinzufügen
 *   3) MultispeQ-Verlauf (Phi2 Scatter-Chart)
 *   4) Audit-Trail
 *
 * Data sources:
 *   - GET  /v1/plants/{id}                  → plant + lifecycle_events + audit_logs
 *   - GET  /v1/plants/{id}/measurements     → Phi2 / Fv-Fm time series
 *   - POST /v1/plants/{id}/lifecycle-event  → add note
 *
 * AUT-1178: plant_id (server PK), genotype_label, batch_label aligned.
 *
 * Used inside SensorsView Pflanzen-Tab (AUT-221).
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { Scatter } from 'vue-chartjs'
import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  Tooltip,
  Legend,
  TimeScale,
} from 'chart.js'
import 'chartjs-adapter-date-fns'
import { Printer, RefreshCw, MessageSquarePlus, Pencil, Beaker } from 'lucide-vue-next'
import { plantsApi } from '@/api/plants'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { planSegmentsApi } from '@/api/planSegments'
import { useToast } from '@/composables/useToast'
import type { PlanSegment } from '@/types/planSegment'
import { AccordionSection, BaseBadge } from '@/shared/design/primitives'
import { datetimeLocalValueToIso, formatRelativeTime, toDatetimeLocalValue } from '@/utils/formatters'
import DateDisplay from '@/components/base/DateDisplay.vue'
import {
  PLANT_PHASE_LABELS,
  TANK_INCIDENT_LABEL,
  formatTankIncidentSummary,
  getPlantEventStatusLabel,
  getPlantEventTypeLabel,
} from '@/components/plants/plantLabels'
import PlantPhaseChangeModal from '@/components/plants/PlantPhaseChangeModal.vue'
import PlantCreateModal from '@/components/plants/PlantCreateModal.vue'
import PlantPhaseTimeline from '@/components/plants/PlantPhaseTimeline.vue'
import { NUTRIENT_PHASES, PLANT_PHASES } from '@/types'
import type {
  Plant,
  PlantEventStatus,
  PlantLifecycleEvent,
  PlantLifecycleEventStatusUpdate,
  PlantMeasurement,
  PlantPhase,
  PlantTankIncidentEvent,
} from '@/types'

ChartJS.register(LinearScale, PointElement, Tooltip, Legend, TimeScale)

interface Props {
  plant: Plant
}

const props = defineProps<Props>()

const plantsStore = usePlantsStore()
const toast = useToast()

/** Zone climate plan_segments for Raumklima In-Phase layer (AUT-1240). */
const plantClimateSegments = ref<PlanSegment[]>([])

// =============================================================================
// Detail data — refresh whenever the panel switches plants
// =============================================================================
const detail = ref<Plant | null>(null)
const measurements = ref<PlantMeasurement[]>([])
const isLoadingDetail = ref(false)
const isLoadingMeasurements = ref(false)
const isDownloadingQR = ref(false)

const showPhaseModal = ref(false)
/** AUT-1182: controls the Stammdaten-Bearbeiten modal */
const showEditModal = ref(false)
const noteInput = ref('')
/**
 * AUT-1204: actual event timestamp for a manually added note, editable so
 * an operator can backdate an observation. Vorbelegt mit "jetzt".
 */
const noteEventTimestamp = ref(toDatetimeLocalValue())
const isAddingNote = ref(false)

/**
 * Lifecycle events loaded from the dedicated endpoint.
 *
 * AUT-1181 (Befund 2): the plant detail endpoint does NOT return an embedded
 * lifecycle_events array.  We fetch them separately and store them here.
 */
const loadedLifecycleEvents = ref<PlantLifecycleEvent[]>([])

/**
 * AUT-1211: system-wide tank incidents affecting this plant via its
 * subzone/tank assignment. Rendered in the same timeline as
 * loadedLifecycleEvents but visually marked (TANK_INCIDENT_LABEL) — never
 * merged into the plant-event data itself.
 */
const loadedTankIncidents = ref<PlantTankIncidentEvent[]>([])

async function loadDetail(plantId: string): Promise<void> {
  isLoadingDetail.value = true
  try {
    detail.value = await plantsStore.fetchPlantDetail(plantId)
    await loadClimateSegments(detail.value?.parent_zone_id ?? props.plant.parent_zone_id)
  } finally {
    isLoadingDetail.value = false
  }
}

async function loadLifecycleEvents(plantId: string): Promise<void> {
  try {
    const result = await plantsStore.fetchLifecycleEvents(plantId)
    loadedLifecycleEvents.value = result.events
    loadedTankIncidents.value = result.tankIncidents
  } catch {
    // Non-fatal: timeline stays empty, user can retry via reload
    loadedLifecycleEvents.value = []
    loadedTankIncidents.value = []
  }
}

async function loadMeasurements(plantId: string): Promise<void> {
  isLoadingMeasurements.value = true
  try {
    measurements.value = await plantsStore.fetchMeasurements(plantId, 90)
  } finally {
    isLoadingMeasurements.value = false
  }
}

async function loadClimateSegments(zoneId: string | null | undefined): Promise<void> {
  if (!zoneId) {
    plantClimateSegments.value = []
    return
  }
  try {
    // Direct API — do not overwrite planSegments store used by PlanTimelineView
    const rows = await planSegmentsApi.list({ zone_id: zoneId, domain: 'climate' })
    plantClimateSegments.value = rows.filter(
      (s) => s.zone_id === zoneId && s.domain === 'climate',
    )
  } catch {
    plantClimateSegments.value = []
  }
}

watch(
  () => props.plant.plant_id,
  (id) => {
    if (id) {
      void loadDetail(id)
      void loadMeasurements(id)
      // AUT-1181: load lifecycle events via dedicated endpoint
      void loadLifecycleEvents(id)
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  detail.value = null
  measurements.value = []
  loadedLifecycleEvents.value = []
  loadedTankIncidents.value = []
  plantClimateSegments.value = []
})

// =============================================================================
// Section 1 — Stammdaten
// =============================================================================
const currentPlant = computed<Plant>(() => detail.value ?? props.plant)

const phaseLabel = computed(() => {
  const phase = currentPlant.value.phase as PlantPhase
  return PLANT_PHASE_LABELS[phase] ?? currentPlant.value.phase
})

/** AUT-1183: nutrient/fertilizer phase axis label, null when not yet set. */
const nutrientPhaseLabel = computed<string | null>(() => {
  const np = currentPlant.value.nutrient_phase as PlantPhase | null | undefined
  if (!np) return null
  return PLANT_PHASE_LABELS[np] ?? np
})

const ageDays = computed<number | null>(() => {
  const date = currentPlant.value.planting_date
  if (!date) return null
  const planted = Date.parse(date)
  if (Number.isNaN(planted)) return null
  return Math.max(0, Math.floor((Date.now() - planted) / (1000 * 60 * 60 * 24)))
})

async function downloadQR(): Promise<void> {
  isDownloadingQR.value = true
  try {
    await plantsApi.downloadQRCode(
      currentPlant.value.plant_id,
      `${currentPlant.value.qr_code || 'plant-' + currentPlant.value.plant_id}.png`,
    )
    toast.success('QR-Label heruntergeladen')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'QR-Download fehlgeschlagen')
  } finally {
    isDownloadingQR.value = false
  }
}

function onPhaseChanged(): void {
  // Reload detail (phase field) + lifecycle events (new phase_changed entry)
  const plantId = currentPlant.value.plant_id
  void loadDetail(plantId)
  void loadLifecycleEvents(plantId)
}

/**
 * AUT-1182: called after a successful PATCH update from the edit modal.
 * Reloads the plant detail so the Stammdaten section reflects the corrected values.
 */
function onEditUpdated(): void {
  const plantId = currentPlant.value.plant_id
  void loadDetail(plantId)
}

// =============================================================================
// Section 2 — Lifecycle-Events
// =============================================================================

/**
 * AUT-1181 (Befund 2 + 4): events come from the dedicated endpoint loaded
 * into loadedLifecycleEvents (not from the plant detail response).
 *
 * AUT-1181 (Befund 5): sorted by event_timestamp DESC so backdated events
 * appear at the chronologically correct position in the timeline.
 */
const sortedEvents = computed<PlantLifecycleEvent[]>(() =>
  [...loadedLifecycleEvents.value].sort(
    (a, b) => Date.parse(b.event_timestamp) - Date.parse(a.event_timestamp),
  ),
)

/**
 * AUT-1211: unified, chronologically sorted timeline entries — real
 * per-plant events plus tank-wide incidents in the same list, tagged by
 * `kind` so the template can render the incident branch with its own
 * label/icon instead of the revert/edit-capable event branch.
 */
type PlantTimelineEntry =
  | { kind: 'plant_event'; timestamp: string; event: PlantLifecycleEvent }
  | { kind: 'tank_incident'; timestamp: string; incident: PlantTankIncidentEvent }

const sortedTimelineEntries = computed<PlantTimelineEntry[]>(() => {
  const entries: PlantTimelineEntry[] = [
    ...sortedEvents.value.map((event) => ({
      kind: 'plant_event' as const,
      timestamp: event.event_timestamp,
      event,
    })),
    ...loadedTankIncidents.value.map((incident) => ({
      kind: 'tank_incident' as const,
      timestamp: incident.occurred_at,
      incident,
    })),
  ]
  return entries.sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
})

async function addNote(): Promise<void> {
  const text = noteInput.value.trim()
  if (!text) {
    toast.warning('Bitte eine Notiz eingeben')
    return
  }
  // AUT-1204: client-side mirror of the server's future-timestamp guard
  // (schemas/plant.py validate_event_timestamp).
  const eventTimestampIso = datetimeLocalValueToIso(noteEventTimestamp.value)
  if (eventTimestampIso === null) {
    toast.error('Ereigniszeitpunkt ist ungültig')
    return
  }
  if (Date.parse(eventTimestampIso) > Date.now() + 60_000) {
    toast.error('Ereigniszeitpunkt darf nicht in der Zukunft liegen')
    return
  }
  isAddingNote.value = true
  try {
    await plantsStore.addLifecycleEvent(currentPlant.value.plant_id, {
      // AUT-1204: 'note' is not a valid event_type (canonical value is
      // 'note_added', see LIFECYCLE_EVENT_TYPES) — every submission failed
      // with HTTP 422 before this fix.
      event_type: 'note_added',
      note: text,
      event_timestamp: eventTimestampIso,
    })
    noteInput.value = ''
    noteEventTimestamp.value = toDatetimeLocalValue()
    toast.success('Notiz gespeichert')
    const plantId = currentPlant.value.plant_id
    // AUT-1181: reload both plant detail and lifecycle events (separate endpoints)
    await Promise.all([loadDetail(plantId), loadLifecycleEvents(plantId)])
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Notiz konnte nicht gespeichert werden')
  } finally {
    isAddingNote.value = false
  }
}

/**
 * AUT-1207: badge color per truth status. 'occurred' never reaches this
 * (getPlantEventStatusLabel returns null and hides the badge).
 */
function eventStatusBadgeVariant(status: PlantEventStatus): 'info' | 'danger' | 'gray' {
  if (status === 'planned') return 'info'
  if (status === 'reverted') return 'danger'
  return 'gray' // test_data
}

// --- Zurücknehmen (AUT-1207) ---------------------------------------------
const revertingEventId = ref<string | null>(null)
const revertReason = ref('')
const isRevertingEvent = ref(false)

function startRevert(eventId: string): void {
  cancelEdit()
  revertingEventId.value = eventId
  revertReason.value = ''
}

function cancelRevert(): void {
  revertingEventId.value = null
  revertReason.value = ''
}

async function confirmRevert(eventId: string): Promise<void> {
  const reason = revertReason.value.trim()
  if (!reason) {
    toast.warning('Bitte eine Begründung eingeben')
    return
  }
  isRevertingEvent.value = true
  try {
    await plantsStore.updateLifecycleEventStatus(currentPlant.value.plant_id, eventId, {
      event_status: 'reverted',
      reason,
    })
    toast.success('Ereignis zurückgenommen')
    revertingEventId.value = null
    revertReason.value = ''
    const plantId = currentPlant.value.plant_id
    await Promise.all([loadDetail(plantId), loadLifecycleEvents(plantId)])
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Zurücknahme fehlgeschlagen')
  } finally {
    isRevertingEvent.value = false
  }
}

// --- Bearbeiten (AUT-1208) --------------------------------------------------
const PHASE_AXIS_EVENT_TYPES = ['phase_changed', 'nutrient_phase_changed'] as const

const editingEventId = ref<string | null>(null)
// Snapshot of the datetime-local value at open time, at the SAME (minute)
// precision as the editable field — comparing against this instead of the
// original ISO string avoids a false "changed" on every save purely from
// the datetime-local input's minute-level rounding (event_timestamp from
// the server carries seconds/microseconds).
const editOriginalTimestamp = ref('')
const editTimestamp = ref('')
const editNotes = ref('')
const editEventType = ref('')
const editNewPhase = ref<PlantPhase | ''>('')
const editReason = ref('')
const isSavingEdit = ref(false)

function startEdit(event: PlantLifecycleEvent): void {
  cancelRevert()
  editingEventId.value = event.event_id
  editOriginalTimestamp.value = toDatetimeLocalValue(new Date(event.event_timestamp))
  editTimestamp.value = editOriginalTimestamp.value
  editNotes.value = event.notes ?? ''
  editEventType.value = event.event_type
  editNewPhase.value = (event.new_phase as PlantPhase) ?? ''
  editReason.value = ''
}

function cancelEdit(): void {
  editingEventId.value = null
  editReason.value = ''
}

async function confirmEdit(event: PlantLifecycleEvent): Promise<void> {
  const reason = editReason.value.trim()
  if (!reason) {
    toast.warning('Bitte eine Begründung eingeben')
    return
  }

  // Only send fields that actually changed — keeps the audit trail precise
  // and avoids "touching" fields the operator did not intend to change.
  const update: PlantLifecycleEventStatusUpdate = { reason }

  if (editTimestamp.value !== editOriginalTimestamp.value) {
    const timestampIso = datetimeLocalValueToIso(editTimestamp.value)
    if (timestampIso === null) {
      toast.warning('Ereigniszeitpunkt ist ungültig.')
      return
    }
    if (Date.parse(timestampIso) > Date.now() + 60_000) {
      toast.warning('Ereigniszeitpunkt darf nicht in der Zukunft liegen.')
      return
    }
    update.event_timestamp = timestampIso
  }
  if (editNotes.value !== (event.notes ?? '')) {
    update.notes = editNotes.value
  }
  if (editEventType.value !== event.event_type) {
    update.event_type = editEventType.value
  }
  const targetType = editEventType.value
  if (
    (PHASE_AXIS_EVENT_TYPES as readonly string[]).includes(targetType) &&
    editNewPhase.value &&
    editNewPhase.value !== event.new_phase
  ) {
    update.new_phase = editNewPhase.value
  }

  if (Object.keys(update).length === 1) {
    toast.warning('Keine Änderung erkannt')
    return
  }

  isSavingEdit.value = true
  try {
    await plantsStore.updateLifecycleEventStatus(currentPlant.value.plant_id, event.event_id, update)
    toast.success('Ereignis korrigiert')
    editingEventId.value = null
    editReason.value = ''
    const plantId = currentPlant.value.plant_id
    await Promise.all([loadDetail(plantId), loadLifecycleEvents(plantId)])
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Korrektur fehlgeschlagen')
  } finally {
    isSavingEdit.value = false
  }
}

// =============================================================================
// Section 3 — MultispeQ Phi2 Scatter chart
// =============================================================================
interface Phi2Point {
  x: number
  y: number
}

const phi2ChartData = computed(() => {
  const points: Phi2Point[] = []
  for (const m of measurements.value) {
    const ts = Date.parse(m.timestamp)
    if (Number.isNaN(ts)) continue
    const value = m.phi2 ?? m.sensor_values?.phi2
    if (typeof value !== 'number' || !Number.isFinite(value)) continue
    points.push({ x: ts, y: value })
  }
  return {
    datasets: [
      {
        label: 'Phi2',
        data: points,
        backgroundColor: 'rgba(96, 165, 250, 0.7)',
        borderColor: 'rgba(96, 165, 250, 1)',
        pointRadius: 4,
        pointHoverRadius: 6,
      },
    ],
  }
})

const phi2HasData = computed(() => phi2ChartData.value.datasets[0].data.length > 0)

const phi2ChartOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  scales: {
    x: {
      type: 'time' as const,
      time: { tooltipFormat: 'dd.MM.yyyy HH:mm' },
      ticks: { color: 'rgba(176, 176, 192, 0.7)' },
      grid: { color: 'rgba(255, 255, 255, 0.04)' },
    },
    y: {
      min: 0,
      max: 1,
      ticks: { color: 'rgba(176, 176, 192, 0.7)' },
      grid: { color: 'rgba(255, 255, 255, 0.04)' },
      title: { display: true, text: 'Phi2', color: 'rgba(176, 176, 192, 0.9)' },
    },
  },
  plugins: {
    legend: { display: false },
    tooltip: {
      callbacks: {
        label: (ctx: { parsed: { y: number | null } }): string => {
          const y = ctx.parsed.y
          return typeof y === 'number' ? `Phi2: ${y.toFixed(3)}` : 'Phi2: —'
        },
      },
    },
  },
}))

const lastPhi2 = computed<{ value: number; at: string } | null>(() => {
  const points = [...measurements.value]
    .filter((m) => {
      const v = m.phi2 ?? m.sensor_values?.phi2
      return typeof v === 'number' && Number.isFinite(v)
    })
    .sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp))
  if (points.length === 0) return null
  const first = points[0]
  const value = (first.phi2 ?? first.sensor_values?.phi2) as number
  return { value, at: first.timestamp }
})

// =============================================================================
// Section 4 — Audit-Trail
// =============================================================================
const auditLogs = computed(() => currentPlant.value.audit_logs ?? [])

// =============================================================================
// Lifecycle
// =============================================================================
onMounted(() => {
  // Initial load handled by the immediate watcher above.
})
</script>

<template>
  <div class="plant-detail">
    <!-- ────────────────────────────────────────────────────────────
         Section 1 — Stammdaten
         ──────────────────────────────────────────────────────────── -->
    <div class="plant-detail__section">
      <div class="plant-detail__header-row">
        <div>
          <div class="plant-detail__qr-label">QR-Code</div>
          <div class="plant-detail__qr-value">{{ currentPlant.qr_code || '—' }}</div>
        </div>
        <button
          type="button"
          class="plant-detail__action-btn"
          :disabled="isDownloadingQR"
          @click="downloadQR"
        >
          <Printer class="w-4 h-4" />
          <span>{{ isDownloadingQR ? 'Wird geladen...' : 'QR-Label drucken' }}</span>
        </button>
      </div>

      <dl class="plant-detail__info-grid">
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Genotyp</dt>
          <dd class="plant-detail__info-value">{{ currentPlant.genotype_label }}</dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Charge</dt>
          <dd class="plant-detail__info-value">{{ currentPlant.batch_label || '—' }}</dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Phase (Licht)</dt>
          <dd class="plant-detail__info-value plant-detail__info-value--primary">
            {{ phaseLabel }}
          </dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Phase (Nährstoff)</dt>
          <dd
            class="plant-detail__info-value"
            :class="{ 'plant-detail__info-value--primary': nutrientPhaseLabel !== null }"
          >
            {{ nutrientPhaseLabel ?? '—' }}
          </dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Alter</dt>
          <dd class="plant-detail__info-value">
            {{ ageDays !== null ? `${ageDays} Tage` : '—' }}
          </dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">External-ID</dt>
          <dd class="plant-detail__info-value plant-detail__info-value--mono">
            {{ currentPlant.external_plant_id || '—' }}
          </dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Letztes Phi2</dt>
          <dd class="plant-detail__info-value">
            <template v-if="lastPhi2">
              {{ lastPhi2.value.toFixed(3) }}
              <span class="plant-detail__hint">({{ formatRelativeTime(lastPhi2.at) }})</span>
            </template>
            <template v-else>—</template>
          </dd>
        </div>
      </dl>

      <!-- action row: phase change + Stammdaten edit -->
      <div class="plant-detail__action-row">
        <button
          type="button"
          class="plant-detail__action-btn plant-detail__action-btn--ghost"
          @click="showPhaseModal = true"
        >
          <RefreshCw class="w-4 h-4" />
          <span>Phase wechseln</span>
        </button>
        <button
          type="button"
          class="plant-detail__action-btn plant-detail__action-btn--ghost"
          @click="showEditModal = true"
        >
          <Pencil class="w-4 h-4" />
          <span>Stammdaten bearbeiten</span>
        </button>
      </div>
    </div>

    <!-- ────────────────────────────────────────────────────────────
         Section 2 — Lifecycle-Events
         ──────────────────────────────────────────────────────────── -->
    <AccordionSection title="Lifecycle-Events" storage-key="ao-plant-events">
      <div v-if="isLoadingDetail" class="plant-detail__hint">
        Lade Ereignisse...
      </div>
      <div v-else-if="sortedTimelineEntries.length === 0" class="plant-detail__hint">
        Noch keine Ereignisse erfasst.
      </div>
      <ul v-else class="plant-events">
        <li
          v-for="entry in sortedTimelineEntries"
          :key="entry.kind === 'plant_event' ? entry.event.event_id : entry.incident.id"
          class="plant-events__item"
          :class="{ 'plant-events__item--reverted': entry.kind === 'plant_event' && entry.event.event_status === 'reverted' }"
        >
          <!-- AUT-1211: tank-wide system incident — own label/icon, no per-plant revert/edit (not a plant_lifecycle_events row) -->
          <template v-if="entry.kind === 'tank_incident'">
            <DateDisplay class="plant-events__date" :date="entry.incident.occurred_at" format="absolute" />
            <BaseBadge variant="orange" size="xs">
              <Beaker class="w-3 h-3" />
              {{ TANK_INCIDENT_LABEL }}
            </BaseBadge>
            <span class="plant-events__note">{{ formatTankIncidentSummary(entry.incident) }}</span>
          </template>
          <template v-else>
            <!-- AUT-1181: show event_timestamp (backfill-aware), not created_at -->
            <DateDisplay class="plant-events__date" :date="entry.event.event_timestamp" format="absolute" />
            <span class="plant-events__type">{{ getPlantEventTypeLabel(entry.event.event_type) }}</span>
            <!-- AUT-1207: status badge — 'occurred' (default) gets no badge -->
            <BaseBadge
              v-if="getPlantEventStatusLabel(entry.event.event_status)"
              :variant="eventStatusBadgeVariant(entry.event.event_status)"
              size="xs"
            >
              {{ getPlantEventStatusLabel(entry.event.event_status) }}
            </BaseBadge>
            <!-- AUT-1181: server field is notes (plural) -->
            <span v-if="entry.event.notes" class="plant-events__note">{{ entry.event.notes }}</span>
            <span v-if="entry.event.status_reason" class="plant-events__status-reason">
              „{{ entry.event.status_reason }}“
            </span>
            <!-- AUT-1208: last-correction marker — the change trail itself lives in the audit log -->
            <span v-if="entry.event.status_changed_at" class="plant-events__status-reason">
              Zuletzt geändert: <DateDisplay :date="entry.event.status_changed_at" format="relative" />
            </span>

            <!-- AUT-1207: revert action, only for still-'occurred' events -->
            <button
              v-if="entry.event.event_status === 'occurred' && revertingEventId !== entry.event.event_id && editingEventId !== entry.event.event_id"
              type="button"
              class="plant-events__revert-btn"
              @click="startRevert(entry.event.event_id)"
            >
              Zurücknehmen
            </button>
            <!-- AUT-1208: edit action — not on already-reverted events (server rejects content corrections there) -->
            <button
              v-if="entry.event.event_status !== 'reverted' && editingEventId !== entry.event.event_id && revertingEventId !== entry.event.event_id"
              type="button"
              class="plant-events__revert-btn"
              @click="startEdit(entry.event)"
            >
              Bearbeiten
            </button>

            <div v-if="revertingEventId === entry.event.event_id" class="plant-events__revert-form">
              <textarea
                v-model="revertReason"
                class="plant-events__textarea"
                placeholder="Begründung (Pflicht) — warum wird dieses Ereignis zurückgenommen?"
                rows="2"
              />
              <div class="plant-events__revert-actions">
                <button
                  type="button"
                  class="plant-detail__action-btn plant-detail__action-btn--ghost"
                  :disabled="isRevertingEvent"
                  @click="cancelRevert"
                >
                  Abbrechen
                </button>
                <button
                  type="button"
                  class="plant-detail__action-btn plant-detail__action-btn--primary"
                  :disabled="isRevertingEvent || !revertReason.trim()"
                  @click="confirmRevert(entry.event.event_id)"
                >
                  {{ isRevertingEvent ? 'Wird gespeichert...' : 'Zurücknahme bestätigen' }}
                </button>
              </div>
            </div>

            <!-- AUT-1208: field-level correction form — timestamp/notes always,
                 event_type + new_phase only for the two phase axes (the
                 demonstrated real case is fixing a wrong-axis event; a
                 generic "any of 17 event types" selector would invite scope
                 the issue never asked for). -->
            <div v-if="editingEventId === entry.event.event_id" class="plant-events__revert-form">
              <label class="plant-events__label">
                Ereigniszeitpunkt
                <input
                  v-model="editTimestamp"
                  type="datetime-local"
                  class="plant-events__textarea"
                  :max="toDatetimeLocalValue()"
                />
              </label>
              <label class="plant-events__label">
                Notiz
                <textarea v-model="editNotes" class="plant-events__textarea" rows="2" />
              </label>
              <label v-if="PHASE_AXIS_EVENT_TYPES.includes(entry.event.event_type as typeof PHASE_AXIS_EVENT_TYPES[number])" class="plant-events__label">
                Achse
                <select v-model="editEventType" class="plant-events__textarea">
                  <option value="phase_changed">{{ getPlantEventTypeLabel('phase_changed') }}</option>
                  <option value="nutrient_phase_changed">{{ getPlantEventTypeLabel('nutrient_phase_changed') }}</option>
                </select>
              </label>
              <label v-if="PHASE_AXIS_EVENT_TYPES.includes(editEventType as typeof PHASE_AXIS_EVENT_TYPES[number])" class="plant-events__label">
                Phasenwert
                <!-- AUT-1209: nutrient axis has its own value list (diverged from PLANT_PHASES) -->
                <select v-model="editNewPhase" class="plant-events__textarea">
                  <option
                    v-for="phase in editEventType === 'nutrient_phase_changed' ? NUTRIENT_PHASES : PLANT_PHASES"
                    :key="phase"
                    :value="phase"
                  >
                    {{ PLANT_PHASE_LABELS[phase] }}
                  </option>
                </select>
              </label>
              <textarea
                v-model="editReason"
                class="plant-events__textarea"
                placeholder="Begründung (Pflicht) — was war falsch, was ist jetzt richtig?"
                rows="2"
              />
              <div class="plant-events__revert-actions">
                <button
                  type="button"
                  class="plant-detail__action-btn plant-detail__action-btn--ghost"
                  :disabled="isSavingEdit"
                  @click="cancelEdit"
                >
                  Abbrechen
                </button>
                <button
                  type="button"
                  class="plant-detail__action-btn plant-detail__action-btn--primary"
                  :disabled="isSavingEdit || !editReason.trim()"
                  @click="confirmEdit(entry.event)"
                >
                  {{ isSavingEdit ? 'Wird gespeichert...' : 'Korrektur speichern' }}
                </button>
              </div>
            </div>
          </template>
        </li>
      </ul>

      <div class="plant-events__add">
        <!-- AUT-1204: editable event timestamp, vorbelegt "jetzt" -->
        <input
          v-model="noteEventTimestamp"
          type="datetime-local"
          class="plant-events__textarea"
          :max="toDatetimeLocalValue()"
        />
        <textarea
          v-model="noteInput"
          class="plant-events__textarea"
          placeholder="Notiz hinzufügen..."
          rows="2"
        />
        <button
          type="button"
          class="plant-detail__action-btn plant-detail__action-btn--primary"
          :disabled="isAddingNote || !noteInput.trim()"
          @click="addNote"
        >
          <MessageSquarePlus class="w-4 h-4" />
          <span>{{ isAddingNote ? 'Speichert...' : 'Notiz hinzufügen' }}</span>
        </button>
      </div>
    </AccordionSection>

    <!-- ────────────────────────────────────────────────────────────
         Section 2b — Phasenverlauf (Master + In-Phase-Layer)
         AUT-1228 / AUT-1240: Licht = Master; Nährstoff + Raumklima = Layer.
         ──────────────────────────────────────────────────────────── -->
    <AccordionSection
      title="Phasenverlauf"
      storage-key="ao-plant-phase-timeline"
      :default-open="true"
    >
      <PlantPhaseTimeline
        :events="loadedLifecycleEvents"
        :climate-segments="plantClimateSegments"
        :zone-id="currentPlant?.parent_zone_id ?? null"
      />
    </AccordionSection>

    <!-- ────────────────────────────────────────────────────────────
         Section 3 — MultispeQ-Verlauf (Phi2 Scatter)
         ──────────────────────────────────────────────────────────── -->
    <AccordionSection title="MultispeQ-Verlauf (Phi2)" storage-key="ao-plant-multispeq">
      <div v-if="isLoadingMeasurements" class="plant-detail__hint">
        Lade Messdaten...
      </div>
      <div v-else-if="!phi2HasData" class="plant-detail__hint">
        Keine MultispeQ-Messungen in den letzten 90 Tagen.
      </div>
      <div v-else class="plant-chart">
        <Scatter :data="phi2ChartData" :options="phi2ChartOptions" />
      </div>
    </AccordionSection>

    <!-- ────────────────────────────────────────────────────────────
         Section 4 — Audit-Trail
         ──────────────────────────────────────────────────────────── -->
    <AccordionSection title="Audit-Trail" storage-key="ao-plant-audit">
      <div v-if="isLoadingDetail" class="plant-detail__hint">
        Lade Audit-Trail...
      </div>
      <div v-else-if="auditLogs.length === 0" class="plant-detail__hint">
        Keine Audit-Einträge.
      </div>
      <ul v-else class="plant-audit">
        <li
          v-for="log in auditLogs"
          :key="log.id"
          class="plant-audit__item"
        >
          <DateDisplay class="plant-audit__date" :date="log.created_at" format="absolute" />
          <span class="plant-audit__action">{{ log.action }}</span>
          <span v-if="log.user" class="plant-audit__user">von {{ log.user }}</span>
        </li>
      </ul>
    </AccordionSection>

    <!-- Phase Change Modal -->
    <PlantPhaseChangeModal
      :open="showPhaseModal"
      :plant="currentPlant"
      @close="showPhaseModal = false"
      @changed="onPhaseChanged"
    />

    <!-- Stammdaten Edit Modal (AUT-1182) -->
    <PlantCreateModal
      :open="showEditModal"
      :edit-plant="currentPlant"
      @close="showEditModal = false"
      @updated="onEditUpdated"
    />
  </div>
</template>

<style scoped>
.plant-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.plant-detail__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.plant-detail__header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.plant-detail__qr-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.plant-detail__qr-value {
  font-family: var(--font-mono);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin-top: 2px;
}

.plant-detail__info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
  margin: 0;
}

.plant-detail__info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.plant-detail__info-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.plant-detail__info-value {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.plant-detail__info-value--primary {
  color: var(--color-text-primary);
  font-weight: 600;
  font-size: var(--text-base);
}

.plant-detail__info-value--mono {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.plant-detail__hint {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* Action row: flex container for phase + edit buttons */
.plant-detail__action-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

/* Action buttons */
.plant-detail__action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-accent-bright);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 38px;
  min-width: 44px;
}

.plant-detail__action-btn:hover:not(:disabled) {
  border-color: var(--color-accent);
  background: rgba(59, 130, 246, 0.06);
}

.plant-detail__action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.plant-detail__action-btn--ghost {
  align-self: flex-start;
}

.plant-detail__action-btn--primary {
  background: var(--color-accent);
  border-color: transparent;
  color: white;
}

.plant-detail__action-btn--primary:hover:not(:disabled) {
  background: var(--color-accent-bright);
  border-color: transparent;
}

/* Lifecycle Events */
.plant-events {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  list-style: none;
  padding: 0;
  margin: 0;
}

.plant-events__item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-left: 2px solid var(--color-iridescent-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
}

/* AUT-1207: reverted events stay visible but visually de-emphasised — never hidden */
.plant-events__item--reverted {
  opacity: 0.6;
  border-left-color: var(--color-error);
}

.plant-events__item--reverted .plant-events__type,
.plant-events__item--reverted .plant-events__note {
  text-decoration: line-through;
}

.plant-events__date {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  white-space: nowrap;
}

.plant-events__type {
  color: var(--color-text-primary);
  font-weight: 600;
}

.plant-events__note {
  color: var(--color-text-secondary);
}

.plant-events__status-reason {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-style: italic;
}

.plant-events__revert-btn {
  margin-left: auto;
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
}

.plant-events__revert-btn:hover {
  color: var(--color-error);
  border-color: var(--color-error);
}

.plant-events__revert-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  width: 100%;
  padding-top: var(--space-2);
  border-top: 1px solid var(--glass-border);
}

.plant-events__revert-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

/* AUT-1208: labelled fields inside the edit form */
.plant-events__label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.plant-events__add {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--glass-border);
}

.plant-events__textarea {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  resize: vertical;
  transition: border-color var(--transition-fast);
}

.plant-events__textarea:focus {
  border-color: var(--color-accent);
}

/* Chart */
.plant-chart {
  height: 240px;
  width: 100%;
}

/* Audit-Trail */
.plant-audit {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  list-style: none;
  padding: 0;
  margin: 0;
}

.plant-audit__item {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  border-bottom: 1px dashed var(--glass-border);
}

.plant-audit__date {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
}

.plant-audit__action {
  color: var(--color-text-primary);
}

.plant-audit__user {
  color: var(--color-text-muted);
}

@media (max-width: 480px) {
  .plant-detail__info-grid {
    grid-template-columns: 1fr;
  }
  .plant-events__item {
    grid-template-columns: 1fr;
  }
}
</style>
