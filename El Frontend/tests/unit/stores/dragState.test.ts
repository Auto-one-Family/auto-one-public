/**
 * DragState Store Unit Tests
 *
 * Tests for global drag-and-drop state management:
 * - Sensor type drag from sidebar
 * - Sensor satellite drag for chart analysis
 * - Actuator type drag from sidebar
 * - ESP card drag between zones (VueDraggable)
 * - Safety timeout (30s auto-reset)
 * - Global event listeners (dragend, Escape key)
 * - Statistics tracking
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  useDragStateStore,
  type SensorTypeDragPayload,
  type SensorDragPayload,
  type ActuatorTypeDragPayload
} from '@/shared/stores/dragState.store'

// =============================================================================
// MOCK LOGGER
// =============================================================================

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  })
}))

// =============================================================================
// MOCK DragEvent (not available in jsdom)
// =============================================================================

if (typeof DragEvent === 'undefined') {
  global.DragEvent = class DragEvent extends Event {
    constructor(type: string, eventInitDict?: EventInit) {
      super(type, eventInitDict)
    }
  } as unknown as typeof DragEvent
}

// =============================================================================
// TEST FIXTURES
// =============================================================================

const sensorTypePayload: SensorTypeDragPayload = {
  action: 'add-sensor',
  sensorType: 'ds18b20',
  label: 'Temperatur (DS18B20)',
  defaultUnit: '°C',
  icon: 'Thermometer'
}

const sensorPayload: SensorDragPayload = {
  type: 'sensor',
  espId: 'wokwi-esp32-001',
  gpio: 14,
  sensorType: 'ds18b20',
  name: 'Temperatur 1',
  unit: '°C'
}

const actuatorTypePayload: ActuatorTypeDragPayload = {
  action: 'add-actuator',
  actuatorType: 'relay',
  label: 'Relais',
  icon: 'Zap',
  isPwm: false
}

// =============================================================================
// INITIAL STATE TESTS
// =============================================================================

describe('DragState Store - Initial State', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('has all isDragging flags false initially', () => {
    const store = useDragStateStore()
    expect(store.isDraggingSensorType).toBe(false)
    expect(store.isDraggingSensor).toBe(false)
    expect(store.isDraggingEspCard).toBe(false)
    expect(store.isDraggingActuatorType).toBe(false)
  })

  it('has all payloads null initially', () => {
    const store = useDragStateStore()
    expect(store.sensorTypePayload).toBeNull()
    expect(store.sensorPayload).toBeNull()
    expect(store.draggingSensorEspId).toBeNull()
    expect(store.actuatorTypePayload).toBeNull()
  })

  it('has isAnyDragActive false initially', () => {
    const store = useDragStateStore()
    expect(store.isAnyDragActive).toBe(false)
  })

  it('has currentDragDuration 0 initially', () => {
    const store = useDragStateStore()
    expect(store.currentDragDuration).toBe(0)
  })

  it('has empty stats initially', () => {
    const store = useDragStateStore()
    const stats = store.getStats()
    expect(stats.startCount).toBe(0)
    expect(stats.endCount).toBe(0)
    expect(stats.timeoutCount).toBe(0)
    expect(stats.lastDragDuration).toBe(0)
  })
})

// =============================================================================
// SENSOR TYPE DRAG TESTS
// =============================================================================

describe('DragState Store - Sensor Type Drag', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('sets isDraggingSensorType to true on startSensorTypeDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isDraggingSensorType).toBe(true)
  })

  it('stores sensorTypePayload on startSensorTypeDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.sensorTypePayload).toEqual(sensorTypePayload)
  })

  it('increments startCount on startSensorTypeDrag', () => {
    const store = useDragStateStore()
    const before = store.getStats().startCount
    store.startSensorTypeDrag(sensorTypePayload)
    const after = store.getStats().startCount
    expect(after).toBe(before + 1)
  })

  it('sets isAnyDragActive to true on startSensorTypeDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isAnyDragActive).toBe(true)
  })

  it('clears sensor type drag on endDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    store.endDrag()
    expect(store.isDraggingSensorType).toBe(false)
    expect(store.sensorTypePayload).toBeNull()
  })

  it('increments endCount on endDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    const before = store.getStats().endCount
    store.endDrag()
    const after = store.getStats().endCount
    expect(after).toBe(before + 1)
  })
})

// =============================================================================
// SENSOR DRAG TESTS
// =============================================================================

describe('DragState Store - Sensor Drag', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('sets isDraggingSensor to true on startSensorDrag', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.isDraggingSensor).toBe(true)
  })

  it('stores sensorPayload on startSensorDrag', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.sensorPayload).toEqual(sensorPayload)
  })

  it('stores draggingSensorEspId on startSensorDrag', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.draggingSensorEspId).toBe(sensorPayload.espId)
  })

  it('increments startCount on startSensorDrag', () => {
    const store = useDragStateStore()
    const before = store.getStats().startCount
    store.startSensorDrag(sensorPayload)
    const after = store.getStats().startCount
    expect(after).toBe(before + 1)
  })

  it('sets isAnyDragActive to true on startSensorDrag', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.isAnyDragActive).toBe(true)
  })

  it('clears sensor drag on endDrag', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    store.endDrag()
    expect(store.isDraggingSensor).toBe(false)
    expect(store.sensorPayload).toBeNull()
    expect(store.draggingSensorEspId).toBeNull()
  })
})

// =============================================================================
// ACTUATOR TYPE DRAG TESTS
// =============================================================================

describe('DragState Store - Actuator Type Drag', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('sets isDraggingActuatorType to true on startActuatorTypeDrag', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.isDraggingActuatorType).toBe(true)
  })

  it('stores actuatorTypePayload on startActuatorTypeDrag', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.actuatorTypePayload).toEqual(actuatorTypePayload)
  })

  it('increments startCount on startActuatorTypeDrag', () => {
    const store = useDragStateStore()
    const before = store.getStats().startCount
    store.startActuatorTypeDrag(actuatorTypePayload)
    const after = store.getStats().startCount
    expect(after).toBe(before + 1)
  })

  it('sets isAnyDragActive to true on startActuatorTypeDrag', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.isAnyDragActive).toBe(true)
  })

  it('clears actuator type drag on endDrag', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    store.endDrag()
    expect(store.isDraggingActuatorType).toBe(false)
    expect(store.actuatorTypePayload).toBeNull()
  })
})

// =============================================================================
// ESP CARD DRAG TESTS
// =============================================================================

describe('DragState Store - ESP Card Drag', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('sets isDraggingEspCard to true on startEspCardDrag', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    expect(store.isDraggingEspCard).toBe(true)
  })

  it('increments startCount on startEspCardDrag', () => {
    const store = useDragStateStore()
    const before = store.getStats().startCount
    store.startEspCardDrag()
    const after = store.getStats().startCount
    expect(after).toBe(before + 1)
  })

  it('sets isAnyDragActive to true on startEspCardDrag', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    expect(store.isAnyDragActive).toBe(true)
  })

  it('clears ESP card drag on endEspCardDrag', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    store.endEspCardDrag()
    expect(store.isDraggingEspCard).toBe(false)
  })

  it('increments endCount on endEspCardDrag', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    const before = store.getStats().endCount
    store.endEspCardDrag()
    const after = store.getStats().endCount
    expect(after).toBe(before + 1)
  })

  it('updates lastDragDuration on endEspCardDrag', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    // Wait a bit
    vi.advanceTimersByTime(100)
    store.endEspCardDrag()
    expect(store.getStats().lastDragDuration).toBeGreaterThan(0)
  })
})

// =============================================================================
// END DRAG TESTS
// =============================================================================

describe('DragState Store - endDrag()', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('resets all drag states', () => {
    const store = useDragStateStore()

    // Start multiple drags (should auto-reset previous)
    store.startSensorTypeDrag(sensorTypePayload)
    store.endDrag()
    store.startSensorDrag(sensorPayload)
    store.endDrag()
    store.startActuatorTypeDrag(actuatorTypePayload)
    store.endDrag()
    store.startEspCardDrag()
    store.endDrag()

    expect(store.isDraggingSensorType).toBe(false)
    expect(store.isDraggingSensor).toBe(false)
    expect(store.isDraggingEspCard).toBe(false)
    expect(store.isDraggingActuatorType).toBe(false)
    expect(store.isAnyDragActive).toBe(false)
  })

  it('clears all payloads', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    store.endDrag()
    expect(store.sensorTypePayload).toBeNull()
    expect(store.sensorPayload).toBeNull()
    expect(store.draggingSensorEspId).toBeNull()
    expect(store.actuatorTypePayload).toBeNull()
  })

  it('increments endCount', () => {
    const store = useDragStateStore()
    const before = store.getStats().endCount
    store.startSensorTypeDrag(sensorTypePayload)
    store.endDrag()
    const after = store.getStats().endCount
    expect(after).toBe(before + 1)
  })

  it('updates lastDragDuration', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    // Wait a bit
    vi.advanceTimersByTime(50)
    store.endDrag()
    expect(store.getStats().lastDragDuration).toBeGreaterThanOrEqual(50)
  })
})

// =============================================================================
// FORCE RESET TESTS
// =============================================================================

describe('DragState Store - forceReset()', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('calls endDrag internally', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    store.forceReset()
    expect(store.isDraggingSensorType).toBe(false)
    expect(store.sensorTypePayload).toBeNull()
    expect(store.isAnyDragActive).toBe(false)
  })

  it('increments endCount', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    const before = store.getStats().endCount
    store.forceReset()
    const after = store.getStats().endCount
    expect(after).toBe(before + 1)
  })
})

// =============================================================================
// IS ANY DRAG ACTIVE TESTS
// =============================================================================

describe('DragState Store - isAnyDragActive', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('returns true when sensor type drag is active', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isAnyDragActive).toBe(true)
  })

  it('returns true when sensor drag is active', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.isAnyDragActive).toBe(true)
  })

  it('returns true when actuator type drag is active', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.isAnyDragActive).toBe(true)
  })

  it('returns true when ESP card drag is active', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    expect(store.isAnyDragActive).toBe(true)
  })

  it('returns false when no drag is active', () => {
    const store = useDragStateStore()
    expect(store.isAnyDragActive).toBe(false)
  })

  it('returns false after endDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    store.endDrag()
    expect(store.isAnyDragActive).toBe(false)
  })
})

// =============================================================================
// GET STATS TESTS
// =============================================================================

describe('DragState Store - getStats()', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns a copy of stats object', () => {
    const store = useDragStateStore()
    const stats1 = store.getStats()
    const stats2 = store.getStats()

    expect(stats1).toEqual(stats2)
    expect(stats1).not.toBe(stats2) // Different object reference
  })

  it('tracks startCount correctly', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    store.startEspCardDrag() // Auto-resets previous
    store.startActuatorTypeDrag(actuatorTypePayload) // Auto-resets previous

    const stats = store.getStats()
    expect(stats.startCount).toBe(3)
  })

  it('tracks endCount correctly', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    store.endDrag()
    store.startSensorDrag(sensorPayload)
    store.endDrag()

    const stats = store.getStats()
    expect(stats.endCount).toBe(2)
  })

  it('tracks lastDragDuration correctly', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    vi.advanceTimersByTime(200)
    store.endDrag()

    const stats = store.getStats()
    expect(stats.lastDragDuration).toBeGreaterThanOrEqual(200)
  })
})

// =============================================================================
// AUTO RESET ON NEW DRAG TESTS
// =============================================================================

describe('DragState Store - Auto-reset on new drag', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('auto-resets previous sensor type drag when starting new drag', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isDraggingSensorType).toBe(true)

    store.startSensorDrag(sensorPayload)
    expect(store.isDraggingSensorType).toBe(false)
    expect(store.isDraggingSensor).toBe(true)
  })

  it('auto-resets previous sensor drag when starting ESP card drag', () => {
    const store = useDragStateStore()

    store.startSensorDrag(sensorPayload)
    expect(store.isDraggingSensor).toBe(true)

    store.startEspCardDrag()
    expect(store.isDraggingSensor).toBe(false)
    expect(store.isDraggingEspCard).toBe(true)
  })

  it('auto-resets previous ESP card drag when starting actuator type drag', () => {
    const store = useDragStateStore()

    store.startEspCardDrag()
    expect(store.isDraggingEspCard).toBe(true)

    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.isDraggingEspCard).toBe(false)
    expect(store.isDraggingActuatorType).toBe(true)
  })

  it('increments endCount on auto-reset', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    const beforeEnd = store.getStats().endCount

    store.startSensorDrag(sensorPayload)
    const afterEnd = store.getStats().endCount

    expect(afterEnd).toBe(beforeEnd + 1)
  })
})

// =============================================================================
// SAFETY TIMEOUT TESTS (with fake timers)
// =============================================================================

describe('DragState Store - Safety Timeout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('auto-resets sensor type drag after 30s timeout', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isDraggingSensorType).toBe(true)

    vi.advanceTimersByTime(30000)
    expect(store.isDraggingSensorType).toBe(false)
  })

  it('auto-resets sensor drag after 30s timeout', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.isDraggingSensor).toBe(true)

    vi.advanceTimersByTime(30000)
    expect(store.isDraggingSensor).toBe(false)
  })

  it('auto-resets actuator type drag after 30s timeout', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.isDraggingActuatorType).toBe(true)

    vi.advanceTimersByTime(30000)
    expect(store.isDraggingActuatorType).toBe(false)
  })

  it('auto-resets ESP card drag after 30s timeout', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    expect(store.isDraggingEspCard).toBe(true)

    vi.advanceTimersByTime(30000)
    expect(store.isDraggingEspCard).toBe(false)
  })

  it('increments timeoutCount on timeout', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    const before = store.getStats().timeoutCount

    vi.advanceTimersByTime(30000)
    const after = store.getStats().timeoutCount

    expect(after).toBe(before + 1)
  })

  it('does not trigger timeout if drag ends normally', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)

    vi.advanceTimersByTime(10000)
    store.endDrag()

    const beforeTimeout = store.getStats().timeoutCount

    vi.advanceTimersByTime(25000) // Past 30s total
    const afterTimeout = store.getStats().timeoutCount

    expect(afterTimeout).toBe(beforeTimeout) // No timeout increment
  })

  it('clears timeout on manual endDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isDraggingSensorType).toBe(true)

    store.endDrag()
    expect(store.isDraggingSensorType).toBe(false)

    // Advance past timeout - should not reset again
    const beforeEnd = store.getStats().endCount
    vi.advanceTimersByTime(30000)
    const afterEnd = store.getStats().endCount

    expect(afterEnd).toBe(beforeEnd) // No additional endDrag call
  })

  it('clears timeout on forceReset', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)

    store.forceReset()
    expect(store.isDraggingSensorType).toBe(false)

    const beforeEnd = store.getStats().endCount
    vi.advanceTimersByTime(30000)
    const afterEnd = store.getStats().endCount

    expect(afterEnd).toBe(beforeEnd)
  })
})

// =============================================================================
// ESCAPE KEY TESTS
// =============================================================================

describe('DragState Store - Escape Key Handler', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('cancels sensor type drag on Escape key', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isDraggingSensorType).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(store.isDraggingSensorType).toBe(false)
  })

  it('cancels sensor drag on Escape key', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.isDraggingSensor).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(store.isDraggingSensor).toBe(false)
  })

  it('cancels actuator type drag on Escape key', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.isDraggingActuatorType).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(store.isDraggingActuatorType).toBe(false)
  })

  it('cancels ESP card drag on Escape key', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    expect(store.isDraggingEspCard).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    expect(store.isDraggingEspCard).toBe(false)
  })

  it('does nothing if no drag is active', () => {
    const store = useDragStateStore()
    const beforeEnd = store.getStats().endCount

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))

    const afterEnd = store.getStats().endCount
    expect(afterEnd).toBe(beforeEnd) // No endDrag call
  })

  it('ignores non-Escape keys', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))

    expect(store.isDraggingSensorType).toBe(true) // Still active
  })
})

// =============================================================================
// GLOBAL DRAGEND TESTS
// =============================================================================

describe('DragState Store - Global dragend Handler', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('cleans up sensor type drag on native dragend event', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)
    expect(store.isDraggingSensorType).toBe(true)

    window.dispatchEvent(new DragEvent('dragend'))
    vi.advanceTimersByTime(100) // 100ms delay before cleanup

    expect(store.isDraggingSensorType).toBe(false)
  })

  it('cleans up sensor drag on native dragend event', () => {
    const store = useDragStateStore()
    store.startSensorDrag(sensorPayload)
    expect(store.isDraggingSensor).toBe(true)

    window.dispatchEvent(new DragEvent('dragend'))
    vi.advanceTimersByTime(100)

    expect(store.isDraggingSensor).toBe(false)
  })

  it('cleans up actuator type drag on native dragend event', () => {
    const store = useDragStateStore()
    store.startActuatorTypeDrag(actuatorTypePayload)
    expect(store.isDraggingActuatorType).toBe(true)

    window.dispatchEvent(new DragEvent('dragend'))
    vi.advanceTimersByTime(100)

    expect(store.isDraggingActuatorType).toBe(false)
  })

  it('ignores dragend event during ESP card drag (VueDraggable managed)', () => {
    const store = useDragStateStore()
    store.startEspCardDrag()
    expect(store.isDraggingEspCard).toBe(true)

    window.dispatchEvent(new DragEvent('dragend'))
    vi.advanceTimersByTime(100)

    // ESP card drag should still be active (VueDraggable manages it)
    expect(store.isDraggingEspCard).toBe(true)
  })

  it('does not double-reset if component already called endDrag', () => {
    const store = useDragStateStore()
    store.startSensorTypeDrag(sensorTypePayload)

    store.endDrag() // Component handles it
    const beforeEnd = store.getStats().endCount

    window.dispatchEvent(new DragEvent('dragend'))
    vi.advanceTimersByTime(100)

    const afterEnd = store.getStats().endCount
    expect(afterEnd).toBe(beforeEnd) // No additional endDrag
  })
})

// =============================================================================
// CLEANUP TESTS
// =============================================================================

describe('DragState Store - cleanup()', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('removes event listeners on cleanup', () => {
    vi.useFakeTimers()
    const store = useDragStateStore()

    // Start and end a drag
    store.startSensorTypeDrag(sensorTypePayload)

    // Cleanup
    store.cleanup()

    // Dispatch events - should not trigger handlers
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    window.dispatchEvent(new DragEvent('dragend'))
    vi.advanceTimersByTime(100)

    expect(store.isDraggingSensorType).toBe(true) // Not affected by events
    vi.useRealTimers()
  })

  it('clears safety timeout on cleanup', () => {
    vi.useFakeTimers()
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    store.cleanup()

    vi.advanceTimersByTime(30000)

    expect(store.isDraggingSensorType).toBe(true) // Timeout not triggered
    vi.useRealTimers()
  })

  it('can be called multiple times safely', () => {
    const store = useDragStateStore()

    store.cleanup()
    store.cleanup()
    store.cleanup()

    // Should not throw or cause issues
    expect(store.isAnyDragActive).toBe(false)
  })
})

// =============================================================================
// STATS TRACKING TESTS
// =============================================================================

describe('DragState Store - Stats Tracking', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('tracks startCount across multiple drag types', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    store.startSensorDrag(sensorPayload) // Auto-resets previous
    store.startActuatorTypeDrag(actuatorTypePayload) // Auto-resets previous
    store.startEspCardDrag() // Auto-resets previous

    expect(store.getStats().startCount).toBe(4)
  })

  it('tracks endCount from explicit endDrag calls', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    store.endDrag()
    store.startSensorDrag(sensorPayload)
    store.endDrag()

    expect(store.getStats().endCount).toBe(2)
  })

  it('tracks endCount from auto-reset on new drag', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload) // startCount: 1
    store.startSensorDrag(sensorPayload) // endCount: 1, startCount: 2
    store.startActuatorTypeDrag(actuatorTypePayload) // endCount: 2, startCount: 3

    expect(store.getStats().startCount).toBe(3)
    expect(store.getStats().endCount).toBe(2) // Auto-reset counts as end
  })

  it('tracks timeoutCount on safety timeout', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    vi.advanceTimersByTime(30000)

    store.startSensorDrag(sensorPayload)
    vi.advanceTimersByTime(30000)

    expect(store.getStats().timeoutCount).toBe(2)
  })

  it('tracks lastDragDuration accurately', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    vi.advanceTimersByTime(1500)
    store.endDrag()

    const stats = store.getStats()
    expect(stats.lastDragDuration).toBeGreaterThanOrEqual(1500)
    expect(stats.lastDragDuration).toBeLessThan(1600) // Allow small variance
  })

  it('updates lastDragDuration on each drag end', () => {
    const store = useDragStateStore()

    store.startSensorTypeDrag(sensorTypePayload)
    vi.advanceTimersByTime(100)
    store.endDrag()
    const firstDuration = store.getStats().lastDragDuration

    store.startSensorDrag(sensorPayload)
    vi.advanceTimersByTime(500)
    store.endDrag()
    const secondDuration = store.getStats().lastDragDuration

    expect(secondDuration).toBeGreaterThan(firstDuration)
  })
})
