<script setup lang="ts">
/**
 * PlantDetailPanel — SlideOver detail view for a single plant.
 *
 * Sections:
 *   1) Notiz hinzufügen (oben, immer erreichbar)
 *   2) Stammdaten + QR-Label + Phase wechseln
 *   3) MultispeQ-Verlauf (Phi2 Scatter-Chart)
 *
 * Data sources:
 *   - GET  /v1/plants/{id}
 *   - GET  /v1/plants/{id}/measurements
 *   - POST /v1/plants/{id}/lifecycle-event  → add note
 */

import { ref, computed, watch, onUnmounted } from 'vue'
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
import { Printer, RefreshCw, MessageSquarePlus, Pencil } from 'lucide-vue-next'
import { plantsApi } from '@/api/plants'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useToast } from '@/composables/useToast'
import { AccordionSection } from '@/shared/design/primitives'
import { datetimeLocalValueToIso, formatRelativeTime, toDatetimeLocalValue } from '@/utils/formatters'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'
import PlantPhaseChangeModal from '@/components/plants/PlantPhaseChangeModal.vue'
import PlantCreateModal from '@/components/plants/PlantCreateModal.vue'
import type { Plant, PlantMeasurement, PlantPhase } from '@/types'

ChartJS.register(LinearScale, PointElement, Tooltip, Legend, TimeScale)

interface Props {
  plant: Plant
}

const props = defineProps<Props>()

const plantsStore = usePlantsStore()
const toast = useToast()

const detail = ref<Plant | null>(null)
const measurements = ref<PlantMeasurement[]>([])
const isLoadingMeasurements = ref(false)
const isDownloadingQR = ref(false)

const showPhaseModal = ref(false)
const showEditModal = ref(false)
const noteInput = ref('')
const noteEventTimestamp = ref(toDatetimeLocalValue())
const isAddingNote = ref(false)

async function loadDetail(plantId: string): Promise<void> {
  try {
    detail.value = await plantsStore.fetchPlantDetail(plantId)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Pflanze konnte nicht geladen werden')
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
  () => props.plant.plant_id,
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

const currentPlant = computed<Plant>(() => detail.value ?? props.plant)

const phaseLabel = computed(() => {
  const phase = currentPlant.value.phase as PlantPhase
  return PLANT_PHASE_LABELS[phase] ?? currentPlant.value.phase
})

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
  void loadDetail(currentPlant.value.plant_id)
}

function onEditUpdated(): void {
  void loadDetail(currentPlant.value.plant_id)
}

async function addNote(): Promise<void> {
  const text = noteInput.value.trim()
  if (!text) {
    toast.warning('Bitte eine Notiz eingeben')
    return
  }
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
      event_type: 'note_added',
      note: text,
      event_timestamp: eventTimestampIso,
    })
    noteInput.value = ''
    noteEventTimestamp.value = toDatetimeLocalValue()
    toast.success('Notiz gespeichert')
    await loadDetail(currentPlant.value.plant_id)
  } catch (e) {
    toast.error(e instanceof Error ? e.message : 'Notiz konnte nicht gespeichert werden')
  } finally {
    isAddingNote.value = false
  }
}

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
</script>

<template>
  <div class="plant-detail">
    <div class="plant-detail__section plant-detail__note">
      <input
        v-model="noteEventTimestamp"
        type="datetime-local"
        class="plant-detail__note-input"
        :max="toDatetimeLocalValue()"
        aria-label="Ereigniszeitpunkt"
      />
      <textarea
        v-model="noteInput"
        class="plant-detail__note-input"
        placeholder="Notiz hinzufügen..."
        rows="2"
        aria-label="Notiz"
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

    <PlantPhaseChangeModal
      :open="showPhaseModal"
      :plant="currentPlant"
      @close="showPhaseModal = false"
      @changed="onPhaseChanged"
    />

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

.plant-detail__note {
  border-bottom: 1px solid var(--glass-border);
}

.plant-detail__note-input {
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

.plant-detail__note-input:focus {
  border-color: var(--color-accent);
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

.plant-detail__action-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

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

.plant-chart {
  height: 240px;
  width: 100%;
}

@media (max-width: 480px) {
  .plant-detail__info-grid {
    grid-template-columns: 1fr;
  }
}
</style>
