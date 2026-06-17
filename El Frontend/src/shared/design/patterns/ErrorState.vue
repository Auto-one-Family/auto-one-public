<script setup lang="ts">
/**
 * ErrorState Component
 * 
 * Displays an error message with:
 * - Error icon
 * - Error message
 * - Optional retry button
 */

import { computed } from 'vue'
import { AlertTriangle, RefreshCw, X } from 'lucide-vue-next'

interface Props {
  /** The error message to display (accepts string or array for fallback) */
  message: string | string[] | unknown
  /** Optional error title */
  title?: string
  /** Whether to show the retry button */
  showRetry?: boolean
  /** Whether to show the dismiss button */
  showDismiss?: boolean
  /** Retry button text */
  retryText?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Ein Fehler ist aufgetreten',
  showRetry: true,
  showDismiss: false,
  retryText: 'Erneut versuchen',
})

// Normalize message to string (handles arrays and objects gracefully)
const normalizedMessage = computed(() => {
  if (typeof props.message === 'string') return props.message
  if (Array.isArray(props.message)) {
    return props.message.map(m => 
      typeof m === 'object' && m !== null 
        ? (m as { msg?: string }).msg || JSON.stringify(m)
        : String(m)
    ).join('; ')
  }
  if (typeof props.message === 'object' && props.message !== null) {
    return JSON.stringify(props.message)
  }
  return String(props.message || 'Unbekannter Fehler')
})

const emit = defineEmits<{
  retry: []
  dismiss: []
}>()
</script>

<template>
  <div class="error-state">
    <div class="error-state__icon">
      <AlertTriangle class="w-6 h-6" />
    </div>
    
    <div class="error-state__content">
      <h4 class="error-state__title">{{ title }}</h4>
      <p class="error-state__message">{{ normalizedMessage }}</p>
    </div>
    
    <div v-if="showRetry || showDismiss" class="error-state__actions">
      <button
        v-if="showRetry"
        class="btn-secondary btn-sm"
        @click="emit('retry')"
      >
        <RefreshCw class="w-4 h-4" />
        {{ retryText }}
      </button>
      
      <button
        v-if="showDismiss"
        class="btn-ghost btn-sm"
        @click="emit('dismiss')"
      >
        <X class="w-4 h-4" />
      </button>
    </div>
  </div>
</template>

<style scoped>
.error-state {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  background-color: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: var(--radius-md);
}

.error-state__icon {
  flex-shrink: 0;
  color: var(--color-error);
}

.error-state__content {
  flex: 1;
  min-width: 0;
}

.error-state__title {
  font-weight: 600;
  color: var(--color-error);
  margin-bottom: 0.25rem;
}

.error-state__message {
  font-size: 0.875rem;
  color: var(--color-error);
  opacity: 0.9;
}

.error-state__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}
</style>

