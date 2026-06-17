/**
 * useESPStatus Composable Tests
 *
 * Tests for ESP device status calculation (getESPStatus)
 * and status display mapping (getESPStatusDisplay).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getESPStatus, getESPStatusDisplay, getESPStatusDetailLabel, getESPStatusTooltip } from '@/composables/useESPStatus'
import type { ESPDevice } from '@/api/esp'

/** Helper: create minimal ESPDevice fixture */
function makeDevice(overrides: Partial<ESPDevice> = {}): ESPDevice {
  return {
    device_id: 'ESP_TEST_001',
    ...overrides,
  }
}

describe('getESPStatus', () => {
  let dateSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    dateSpy = vi.spyOn(Date, 'now').mockReturnValue(1_700_000_000_000)
  })

  afterEach(() => {
    dateSpy.mockRestore()
  })

  describe('server-provided status (Priority 1)', () => {
    it('returns online when device.status is "online"', () => {
      const device = makeDevice({ status: 'online' })
      expect(getESPStatus(device)).toBe('online')
    })

    it('returns online when device.connected is true', () => {
      const device = makeDevice({ connected: true })
      expect(getESPStatus(device)).toBe('online')
    })

    it('returns error when device.status is "error"', () => {
      const device = makeDevice({ status: 'error' })
      expect(getESPStatus(device)).toBe('error')
    })

    it('returns safemode when device.status is "safemode"', () => {
      const device = makeDevice({ status: 'safemode' })
      expect(getESPStatus(device)).toBe('safemode')
    })

    it('returns safemode when system_state is "SAFE_MODE"', () => {
      const device = makeDevice({ system_state: 'SAFE_MODE' })
      expect(getESPStatus(device)).toBe('safemode')
    })

    it('returns offline when device.status is "offline"', () => {
      const device = makeDevice({ status: 'offline' })
      expect(getESPStatus(device)).toBe('offline')
    })
  })

  describe('heartbeat-based timing (Priority 2)', () => {
    it('returns online when last_seen is within 120 seconds', () => {
      // 30 seconds ago
      const ts = new Date(1_700_000_000_000 - 30_000).toISOString()
      const device = makeDevice({ last_seen: ts })
      expect(getESPStatus(device)).toBe('online')
    })

    it('returns stale when last_seen is between 120s and 210s', () => {
      // 150 seconds ago
      const ts = new Date(1_700_000_000_000 - 150_000).toISOString()
      const device = makeDevice({ last_seen: ts })
      expect(getESPStatus(device)).toBe('stale')
    })

    it('returns offline when last_seen is older than 210 seconds', () => {
      // 10 minutes ago
      const ts = new Date(1_700_000_000_000 - 600_000).toISOString()
      const device = makeDevice({ last_seen: ts })
      expect(getESPStatus(device)).toBe('offline')
    })

    it('uses last_heartbeat as fallback when last_seen is null', () => {
      // 60 seconds ago — within online threshold
      const ts = new Date(1_700_000_000_000 - 60_000).toISOString()
      const device = makeDevice({ last_seen: null, last_heartbeat: ts })
      expect(getESPStatus(device)).toBe('online')
    })

    it('returns stale at exactly 120s boundary', () => {
      const ts = new Date(1_700_000_000_000 - 120_000).toISOString()
      const device = makeDevice({ last_seen: ts })
      expect(getESPStatus(device)).toBe('stale')
    })

    it('returns offline at exactly 210s boundary', () => {
      const ts = new Date(1_700_000_000_000 - 210_000).toISOString()
      const device = makeDevice({ last_seen: ts })
      expect(getESPStatus(device)).toBe('offline')
    })
  })

  describe('unknown fallback', () => {
    it('returns unknown when no status, no connected, no timestamps', () => {
      const device = makeDevice({})
      expect(getESPStatus(device)).toBe('unknown')
    })

    it('returns unknown when last_seen and last_heartbeat are both null', () => {
      const device = makeDevice({ last_seen: null, last_heartbeat: null })
      expect(getESPStatus(device)).toBe('unknown')
    })
  })

  describe('priority ordering', () => {
    it('status "online" is downgraded when heartbeat is too old', () => {
      // Old heartbeat with stale server status should not stay online forever
      const ts = new Date(1_700_000_000_000 - 600_000).toISOString()
      const device = makeDevice({ status: 'online', last_seen: ts })
      expect(getESPStatus(device)).toBe('offline')
    })

    it('status "offline" takes precedence over connected=true', () => {
      const device = makeDevice({ status: 'offline', connected: true })
      expect(getESPStatus(device)).toBe('offline')
    })

    it('error takes precedence over heartbeat timing', () => {
      const ts = new Date(1_700_000_000_000 - 30_000).toISOString()
      const device = makeDevice({ status: 'error', last_seen: ts })
      expect(getESPStatus(device)).toBe('error')
    })

    it('error takes precedence over connected=true', () => {
      const device = makeDevice({ status: 'error', connected: true })
      expect(getESPStatus(device)).toBe('error')
    })

    it('safemode takes precedence over connected=true', () => {
      const device = makeDevice({ status: 'safemode', connected: true })
      expect(getESPStatus(device)).toBe('safemode')
    })
  })

  describe('mock ESP system_state support', () => {
    it('returns error when system_state is "ERROR" (Mock ESP)', () => {
      const device = makeDevice({ system_state: 'ERROR' } as any)
      expect(getESPStatus(device)).toBe('error')
    })

    it('system_state ERROR takes precedence over connected=true', () => {
      const device = makeDevice({ connected: true, system_state: 'ERROR' } as any)
      expect(getESPStatus(device)).toBe('error')
    })

    it('system_state SAFE_MODE with connected=true returns safemode', () => {
      const device = makeDevice({ connected: true, system_state: 'SAFE_MODE' } as any)
      expect(getESPStatus(device)).toBe('safemode')
    })

    it('system_state OPERATIONAL does not override normal status logic', () => {
      const device = makeDevice({ connected: true, system_state: 'OPERATIONAL' } as any)
      expect(getESPStatus(device)).toBe('online')
    })

    it('mock and real ESP with same status yield identical results', () => {
      // Simulate Mock ESP: system_state ERROR + connected
      const mock = makeDevice({ connected: true, system_state: 'ERROR' } as any)
      // Simulate Real ESP: status error
      const real = makeDevice({ status: 'error' })
      expect(getESPStatus(mock)).toBe(getESPStatus(real))
    })
  })
})

