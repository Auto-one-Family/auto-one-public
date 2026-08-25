<script setup lang="ts">
/**
 * PlantBatchCreateModal — "N Pflanzen anlegen" Dialog
 *
 * Creates N plants with shared base properties (genotype, batch, zone,
 * subzone, planting_date, phase) via sequential POST /v1/plants calls.
 * Form fields are structurally identical to PlantCreateModal (same
 * availableSubzones logic, same zone→subzone reset watcher).
 *
 * New vs PlantCreateModal:
 *  - "Anzahl" counter (1–20)
 *  - Progress bar during submission
 *
 * AUT-1160 C2 — Batch-Anlage-Formular.
 */

import { ref, computed, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useEspStore } from '@/stores/esp'
import { PLANT_PHASES, type PlantCreate, type PlantPhase } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'

interface Props {
  open: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  /** Emitted after all plants created, arg = number successfully created */
  created: [count: number]
}>()

const plantsStore = usePlantsStore()
const zoneStore = useZoneStore()
const espStore = useEspStore()
const toast = useToast()

// ---------------------------------------------------------------------------
// Form state
// ---------------------------------------------------------------------------
interface FormState {
  count: number
  /** Server field: genotype_label */
  genotype_label: string
  /** Server field: batch_label */
  batch_label: string
  /** Local-only: used to filter subzone options, NOT sent to server */
  zone_id: string
  subzone_id: string
  planting_date: string
  phase: PlantPhase
}

function emptyForm(): FormState {
  return {
    count: 5,
    genotype_label: '',
    batch_label: '',
    zone_id: '',
    subzone_id: '',
    planting_date: new Date().toISOString().slice(0, 10),
    phase: 'clone',
  }
}

const form = ref<FormState>(emptyForm())
const isSubmitting = ref(false)
const progress = ref(0)
const errorMessage = ref<string | null>(null)

// ---------------------------------------------------------------------------
// Derived options (same logic as PlantCreateModal.availableSubzones)
// ---------------------------------------------------------------------------
const availableZones = computed(() => zoneStore.activeZones)

/**
 * Subzone options scoped to the selected zone.
 *
 * Uses device.subzones[] (SubzoneSummary[], n:m via AUT-1155) instead of
 * the deprecated singular device.subzone_id — same fix as PlantCreateModal
 * (AUT-1178), mirrored here since this form has the identical logic.
 */
const availableSubzones = computed(() => {
  if (!form.value.zone_id) return []
  const seen = new Set<string>()
  const result: Array<{ id: string; name: string }> = []
  for (const device of espStore.devices) {
    if (device.zone_id !== form.value.zone_id) continue
    for (const sz of device.subzones ?? []) {
      if (seen.has(sz.subzone_id)) continue
      seen.add(sz.subzone_id)
      result.push({ id: sz.subzone_id, name: sz.subzone_name || sz.subzone_id })
    }
  }
  result.sort((a, b) => a.name.localeCompare(b.name))
  return result
})

// Reset subzone when zone changes
watch(() => form.value.zone_id, () => {
  form.value.subzone_id = ''
})

// Reset form + progress when modal opens
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    form.value = emptyForm()
    errorMessage.value = null
    progress.value = 0
    if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
      void zoneStore.fetchZoneEntities()
    }
  }
})

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------
function validate(): string | null {
  const v = form.value
  if (!v.genotype_label.trim()) return 'Genotyp ist erforderlich.'
  if (!v.phase) return 'Phase ist erforderlich.'
  if (!Number.isInteger(v.count) || v.count < 1 || v.count > 20) {
    return 'Anzahl muss eine ganze Zahl zwischen 1 und 20 sein.'
  }
  return null
}

