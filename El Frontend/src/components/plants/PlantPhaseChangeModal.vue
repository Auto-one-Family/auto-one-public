<script setup lang="ts">
/**
 * PlantPhaseChangeModal — Phase wechseln Dialog
 *
 * AUT-1183: Two independent phase axes.
 *   - Licht-/Wachstumsphase  → event_type 'phase_changed'         → plants.phase
 *   - Nährstoff-/Düngephase  → event_type 'nutrient_phase_changed' → plants.nutrient_phase
 *
 * AUT-1180 fix: new_phase is sent as a top-level field (not inside metadata).
 * The server atomically updates the plant column inside add_lifecycle_event —
 * the redundant updatePlant PATCH has been removed.
 *
 * At least one axis must change for the form to submit.
 */

import { ref, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { NUTRIENT_PHASES, PLANT_PHASES, type Plant, type PlantPhase } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'
import { datetimeLocalValueToIso, toDatetimeLocalValue } from '@/utils/formatters'

interface Props {
  open: boolean
  plant: Plant | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  changed: []
}>()

const plantsStore = usePlantsStore()
const toast = useToast()

/** Light/growth phase axis */
const newLightPhase = ref<PlantPhase>('clone')

/**
 * Nutrient/fertilizer phase axis.
 * null = "keine Änderung" — used when the plant has no current nutrient_phase
 * and the user has not selected one yet.
 */
const newNutrientPhase = ref<PlantPhase | null>(null)

const note = ref('')
/**
 * AUT-1204: actual event timestamp, editable so an operator can backdate a
 * phase change instead of it always landing on the moment of entry.
 * Vorbelegt mit "jetzt".
 */
const eventTimestamp = ref(toDatetimeLocalValue())
/**
 * AUT-1207: "geplant" instead of "ist passiert" — a foreseen-but-not-yet-
 * occurred transition. Must never set the plant's current state (enforced
 * server-side); purely a status label here, not a reminder/planning tool.
 */
const isPlanned = ref(false)
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

watch(() => props.open, (isOpen) => {
  if (isOpen && props.plant) {
    newLightPhase.value = props.plant.phase
    newNutrientPhase.value = (props.plant.nutrient_phase as PlantPhase | null) ?? null
    note.value = ''
    eventTimestamp.value = toDatetimeLocalValue()
    isPlanned.value = false
    errorMessage.value = null
  }
})

async function handleSubmit(): Promise<void> {
  if (!props.plant) return
  errorMessage.value = null

  const plant = props.plant
  const currentLightPhase = plant.phase
  const currentNutrientPhase = (plant.nutrient_phase as PlantPhase | null) ?? null

  const lightChanged = newLightPhase.value !== currentLightPhase
  // Nutrient changed only when a phase is actually selected AND it differs from current.
  const nutrientChanged =
    newNutrientPhase.value !== null && newNutrientPhase.value !== currentNutrientPhase

  if (!lightChanged && !nutrientChanged) {
    errorMessage.value = 'Bitte mindestens eine Phase ändern.'
    return
  }

  // AUT-1204: client-side mirror of the server's future-timestamp guard
  // (schemas/plant.py validate_event_timestamp) — catch it before the
  // request instead of surfacing a raw 422.
  const eventTimestampIso = datetimeLocalValueToIso(eventTimestamp.value)
  if (eventTimestampIso === null) {
    errorMessage.value = 'Ereigniszeitpunkt ist ungültig.'
    return
  }
  if (Date.parse(eventTimestampIso) > Date.now() + 60_000) {
    errorMessage.value = 'Ereigniszeitpunkt darf nicht in der Zukunft liegen.'
    return
  }

  isSubmitting.value = true
  const noteText = note.value.trim() || null
  const changedLabels: string[] = []
  // Capture values once — Ref.value cannot be narrowed across multiple accesses.
  const selectedLightPhase = newLightPhase.value
  const selectedNutrientPhase = newNutrientPhase.value

  const eventStatus = isPlanned.value ? 'planned' : 'occurred'

  try {
    // --- Light/growth axis ---
    if (lightChanged) {
      await plantsStore.addLifecycleEvent(plant.plant_id, {
        event_type: 'phase_changed',
        new_phase: selectedLightPhase,
        note: noteText,
        event_timestamp: eventTimestampIso,
        event_status: eventStatus,
        metadata: {
          from: currentLightPhase,
          to: selectedLightPhase,
        },
      })
      changedLabels.push(`Licht: "${PLANT_PHASE_LABELS[selectedLightPhase]}"`)
    }

    // --- Nutrient/fertilizer axis ---
    if (nutrientChanged && selectedNutrientPhase !== null) {
      await plantsStore.addLifecycleEvent(plant.plant_id, {
        event_type: 'nutrient_phase_changed',
        new_phase: selectedNutrientPhase,
        note: noteText,
        event_timestamp: eventTimestampIso,
        event_status: eventStatus,
        metadata: {
          from: currentNutrientPhase,
          to: selectedNutrientPhase,
        },
      })
      changedLabels.push(`Nährstoff: "${PLANT_PHASE_LABELS[selectedNutrientPhase]}"`)
    }

    toast.success(
      isPlanned.value
        ? `Phasenwechsel als geplant vorgemerkt — ${changedLabels.join(', ')}`
        : `Phase gewechselt — ${changedLabels.join(', ')}`,
    )
    emit('changed')
    emit('close')
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Phasenwechsel fehlgeschlagen'
    errorMessage.value = message
    toast.error(message)
  } finally {
    isSubmitting.value = false
  }
}

function handleClose(): void {
  if (!isSubmitting.value) {
    emit('close')
  }
}
</script>

<template>
  <BaseModal
    :open="props.open"
    title="Phase wechseln"
    max-width="max-w-md"
    @close="handleClose"
  >
    <form v-if="plant" class="phase-change-form" @submit.prevent="handleSubmit">
      <!-- Current state overview -->
      <div class="phase-change-form__current-row">
        <span class="phase-change-form__current-item">
          <span class="phase-change-form__current-axis">Licht:</span>
          <strong>{{ PLANT_PHASE_LABELS[plant.phase] ?? plant.phase }}</strong>
        </span>
        <span class="phase-change-form__current-item">
          <span class="phase-change-form__current-axis">Nährstoff:</span>
          <strong>{{
            plant.nutrient_phase
              ? (PLANT_PHASE_LABELS[plant.nutrient_phase as PlantPhase] ?? plant.nutrient_phase)
              : '— nicht gesetzt —'
          }}</strong>
        </span>
      </div>

      <!-- Light / growth axis -->
      <fieldset class="phase-change-form__axis-group">
        <legend class="phase-change-form__axis-legend">
          Licht-/Wachstumsphase
        </legend>
        <label class="phase-change-form__field">
          <span class="phase-change-form__label">Neue Phase</span>
          <select v-model="newLightPhase" class="phase-change-form__input" required>
            <option v-for="phase in PLANT_PHASES" :key="phase" :value="phase">
              {{ PLANT_PHASE_LABELS[phase] }}
            </option>
          </select>
        </label>
      </fieldset>

      <!-- Nutrient / fertilizer axis -->
      <fieldset class="phase-change-form__axis-group">
        <legend class="phase-change-form__axis-legend">
          Nährstoff-/Düngephase
        </legend>
        <label class="phase-change-form__field">
          <span class="phase-change-form__label">Neue Phase (optional)</span>
          <select v-model="newNutrientPhase" class="phase-change-form__input">
            <!-- Shown only when no nutrient phase is currently set -->
            <option v-if="!plant.nutrient_phase" :value="null">— Keine Änderung —</option>
            <!-- AUT-1209: nutrient axis has its own value list (diverged from PLANT_PHASES) -->
            <option v-for="phase in NUTRIENT_PHASES" :key="phase" :value="phase">
              {{ PLANT_PHASE_LABELS[phase] }}
            </option>
          </select>
        </label>
      </fieldset>

      <!-- AUT-1204: shared event timestamp for all events sent by this submission -->
      <label class="phase-change-form__field">
        <span class="phase-change-form__label">Ereigniszeitpunkt</span>
        <input
          v-model="eventTimestamp"
          type="datetime-local"
          class="phase-change-form__input"
          :max="toDatetimeLocalValue()"
        />
      </label>

      <!-- AUT-1207: "geplant" instead of "ist passiert" -->
      <label class="phase-change-form__checkbox-field">
        <input v-model="isPlanned" type="checkbox" />
        <span>Ist geplant, noch nicht eingetreten (setzt den aktuellen Zustand nicht)</span>
      </label>

      <!-- Shared note for all events sent by this submission -->
      <label class="phase-change-form__field">
        <span class="phase-change-form__label">Notiz (optional)</span>
        <textarea
          v-model="note"
          class="phase-change-form__textarea"
          placeholder="Beobachtungen, Begründung, ..."
          rows="3"
        />
      </label>

      <div v-if="errorMessage" class="phase-change-form__error">
        {{ errorMessage }}
      </div>
    </form>

    <template #footer>
      <div class="phase-change-form__actions">
        <button
          type="button"
          class="plant-btn plant-btn--ghost"
          :disabled="isSubmitting"
          @click="handleClose"
        >
          Abbrechen
        </button>
        <button
          type="button"
          class="plant-btn plant-btn--primary"
          :disabled="isSubmitting"
          @click="handleSubmit"
        >
          {{ isSubmitting ? 'Wird gespeichert...' : 'Phase wechseln' }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.phase-change-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

/* Current state row — two inline pills */
.phase-change-form__current-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.phase-change-form__current-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
}

.phase-change-form__current-axis {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.phase-change-form__current-item strong {
  color: var(--color-text-primary);
}

/* Axis fieldsets */
.phase-change-form__axis-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  margin: 0;
}

.phase-change-form__axis-legend {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-accent-bright);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0 var(--space-1);
}

.phase-change-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.phase-change-form__checkbox-field {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.phase-change-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.phase-change-form__input,
.phase-change-form__textarea {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  transition: border-color var(--transition-fast);
}

.phase-change-form__input {
  min-height: 38px;
}

.phase-change-form__textarea {
  resize: vertical;
}

.phase-change-form__input:focus,
.phase-change-form__textarea:focus {
  border-color: var(--color-accent);
}

.phase-change-form__error {
  padding: var(--space-2) var(--space-3);
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: var(--radius-sm);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.phase-change-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.plant-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 38px;
  min-width: 44px;
  border: 1px solid transparent;
}

.plant-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.plant-btn--primary {
  background: var(--color-accent);
  color: white;
}

.plant-btn--primary:not(:disabled):hover {
  background: var(--color-accent-bright);
}

.plant-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.plant-btn--ghost:not(:disabled):hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}
</style>
