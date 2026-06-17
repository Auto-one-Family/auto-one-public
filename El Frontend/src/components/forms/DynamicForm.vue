<script setup lang="ts">
/**
 * DynamicForm Component
 *
 * Renders a complete form from a declarative FormSchema.
 * Iterates groups → fields, handles conditional visibility (dependsOn),
 * and provides v-model binding for form data.
 */

import type { FormSchema, FormFieldSchema } from '@/types/form-schema'
import FormGroup from './FormGroup.vue'
import FormField from './FormField.vue'

interface Props {
  /** Form schema definition */
  schema: FormSchema
  /** Form data (v-model) */
  modelValue: Record<string, unknown>
  /** Disable all fields */
  disabled?: boolean
  /** Show loading state */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  loading: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: Record<string, unknown>]
  submit: []
  'field-change': [key: string, value: unknown]
}>()

/**
 * Check if a field should be visible based on its dependsOn condition.
 */
function isFieldVisible(field: FormFieldSchema): boolean {
  if (!field.dependsOn) return true

  const { field: depKey, value: depValue, operator = '==' } = field.dependsOn
  const currentValue = props.modelValue[depKey]

  switch (operator) {
    case '==': return currentValue === depValue
    case '!=': return currentValue !== depValue
    case '>': return Number(currentValue) > Number(depValue)
    case '<': return Number(currentValue) < Number(depValue)
    default: return true
  }
}

/**
 * Update a single field value, emit the full updated model.
 */
function updateField(key: string, value: unknown): void {
  const updated = { ...props.modelValue, [key]: value }
  emit('update:modelValue', updated)
  emit('field-change', key, value)
}

function handleSubmit(e: Event): void {
  e.preventDefault()
  emit('submit')
}
</script>

<template>
  <form
    class="dynamic-form"
    :class="{ 'dynamic-form--loading': loading }"
    @submit="handleSubmit"
  >
    <FormGroup
      v-for="(group, gi) in schema.groups"
      :key="gi"
      :schema="group"
    >
      <template v-for="field in group.fields" :key="field.key">
        <FormField
          v-show="isFieldVisible(field)"
          :schema="field"
          :model-value="modelValue[field.key]"
          :disabled="disabled || loading"
          @update:model-value="updateField(field.key, $event)"
        />
      </template>
    </FormGroup>

    <slot name="actions" />
  </form>
</template>

<style scoped>
.dynamic-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.dynamic-form--loading {
  opacity: 0.6;
  pointer-events: none;
}
</style>
