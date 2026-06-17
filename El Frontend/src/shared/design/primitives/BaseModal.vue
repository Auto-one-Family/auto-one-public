<script setup lang="ts">
/**
 * Modal Component
 * 
 * A dialog modal with:
 * - Glass morphism backdrop
 * - Smooth transitions
 * - Escape key and overlay click to close
 * - Body scroll lock
 * - Responsive sizing
 */

import { X } from 'lucide-vue-next'
import { onMounted, onUnmounted, watch } from 'vue'
import { useScrollLock } from '@/composables/useScrollLock'

interface Props {
  /** Whether the modal is open */
  open: boolean
  /** Modal title */
  title: string
  /** Max width class (e.g., 'max-w-md', 'max-w-lg', 'max-w-2xl') */
  maxWidth?: string
  /** Whether to show the close button in the header */
  showClose?: boolean
  /** Whether clicking overlay closes the modal */
  closeOnOverlay?: boolean
  /** Whether pressing Escape closes the modal */
  closeOnEscape?: boolean
  /** Z-index level: 'dialog' (default, 65) or 'prompt' (78, for confirm dialogs above other modals) */
  level?: 'dialog' | 'prompt'
}

const props = withDefaults(defineProps<Props>(), {
  maxWidth: 'max-w-md',
  showClose: true,
  closeOnOverlay: true,
  closeOnEscape: true,
  level: 'dialog',
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
}>()

function close() {
  emit('update:open', false)
  emit('close')
}

function handleOverlayClick() {
  if (props.closeOnOverlay) {
    close()
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.closeOnEscape && props.open) {
    close()
  }
}

// Reference-counted scroll lock
const scrollLock = useScrollLock()

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    scrollLock.lock()
  } else {
    scrollLock.unlock()
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  scrollLock.unlock()
})
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        class="fixed inset-0 flex items-center justify-center p-2 sm:p-4"
        :style="{ zIndex: `var(--z-${level})` }"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="title"
      >
        <!-- Glass Overlay -->
        <div
          class="glass-overlay absolute inset-0"
          @click="handleOverlayClick"
        />

        <!-- Modal Content -->
        <div
          :class="[
            'modal-content relative w-full',
            maxWidth,
            'max-h-[90vh] overflow-hidden flex flex-col',
            'transform transition-all duration-200'
          ]"
          @click.stop
        >
          <!-- Header -->
          <div class="modal-header">
            <h3 class="modal-title">
              {{ title }}
            </h3>
            <button
              v-if="showClose"
              class="modal-close-btn"
              @click="close"
              aria-label="Schließen"
            >
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- Body (scrollable) -->
          <div class="modal-body">
            <slot />
          </div>

          <!-- Footer (optional slot) -->
          <div v-if="$slots.footer" class="modal-footer">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* Modal content with glass effect (L3) */
.modal-content {
  background-color: var(--glass-bg-l3);
  -webkit-backdrop-filter: blur(var(--glass-blur-l3));
  backdrop-filter: blur(var(--glass-blur-l3));
  border: 1px solid var(--glass-border-l3);
  border-radius: var(--radius-md);
  box-shadow: var(--glass-shadow-l3);
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.modal-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.modal-close-btn {
  padding: 0.5rem;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  transition: all 0.2s;
  min-height: 44px;
  min-width: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-close-btn:hover {
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
}

.modal-body {
  padding: 1.25rem;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
  background-color: rgba(26, 26, 36, 0.5);
}

/* Modal enter/leave transitions */
.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--transition-overlay), transform var(--transition-overlay);
}

.modal-enter-active .modal-content,
.modal-leave-active .modal-content {
  transition: transform var(--transition-overlay), opacity var(--transition-overlay);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-content,
.modal-leave-to .modal-content {
  transform: scale(0.95) translateY(-10px);
  opacity: 0;
}

/* Responsive */
@media (min-width: 640px) {
  .modal-header {
    padding: 1.25rem 1.5rem;
  }
  
  .modal-body {
    padding: 1.5rem;
  }
  
  .modal-footer {
    padding: 1rem 1.5rem;
  }
}
</style>
