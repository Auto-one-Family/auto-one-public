<script setup lang="ts">
/**
 * Measures on the planning timeline — executed ranges + planned points.
 *
 * Writes PlantLifecycleEvent (same log as Pflanzen). No second structure.
 */

import { computed, ref } from 'vue'
import { Plus } from 'lucide-vue-next'
import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import { nowMarkerPercent } from '@/components/plan-timeline/planTimelineTracks'
import {
  PLAN_PLANT_MEASURE_OPTIONS,
  defaultExecutedMeasureWindowStartMs,
  type PlanMeasureCreatePayload,
  type PlanMeasureMarker,
  type PlanPlantMeasureEventType,
} from '@/components/plan-timeline/planMeasureMarkers'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'

interface PlantOption {
  plantId: string
  label: string
}

interface Props {
  markers: PlanMeasureMarker[]
  window: PlanTimelineWindow
  plantId: string
  plants?: PlantOption[]
  /** Latest occurred light-phase start (ms) per plant — clamps default Von. */
  phaseStartMsByPlantId?: Record<string, number>
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  plants: () => [],
  phaseStartMsByPlantId: () => ({}),
  disabled: false,
})

const emit = defineEmits<{
  create: [payload: PlanMeasureCreatePayload]
  select: [marker: PlanMeasureMarker]
}>()

const nowPct = computed(() => nowMarkerPercent(props.window))
const createOpen = ref(false)
const eventType = ref<PlanPlantMeasureEventType>('topping')
const note = ref('')
const saving = ref(false)
const selectedPlantId = ref(props.plantId)
const eventStatus = ref<'occurred' | 'planned'>('occurred')
const windowStartLocal = ref('')
const windowEndLocal = ref('')

const measureOptions = PLAN_PLANT_MEASURE_OPTIONS.map((o) => ({
  value: o.value,
  label: o.label,
}))

const statusOptions = [
  { value: 'occurred', label: 'Ausgeführt' },
  { value: 'planned', label: 'Geplant' },
]

const plantOptions = computed(() =>
  props.plants.map((p) => ({ value: p.plantId, label: p.label })),
)

const canCreate = computed(() => !props.disabled && Boolean(props.plantId || props.plants.length))

