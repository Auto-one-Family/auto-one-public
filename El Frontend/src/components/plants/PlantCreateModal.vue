<script setup lang="ts">
/**
 * PlantCreateModal — "Neue Pflanze" Dialog / "Stammdaten bearbeiten" Dialog
 *
 * AUT-1178: aligned to server PlantCreate schema.
 * - genotype_label / batch_label (server field names)
 * - zone_id is local-only (used to filter subzone options, NOT sent to server)
 * - availableSubzones uses device.subzones[] (SubzoneSummary n:m, AUT-1155)
 * - POST payload: genotype_label, batch_label, subzone_id (UUID), phase, planting_date,
 *   cultivar_or_variety
 *
 * AUT-1182: edit mode via optional `editPlant` prop.
 * - When editPlant is set, the dialog switches to "Stammdaten bearbeiten" mode.
 * - PATCH payload: genotype_label + cultivar_or_variety (only patchable Stammdaten fields).
 * - Server PlantUpdate accepts subzone_id (AUT-1266); batch_label / planting_date still not.
 * - Phase change has its own dedicated PlantPhaseChangeModal.
 *
 * Posts via plantsStore.createPlant() (POST /v1/plants).
 * Patches via plantsStore.updatePlant() (PATCH /v1/plants/{id}).
 *
 * Used in PlantsView (AUT-1159 / AUT-1160) and PlantDetailPanel (AUT-1182).
 */

import { ref, computed, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useEspStore } from '@/stores/esp'
import { PLANT_PHASES, type Plant, type PlantCreate, type PlantUpdate, type PlantPhase } from '@/types'
import { PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'

interface Props {
  open: boolean
  /**
   * When set the dialog operates in "edit" mode: pre-fills the form with the
   * plant's current Stammdaten and calls updatePlant (PATCH) on submit.
   * The title and submit-button label adapt automatically.
   */
  editPlant?: Plant
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  created: [plantId: string]
  /** Emitted after a successful PATCH update (edit mode). */
  updated: [plantId: string]
}>()

const plantsStore = usePlantsStore()
const zoneStore = useZoneStore()
const espStore = useEspStore()
const toast = useToast()

/** True when the dialog is operating in edit-mode (editPlant prop set). */
const isEditMode = computed(() => !!props.editPlant)

interface FormState {
  /** Server field: genotype_label */
  genotype_label: string
  /** Server field: cultivar_or_variety — shown in both create and edit modes */
  cultivar_or_variety: string
  /** Server field: batch_label — create-only (not patchable via PATCH) */
  batch_label: string
  /** Local-only: used to filter subzone options, NOT sent to server */
  zone_id: string
  subzone_id: string
  planting_date: string
  phase: PlantPhase
}

function emptyForm(): FormState {
  return {
    genotype_label: '',
    cultivar_or_variety: '',
    batch_label: '',
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

/**
 * Subzone options scoped to the selected zone.
 *
 * AUT-1178: Uses device.subzones[] (SubzoneSummary[], n:m via AUT-1155)
 * instead of the deprecated singular device.subzone_id. This correctly
 * handles devices that are assigned to multiple subzones.
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
watch(
  () => form.value.zone_id,
  () => {
    form.value.subzone_id = ''
  },
)

// Reset / pre-fill form when modal opens
watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      errorMessage.value = null
      if (props.editPlant) {
        // Edit mode: pre-fill from existing plant's Stammdaten
        form.value = {
          genotype_label: props.editPlant.genotype_label ?? '',
          cultivar_or_variety: props.editPlant.cultivar_or_variety ?? '',
          // Fields below are not shown/sent in edit mode
          batch_label: '',
          zone_id: '',
          subzone_id: '',
          planting_date: '',
          phase: props.editPlant.phase,
        }
      } else {
        form.value = emptyForm()
        if (zoneStore.zoneEntities.length === 0 && !zoneStore.isLoadingZones) {
          void zoneStore.fetchZoneEntities()
        }
      }
    }
  },
)

function validate(): string | null {
  const v = form.value
  if (!v.genotype_label.trim()) return 'Genotyp ist erforderlich.'
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

  isSubmitting.value = true
  try {
    if (isEditMode.value && props.editPlant) {
      // AUT-1182: edit mode — PATCH only the patchable Stammdaten fields.
      // Edit mode: location fields stay hidden (create-only UI). AUT-1266 writes
      // Ort via drag-and-drop (subzone_id), not this modal.
      const payload: PlantUpdate = {
        genotype_label: form.value.genotype_label.trim(),
        cultivar_or_variety: form.value.cultivar_or_variety.trim() || null,
      }
      const updated = await plantsStore.updatePlant(props.editPlant.plant_id, payload)
      toast.success(`${updated.genotype_label} aktualisiert`)
      emit('updated', updated.plant_id)
      emit('close')
    } else {
      // AUT-1178: create mode — use server-canonical field names; zone_id is local-only.
      const payload: PlantCreate = {
        genotype_label: form.value.genotype_label.trim(),
        phase: form.value.phase,
        batch_label: form.value.batch_label.trim() || null,
        subzone_id: form.value.subzone_id.trim() || null,
        planting_date: form.value.planting_date || null,
        cultivar_or_variety: form.value.cultivar_or_variety.trim() || null,
      }
      const created = await plantsStore.createPlant(payload)
      toast.success(`Pflanze ${created.qr_code || created.genotype_label} angelegt`)
      emit('created', created.plant_id)
      emit('close')
    }
  } catch (e) {
    const message = e instanceof Error
      ? e.message
      : isEditMode.value ? 'Aktualisieren fehlgeschlagen' : 'Anlegen fehlgeschlagen'
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
    :title="isEditMode ? 'Stammdaten bearbeiten' : 'Neue Pflanze'"
    max-width="max-w-lg"
    @close="handleClose"
  >
    <form class="plant-create-form" @submit.prevent="handleSubmit">
      <!-- ── Genotyp — always shown ── -->
      <label class="plant-create-form__field">
        <span class="plant-create-form__label">Genotyp *</span>
        <input
          v-model="form.genotype_label"
          type="text"
          class="plant-create-form__input"
          placeholder="z.B. Northern Lights"
          required
          autofocus
        />
      </label>

      <!-- ── Sorte / Varietät — always shown (AUT-1182) ── -->
      <label class="plant-create-form__field">
        <span class="plant-create-form__label">Sorte / Varietät</span>
        <input
          v-model="form.cultivar_or_variety"
          type="text"
          class="plant-create-form__input"
          placeholder="z.B. Auto-flowering, OG Kush #4"
        />
      </label>

      <!-- ── Create-only fields (hidden in edit mode) ── -->
      <template v-if="!isEditMode">
        <div class="plant-create-form__row grid-auto-sm">
          <label class="plant-create-form__field">
            <span class="plant-create-form__label">Charge</span>
            <input
              v-model="form.batch_label"
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
            <select
              v-model="form.subzone_id"
              class="plant-create-form__input"
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
      </template>

      <!-- ── Edit-mode hint ── -->
      <p v-if="isEditMode" class="plant-create-form__hint">
        Nur Genotyp und Sorte können hier korrigiert werden.
        Phase wechseln über „Phase wechseln".
      </p>

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
          <template v-if="isEditMode">
            {{ isSubmitting ? 'Wird gespeichert...' : 'Speichern' }}
          </template>
          <template v-else>
            {{ isSubmitting ? 'Wird angelegt...' : 'Anlegen' }}
          </template>
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

.plant-create-form__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
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