describe('getESPStatusDisplay', () => {
  it('returns correct display for "online"', () => {
    const display = getESPStatusDisplay('online')
    expect(display.text).toBe('Online')
    expect(display.color).toBe('var(--color-success)')
    expect(display.icon).toBe('check-circle')
    expect(display.pulse).toBe(true)
  })

  it('returns correct display for "stale"', () => {
    const display = getESPStatusDisplay('stale')
    expect(display.text).toBe('Verzögert')
    expect(display.color).toBe('var(--color-warning)')
    expect(display.icon).toBe('clock')
    expect(display.pulse).toBe(false)
  })

  it('returns correct display for "offline"', () => {
    const display = getESPStatusDisplay('offline')
    expect(display.text).toBe('Offline')
    expect(display.color).toBe('var(--color-text-muted)')
    expect(display.icon).toBe('wifi-off')
    expect(display.pulse).toBe(false)
  })

  it('returns correct display for "error"', () => {
    const display = getESPStatusDisplay('error')
    expect(display.text).toBe('Fehler')
    expect(display.color).toBe('var(--color-error)')
    expect(display.icon).toBe('alert-triangle')
    expect(display.pulse).toBe(false)
  })

  it('returns correct display for "safemode"', () => {
    const display = getESPStatusDisplay('safemode')
    expect(display.text).toBe('SafeMode')
    expect(display.color).toBe('var(--color-warning)')
    expect(display.icon).toBe('shield-alert')
    expect(display.pulse).toBe(false)
  })

  it('returns correct display for "unknown"', () => {
    const display = getESPStatusDisplay('unknown')
    expect(display.text).toBe('Unbekannt')
    expect(display.color).toBe('var(--color-text-muted)')
    expect(display.icon).toBe('help-circle')
    expect(display.pulse).toBe(false)
  })

  it('all 6 status values return distinct text labels', () => {
    const statuses = ['online', 'stale', 'offline', 'error', 'safemode', 'unknown'] as const
    const texts = new Set(statuses.map(s => getESPStatusDisplay(s).text))
    expect(texts.size).toBe(6)
  })
})

