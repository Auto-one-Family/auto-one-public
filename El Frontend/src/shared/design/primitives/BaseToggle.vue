<script setup lang="ts">
import { computed } from 'vue'

type ToggleSize = 'sm' | 'md' | 'lg'

interface Props {
  /** v-model value */
  modelValue: boolean
  /** Toggle size */
  size?: ToggleSize
  /** Whether the toggle is disabled */
  disabled?: boolean
  /** Label text */
  label?: string
  /** Description text */
  description?: string
  /** Color when active */
  activeColor?: 'blue' | 'green' | 'red' | 'orange' | 'purple'
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  disabled: false,
  activeColor: 'blue',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const sizeClasses = computed(() => {
  const sizes: Record<ToggleSize, { track: string; thumb: string; translate: string }> = {
    sm: {
      track: 'w-8 h-4',
      thumb: 'w-3 h-3',
      translate: 'translate-x-4',
    },
    md: {
      track: 'w-11 h-6',
      thumb: 'w-5 h-5',
      translate: 'translate-x-5',
    },
    lg: {
      track: 'w-14 h-8',
      thumb: 'w-7 h-7',
      translate: 'translate-x-6',
    },
  }
  return sizes[props.size]
})

const activeColorClasses: Record<string, string> = {
  blue: 'bg-blue-600',
  green: 'bg-green-600',
  red: 'bg-red-600',
  orange: 'bg-orange-600',
  purple: 'bg-purple-600',
}

function toggle() {
  if (!props.disabled) {
    emit('update:modelValue', !props.modelValue)
  }
}
</script>

<template>
  <div
    class="flex items-start gap-3"
    :class="disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'"
    @click="toggle"
  >
    <!-- Toggle switch -->
    <button
      type="button"
      role="switch"
      :aria-checked="modelValue"
      :disabled="disabled"
      :class="[
        'relative inline-flex flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out',
        'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-dark-900',
        sizeClasses.track,
        modelValue ? activeColorClasses[activeColor] : 'bg-dark-600'
      ]"
      @click.stop="toggle"
    >
      <span
        :class="[
          'pointer-events-none inline-block rounded-full bg-white shadow-lg transform transition-transform duration-200 ease-in-out',
          sizeClasses.thumb,
          modelValue ? sizeClasses.translate : 'translate-x-0.5',
          'mt-0.5 ml-0.5'
        ]"
      />
    </button>

    <!-- Label and description -->
    <div v-if="label || description" class="flex flex-col">
      <span v-if="label" class="text-sm font-medium text-dark-100">
        {{ label }}
      </span>
      <span v-if="description" class="text-sm text-dark-400">
        {{ description }}
      </span>
    </div>
  </div>
</template>
