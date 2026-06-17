<script setup lang="ts">
import { computed } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

interface SelectOption {
  value: string | number
  label: string
  disabled?: boolean
}

interface Props {
  /** v-model value */
  modelValue: string | number
  /** Options to display */
  options: SelectOption[]
  /** Label text */
  label?: string
  /** Placeholder text */
  placeholder?: string
  /** Whether the select is disabled */
  disabled?: boolean
  /** Whether the select is required */
  required?: boolean
  /** Error message to display */
  error?: string
  /** Helper text to display below select */
  helper?: string
  /** Select id (auto-generated if not provided) */
  id?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  required: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const selectId = computed(() => props.id || `select-${Math.random().toString(36).slice(2, 9)}`)

const selectClasses = computed(() => [
  'base-select w-full px-4 py-2.5 border rounded-lg',
  'focus:outline-none',
  'transition-all duration-200',
  'appearance-none cursor-pointer',
  'touch-target',
  'pr-10', // Space for chevron
  props.error ? 'base-select--error' : '',
  props.disabled ? 'opacity-50 cursor-not-allowed' : '',
])

function handleChange(event: Event) {
  const target = event.target as HTMLSelectElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <div class="w-full">
    <!-- Label -->
    <label
      v-if="label"
      :for="selectId"
      class="base-select__label block text-sm font-medium mb-1.5"
    >
      {{ label }}
      <span v-if="required" class="base-select__required ml-0.5">*</span>
    </label>

    <!-- Select wrapper -->
    <div class="relative">
      <select
        :id="selectId"
        :value="modelValue"
        :disabled="disabled"
        :required="required"
        :class="selectClasses"
        @change="handleChange"
      >
        <option v-if="placeholder" value="" disabled>
          {{ placeholder }}
        </option>
        <option
          v-for="option in options"
          :key="option.value"
          :value="option.value"
          :disabled="option.disabled"
        >
          {{ option.label }}
        </option>
      </select>

      <!-- Chevron icon -->
      <div class="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none">
        <ChevronDown class="base-select__chevron w-5 h-5" />
      </div>
    </div>

    <!-- Error message -->
    <p v-if="error" class="base-select__error mt-1.5 text-sm">
      {{ error }}
    </p>

    <!-- Helper text -->
    <p v-else-if="helper" class="base-select__helper mt-1.5 text-sm">
      {{ helper }}
    </p>
  </div>
</template>

<style scoped>
/* Remove default select arrow in some browsers */
select {
  background-image: none;
}

.base-select__label {
  color: var(--color-text-secondary);
}

.base-select__required {
  color: var(--color-error);
}

.base-select {
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border-l2);
  color: var(--color-text-primary);
}

.base-select:focus {
  border-color: transparent;
  box-shadow: 0 0 0 2px var(--color-accent);
}

.base-select--error {
  border-color: var(--color-error);
}

.base-select--error:focus {
  box-shadow: 0 0 0 2px var(--color-error);
}

.base-select__chevron {
  color: var(--color-text-muted);
}

.base-select__error {
  color: var(--color-error);
}

.base-select__helper {
  color: var(--color-text-muted);
}
</style>