describe('getESPStatusDetailLabel', () => {
  it('maps stale to operator label Keine Live-Daten', () => {
    expect(getESPStatusDetailLabel('stale')).toBe('Keine Live-Daten')
  })

  it('maps safemode to Sicherheitsmodus', () => {
    expect(getESPStatusDetailLabel('safemode')).toBe('Sicherheitsmodus')
  })

  it('falls back to display text for online', () => {
    expect(getESPStatusDetailLabel('online')).toBe('Online')
  })
})

describe('getESPStatusTooltip', () => {
  let dateSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    dateSpy = vi.spyOn(Date, 'now').mockReturnValue(1_700_000_000_000)
  })

  afterEach(() => {
    dateSpy.mockRestore()
  })

  it('includes status line for online devices', () => {
    const device = makeDevice({ status: 'online' })
    expect(getESPStatusTooltip(device)).toBe('Status: Online')
  })

  it('includes last seen and offline context for offline devices', () => {
    const ts = new Date(1_700_000_000_000 - 600_000).toISOString()
    const device = makeDevice({
      status: 'offline',
      last_seen: ts,
      offlineInfo: {
        displayText: 'Timeout nach 180s',
        source: 'heartbeat_timeout',
        reason: 'heartbeat_timeout',
        timestamp: 1_700_000_000,
      },
    })
    const tooltip = getESPStatusTooltip(device)
    expect(tooltip).toContain('Status: Offline')
    expect(tooltip).toContain('Letztes Lebenszeichen:')
    expect(tooltip).toContain('Erkennung: Timeout nach 180s')
    expect(tooltip).toContain('Quelle: heartbeat_timeout')
    expect(tooltip).toContain('Grund: heartbeat_timeout')
  })
})

// =============================================================================
// STATUS TRANSITIONS WITH FAKE TIMERS
// =============================================================================

