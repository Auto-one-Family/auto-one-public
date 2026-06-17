<script setup lang="ts">
/**
 * FormField Component
 *
 * Renders a single form field based on its schema type.
 * Maps type to the appropriate BaseInput/BaseSelect/BaseToggle primitive.
 */

import { computed } from 'vue'
import type { FormFieldSchema } from '@/types/form-schema'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import BaseToggle from '@/shared/design/primitives/BaseToggle.vue'

interface Props {
  /** Field schema definition */
  schema: FormFieldSchema
  /** Current field value */
  modelValue: unknown
  /** Validation error message */
  error?: string
  /** Override disabled state */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  error: '',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const isDisabled = computed(() => props.disabled || props.schema.disabled)

const selectOptions = computed(() =>
  (props.schema.options ?? []).map(o => ({
    value: String(o.value),
    label: o.label,
  }))
)

function handleInput(value: unknown): void {
  // Convert string to number for number/range fields
  if (props.schema.type === 'number' || props.schema.type === 'range') {
    const num = Number(value)
    emit('update:modelValue', isNaN(num) ? value : num)
  } else {
    emit('update:modelValue', value)
  }
}
</script>

<template>
  <div class="form-field">
    <!-- Text / Number Input -->
    <BaseInput
      v-if="schema.type === 'text' || schema.type === 'number'"
      :type="schema.type"
      :model-value="String(modelValue ?? '')"
      :label="schema.label"
      :placeholder="schema.placeholder"
      :error="error"
      :helper="schema.helper"
      :disabled="isDisabled"
      :min="schema.min"
      :max="schema.max"
      :step="schema.step"
      @update:model-value="handleInput"
    />

    <!-- Range Slider -->
    <div v-else-if="schema.type === 'range'" class="form-field__range">
      <label class="form-field__label">{{ schema.label }}</label>
      <div class="form-field__range-row">
        <input
          type="range"
          class="form-field__slider"
          :value="modelValue"
          :min="schema.min ?? 0"
          :max="schema.max ?? 100"
          :step="schema.step ?? 1"
          :disabled="isDisabled"
          @input="handleInput(($event.target as HTMLInputElement).value)"
        />
        <span class="form-field__range-value">{{ modelValue }}</span>
      </div>
      <span v-if="schema.helper" class="form-field__helper">{{ schema.helper }}</span>
      <span v-if="error" class="form-field__error">{{ error }}</span>
    </div>

    <!-- Select -->
    <BaseSelect
      v-else-if="schema.type === 'select' || schema.type === 'gpio-select'"
      :model-value="String(modelValue ?? '')"
      :label="schema.label"
      :options="selectOptions"
      :error="error"
      :helper="schema.helper"
      :disabled="isDisabled"
      @update:model-value="handleInput"
    />

    <!-- Toggle -->
    <BaseToggle
      v-else-if="schema.type === 'toggle'"
      :model-value="Boolean(modelValue)"
      :label="schema.label"
      :description="schema.helper"
      :disabled="isDisabled"
      @update:model-value="emit('update:modelValue', $event)"
    />
  </div>
</template>

<style scoped>
.form-field {
  width: 100%;
}

.form-field__range {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.form-field__label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.form-field__range-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.form-field__slider {
  flex: 1;
  height: 4px;
  appearance: none;
  -webkit-appearance: none;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-xs);
  outline: none;
}

.form-field__slider::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-accent);
  cursor: pointer;
}

.form-field__range-value {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  min-width: 40px;
  text-align: right;
}

.form-field__helper {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.form-field__error {
  font-size: var(--text-xs);
  color: var(--color-error);
}
</style>
