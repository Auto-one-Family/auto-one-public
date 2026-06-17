<script setup lang="ts">
/**
 * PluginConfigDialog
 *
 * Dynamic configuration dialog for AutoOps plugins.
 * Renders config fields based on the plugin's config_schema.
 */

import { ref, watch, computed } from 'vue'
import { Save, X } from 'lucide-vue-next'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'

interface Props {
  visible: boolean
  pluginId: string
  pluginName: string
  config: Record<string, unknown>
  configSchema: Record<string, unknown>
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', config: Record<string, unknown>): void
}>()

const localConfig = ref<Record<string, unknown>>({})

// Sync when dialog opens
watch(
  () => props.visible,
  (v) => {
    if (v) {
      localConfig.value = JSON.parse(JSON.stringify(props.config))
    }
  },
)

/**
 * Parse config schema into renderable fields.
 * Supports simple schema: { key: { type, description, default } }
 */
const configFields = computed(() => {
  const schema = props.configSchema || {}
  return Object.entries(schema).map(([key, def]) => {
    const fieldDef = (def || {}) as Record<string, unknown>
    return {
      key,
      type: (fieldDef.type as string) || 'string',
      label: (fieldDef.label as string) || (fieldDef.description as string) || key,
      defaultValue: fieldDef.default,
      options: (fieldDef.options as string[]) || [],
    }
  })
})

function updateField(key: string, value: unknown) {
  localConfig.value[key] = value
}

function handleSave() {
  emit('save', { ...localConfig.value })
}
</script>

<template>
  <BaseModal
    :open="visible"
    :title="`${pluginName} — Konfiguration`"
    max-width="max-w-lg"
    @close="emit('close')"
  >
    <div class="config-dialog">
      <!-- No schema available -->
      <div v-if="configFields.length === 0" class="config-dialog__empty">
        <p>Keine konfigurierbaren Parameter vorhanden.</p>
        <p class="config-dialog__empty-hint">
          Aktuelle Konfiguration als JSON:
        </p>
        <pre class="config-dialog__json">{{ JSON.stringify(config, null, 2) }}</pre>
      </div>

      <!-- Dynamic fields -->
      <div v-else class="config-dialog__fields">
        <div
          v-for="field in configFields"
          :key="field.key"
          class="config-dialog__field"
        >
          <label class="config-dialog__label">
            {{ field.label }}
            <span class="config-dialog__field-key">({{ field.key }})</span>
          </label>

          <!-- Boolean -->
          <div v-if="field.type === 'boolean'" class="config-dialog__toggle-row">
            <input
              type="checkbox"
              :checked="!!localConfig[field.key]"
              class="config-dialog__checkbox"
              @change="updateField(field.key, ($event.target as HTMLInputElement).checked)"
            />
            <span class="config-dialog__toggle-label">
              {{ localConfig[field.key] ? 'Aktiv' : 'Inaktiv' }}
            </span>
          </div>

          <!-- Select -->
          <select
            v-else-if="field.type === 'select' && field.options.length > 0"
            :value="(localConfig[field.key] as string) ?? (field.defaultValue as string) ?? ''"
            class="config-dialog__input"
            @change="updateField(field.key, ($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="opt in field.options"
              :key="opt"
              :value="opt"
            >
              {{ opt }}
            </option>
          </select>

          <!-- Number -->
          <input
            v-else-if="field.type === 'number' || field.type === 'integer'"
            type="number"
            :value="(localConfig[field.key] as number) ?? field.defaultValue ?? 0"
            class="config-dialog__input"
            @input="updateField(field.key, Number(($event.target as HTMLInputElement).value))"
          />

          <!-- String (default) -->
          <input
            v-else
            type="text"
            :value="(localConfig[field.key] as string) ?? (field.defaultValue as string) ?? ''"
            class="config-dialog__input"
            @input="updateField(field.key, ($event.target as HTMLInputElement).value)"
          />
        </div>
      </div>
    </div>

    <!-- Footer -->
    <template #footer>
      <div class="config-dialog__footer">
        <button class="config-dialog__btn config-dialog__btn--cancel" @click="emit('close')">
          <X class="w-4 h-4" />
          Abbrechen
        </button>
        <button class="config-dialog__btn config-dialog__btn--save" @click="handleSave">
          <Save class="w-4 h-4" />
          Speichern
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.config-dialog {
  padding: 0.5rem 0;
}

.config-dialog__empty {
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.config-dialog__empty-hint {
  margin-top: 0.75rem;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.config-dialog__json {
  margin-top: 0.5rem;
  padding: 0.75rem;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  text-align: left;
  overflow-x: auto;
  max-height: 200px;
}

.config-dialog__fields {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.config-dialog__field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.config-dialog__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.config-dialog__field-key {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: var(--font-mono);
}

.config-dialog__input {
  padding: 0.5rem 0.75rem;
  font-size: var(--text-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color var(--transition-fast);
}

.config-dialog__input:focus {
  border-color: var(--color-iridescent-2);
}

.config-dialog__toggle-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.config-dialog__checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--color-iridescent-2);
}

.config-dialog__toggle-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.config-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.config-dialog__btn {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: var(--text-sm);
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.config-dialog__btn--cancel {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
}

.config-dialog__btn--cancel:hover {
  color: var(--color-text-primary);
  border-color: var(--color-text-muted);
}

.config-dialog__btn--save {
  background: rgba(129, 140, 248, 0.1);
  color: var(--color-iridescent-2);
  border-color: rgba(129, 140, 248, 0.3);
}

.config-dialog__btn--save:hover {
  background: rgba(129, 140, 248, 0.2);
}
</style>
