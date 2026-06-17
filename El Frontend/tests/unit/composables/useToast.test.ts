/**
 * useToast Composable Unit Tests
 *
 * Tests for toast notification system including:
 * - Showing toasts with different types
 * - Auto-dismiss functionality
 * - Deduplication within time window
 * - Max toast limits
 * - Persistent toasts
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useToast } from '@/composables/useToast'

// =============================================================================
// SETUP / TEARDOWN
// =============================================================================

beforeEach(() => {
  vi.useFakeTimers()
  const { clear } = useToast()
  clear()
})

afterEach(() => {
  const { clear } = useToast()
  clear()
  vi.useRealTimers()
})

// =============================================================================
// BASIC FUNCTIONALITY
// =============================================================================

describe('useToast - Basic Show', () => {
  it('returns show, success, error, warning, info functions', () => {
    const toast = useToast()

    expect(typeof toast.show).toBe('function')
    expect(typeof toast.success).toBe('function')
    expect(typeof toast.error).toBe('function')
    expect(typeof toast.warning).toBe('function')
    expect(typeof toast.info).toBe('function')
  })

  it('shows a toast with message and type', () => {
    const { show, toasts } = useToast()

    show({ message: 'Test message', type: 'info' })

    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].message).toBe('Test message')
    expect(toasts.value[0].type).toBe('info')
  })

  it('returns a unique toast ID', () => {
    const { show } = useToast()

    const id1 = show({ message: 'Toast 1', type: 'info' })
    const id2 = show({ message: 'Toast 2', type: 'info' })

    expect(id1).toBeDefined()
    expect(id2).toBeDefined()
    expect(id1).not.toBe(id2)
    expect(id1).toMatch(/^toast-/)
  })

  it('adds createdAt timestamp to toast', () => {
    const { show, toasts } = useToast()
    const before = Date.now()

    show({ message: 'Test', type: 'info' })

    expect(toasts.value[0].createdAt).toBeGreaterThanOrEqual(before)
    expect(toasts.value[0].createdAt).toBeLessThanOrEqual(Date.now())
  })
})

// =============================================================================
// CONVENIENCE METHODS
// =============================================================================

describe('useToast - Convenience Methods', () => {
  it('success() creates success toast', () => {
    const { success, toasts } = useToast()

    success('Operation completed')

    expect(toasts.value[0].type).toBe('success')
    expect(toasts.value[0].message).toBe('Operation completed')
  })

  it('error() creates error toast', () => {
    const { error, toasts } = useToast()

    error('Something went wrong')

    expect(toasts.value[0].type).toBe('error')
    expect(toasts.value[0].message).toBe('Something went wrong')
  })

  it('warning() creates warning toast', () => {
    const { warning, toasts } = useToast()

    warning('Please check input')

    expect(toasts.value[0].type).toBe('warning')
    expect(toasts.value[0].message).toBe('Please check input')
  })

  it('info() creates info toast', () => {
    const { info, toasts } = useToast()

    info('Additional information')

    expect(toasts.value[0].type).toBe('info')
    expect(toasts.value[0].message).toBe('Additional information')
  })

  it('convenience methods accept optional parameters', () => {
    const { success, toasts } = useToast()

    success('Test', { duration: 10000, persistent: true })

    expect(toasts.value[0].duration).toBe(10000)
    expect(toasts.value[0].persistent).toBe(true)
  })
})

// =============================================================================
// DURATION & AUTO-DISMISS
// =============================================================================

describe('useToast - Duration', () => {
  it('uses default duration of 5000ms', () => {
    const { show, toasts } = useToast()

    show({ message: 'Test', type: 'info' })

    expect(toasts.value[0].duration).toBe(5000)
  })

  it('uses longer duration of 8000ms for error toasts', () => {
    const { error, toasts } = useToast()

    error('Error message')

    expect(toasts.value[0].duration).toBe(8000)
  })

  it('allows custom duration override', () => {
    const { show, toasts } = useToast()

    show({ message: 'Test', type: 'info', duration: 3000 })

    expect(toasts.value[0].duration).toBe(3000)
  })

  it('auto-dismisses toast after duration', () => {
    const { show, toasts } = useToast()

    show({ message: 'Test', type: 'info', duration: 5000 })
    expect(toasts.value).toHaveLength(1)

    vi.advanceTimersByTime(4999)
    expect(toasts.value).toHaveLength(1)

    vi.advanceTimersByTime(1)
    expect(toasts.value).toHaveLength(0)
  })

  it('does not auto-dismiss persistent toasts', () => {
    const { show, toasts } = useToast()

    show({ message: 'Persistent', type: 'info', persistent: true })

    vi.advanceTimersByTime(10000)

    expect(toasts.value).toHaveLength(1)
  })
})

// =============================================================================
// DISMISS & CLEAR
// =============================================================================

describe('useToast - Dismiss', () => {
  it('dismisses toast by ID', () => {
    const { show, dismiss, toasts } = useToast()

    const id1 = show({ message: 'Toast 1', type: 'info' })
    const id2 = show({ message: 'Toast 2', type: 'info' })

    dismiss(id1)

    expect(toasts.value).toHaveLength(1)
    expect(toasts.value[0].id).toBe(id2)
  })

  it('does nothing when dismissing non-existent ID', () => {
    const { show, dismiss, toasts } = useToast()

    show({ message: 'Test', type: 'info' })
    dismiss('non-existent-id')

    expect(toasts.value).toHaveLength(1)
  })

  it('clears all toasts', () => {
    const { show, clear, toasts } = useToast()

    show({ message: 'Toast 1', type: 'info' })
    show({ message: 'Toast 2', type: 'error' })
    show({ message: 'Toast 3', type: 'warning' })

    expect(toasts.value).toHaveLength(3)

    clear()

    expect(toasts.value).toHaveLength(0)
  })
})

// =============================================================================
// DEDUPLICATION
// =============================================================================

describe('useToast - Deduplication', () => {
  it('deduplicates identical toasts within 2000ms window', () => {
    const { show, toasts } = useToast()

    const id1 = show({ message: 'Same message', type: 'info' })
    const id2 = show({ message: 'Same message', type: 'info' })

    expect(toasts.value).toHaveLength(1)
    expect(id1).toBe(id2) // Returns same ID for duplicate
  })

  it('allows same message with different type', () => {
    const { show, toasts } = useToast()

    show({ message: 'Same message', type: 'info' })
    show({ message: 'Same message', type: 'error' })

    expect(toasts.value).toHaveLength(2)
  })

  it('allows duplicate after dedup window expires', () => {
    const { show, toasts, clear } = useToast()

    show({ message: 'Same message', type: 'info' })

    // Advance past dedup window (2000ms)
    vi.advanceTimersByTime(2001)

    // Clear auto-dismissed toast and add new one
    clear()
    show({ message: 'Same message', type: 'info' })

    expect(toasts.value).toHaveLength(1)
  })

  it('dedupliziert unterschiedliche messages über dedupeKey', () => {
    const { show, toasts } = useToast()

    const id1 = show({
      message: 'REST: Löschauftrag akzeptiert',
      type: 'info',
      dedupeKey: 'delete:sensor:esp1:gpio5',
    })
    const id2 = show({
      message: 'WS: Sensor entfernt',
      type: 'info',
      dedupeKey: 'delete:sensor:esp1:gpio5',
    })

    expect(toasts.value).toHaveLength(1)
    expect(id1).toBe(id2)
  })
})

// =============================================================================
// MAX LIMITS
// =============================================================================

describe('useToast - Max Limits', () => {
  it('enforces maximum of 20 toasts', () => {
    const { show, toasts } = useToast()

    // Add 25 toasts
    for (let i = 0; i < 25; i++) {
      show({ message: `Toast ${i}`, type: 'info', persistent: true })
    }

    expect(toasts.value.length).toBeLessThanOrEqual(20)
  })

  it('removes oldest non-persistent toast when limit reached', () => {
    const { show, toasts } = useToast()

    // Fill up with non-persistent toasts
    for (let i = 0; i < 20; i++) {
      show({ message: `Toast ${i}`, type: 'info' })
    }

    // Add one more - should remove oldest
    show({ message: 'Newest toast', type: 'info' })

    expect(toasts.value).toHaveLength(20)
    expect(toasts.value.some(t => t.message === 'Newest toast')).toBe(true)
    expect(toasts.value.some(t => t.message === 'Toast 0')).toBe(false)
  })

  it('enforces maximum of 10 persistent toasts', () => {
    const { show, toasts } = useToast()

    // Add 15 persistent toasts
    for (let i = 0; i < 15; i++) {
      show({ message: `Persistent ${i}`, type: 'info', persistent: true })
    }

    const persistentCount = toasts.value.filter(t => t.persistent).length
    expect(persistentCount).toBeLessThanOrEqual(10)
  })
})

// =============================================================================
// SINGLETON BEHAVIOR
// =============================================================================

describe('useToast - Singleton State', () => {
  it('shares state across multiple useToast calls', () => {
    const toast1 = useToast()
    const toast2 = useToast()

    toast1.show({ message: 'From first instance', type: 'info' })

    expect(toast2.toasts.value).toHaveLength(1)
    expect(toast2.toasts.value[0].message).toBe('From first instance')
  })

  it('clear() affects all instances', () => {
    const toast1 = useToast()
    const toast2 = useToast()

    toast1.show({ message: 'Toast 1', type: 'info' })
    toast2.show({ message: 'Toast 2', type: 'info' })

    expect(toast1.toasts.value).toHaveLength(2)
    expect(toast2.toasts.value).toHaveLength(2)

    toast1.clear()

    expect(toast1.toasts.value).toHaveLength(0)
    expect(toast2.toasts.value).toHaveLength(0)
  })
})

// =============================================================================
// TOAST ACTIONS
// =============================================================================

describe('useToast - Actions', () => {
  it('includes actions in toast options', () => {
    const { show, toasts } = useToast()
    const onClick = vi.fn()

    show({
      message: 'With action',
      type: 'info',
      actions: [
        { label: 'Retry', onClick, variant: 'primary' }
      ]
    })

    expect(toasts.value[0].actions).toHaveLength(1)
    expect(toasts.value[0].actions![0].label).toBe('Retry')
    expect(toasts.value[0].actions![0].variant).toBe('primary')
  })

  it('supports multiple actions', () => {
    const { show, toasts } = useToast()

    show({
      message: 'Multiple actions',
      type: 'info',
      actions: [
        { label: 'Undo', onClick: vi.fn(), variant: 'primary' },
        { label: 'Dismiss', onClick: vi.fn(), variant: 'secondary' }
      ]
    })

    expect(toasts.value[0].actions).toHaveLength(2)
  })
})
