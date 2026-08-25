<script setup lang="ts">
/**
 * ToastContainer Component
 *
 * Renders toast notifications in top-right corner with:
 * - Smooth enter/leave animations
 * - Progress bar for auto-dismiss countdown
 * - Action buttons (Retry, Undo, etc.)
 * - Accessible: aria-live regions
 * - AUT-614: UUID-stripped display text, severity-sorted stack, pending Loader2 spinner
 */

import { computed } from 'vue'
import {
  CheckCircle,
  AlertCircle,
  AlertTriangle,
  Info,
  X,
  Loader2,
} from 'lucide-vue-next'
import { useToast, type Toast, type ToastAction } from '@/composables/useToast'

const { toasts, dismiss } = useToast()

// AUT-614: Severity priority for display sort (higher = visually on top)
const TYPE_DISPLAY_PRIORITY: Record<Toast['type'], number> = {
  error: 4,
  warning: 3,
  success: 2,
  info: 1,
}

/** Sort toasts: highest severity on top, then newest within same severity */
const sortedToasts = computed(() =>
  [...toasts.value].sort((a, b) => {
    const pa = TYPE_DISPLAY_PRIORITY[a.type] ?? 0
    const pb = TYPE_DISPLAY_PRIORITY[b.type] ?? 0
    if (pa !== pb) return pb - pa
    return b.createdAt - a.createdAt
  })
)

/** AUT-614: Strip UUID strings (bare or inside parentheses) from display text */
function stripUuids(message: string): string {
  const UUID_IN_PARENS = /\s*\(\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\s*\)/gi
  const UUID_BARE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi
  // Also strip "Korrelation: <uuid>" suffix
  const CORRELATION_SUFFIX = /,?\s*\(Korrelation:\s*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\)/gi
  return message
    .replace(CORRELATION_SUFFIX, '')
    .replace(UUID_IN_PARENS, '')
    .replace(UUID_BARE, '')
    .trim()
}

/** AUT-614: A toast is "pending" when it signals an in-progress command */
function isPending(toast: Toast): boolean {
  return toast.type === 'info' && /bearbeitung|wird ausgeführt|pending/i.test(toast.message)
}

// Icon mapping by toast type (AUT-628: warn→AlertTriangle, error→AlertCircle, consistent with alert panel)
const iconMap = {
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}

function getIcon(toast: Toast) {
  if (isPending(toast)) return Loader2
  return iconMap[toast.type]
}

function getAriaLive(type: Toast['type']): 'assertive' | 'polite' {
  return type === 'error' ? 'assertive' : 'polite'
}

