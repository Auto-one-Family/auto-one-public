<script setup lang="ts">
/**
 * SubzoneContextEditor — Form for subzone-level metadata.
 *
 * Manages subzone-specific custom_data: plant info, material, notes
 * that are more specific than the zone-level context.
 */

import { ref, onMounted } from 'vue'
import { Save, Leaf } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { subzonesApi } from '@/api/subzones'

const props = defineProps<{
  espId: string
  subzoneId: string
  subzoneName?: string
  initialData?: Record<string, unknown>
}>()

const emit = defineEmits<{
  (e: 'saved', data: Record<string, unknown>): void
}>()

const { success, error: showError } = useToast()

const isSaving = ref(false)
const isDirty = ref(false)

const form = ref({
  variety: '',
  substrate: '',
  notes: '',
  responsible_person: '',
})

function loadFromData(data: Record<string, unknown> | undefined) {
  if (!data) return
  form.value.variety = (data.variety as string) || ''
  form.value.substrate = (data.substrate as string) || ''
  form.value.notes = (data.notes as string) || ''
  form.value.responsible_person = (data.responsible_person as string) || ''
}

onMounted(() => {
  loadFromData(props.initialData)
})

function markDirty() {
  isDirty.value = true
}

async function save() {
  isSaving.value = true
  try {
    const customData: Record<string, unknown> = {}
    if (form.value.variety) customData.variety = form.value.variety
    if (form.value.substrate) customData.substrate = form.value.substrate
    if (form.value.notes) customData.notes = form.value.notes
    if (form.value.responsible_person) customData.responsible_person = form.value.responsible_person

    const result = await subzonesApi.updateMetadata(props.espId, props.subzoneId, customData)
    isDirty.value = false
    success('Subzone-Metadaten gespeichert')
    emit('saved', result.custom_data || {})
  } catch (e) {
    showError(e instanceof Error ? e.message : 'Fehler beim Speichern')
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="subzone-ctx">
    <div class="subzone-ctx__header">
      <Leaf :size="16" class="text-[var(--color-iridescent-3)]" />
      <span class="text-sm font-medium text-[var(--color-text-primary)]">
        Subzone-Metadaten{{ subzoneName ? `: ${subzoneName}` : '' }}
      </span>
    </div>

    <div class="subzone-ctx__grid">
      <label class="subzone-ctx__label">
        <span class="text-xs text-[var(--color-text-muted)]">Sorte / Variante</span>
        <input
          v-model="form.variety"
          type="text"
          placeholder="z.B. Wedding Cake"
          class="subzone-ctx__input"
          @input="markDirty"
        />
      </label>

      <label class="subzone-ctx__label">
        <span class="text-xs text-[var(--color-text-muted)]">Substrat</span>
        <input
          v-model="form.substrate"
          type="text"
          placeholder="z.B. Coco/Perlite"
          class="subzone-ctx__input"
          @input="markDirty"
        />
      </label>

      <label class="subzone-ctx__label">
        <span class="text-xs text-[var(--color-text-muted)]">Verantwortlich</span>
        <input
          v-model="form.responsible_person"
          type="text"
          placeholder="z.B. Robin"
          class="subzone-ctx__input"
          @input="markDirty"
        />
      </label>

      <label class="subzone-ctx__label col-span-full">
        <span class="text-xs text-[var(--color-text-muted)]">Notizen</span>
        <textarea
          v-model="form.notes"
          rows="2"
          placeholder="Subzone-spezifische Notizen..."
          class="subzone-ctx__input"
          @input="markDirty"
        />
      </label>
    </div>

    <div v-if="isDirty" class="subzone-ctx__actions">
      <button
        class="subzone-ctx__save"
        :disabled="isSaving"
        @click="save"
      >
        <Save :size="14" />
        {{ isSaving ? 'Speichern...' : 'Speichern' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.subzone-ctx {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(255, 255, 255, 0.06);
}

.subzone-ctx__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.subzone-ctx__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
}

.subzone-ctx__label {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.col-span-full {
  grid-column: 1 / -1;
}

.subzone-ctx__input {
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-secondary);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--transition-fast);
  resize: vertical;
}

.subzone-ctx__input:focus {
  border-color: var(--color-iridescent-2);
}

.subzone-ctx__actions {
  display: flex;
  justify-content: flex-end;
}

.subzone-ctx__save {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  background: var(--color-iridescent-2);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.subzone-ctx__save:hover {
  opacity: 0.85;
}

.subzone-ctx__save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
