/**
 * Event Grouper Utility Unit Tests
 *
 * Tests for grouping events by time window, emergency detection,
 * and group label generation.
 */

import { describe, it, expect } from 'vitest'
import { groupEventsByTimeWindow } from '@/utils/eventGrouper'
import type { UnifiedEvent } from '@/types/websocket-events'
import type { GroupingOptions } from '@/types/event-grouping'

// =============================================================================
// Helper: Create mock events
// =============================================================================

function makeEvent(overrides: Partial<UnifiedEvent> = {}): UnifiedEvent {
  return {
    id: `evt-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: new Date().toISOString(),
    event_type: 'sensor_data',
    severity: 'info',
    source: 'esp',
    message: 'Test event',
    data: {},
    ...overrides,
  }
}

function makeEvents(count: number, baseTime: number, intervalMs: number, overrides: Partial<UnifiedEvent> = {}): UnifiedEvent[] {
  return Array.from({ length: count }, (_, i) => makeEvent({
    id: `evt-${i}`,
    timestamp: new Date(baseTime + i * intervalMs).toISOString(),
    ...overrides,
  }))
}

// =============================================================================
// Default options for testing
// =============================================================================

const defaultOptions: GroupingOptions = {
  enabled: true,
  windowMs: 5000,
  minGroupSize: 2
}

// =============================================================================
// groupEventsByTimeWindow - Basic
// =============================================================================

describe('groupEventsByTimeWindow - Basic', () => {
  it('returns empty array for empty input', () => {
    const result = groupEventsByTimeWindow([], defaultOptions)
    expect(result).toEqual([])
  })

  it('returns individual events when grouping disabled', () => {
    const events = makeEvents(3, Date.now(), 1000)
    const result = groupEventsByTimeWindow(events, { ...defaultOptions, enabled: false })
    expect(result).toHaveLength(3)
    expect(result.every(item => item.type === 'event')).toBe(true)
  })

  it('groups events within time window', () => {
    const baseTime = Date.now()
    const events = makeEvents(3, baseTime, 2000) // 2s apart, within 5s window
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('group')
  })

  it('separates events outside time window', () => {
    const baseTime = Date.now()
    // Function expects newest-first input
    const events = makeEvents(2, baseTime, 10000).reverse() // 10s apart, exceeds 5s window
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(2)
    expect(result.every(item => item.type === 'event')).toBe(true)
  })

  it('respects minGroupSize threshold', () => {
    const baseTime = Date.now()
    const events = makeEvents(3, baseTime, 1000) // 3 events within window
    const options = { ...defaultOptions, minGroupSize: 4 }
    const result = groupEventsByTimeWindow(events, options)
    expect(result).toHaveLength(3)
    expect(result.every(item => item.type === 'event')).toBe(true)
  })

  it('creates multiple groups from one array', () => {
    const baseTime = Date.now()
    // Group 1: 0ms, 2000ms (within 5s)
    // Gap of 10s
    // Group 2: 12000ms, 14000ms (within 5s)
    // Function expects newest-first order
    const events = [
      ...makeEvents(2, baseTime, 2000),
      ...makeEvents(2, baseTime + 12000, 2000)
    ].reverse()
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(2)
    expect(result.every(item => item.type === 'group')).toBe(true)
  })
})

// =============================================================================
// groupEventsByTimeWindow - Emergency Detection
// =============================================================================

describe('groupEventsByTimeWindow - Emergency Detection', () => {
  it('extends time window for emergency events', () => {
    const baseTime = Date.now()
    const events = [
      makeEvent({ id: 'evt-1', timestamp: new Date(baseTime).toISOString(), event_type: 'emergency_stop' }),
      makeEvent({ id: 'evt-2', timestamp: new Date(baseTime + 8000).toISOString(), event_type: 'actuator_status' })
    ]
    // Normal window: 5s, Emergency window: 10s
    // 8s gap should group with emergency but not without
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('group')
  })

  it('detects emergency_stop event type', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, { event_type: 'emergency_stop' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('group')
    if (result[0].type === 'group') {
      expect(result[0].data.isEmergency).toBe(true)
    }
  })

  it('detects emergency via actuator_alert with emergency_stop alert_type', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, {
      event_type: 'actuator_alert',
      data: { alert_type: 'emergency_stop' }
    })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('group')
    if (result[0].type === 'group') {
      expect(result[0].data.isEmergency).toBe(true)
    }
  })

  it('detects emergency via 3+ actuator_alert events', () => {
    const baseTime = Date.now()
    const events = makeEvents(3, baseTime, 1000, { event_type: 'actuator_alert' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('group')
    if (result[0].type === 'group') {
      expect(result[0].data.isEmergency).toBe(true)
    }
  })

  it('does not mark emergency with only 2 actuator_alerts', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, { event_type: 'actuator_alert' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('group')
    if (result[0].type === 'group') {
      expect(result[0].data.isEmergency).toBe(false)
    }
  })
})

// =============================================================================
// groupEventsByTimeWindow - Group Properties
// =============================================================================

describe('groupEventsByTimeWindow - Group Properties', () => {
  it('group has correct count', () => {
    const baseTime = Date.now()
    const events = makeEvents(4, baseTime, 1000)
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    if (result[0].type === 'group') {
      expect(result[0].data.count).toBe(4)
    }
  })

  it('group has correct timeSpanMs', () => {
    const baseTime = Date.now()
    // Function expects newest-first input
    const events = makeEvents(3, baseTime, 2000).reverse() // 0ms, 2000ms, 4000ms
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.timeSpanMs).toBe(4000)
    }
  })

  it('group collects unique espIds', () => {
    const baseTime = Date.now()
    const events = [
      makeEvent({ id: 'evt-1', timestamp: new Date(baseTime).toISOString(), esp_id: 'ESP_001' }),
      makeEvent({ id: 'evt-2', timestamp: new Date(baseTime + 1000).toISOString(), esp_id: 'ESP_002' }),
      makeEvent({ id: 'evt-3', timestamp: new Date(baseTime + 2000).toISOString(), esp_id: 'ESP_001' })
    ]
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.espIds).toHaveLength(2)
      expect(result[0].data.espIds).toContain('ESP_001')
      expect(result[0].data.espIds).toContain('ESP_002')
    }
  })

  it('results are newest-first order', () => {
    const baseTime = Date.now()
    // Function expects newest-first input
    const events = makeEvents(3, baseTime, 1000).reverse()
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    if (result[0].type === 'group') {
      // Events within a group are in oldest-first order (chronological)
      const firstEvent = result[0].data.events[0]
      const lastEvent = result[0].data.events[result[0].data.events.length - 1]
      expect(new Date(firstEvent.timestamp).getTime()).toBeLessThanOrEqual(
        new Date(lastEvent.timestamp).getTime()
      )
    }
  })
})

// =============================================================================
// groupEventsByTimeWindow - Dominant Category
// =============================================================================

describe('groupEventsByTimeWindow - Dominant Category', () => {
  it('determines dominant category correctly', () => {
    const baseTime = Date.now()
    const events = [
      makeEvent({ id: 'evt-1', timestamp: new Date(baseTime).toISOString(), event_type: 'sensor_data' }),
      makeEvent({ id: 'evt-2', timestamp: new Date(baseTime + 1000).toISOString(), event_type: 'sensor_data' }),
      makeEvent({ id: 'evt-3', timestamp: new Date(baseTime + 2000).toISOString(), event_type: 'actuator_status' })
    ]
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.dominantCategory).toBe('sensors')
    }
  })

  it('handles tie in category counts', () => {
    const baseTime = Date.now()
    const events = [
      makeEvent({ id: 'evt-1', timestamp: new Date(baseTime).toISOString(), event_type: 'sensor_data' }),
      makeEvent({ id: 'evt-2', timestamp: new Date(baseTime + 1000).toISOString(), event_type: 'actuator_status' })
    ]
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      // Should pick one of them (deterministic based on order)
      expect(['sensors', 'actuators']).toContain(result[0].data.dominantCategory)
    }
  })
})

// =============================================================================
// groupEventsByTimeWindow - Group Labels
// =============================================================================

describe('groupEventsByTimeWindow - Group Labels', () => {
  it('labels config_published events as Config-Update', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, { event_type: 'config_published' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.label).toBe('Config-Update')
    }
  })

  it('labels actuator_command events as Aktor-Steuerung', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, { event_type: 'actuator_command' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.label).toBe('Aktor-Steuerung')
    }
  })

  it('labels emergency group as Notfall-Stopp', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, { event_type: 'emergency_stop' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.label).toBe('Notfall-Stopp')
    }
  })

  it('uses category-based label for generic groups', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, { event_type: 'sensor_data' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.label).toBe('Sensor-Daten')
    }
  })

  it('labels actuator_alert events as Aktor-Alarm', () => {
    const baseTime = Date.now()
    const events = makeEvents(2, baseTime, 1000, { event_type: 'actuator_alert' })
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.label).toBe('Aktor-Alarm')
    }
  })
})

// =============================================================================
// groupEventsByTimeWindow - Edge Cases
// =============================================================================

describe('groupEventsByTimeWindow - Edge Cases', () => {
  it('handles single event (below minGroupSize)', () => {
    const baseTime = Date.now()
    const events = makeEvents(1, baseTime, 0)
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('event')
  })

  it('handles events with null esp_id', () => {
    const baseTime = Date.now()
    const events = [
      makeEvent({ id: 'evt-1', timestamp: new Date(baseTime).toISOString(), esp_id: undefined }),
      makeEvent({ id: 'evt-2', timestamp: new Date(baseTime + 1000).toISOString(), esp_id: undefined })
    ]
    const result = groupEventsByTimeWindow(events, defaultOptions)
    expect(result).toHaveLength(1)
    if (result[0].type === 'group') {
      expect(result[0].data.espIds).toEqual([])
    }
  })

  it('handles mixed events (some with esp_id, some without)', () => {
    const baseTime = Date.now()
    const events = [
      makeEvent({ id: 'evt-1', timestamp: new Date(baseTime).toISOString(), esp_id: 'ESP_001' }),
      makeEvent({ id: 'evt-2', timestamp: new Date(baseTime + 1000).toISOString(), esp_id: undefined })
    ]
    const result = groupEventsByTimeWindow(events, defaultOptions)
    if (result[0].type === 'group') {
      expect(result[0].data.espIds).toEqual(['ESP_001'])
    }
  })

  it('handles zero time window (each event separate)', () => {
    const baseTime = Date.now()
    // Events 1ms apart, newest-first, so they exceed windowMs=0
    const events = makeEvents(3, baseTime, 1).reverse()
    const options = { ...defaultOptions, windowMs: 0 }
    const result = groupEventsByTimeWindow(events, options)
    expect(result).toHaveLength(3)
    expect(result.every(item => item.type === 'event')).toBe(true)
  })

  it('handles very large time window (all events grouped)', () => {
    const baseTime = Date.now()
    const events = makeEvents(5, baseTime, 10000) // 10s apart
    const options = { ...defaultOptions, windowMs: 100000 } // 100s window
    const result = groupEventsByTimeWindow(events, options)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe('group')
  })
})