describe('getESPStatus - Status Transitions (FakeTimers)', () => {
  const BASE_TIME = 1_700_000_000_000

  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(BASE_TIME)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('Online → Stale after 121 seconds without heartbeat', () => {
    const heartbeatTime = new Date(BASE_TIME).toISOString()
    const device = makeDevice({ last_seen: heartbeatTime })

    // Initially online
    expect(getESPStatus(device)).toBe('online')

    // Advance 121 seconds — crosses HEARTBEAT_STALE_MS (120_000)
    vi.advanceTimersByTime(121_000)
    expect(getESPStatus(device)).toBe('stale')
  })

  it('Online → Stale → Offline after 211 seconds without heartbeat', () => {
    const heartbeatTime = new Date(BASE_TIME).toISOString()
    const device = makeDevice({ last_seen: heartbeatTime })

    expect(getESPStatus(device)).toBe('online')

    // Advance to stale range
    vi.advanceTimersByTime(121_000)
    expect(getESPStatus(device)).toBe('stale')

    // Advance to offline range (total: 211s)
    vi.advanceTimersByTime(90_000) // 121 + 90 = 211s total
    expect(getESPStatus(device)).toBe('offline')
  })

  it('Offline → Online when new heartbeat arrives', () => {
    const oldTime = new Date(BASE_TIME - 600_000).toISOString()
    const device = makeDevice({ last_seen: oldTime })

    // Initially offline (10 min old heartbeat)
    expect(getESPStatus(device)).toBe('offline')

    // Simulate new heartbeat: update last_seen to current time
    device.last_seen = new Date(BASE_TIME).toISOString()
    expect(getESPStatus(device)).toBe('online')
  })

  it('stays Online when heartbeat is within 119 seconds', () => {
    const heartbeatTime = new Date(BASE_TIME).toISOString()
    const device = makeDevice({ last_seen: heartbeatTime })

    vi.advanceTimersByTime(119_000)
    expect(getESPStatus(device)).toBe('online')
  })

  it('boundary: exactly 120_000ms = stale (threshold is >=)', () => {
    const heartbeatTime = new Date(BASE_TIME).toISOString()
    const device = makeDevice({ last_seen: heartbeatTime })

    vi.advanceTimersByTime(120_000)
    expect(getESPStatus(device)).toBe('stale')
  })

  it('boundary: exactly 210_000ms = offline (threshold is >=)', () => {
    const heartbeatTime = new Date(BASE_TIME).toISOString()
    const device = makeDevice({ last_seen: heartbeatTime })

    vi.advanceTimersByTime(210_000)
    // age < HEARTBEAT_OFFLINE_MS: 210_000 is NOT < 210_000 → offline
    expect(getESPStatus(device)).toBe('offline')
  })

  it('simulates realistic heartbeat cycle (60s intervals)', () => {
    const device = makeDevice({ last_seen: new Date(BASE_TIME).toISOString() })

    // Heartbeat 1: t=0 → online
    expect(getESPStatus(device)).toBe('online')

    // 60s later, new heartbeat arrives
    vi.advanceTimersByTime(60_000)
    device.last_seen = new Date(BASE_TIME + 60_000).toISOString()
    expect(getESPStatus(device)).toBe('online')

    // 60s later, another heartbeat
    vi.advanceTimersByTime(60_000)
    device.last_seen = new Date(BASE_TIME + 120_000).toISOString()
    expect(getESPStatus(device)).toBe('online')

    // Heartbeat stops — 60s later, still online (60s since last heartbeat at t=120s)
    vi.advanceTimersByTime(60_000)
    expect(getESPStatus(device)).toBe('online')

    // 59 more seconds (119s since last heartbeat) — still online
    vi.advanceTimersByTime(59_000)
    expect(getESPStatus(device)).toBe('online')

    // 1 more second (120s since last heartbeat = boundary) → stale
    vi.advanceTimersByTime(1_000)
    expect(getESPStatus(device)).toBe('stale')
  })
})

// =============================================================================
// ADVANCED PRIORITY TESTS
// =============================================================================

describe('getESPStatus - Advanced Priority Scenarios', () => {
  let dateSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    dateSpy = vi.spyOn(Date, 'now').mockReturnValue(1_700_000_000_000)
  })

  afterEach(() => {
    dateSpy.mockRestore()
  })

  it('status "offline" wins against connected=true', () => {
    const device = makeDevice({ status: 'offline', connected: true })
    expect(getESPStatus(device)).toBe('offline')
  })

  it('error via system_state ERROR ignores fresh heartbeat', () => {
    const freshTs = new Date(1_700_000_000_000 - 5_000).toISOString()
    const device = makeDevice({
      last_seen: freshTs,
      system_state: 'ERROR',
    } as any)
    expect(getESPStatus(device)).toBe('error')
  })

  it('safemode via system_state SAFE_MODE ignores fresh heartbeat', () => {
    const freshTs = new Date(1_700_000_000_000 - 5_000).toISOString()
    const device = makeDevice({
      last_seen: freshTs,
      system_state: 'SAFE_MODE',
    } as any)
    expect(getESPStatus(device)).toBe('safemode')
  })

  it('connected=true without status field returns online', () => {
    const device = makeDevice({ connected: true, status: undefined })
    expect(getESPStatus(device)).toBe('online')
  })

  it('no status fields but last_heartbeat 2 minutes ago returns stale', () => {
    const ts = new Date(1_700_000_000_000 - 120_000).toISOString()
    const device = makeDevice({ last_heartbeat: ts })
    expect(getESPStatus(device)).toBe('stale')
  })

  it('quality field does not affect status calculation', () => {
    // Ensure sensor quality has no bearing on device status
    const device = makeDevice({
      connected: true,
      quality: 'critical',
    } as any)
    expect(getESPStatus(device)).toBe('online')
  })
})
