<script setup lang="ts">
type SpinnerSize = 'sm' | 'md' | 'lg' | 'xl'

interface Props {
  /** Spinner size */
  size?: SpinnerSize
  /** Color class for the spinner */
  color?: string
  /** Label text (for accessibility and display) */
  label?: string
  /** Whether to center the spinner in its container */
  center?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  size: 'md',
  color: 'border-t-blue-500',
  center: false,
})
void props // Used in template

const sizeClasses: Record<SpinnerSize, string> = {
  sm: 'w-4 h-4 border-2',
  md: 'w-8 h-8 border-2',
  lg: 'w-12 h-12 border-3',
  xl: 'w-16 h-16 border-4',
}
</script>

<template>
  <div
    :class="[
      'inline-flex flex-col items-center gap-2',
      center ? 'w-full justify-center py-8' : ''
    ]"
    role="status"
    aria-live="polite"
  >
    <div
      :class="[
        'animate-spin rounded-full border-dark-600',
        sizeClasses[size],
        color
      ]"
    />
    <span v-if="label" class="text-sm text-dark-400">{{ label }}</span>
    <span class="sr-only">{{ label || 'Loading...' }}</span>
  </div>
</template>
