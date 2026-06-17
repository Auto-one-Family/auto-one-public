<script setup lang="ts">
/**
 * RejectDeviceModal
 *
 * Modal dialog for rejecting a pending ESP device.
 * Uses BaseModal from shared/design/primitives for consistency
 * with the rest of the design system (replaces window.prompt).
 *
 * Features:
 * - Optional reason text input
 * - Danger-styled confirm button
 * - Device ID display
 * - Keyboard support (Enter to confirm, Escape to cancel)
 */

import { ref, watch, nextTick } from 'vue'
import { Ban } from 'lucide-vue-next'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'

interface Props {
  /** Whether the modal is open */
  open: boolean
  /** Device ID being rejected */
  deviceId: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: [reason: string]
  cancel: []
}>()

const reason = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

// Reset and focus when modal opens
watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    reason.value = ''
    await nextTick()
    inputRef.value?.focus()
  }
})

function handleConfirm() {
  emit('confirm', reason.value.trim() || 'Manuell abgelehnt')
  close()
}

function handleCancel() {
  emit('cancel')
  close()
}

function close() {
  emit('update:open', false)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    handleConfirm()
  }
}
</script>

<template>
  <BaseModal
    :open="open"
    title="Gerät ablehnen"
    max-width="max-w-sm"
    @close="handleCancel"
  >
    <div class="reject-modal">
      <!-- Icon + Device ID -->
      <div class="reject-modal__header">
        <div class="reject-modal__icon">
          <Ban class="w-6 h-6" />
        </div>
        <div class="reject-modal__device">
          <p class="reject-modal__label">Gerät ablehnen:</p>
          <p class="reject-modal__device-id">{{ deviceId }}</p>
        </div>
      </div>

      <!-- Reason Input -->
      <div class="reject-modal__field">
        <label for="reject-reason" class="reject-modal__field-label">
          Grund für die Ablehnung (optional)
        </label>
        <input
          id="reject-reason"
          ref="inputRef"
          v-model="reason"
          type="text"
          class="reject-modal__input"
          placeholder="z.B. Unbekanntes Gerät, Testgerät..."
          @keydown="handleKeydown"
        />
      </div>
    </div>

    <template #footer>
      <div class="reject-modal__actions">
        <button
          class="reject-modal__btn reject-modal__btn--cancel"
          @click="handleCancel"
        >
          Abbrechen
        </button>
        <button
          class="reject-modal__btn reject-modal__btn--danger"
          @click="handleConfirm"
        >
          <Ban class="w-4 h-4" />
          Ablehnen
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.reject-modal__header {
  display: flex;
  gap: 1rem;
  align-items: flex-start;
  margin-bottom: 1.25rem;
}

.reject-modal__icon {
  flex-shrink: 0;
  padding: 0.5rem;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: rgba(248, 113, 113, 0.1);
  color: var(--color-error);
}

.reject-modal__device {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  padding-top: 0.25rem;
}

.reject-modal__label {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  margin: 0;
}

.reject-modal__device-id {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  margin: 0;
}

.reject-modal__field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.reject-modal__field-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.reject-modal__input {
  width: 100%;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  outline: none;
  transition: border-color 0.15s ease;
}

.reject-modal__input::placeholder {
  color: var(--color-text-muted);
}

.reject-modal__input:focus {
  border-color: rgba(248, 113, 113, 0.5);
}

.reject-modal__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.reject-modal__btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  transition: all 0.12s ease;
  min-height: 40px;
}

.reject-modal__btn--cancel {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
}

.reject-modal__btn--cancel:hover {
  background-color: var(--color-bg-quaternary);
  color: var(--color-text-primary);
}

.reject-modal__btn--danger {
  background-color: var(--color-error);
  color: var(--color-text-inverse);
}

.reject-modal__btn--danger:hover {
  background-color: var(--color-error);
}

.reject-modal__btn:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}
</style>
