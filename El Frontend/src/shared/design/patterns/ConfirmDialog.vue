<script setup lang="ts">
/**
 * ConfirmDialog
 *
 * Promise-based confirmation dialog using BaseModal.
 * Globally mounted in App.vue, reads state from uiStore.
 * Three variants: info (blue), warning (yellow), danger (red).
 */

import { computed, nextTick, ref, watch } from 'vue'
import { AlertTriangle, Info } from 'lucide-vue-next'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { useUiStore } from '@/shared/stores/ui.store'

const uiStore = useUiStore()
const cancelBtnRef = ref<HTMLButtonElement | null>(null)

const state = computed(() => uiStore.confirmState)
const isOpen = computed(() => state.value.isOpen)

const confirmText = computed(() => {
  if (state.value.confirmText) return state.value.confirmText
  return state.value.variant === 'danger' ? 'Löschen' : 'Bestätigen'
})

const cancelText = computed(() => state.value.cancelText || 'Abbrechen')

const iconComponent = computed(() => {
  if (state.value.icon) return state.value.icon
  return state.value.variant === 'info' ? Info : AlertTriangle
})

const variantClass = computed(() => `confirm-dialog--${state.value.variant}`)

const confirmBtnClass = computed(() => {
  switch (state.value.variant) {
    case 'danger': return 'confirm-dialog__btn--danger'
    case 'warning': return 'confirm-dialog__btn--warning'
    default: return 'confirm-dialog__btn--info'
  }
})

function handleConfirm(): void {
  uiStore.resolveConfirm(true)
}

function handleCancel(): void {
  uiStore.resolveConfirm(false)
}

// Auto-focus cancel button when dialog opens (safe default)
watch(isOpen, async (open) => {
  if (open) {
    await nextTick()
    cancelBtnRef.value?.focus()
  }
})
</script>

<template>
  <BaseModal
    :open="isOpen"
    :title="state.title"
    max-width="max-w-md"
    level="prompt"
    :show-close="false"
    :close-on-overlay="false"
    :close-on-escape="false"
  >
    <div :class="['confirm-dialog', variantClass]">
      <!-- Icon + Message -->
      <div class="confirm-dialog__body">
        <div class="confirm-dialog__icon">
          <component :is="iconComponent" class="w-6 h-6" />
        </div>
        <p class="confirm-dialog__message">{{ state.message }}</p>
      </div>
    </div>

    <template #footer>
      <div class="confirm-dialog__actions">
        <button
          ref="cancelBtnRef"
          class="confirm-dialog__btn confirm-dialog__btn--cancel"
          data-testid="confirm-dialog-cancel-button"
          @click="handleCancel"
        >
          {{ cancelText }}
        </button>
        <button
          :class="['confirm-dialog__btn', confirmBtnClass]"
          data-testid="confirm-dialog-confirm-button"
          @click="handleConfirm"
        >
          {{ confirmText }}
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.confirm-dialog__body {
  display: flex;
  gap: var(--space-4);
  align-items: flex-start;
}

.confirm-dialog__icon {
  flex-shrink: 0;
  padding: var(--space-2);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
}

.confirm-dialog--info .confirm-dialog__icon {
  background-color: var(--color-info-bg);
  color: var(--color-info);
}

.confirm-dialog--warning .confirm-dialog__icon {
  background-color: var(--color-warning-bg);
  color: var(--color-warning);
}

.confirm-dialog--danger .confirm-dialog__icon {
  background-color: var(--color-error-bg);
  color: var(--color-error);
}

.confirm-dialog__message {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.5;
  margin: 0;
  padding-top: var(--space-2);
}

.confirm-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}

.confirm-dialog__btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 40px;
  border: none;
}

.confirm-dialog__btn--cancel {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
}

.confirm-dialog__btn--cancel:hover {
  background-color: var(--color-surface-hover);
  color: var(--color-text-primary);
}

.confirm-dialog__btn--cancel:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

.confirm-dialog__btn--info {
  background-color: var(--color-info);
  color: var(--color-text-inverse);
}

.confirm-dialog__btn--info:hover {
  background-color: color-mix(in srgb, var(--color-info) 88%, var(--color-text-inverse));
}

.confirm-dialog__btn--warning {
  background-color: var(--color-warning);
  color: var(--color-bg-primary);
}

.confirm-dialog__btn--warning:hover {
  background-color: color-mix(in srgb, var(--color-warning) 88%, var(--color-bg-primary));
}

.confirm-dialog__btn--danger {
  background-color: var(--color-error);
  color: var(--color-text-inverse);
}

.confirm-dialog__btn--danger:hover {
  background-color: color-mix(in srgb, var(--color-error) 88%, var(--color-text-inverse));
}

.confirm-dialog__btn--danger:focus-visible,
.confirm-dialog__btn--info:focus-visible,
.confirm-dialog__btn--warning:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
</style>
