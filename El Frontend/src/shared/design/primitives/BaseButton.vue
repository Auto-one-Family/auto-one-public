<script setup lang="ts">
/**
 * Button Component
 * 
 * A versatile button component with support for:
 * - Multiple variants including primary with iridescent gradient
 * - Multiple sizes
 * - Loading state with spinner
 * - Icon slots
 * - Full width option
 */

import { computed } from 'vue'

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'success' | 'ghost' | 'outline'
type ButtonSize = 'sm' | 'md' | 'lg'

interface Props {
  /** Button variant/style */
  variant?: ButtonVariant
  /** Button size */
  size?: ButtonSize
  /** Whether the button is disabled */
  disabled?: boolean
  /** Whether to show loading spinner */
  loading?: boolean
  /** Whether the button should take full width */
  fullWidth?: boolean
  /** HTML button type */
  type?: 'button' | 'submit' | 'reset'
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  fullWidth: false,
  type: 'button',
})

const buttonClasses = computed(() => {
  const classes: string[] = ['btn']

  // Variant classes
  const variantClasses: Record<ButtonVariant, string> = {
    primary: 'btn-primary',
    secondary: 'btn-secondary',
    danger: 'btn-danger',
    success: 'btn-success',
    ghost: 'btn-ghost',
    outline: 'btn-secondary', // Alias for secondary with border
  }

  classes.push(variantClasses[props.variant])

  // Size classes
  const sizeClasses: Record<ButtonSize, string> = {
    sm: 'btn-sm',
    md: '', // Default size in btn base
    lg: 'btn-lg',
  }

  if (sizeClasses[props.size]) {
    classes.push(sizeClasses[props.size])
  }

  // Full width
  if (props.fullWidth) {
    classes.push('w-full')
  }

  // Loading cursor
  if (props.loading) {
    classes.push('cursor-wait')
  }

  // Touch target for accessibility
  classes.push('touch-target')

  return classes.filter(Boolean).join(' ')
})
</script>

<template>
  <button
    :type="type"
    :class="buttonClasses"
    :disabled="disabled || loading"
  >
    <!-- Loading Spinner -->
    <svg
      v-if="loading"
      class="animate-spin h-4 w-4"
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        class="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="4"
      />
      <path
        class="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>

    <!-- Button Content -->
    <slot />
  </button>
</template>
