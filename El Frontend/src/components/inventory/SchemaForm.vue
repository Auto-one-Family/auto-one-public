<script setup lang="ts">
/**
 * SchemaForm — Dynamic form renderer from JSON Schema.
 *
 * Renders input fields based on schema property definitions (type, enum, format, ui:widget).
 * Emits granular field changes so the parent can persist selectively.
 */

import { computed } from 'vue'
import type { SchemaProperty } from '@/config/device-schemas'

const props = defineProps<{
  /** Schema properties to render */
  properties: Record<string, SchemaProperty>
  /** Current field values */
  modelValue: Record<string, unknown>
  /** Section title displayed above the fields */
  title?: string
  /** Disable all fields */
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: Record<string, unknown>): void
  (e: 'field-change', key: string, value: unknown): void
}>()

const propertyEntries = computed(() =>
  Object.entries(props.properties)
)

function getFieldValue(key: string): unknown {
  return props.modelValue[key] ?? ''
}

function updateField(key: string, value: unknown) {
  const updated = { ...props.modelValue, [key]: value }
  emit('update:modelValue', updated)
  emit('field-change', key, value)
}

function getInputType(prop: SchemaProperty): string {
  if (prop.format === 'date') return 'date'
  if (prop.format === 'uri') return 'url'
  if (prop.type === 'number' || prop.type === 'integer') return 'number'
  return 'text'
}

function isTextarea(prop: SchemaProperty): boolean {
  return prop['ui:widget'] === 'textarea'
}

function isEnum(prop: SchemaProperty): boolean {
  return Array.isArray(prop.enum) && prop.enum.length > 0
}

function isBoolean(prop: SchemaProperty): boolean {
  return prop.type === 'boolean'
}

function isReadOnly(prop: SchemaProperty): boolean {
  return prop.readOnly === true
}

function displayReadOnlyValue(key: string, prop: SchemaProperty): string {
  const val = getFieldValue(key)
  if (val === '' || val == null) return prop.default != null ? String(prop.default) : '—'
  return String(val)
}
</script>

<template>
  <div class="schema-form">
    <h4 v-if="title" class="schema-form__title">{{ title }}</h4>

    <div class="schema-form__fields">
      <div
        v-for="[key, prop] in propertyEntries"
        :key="key"
        class="schema-form__field"
      >
        <label :for="`sf-${key}`" class="schema-form__label">
          {{ prop.title || key }}
        </label>

        <!-- ReadOnly Field (display as text) -->
        <span v-if="isReadOnly(prop)" class="schema-form__readonly">
          {{ displayReadOnlyValue(key, prop) }}
        </span>

        <!-- Boolean Toggle -->
        <div v-else-if="isBoolean(prop)" class="schema-form__toggle-row">
          <input
            :id="`sf-${key}`"
            type="checkbox"
            :checked="!!getFieldValue(key)"
            :disabled="disabled"
            class="schema-form__checkbox"
            @change="updateField(key, ($event.target as HTMLInputElement).checked)"
          />
          <span v-if="prop.description" class="schema-form__hint">{{ prop.description }}</span>
        </div>

        <!-- Enum Select -->
        <select
          v-else-if="isEnum(prop)"
          :id="`sf-${key}`"
          :value="getFieldValue(key)"
          :disabled="disabled"
          class="schema-form__select"
          @change="updateField(key, ($event.target as HTMLSelectElement).value)"
        >
          <option value="">— Auswählen —</option>
          <option
            v-for="opt in prop.enum"
            :key="String(opt)"
            :value="opt as string | number"
          >
            {{ opt }}
          </option>
        </select>

        <!-- Textarea -->
        <textarea
          v-else-if="isTextarea(prop)"
          :id="`sf-${key}`"
          :value="String(getFieldValue(key))"
          :disabled="disabled"
          :placeholder="prop.description"
          class="schema-form__textarea"
          rows="3"
          @input="updateField(key, ($event.target as HTMLTextAreaElement).value)"
        />

        <!-- Standard Input -->
        <input
          v-else
          :id="`sf-${key}`"
          :type="getInputType(prop)"
          :value="getFieldValue(key)"
          :disabled="disabled"
          :placeholder="prop.description"
          :min="prop.minimum"
          :max="prop.maximum"
          :step="prop.type === 'number' ? 'any' : undefined"
          class="schema-form__input"
          @input="updateField(key, getInputType(prop) === 'number'
            ? parseFloat(($event.target as HTMLInputElement).value) || undefined
            : ($event.target as HTMLInputElement).value)"
        />

        <span v-if="prop.description && !isBoolean(prop)" class="schema-form__hint">
          {{ prop.description }}
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.schema-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.schema-form__title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-1);
}

.schema-form__fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.schema-form__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.schema-form__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.schema-form__input,
.schema-form__select,
.schema-form__textarea {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}

.schema-form__input:focus,
.schema-form__select:focus,
.schema-form__textarea:focus {
  border-color: var(--color-accent);
}

.schema-form__input::placeholder,
.schema-form__textarea::placeholder {
  color: var(--color-text-muted);
}

.schema-form__input:disabled,
.schema-form__select:disabled,
.schema-form__textarea:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.schema-form__select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.schema-form__textarea {
  resize: vertical;
  min-height: 60px;
  font-family: inherit;
}

.schema-form__toggle-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.schema-form__checkbox {
  width: 16px;
  height: 16px;
  accent-color: var(--color-accent);
  cursor: pointer;
}

.schema-form__checkbox:disabled {
  cursor: not-allowed;
}

.schema-form__readonly {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  padding: var(--space-2) 0;
  font-style: italic;
}

.schema-form__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.3;
}
</style>
