<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'

interface Props {
  /** v-model value */
  modelValue: string | number
  /** Input type */
  type?: 'text' | 'email' | 'password' | 'number' | 'search' | 'tel' | 'url'
  /** Label text */
  label?: string
  /** Placeholder text */
  placeholder?: string
  /** Whether the input is disabled */
  disabled?: boolean
  /** Whether the input is required */
  required?: boolean
  /** Error message to display */
  error?: string
  /** Helper text to display below input */
  helper?: string
  /** Whether to show a clear button */
  clearable?: boolean
  /** Input id (auto-generated if not provided) */
  id?: string
  /** Min value for number inputs */
  min?: number
  /** Max value for number inputs */
  max?: number
  /** Step value for number inputs */
  step?: number
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  disabled: false,
  required: false,
  clearable: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const inputId = computed(() => props.id || `input-${Math.random().toString(36).slice(2, 9)}`)

const inputClasses = computed(() => [
  'base-input w-full px-4 py-2.5 border rounded-lg',
  'focus:outline-none',
  'transition-all duration-200',
  'touch-target',
  props.error ? 'base-input--error' : '',
  props.disabled ? 'opacity-50 cursor-not-allowed' : '',
  props.clearable && props.modelValue ? 'pr-10' : '',
])

function handleInput(event: Event) {
  const target = event.target as HTMLInputElement
  const value = props.type === 'number' ? parseFloat(target.value) || 0 : target.value
  emit('update:modelValue', value)
}

function clear() {
  emit('update:modelValue', props.type === 'number' ? 0 : '')
}
</script>

<template>
  <div class="w-full">
    <!-- Label -->
    <label
      v-if="label"
      :for="inputId"
      class="base-input__label block text-sm font-medium mb-1.5"
    >
      {{ label }}
      <span v-if="required" class="base-input__required ml-0.5">*</span>
    </label>

    <!-- Input wrapper -->
    <div class="relative">
      <input
        :id="inputId"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        :min="min"
        :max="max"
        :step="step"
        :class="inputClasses"
        @input="handleInput"
      />

      <!-- Clear button -->
      <button
        v-if="clearable && modelValue"
        type="button"
        class="base-input__clear absolute right-2 top-1/2 -translate-y-1/2 p-1 transition-colors"
        @click="clear"
      >
        <X class="w-4 h-4" />
      </button>
    </div>

    <!-- Error message -->
    <p v-if="error" class="base-input__error mt-1.5 text-sm">
      {{ error }}
    </p>

    <!-- Helper text -->
    <p v-else-if="helper" class="base-input__helper mt-1.5 text-sm">
      {{ helper }}
    </p>
  </div>
</template>

<style scoped>
.base-input__label {
  color: var(--color-text-secondary);
}

.base-input__required {
  color: var(--color-error);
}

.base-input {
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border-l2);
  color: var(--color-text-primary);
}

.base-input::placeholder {
  color: var(--color-text-muted);
}

.base-input:focus {
  border-color: transparent;
  box-shadow: 0 0 0 2px var(--color-accent);
}

.base-input--error {
  border-color: var(--color-error);
}

.base-input--error:focus {
  box-shadow: 0 0 0 2px var(--color-error);
}

.base-input__clear {
  color: var(--color-text-muted);
}

.base-input__clear:hover {
  color: var(--color-text-primary);
}

.base-input__error {
  color: var(--color-error);
}

.base-input__helper {
  color: var(--color-text-muted);
}
</style>
