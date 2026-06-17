<script setup lang="ts">
/**
 * PlantPhaseChangeModal — Phase wechseln Dialog
 *
 * Posts a `phase_change` lifecycle event AND updates the plant.phase
 * via PATCH /v1/plants/{id} so the inventory reflects the new phase.
 */

import { ref, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { PLANT_PHASES, type Plant, type PlantPhase } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'

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

const newPhase = ref<PlantPhase>('clone')
const note = ref('')
const isSubmitting = ref(false)
const errorMessage = ref<string | null>(null)

watch(() => props.open, (isOpen) => {
  if (isOpen && props.plant) {
    newPhase.value = props.plant.phase
    note.value = ''
    errorMessage.value = null
  }
})

async function handleSubmit(): Promise<void> {
  if (!props.plant) return
  errorMessage.value = null

  if (newPhase.value === props.plant.phase) {
    errorMessage.value = 'Bitte eine andere Phase auswählen.'
    return
  }

  isSubmitting.value = true
  try {
    // 1) Lifecycle-Event (audit-trail)
    await plantsStore.addLifecycleEvent(props.plant.id, {
      event_type: 'phase_change',
      note: note.value.trim() || null,
      metadata: {
        from: props.plant.phase,
        to: newPhase.value,
      },
    })
    // 2) PATCH plant.phase so the inventory list reflects the change
    await plantsStore.updatePlant(props.plant.id, { phase: newPhase.value })

    toast.success(`Phase auf "${PLANT_PHASE_LABELS[newPhase.value]}" geändert`)
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
      <p class="phase-change-form__current">
        Aktuelle Phase:
        <strong>{{ PLANT_PHASE_LABELS[plant.phase] ?? plant.phase }}</strong>
      </p>

      <label class="phase-change-form__field">
        <span class="phase-change-form__label">Neue Phase *</span>
        <select v-model="newPhase" class="phase-change-form__input" required>
          <option v-for="phase in PLANT_PHASES" :key="phase" :value="phase">
            {{ PLANT_PHASE_LABELS[phase] }}
          </option>
        </select>
      </label>

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

.phase-change-form__current {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.phase-change-form__current strong {
  color: var(--color-text-primary);
}

.phase-change-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
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