function toLocalInput(ms: number): string {
  const d = new Date(ms)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function openCreate(): void {
  if (!canCreate.value) return
  note.value = ''
  eventType.value = 'topping'
  eventStatus.value = 'occurred'
  selectedPlantId.value = props.plantId || props.plants[0]?.plantId || ''
  const phaseStart = props.phaseStartMsByPlantId[selectedPlantId.value]
  windowStartLocal.value = toLocalInput(
    defaultExecutedMeasureWindowStartMs(props.window.nowMs, phaseStart),
  )
  windowEndLocal.value = toLocalInput(props.window.nowMs)
  createOpen.value = true
}

async function submitCreate(): Promise<void> {
  const plantId = selectedPlantId.value || props.plantId
  if (!plantId) return
  saving.value = true
  try {
    const executed = eventStatus.value === 'occurred'
    emit('create', {
      plantId,
      eventType: eventType.value,
      note: note.value.trim() || null,
      eventStatus: eventStatus.value,
      windowStart: executed && windowStartLocal.value
        ? new Date(windowStartLocal.value).toISOString()
        : null,
      windowEnd: executed && windowEndLocal.value
        ? new Date(windowEndLocal.value).toISOString()
        : null,
    })
    createOpen.value = false
  } finally {
    saving.value = false
  }
}

function markerTitle(m: PlanMeasureMarker): string {
  const note = m.notes ? ` — ${m.notes}` : ''
  if (m.visualState === 'withdrawn') return `${m.label}${note}\nZurückgenommen`
  if (m.visualState === 'ghosted') {
    return `${m.label}${note}\nGeplant, bisher nicht eingetreten`
  }
  return `${m.label}${note}`
}

function markerAria(m: PlanMeasureMarker): string {
  if (m.visualState === 'withdrawn') return `Zurückgenommen: ${m.label}`
  if (m.visualState === 'ghosted') return `Geplant (nicht eingetreten): ${m.label}`
  return `Maßnahme: ${m.label}`
}

function onMarkerClick(m: PlanMeasureMarker): void {
  if (m.eventStatus === 'reverted') return
  emit('select', m)
}
</script>

<template>
  <div class="measure-row" aria-label="Pflanzenmaßnahmen">
    <div class="measure-row__meta">
      <span class="measure-row__title">Maßnahmen</span>
      <span class="measure-row__sub">Ausgeführt auf Phasenabschnitt</span>
      <button
        type="button"
        class="measure-row__add"
        :disabled="!canCreate"
        aria-label="Maßnahme eintragen"
        @click="openCreate"
      >
        <Plus class="w-3.5 h-3.5" aria-hidden="true" />
        Eintragen
      </button>
    </div>

    <div class="measure-row__bar">
      <div
        class="measure-row__now"
        :style="{ left: nowPct + '%' }"
        aria-hidden="true"
      />
      <div v-if="markers.length === 0" class="measure-row__empty">
        keine Maßnahmen in diesem Zeitraum
      </div>
      <button
        v-for="m in markers"
        :key="m.eventId"
        type="button"
        class="measure-row__marker"
        :class="{
          'measure-row__marker--range': m.widthPct > 0,
          'measure-row__marker--ghosted': m.visualState === 'ghosted',
          'measure-row__marker--withdrawn': m.visualState === 'withdrawn',
        }"
        :style="m.widthPct > 0
          ? { left: m.leftPct + '%', width: Math.max(m.widthPct, 1.2) + '%' }
          : { left: m.leftPct + '%' }"
        :title="markerTitle(m)"
        :aria-label="markerAria(m)"
        :disabled="m.eventStatus === 'reverted'"
        @click="onMarkerClick(m)"
      />
    </div>

    <BaseModal
      :open="createOpen"
      title="Maßnahme eintragen"
      max-width="max-w-sm"
      @update:open="createOpen = $event"
    >
      <div class="measure-create">
        <BaseSelect
          v-if="plantOptions.length > 1"
          v-model="selectedPlantId"
          :options="plantOptions"
          label="Pflanze"
          aria-label="Pflanze für die Maßnahme"
        />
        <BaseSelect
          v-model="eventType"
          :options="measureOptions"
          label="Art"
          aria-label="Maßnahmenart"
        />
        <BaseSelect
          v-model="eventStatus"
          :options="statusOptions"
          label="Status"
          aria-label="Ausgeführt oder geplant"
        />
        <template v-if="eventStatus === 'occurred'">
          <label class="measure-create__label">
            Von
            <input
              v-model="windowStartLocal"
              type="datetime-local"
              class="measure-create__note"
              aria-label="Beginn des Maßnahmenzeitraums"
            />
          </label>
          <label class="measure-create__label">
            Bis
            <input
              v-model="windowEndLocal"
              type="datetime-local"
              class="measure-create__note"
              aria-label="Ende des Maßnahmenzeitraums"
            />
          </label>
        </template>
        <label class="measure-create__label">
          Notiz (optional)
          <textarea
            v-model="note"
            class="measure-create__note"
            rows="2"
            aria-label="Notiz zur Maßnahme"
          />
        </label>
        <p class="measure-create__hint">
          Die Maßnahme gehört zum Phasenabschnitt (Zeit) und zur Zone/Subzone der Pflanze (Ort).
        </p>
        <div class="measure-create__actions">
          <BaseButton type="button" variant="ghost" @click="createOpen = false">
            Abbrechen
          </BaseButton>
          <BaseButton
            type="button"
            variant="primary"
            :loading="saving"
            @click="submitCreate"
          >
            Anlegen
          </BaseButton>
        </div>
      </div>
    </BaseModal>
  </div>
</template>

<style scoped>
.measure-row {
  display: grid;
  grid-template-columns: minmax(120px, 180px) 1fr;
  gap: var(--space-3);
  align-items: center;
  min-height: 36px;
}

.measure-row__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.measure-row__title {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.measure-row__sub {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.measure-row__add {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
  padding: 2px 6px;
  width: fit-content;
  font-size: var(--text-xs);
  color: var(--color-accent);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
}

.measure-row__add:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.measure-row__bar {
  position: relative;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  overflow: hidden;
}

.measure-row__now {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 2px;
  margin-left: -1px;
  background: var(--color-accent);
  opacity: 0.85;
  z-index: 2;
  pointer-events: none;
}

.measure-row__empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  opacity: 0.7;
}

.measure-row__marker {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  margin-left: -5px;
  margin-top: -5px;
  border-radius: 50%;
  background: var(--color-warning);
  border: 2px solid var(--color-bg-secondary);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-warning) 50%, transparent);
  z-index: 3;
  cursor: pointer;
  padding: 0;
}

.measure-row__marker--range {
  height: 12px;
  margin-left: 0;
  margin-top: -6px;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-success) 35%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 60%, transparent);
  box-shadow: none;
}

.measure-row__marker--ghosted {
  opacity: 0.35;
  background: transparent;
  border: 2px dashed var(--color-warning);
  box-shadow: none;
}

.measure-row__marker--withdrawn {
  opacity: 0.55;
  background: var(--color-danger);
  box-shadow: none;
  cursor: default;
}

.measure-row__marker:disabled {
  cursor: default;
}

.measure-create {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.measure-create__label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.measure-create__note {
  padding: var(--space-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  resize: vertical;
}

.measure-create__hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.measure-create__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
