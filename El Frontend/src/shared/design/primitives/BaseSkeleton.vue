<script setup lang="ts">
/**
 * LoadingState Component
 * 
 * Displays a loading indicator with optional text.
 * Can be used inline or as a full-screen overlay.
 */

import { Loader2 } from 'lucide-vue-next'

interface Props {
  /** Loading message text */
  text?: string
  /** Whether to show as a full container */
  fullHeight?: boolean
  /** Size of the spinner */
  size?: 'sm' | 'md' | 'lg'
}

const props = withDefaults(defineProps<Props>(), {
  text: 'Lädt...',
  fullHeight: false,
  size: 'md',
})
void props // Used in template

const sizeClasses = {
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-8 h-8',
}

const containerClasses = {
  sm: 'py-4',
  md: 'py-8',
  lg: 'py-12',
}
</script>

<template>
  <div 
    :class="[
      'flex flex-col items-center justify-center gap-3',
      fullHeight ? 'min-h-[200px]' : containerClasses[size]
    ]"
  >
    <Loader2 
      :class="[sizeClasses[size], 'animate-spin']" 
      style="color: var(--color-iridescent-1)"
    />
    <span 
      v-if="text" 
      class="text-sm"
      style="color: var(--color-text-secondary)"
    >
      {{ text }}
    </span>
  </div>
</template>





















