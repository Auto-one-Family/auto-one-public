/**
 * Event Type Labels Unit Tests
 *
 * Tests the SSOT label resolution for top-level event types and the nested
 * system_event sub-types.
 */

import { describe, it, expect } from 'vitest'
import {
  getEventTypeLabel,
  getSystemEventLabel,
  EVENT_TYPE_LABELS,
  SYSTEM_EVENT_LABELS,
} from '@/utils/eventTypeLabels'

describe('getEventTypeLabel', () => {
  it('returns the German label for a known event type', () => {
    expect(getEventTypeLabel('system_event')).toBe('System')
    expect(getEventTypeLabel('esp_health')).toBe('Heartbeat')
  })

  it('falls back to the raw type for unknown event types', () => {
    expect(getEventTypeLabel('totally_unknown')).toBe('totally_unknown')
  })
})

describe('getSystemEventLabel', () => {
  it('resolves known system sub-types', () => {
    expect(getSystemEventLabel('mqtt_disconnected')).toBe('MQTT-Verbindung getrennt')
    expect(getSystemEventLabel('database_restore_status')).toBe('Datenbank-Wiederherstellung')
  })

  it('keeps the SSOT map and lookup in sync', () => {
    for (const [key, label] of Object.entries(SYSTEM_EVENT_LABELS)) {
      expect(getSystemEventLabel(key)).toBe(label)
    }
  })

  it('humanizes unknown sub-types', () => {
    expect(getSystemEventLabel('some_future_event')).toBe('Some Future Event')
    expect(getSystemEventLabel('cache.cleared')).toBe('Cache Cleared')
  })

  it('falls back to the generic System label for empty input', () => {
    expect(getSystemEventLabel('')).toBe(EVENT_TYPE_LABELS.system_event)
    expect(getSystemEventLabel(null)).toBe('System')
    expect(getSystemEventLabel(undefined)).toBe('System')
  })
})
