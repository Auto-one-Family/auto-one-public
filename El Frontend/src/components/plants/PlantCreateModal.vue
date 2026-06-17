<script setup lang="ts">
/**
 * PlantCreateModal — "Neue Pflanze" Dialog
 *
 * Form fields: genotype, batch, zone_id, subzone_id, planting_date, phase.
 * Posts via plantsStore.createPlant() (POST /v1/plants).
 *
 * Used in SensorsView Pflanzen-Tab (AUT-221).
 */

import { ref, computed, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { PLANT_PHASES, type PlantCreate, type PlantPhase } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'

interface Props {
  open: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  created: [plantId: string]
}>()

const plantsStore = usePlantsStore()
const zoneStore = useZoneStore()
const toast = useToast()

interface FormState {
  genotype: string
  batch: string
  zone_id: string
  subzone_id: string
  planting_date: string
  phase: PlantPhase
}

function emptyForm(): FormState {
  return {
    genotype: '',
    batch: '',
    zone_id: '',
    subzone_id: '',
    planting_date: new Date().toISOString().slice(0, 10),
    phase: 'clone',
  }
}

const form = ref<FormState>(emptyForm())
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

const availableZones = computed(() => zoneStore.activeZones)

// Reset form when modal opens
watch(() => props.open, (isOpen) => {
  if (isOpen) {
    form.value = emptyForm()
    errorMessage.value = null
    if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
      void zoneStore.fetchZoneEntities()
    }
  }
})

function validate(): string | null {
  const v = form.value
  if (!v.genotype.trim()) return 'Genotyp ist erforderlich.'
  if (!v.phase) return 'Phase ist erforderlich.'
  return null
}

async function handleSubmit(): Promise<void> {
  errorMessage.value = null
  const validation = validate()
  if (validation) {
    errorMessage.value = validation
    return
  }

  const payload: PlantCreate = {
    genotype: form.value.genotype.trim(),
    phase: form.value.phase,
    batch: form.value.batch.trim() || null,
    zone_id: form.value.zone_id || null,
    subzone_id: form.value.subzone_id.trim() || null,
    planting_date: form.value.planting_date || null,
  }

  isSubmitting.value = true
  try {
    const created = await plantsStore.createPlant(payload)
    toast.success(`Pflanze ${created.qr_code || created.genotype} angelegt`)
    emit('created', created.id)
    emit('close')
  } catch (e) {
    const message = e instanceof Error ? e.message : 'Anlegen fehlgeschlagen'
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
    title="Neue Pflanze"
    max-width="max-w-lg"
    @close="handleClose"
  >
    <form class="plant-create-form" @submit.prevent="handleSubmit">
      <label class="plant-create-form__field">
        <span class="plant-create-form__label">Genotyp *</span>
        <input
          v-model="form.genotype"
          type="text"
          class="plant-create-form__input"
          placeholder="z.B. Northern Lights"
          required
          autofocus
        />
      </label>

      <div class="plant-create-form__row grid-auto-sm">
        <label class="plant-create-form__field">
          <span class="plant-create-form__label">Charge</span>
          <input
            v-model="form.batch"
            type="text"
            class="plant-create-form__input"
            placeholder="z.B. 2026-NL-A"
          />
        </label>

        <label class="plant-create-form__field">
          <span class="plant-create-form__label">Pflanzdatum</span>
          <input
            v-model="form.planting_date"
            type="date"
            class="plant-create-form__input"
          />
        </label>
      </div>

      <label class="plant-create-form__field">
        <span class="plant-create-form__label">Phase *</span>
        <select v-model="form.phase" class="plant-create-form__input" required>
          <option v-for="phase in PLANT_PHASES" :key="phase" :value="phase">
            {{ PLANT_PHASE_LABELS[phase] }}
          </option>
        </select>
      </label>

      <div class="plant-create-form__row grid-auto-sm">
        <label class="plant-create-form__field">
          <span class="plant-create-form__label">Zone</span>
          <select v-model="form.zone_id" class="plant-create-form__input">
            <option value="">Keine Zone</option>
            <option v-for="zone in availableZones" :key="zone.zone_id" :value="zone.zone_id">
              {{ zone.name }}
            </option>
          </select>
        </label>

        <label class="plant-create-form__field">
          <span class="plant-create-form__label">Subzone</span>
          <input
            v-model="form.subzone_id"
            type="text"
            class="plant-create-form__input"
            placeholder="z.B. north_bench"
          />
        </label>
      </div>

      <div v-if="errorMessage" class="plant-create-form__error">
        {{ errorMessage }}
      </div>
    </form>

    <template #footer>
      <div class="plant-create-form__actions">
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
          {{ isSubmitting ? 'Wird angelegt...' : 'Anlegen' }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.plant-create-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.plant-create-form__row {
  gap: var(--space-3);
}

.plant-create-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.plant-create-form__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.plant-create-form__input {
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

.plant-create-form__input:focus {
  border-color: var(--color-accent);
}

.plant-create-form__error {
  padding: var(--space-2) var(--space-3);
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: var(--radius-sm);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.plant-create-form__actions {
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
