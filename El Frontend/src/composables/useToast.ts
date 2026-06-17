/**
 * useToast Composable
 *
 * Lightweight toast notification system with:
 * - Singleton pattern for shared state
 * - Auto-dismiss with configurable duration
 * - Action buttons (Retry, Undo, etc.)
 * - Multiple toast stacking
 */

import { reactive, computed, type ComputedRef } from 'vue'

export interface ToastAction {
  label: string
  onClick: () => void | Promise<void>
  variant?: 'primary' | 'secondary'
}

export interface ToastOptions {
  message: string
  type: 'success' | 'error' | 'warning' | 'info'
  duration?: number
  persistent?: boolean
  actions?: ToastAction[]
  /**
   * Optionaler stabiler Deduplizierungs-Schlüssel.
   * Nutze ihn bei REST+WS-Kombinationen, um doppelte Operator-Rückmeldungen
   * für dieselbe Fachaktion zu verhindern.
   */
  dedupeKey?: string
}

export interface Toast extends ToastOptions {
  id: string
  createdAt: number
}

interface ToastState {
  toasts: Toast[]
}

// Default durations
const DEFAULT_DURATION = 5000
const ERROR_DURATION = 8000
const MAX_TOASTS = 20
const MAX_PERSISTENT_TOASTS = 10
const DEDUP_WINDOW_MS = 2000

const TOAST_TYPE_PRIORITY: Record<ToastOptions['type'], number> = {
  info: 1,
  success: 2,
  warning: 3,
  error: 4,
}

// Singleton state - shared across all components
const state = reactive<ToastState>({
  toasts: []
})

// Generate unique ID
function generateId(): string {
  return `toast-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`
}

export function useToast() {
  /**
   * Show a toast notification
   * @returns Toast ID for programmatic removal
   */
  function show(options: ToastOptions): string {
    const now = Date.now()

    // Dedup: skip if identical toast exists within time window
    const duplicate = state.toasts.find(
      t => {
        const withinWindow = (now - t.createdAt) < DEDUP_WINDOW_MS
        if (!withinWindow) return false
        if (options.dedupeKey && t.dedupeKey) return t.dedupeKey === options.dedupeKey
        return t.message === options.message && t.type === options.type
      }
    )
    if (duplicate) {
      const sameKey = Boolean(options.dedupeKey && duplicate.dedupeKey && options.dedupeKey === duplicate.dedupeKey)
      const shouldUpgrade =
        sameKey &&
        TOAST_TYPE_PRIORITY[options.type] > TOAST_TYPE_PRIORITY[duplicate.type]
      if (shouldUpgrade) {
        dismiss(duplicate.id)
      } else {
        return duplicate.id
      }
    }

    const id = generateId()
    const duration = options.duration ??
      (options.type === 'error' ? ERROR_DURATION : DEFAULT_DURATION)

    const toast: Toast = {
      ...options,
      id,
      duration,
      createdAt: now
    }

    // Enforce max limits: remove oldest non-persistent toasts first
    while (state.toasts.length >= MAX_TOASTS) {
      const oldestNonPersistent = state.toasts.findIndex(t => !t.persistent)
      if (oldestNonPersistent !== -1) {
        state.toasts.splice(oldestNonPersistent, 1)
      } else {
        state.toasts.shift()
      }
    }

    // Enforce persistent toast limit
    if (options.persistent) {
      const persistentCount = state.toasts.filter(t => t.persistent).length
      if (persistentCount >= MAX_PERSISTENT_TOASTS) {
        const oldestPersistent = state.toasts.findIndex(t => t.persistent)
        if (oldestPersistent !== -1) {
          state.toasts.splice(oldestPersistent, 1)
        }
      }
    }

    state.toasts.push(toast)

    // Auto-dismiss unless persistent
    if (!options.persistent) {
      setTimeout(() => {
        dismiss(id)
      }, duration)
    }

    return id
  }

  /**
   * Show success toast
   */
  function success(message: string, options?: Partial<Omit<ToastOptions, 'message' | 'type'>>): string {
    return show({ message, type: 'success', ...options })
  }

  /**
   * Show error toast
   */
  function error(message: string, options?: Partial<Omit<ToastOptions, 'message' | 'type'>>): string {
    return show({ message, type: 'error', ...options })
  }

  /**
   * Show warning toast
   */
  function warning(message: string, options?: Partial<Omit<ToastOptions, 'message' | 'type'>>): string {
    return show({ message, type: 'warning', ...options })
  }

  /**
   * Show info toast
   */
  function info(message: string, options?: Partial<Omit<ToastOptions, 'message' | 'type'>>): string {
    return show({ message, type: 'info', ...options })
  }

  /**
   * Dismiss a specific toast by ID
   */
  function dismiss(id: string): void {
    const index = state.toasts.findIndex(t => t.id === id)
    if (index !== -1) {
      state.toasts.splice(index, 1)
    }
  }

  /**
   * Clear all toasts
   */
  function clear(): void {
    state.toasts.splice(0, state.toasts.length)
  }

  // Computed reactive list for ToastContainer
  const toasts: ComputedRef<Toast[]> = computed(() => state.toasts)

  return {
    show,
    success,
    error,
    warning,
    info,
    dismiss,
    clear,
    toasts
  }
}