// ---------------------------------------------------------------------------
// Submit: create N plants sequentially, show progress
// ---------------------------------------------------------------------------
async function handleSubmit(): Promise<void> {
  errorMessage.value = null
  const validation = validate()
  if (validation) {
    errorMessage.value = validation
    return
  }

  // zone_id is local-only (used to filter subzone options above), not sent to
  // the server — the Plant model has no zone_id column (AUT-1178).
  const basePayload: PlantCreate = {
    genotype_label: form.value.genotype_label.trim(),
    phase: form.value.phase,
    batch_label: form.value.batch_label.trim() || null,
    subzone_id: form.value.subzone_id.trim() || null,
    planting_date: form.value.planting_date || null,
  }

  isSubmitting.value = true
  progress.value = 0
  let createdCount = 0

  try {
    for (let i = 0; i < form.value.count; i++) {
      await plantsStore.createPlant(basePayload)
      createdCount++
      progress.value = createdCount
    }
    toast.success(`${createdCount} Pflanzen angelegt`)
    emit('created', createdCount)
    emit('close')
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Anlegen fehlgeschlagen'
    errorMessage.value = `Nach ${createdCount}/${form.value.count}: ${message}`
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
    title="Batch-Anlage: Mehrere Pflanzen"
    max-width="max-w-lg"
    @close="handleClose"
  >
    <form class="batch-form" @submit.prevent="handleSubmit">
      <!-- Anzahl -->
      <label class="batch-form__field">
        <span class="batch-form__label">Anzahl (1–20) *</span>
        <input
          v-model.number="form.count"
          type="number"
          min="1"
          max="20"
          step="1"
          class="batch-form__input"
          required
        />
      </label>

      <!-- Progress bar during submit -->
      <div v-if="isSubmitting" class="batch-form__progress">
        <div class="batch-form__progress-bar">
          <div
            class="batch-form__progress-fill"
            :style="{ width: `${(progress / form.count) * 100}%` }"
          />
        </div>
        <span class="batch-form__progress-label">{{ progress }} / {{ form.count }} angelegt...</span>
      </div>

      <!-- Genotype -->
      <label class="batch-form__field">
        <span class="batch-form__label">Genotyp *</span>
        <input
          v-model="form.genotype_label"
          type="text"
          class="batch-form__input"
          placeholder="z.B. Northern Lights"
          required
          autofocus
        />
      </label>

      <!-- Charge + Pflanzdatum -->
      <div class="batch-form__row grid-auto-sm">
        <label class="batch-form__field">
          <span class="batch-form__label">Charge</span>
          <input
            v-model="form.batch_label"
            type="text"
            class="batch-form__input"
            placeholder="z.B. 2026-NL-A"
          />
        </label>

        <label class="batch-form__field">
          <span class="batch-form__label">Pflanzdatum</span>
          <input
            v-model="form.planting_date"
            type="date"
            class="batch-form__input"
          />
        </label>
      </div>

      <!-- Phase -->
      <label class="batch-form__field">
        <span class="batch-form__label">Phase *</span>
        <select v-model="form.phase" class="batch-form__input" required>
          <option
            v-for="phase in PLANT_PHASES"
            :key="phase"
            :value="phase"
          >
            {{ PLANT_PHASE_LABELS[phase] }}
          </option>
        </select>
      </label>

      <!-- Zone + Subzone (same logic as PlantCreateModal) -->
      <div class="batch-form__row grid-auto-sm">
        <label class="batch-form__field">
          <span class="batch-form__label">Zone</span>
          <select v-model="form.zone_id" class="batch-form__input">
            <option value="">Keine Zone</option>
            <option
              v-for="zone in availableZones"
              :key="zone.zone_id"
              :value="zone.zone_id"
            >
              {{ zone.name }}
            </option>
          </select>
        </label>

        <label class="batch-form__field">
          <span class="batch-form__label">Subzone</span>
          <select
            v-model="form.subzone_id"
            class="batch-form__input"
            :disabled="!form.zone_id || availableSubzones.length === 0"
          >
            <option value="">
              {{ !form.zone_id ? 'Zuerst Zone wählen' : 'Keine Subzone' }}
            </option>
            <option
              v-for="subzone in availableSubzones"
              :key="subzone.id"
              :value="subzone.id"
            >
              {{ subzone.name }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="errorMessage" class="batch-form__error">
        {{ errorMessage }}
      </div>
    </form>

    <template #footer>
      <div class="batch-form__actions">
        <button
          type="button"
          class="batch-btn batch-btn--ghost"
          :disabled="isSubmitting"
          @click="handleClose"
        >
          Abbrechen
        </button>
        <button
          type="button"
          class="batch-btn batch-btn--primary"
          :disabled="isSubmitting"
          @click="handleSubmit"
        >
          {{
            isSubmitting
              ? `${progress}/${form.count} angelegt...`
              : `${form.count} Pflanzen anlegen`
          }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
/* Mirrors PlantCreateModal styles for visual consistency */
.batch-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.batch-form__row {
  gap: var(--space-3);
}

.batch-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.batch-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.batch-form__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: inherit;
  outline: none;
  transition: border-color var(--transition-fast);
  min-height: 38px;
}

.batch-form__input:focus {
  border-color: var(--color-accent);
}

/* Progress */
.batch-form__progress {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.batch-form__progress-bar {
  height: 4px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.batch-form__progress-fill {
  height: 100%;
  background: var(--color-success);
  border-radius: var(--radius-full);
  transition: width var(--transition-fast);
}

.batch-form__progress-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-align: center;
}

.batch-form__error {
  padding: var(--space-2) var(--space-3);
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: var(--radius-sm);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.batch-form__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

/* Button styles mirrored from PlantCreateModal */
.batch-btn {
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

.batch-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.batch-btn--primary {
  background: var(--color-accent);
  color: white;
}

.batch-btn--primary:not(:disabled):hover {
  background: var(--color-accent-bright);
}

.batch-btn--ghost {
  background: transparent;
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.batch-btn--ghost:not(:disabled):hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}
</style>