async function handleAction(toastId: string, action: ToastAction) {
  try {
    await action.onClick()
  } finally {
    dismiss(toastId)
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="toast-container" aria-label="Benachrichtigungen">
      <TransitionGroup name="toast">
        <div
          v-for="toast in sortedToasts"
          :key="toast.id"
          :class="['toast', `toast--${toast.type}`, { 'toast--pending': isPending(toast) }]"
          role="alert"
          :aria-live="getAriaLive(toast.type)"
          :data-correlation-id="toast.dedupeKey ?? undefined"
        >
          <!-- Icon (AUT-614: Loader2 for pending in-progress toasts) -->
          <div class="toast__icon-wrapper">
            <component
              :is="getIcon(toast)"
              :class="['toast__icon', { 'toast__icon--spin': isPending(toast) }]"
            />
          </div>

          <!-- Content (AUT-614: UUIDs stripped from display text) -->
          <div class="toast__content">
            <p class="toast__message">{{ stripUuids(toast.message) }}</p>

            <!-- Action buttons -->
            <div v-if="toast.actions?.length" class="toast__actions">
              <button
                v-for="(action, idx) in toast.actions"
                :key="idx"
                :class="['toast__action', `toast__action--${action.variant || 'secondary'}`]"
                @click="handleAction(toast.id, action)"
              >
                {{ action.label }}
              </button>
            </div>
          </div>

          <!-- Dismiss button -->
          <button
            class="toast__close"
            @click="dismiss(toast.id)"
            aria-label="Schließen"
          >
            <X class="w-4 h-4" />
          </button>

          <!-- Progress bar for auto-dismiss -->
          <div
            v-if="!toast.persistent"
            class="toast__progress"
            :style="{ animationDuration: `${toast.duration}ms` }"
          />
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<style scoped>
.toast-container {
  position: fixed;
  top: 1.5rem;
  right: 1.5rem;
  z-index: var(--z-toast);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  max-width: 400px;
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: var(--radius-md);
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  box-shadow: var(--glass-shadow);
  position: relative;
  overflow: hidden;
}

/* AUT-614: Spinner animation for pending toasts */
@keyframes toast-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.toast__icon--spin {
  animation: toast-spin 1.2s linear infinite;
}

/* Type-specific accents */
.toast--success {
  border-left: 3px solid var(--color-success);
}

.toast--error {
  border-left: 3px solid var(--color-error);
}

.toast--warning {
  border-left: 3px solid var(--color-warning);
}

.toast--info {
  border-left: 3px solid var(--color-iridescent-1);
}

/* Icon */
.toast__icon-wrapper {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.toast__icon {
  width: 1.25rem;
  height: 1.25rem;
}

.toast--success .toast__icon {
  color: var(--color-success);
}

.toast--error .toast__icon {
  color: var(--color-error);
}

.toast--warning .toast__icon {
  color: var(--color-warning);
}

.toast--info .toast__icon {
  color: var(--color-iridescent-1);
}

/* Content */
.toast__content {
  flex: 1;
  min-width: 0;
}

.toast__message {
  margin: 0;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  line-height: 1.4;
  word-wrap: break-word;
}

/* Actions */
.toast__actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

.toast__action {
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: var(--radius-sm);
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.toast__action--primary {
  background-color: var(--color-iridescent-1);
  color: white;
}

.toast__action--primary:hover {
  background-color: var(--color-iridescent-2);
}

.toast__action--secondary {
  background-color: rgba(255, 255, 255, 0.1);
  color: var(--color-text-secondary);
  border: 1px solid var(--glass-border);
}

.toast__action--secondary:hover {
  background-color: rgba(255, 255, 255, 0.15);
  color: var(--color-text-primary);
}

/* Close button */
.toast__close {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: var(--radius-xs);
  transition: all 0.2s ease;
}

.toast__close:hover {
  background-color: rgba(255, 255, 255, 0.1);
  color: var(--color-text-primary);
}

/* Progress bar */
.toast__progress {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 3px;
  width: 100%;
  background: currentColor;
  opacity: 0.2;
  animation: toast-progress linear forwards;
}

.toast--success .toast__progress {
  color: var(--color-success);
}

.toast--error .toast__progress {
  color: var(--color-error);
}

.toast--warning .toast__progress {
  color: var(--color-warning);
}

.toast--info .toast__progress {
  color: var(--color-iridescent-1);
}

@keyframes toast-progress {
  from {
    width: 100%;
  }
  to {
    width: 0%;
  }
}

/* Transition animations */
.toast-enter-active {
  animation: toast-in 0.3s ease-out;
}

.toast-leave-active {
  animation: toast-out 0.2s ease-in forwards;
}

.toast-move {
  transition: transform 0.3s ease;
}

@keyframes toast-in {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}

@keyframes toast-out {
  from {
    transform: translateX(0);
    opacity: 1;
  }
  to {
    transform: translateX(100%);
    opacity: 0;
  }
}

/* Tablet & Mobile: clear the hamburger bar (.shell__mobile-bar, 48px, visible < 768px) */
@media (max-width: 767px) {
  .toast-container {
    top: calc(48px + 0.5rem);
  }
}

/* Mobile: full-width stack */
@media (max-width: 480px) {
  .toast-container {
    left: 1rem;
    right: 1rem;
    max-width: none;
  }
}
</style>
