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
import { Printer, RefreshCw, MessageSquarePlus } from 'lucide-vue-next'
import { plantsApi } from '@/api/plants'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useToast } from '@/composables/useToast'
import { AccordionSection } from '@/shared/design/primitives'
import { formatRelativeTime } from '@/utils/formatters'
import DateDisplay from '@/components/base/DateDisplay.vue'
import { PLANT_PHASE_LABELS, getPlantEventTypeLabel } from '@/components/plants/plantLabels'
import PlantPhaseChangeModal from '@/components/plants/PlantPhaseChangeModal.vue'
import type { Plant, PlantLifecycleEvent, PlantMeasurement, PlantPhase } from '@/types'

ChartJS.register(LinearScale, PointElement, Tooltip, Legend, TimeScale)

interface Props {
  plant: Plant
}

const props = defineProps<Props>()

const plantsStore = usePlantsStore()
const toast = useToast()

// =============================================================================
// Detail data — refresh whenever the panel switches plants
// =============================================================================
const detail = ref<Plant | null>(null)
const measurements = ref<PlantMeasurement[]>([])
const isLoadingDetail = ref(false)
const isLoadingMeasurements = ref(false)
const isDownloadingQR = ref(false)

const showPhaseModal = ref(false)
const noteInput = ref('')
const isAddingNote = ref(false)

async function loadDetail(plantId: string): Promise<void> {
  isLoadingDetail.value = true
  try {
    detail.value = await plantsStore.fetchPlantDetail(plantId)
  } finally {
    isLoadingDetail.value = false
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

watch(
  () => props.plant.id,
  (id) => {
    if (id) {
      void loadDetail(id)
      void loadMeasurements(id)
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  detail.value = null
  measurements.value = []
})

// =============================================================================
// Section 1 — Stammdaten
// =============================================================================
const currentPlant = computed<Plant>(() => detail.value ?? props.plant)

const phaseLabel = computed(() => {
  const phase = currentPlant.value.phase as PlantPhase
  return PLANT_PHASE_LABELS[phase] ?? currentPlant.value.phase
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
      currentPlant.value.id,
      `${currentPlant.value.qr_code || 'plant-' + currentPlant.value.id}.png`,
    )
    toast.success('QR-Label heruntergeladen')
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'QR-Download fehlgeschlagen')
  } finally {
    isDownloadingQR.value = false
  }
}

function onPhaseChanged(): void {
  // Reload detail to pick up the new lifecycle event + phase
  void loadDetail(currentPlant.value.id)
}

// =============================================================================
// Section 2 — Lifecycle-Events
// =============================================================================
const lifecycleEvents = computed<PlantLifecycleEvent[]>(
  () => currentPlant.value.lifecycle_events ?? [],
)

const sortedEvents = computed<PlantLifecycleEvent[]>(() =>
  [...lifecycleEvents.value].sort(
    (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
  ),
)

async function addNote(): Promise<void> {
  const text = noteInput.value.trim()
  if (!text) {
    toast.warning('Bitte eine Notiz eingeben')
    return
  }
  isAddingNote.value = true
  try {
    await plantsStore.addLifecycleEvent(currentPlant.value.id, {
      event_type: 'note',
      note: text,
    })
    noteInput.value = ''
    toast.success('Notiz gespeichert')
    await loadDetail(currentPlant.value.id)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Notiz konnte nicht gespeichert werden')
  } finally {
    isAddingNote.value = false
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
          <dd class="plant-detail__info-value">{{ currentPlant.genotype }}</dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Charge</dt>
          <dd class="plant-detail__info-value">{{ currentPlant.batch || '—' }}</dd>
        </div>
        <div class="plant-detail__info-item">
          <dt class="plant-detail__info-label">Phase</dt>
          <dd class="plant-detail__info-value plant-detail__info-value--primary">
            {{ phaseLabel }}
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

      <button
        type="button"
        class="plant-detail__action-btn plant-detail__action-btn--ghost"
        @click="showPhaseModal = true"
      >
        <RefreshCw class="w-4 h-4" />
        <span>Phase wechseln</span>
      </button>
    </div>

    <!-- ────────────────────────────────────────────────────────────
         Section 2 — Lifecycle-Events
         ──────────────────────────────────────────────────────────── -->
    <AccordionSection title="Lifecycle-Events" storage-key="ao-plant-events">
      <div v-if="isLoadingDetail" class="plant-detail__hint">
        Lade Ereignisse...
      </div>
      <div v-else-if="sortedEvents.length === 0" class="plant-detail__hint">
        Noch keine Ereignisse erfasst.
      </div>
      <ul v-else class="plant-events">
        <li
          v-for="event in sortedEvents"
          :key="event.id"
          class="plant-events__item"
        >
          <DateDisplay class="plant-events__date" :date="event.created_at" format="absolute" />
          <span class="plant-events__type">{{ getPlantEventTypeLabel(event.event_type) }}</span>
          <span v-if="event.note" class="plant-events__note">{{ event.note }}</span>
        </li>
      </ul>

      <div class="plant-events__add">
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
  display: grid;
  grid-template-columns: auto auto 1fr;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-left: 2px solid var(--color-iridescent-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
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
