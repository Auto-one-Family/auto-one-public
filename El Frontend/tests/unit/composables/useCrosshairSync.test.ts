/**
 * useCrosshairSync Composable Unit Tests (AUT-912)
 *
 * The dashboard-level crosshair-sync registry is the SSOT that replaced the
 * per-widget `syncTimeAxis` toggle. Verifies:
 * - toggle / setActive / isActive semantics per group id
 * - reactive Set replacement (computed consumers re-evaluate)
 * - localStorage persistence
 * - load-from-localStorage on module init
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { computed, nextTick } from 'vue'
import { useCrosshairSync } from '@/composables/useCrosshairSync'

const STORAGE_KEY = 'automationone.crosshairSyncGroups'

function resetState() {
  const { activeGroups } = useCrosshairSync()
  // Empty the shared module-singleton Set between tests.
  for (const g of [...activeGroups.value]) {
    useCrosshairSync().setActive(g, false)
  }
  localStorage.clear()
}

beforeEach(() => resetState())
afterEach(() => resetState())

describe('useCrosshairSync', () => {
  it('isActive is false for unknown / nullish group ids', () => {
    const { isActive } = useCrosshairSync()
    expect(isActive('dash-1')).toBe(false)
    expect(isActive(undefined)).toBe(false)
    expect(isActive(null)).toBe(false)
    expect(isActive('')).toBe(false)
  })

  it('toggle activates and deactivates a group', () => {
    const { toggle, isActive } = useCrosshairSync()
    toggle('dash-1')
    expect(isActive('dash-1')).toBe(true)
    toggle('dash-1')
    expect(isActive('dash-1')).toBe(false)
  })

  it('setActive is idempotent and isolates groups', () => {
    const { setActive, isActive } = useCrosshairSync()
    setActive('dash-1', true)
    setActive('dash-1', true)
    expect(isActive('dash-1')).toBe(true)
    expect(isActive('dash-2')).toBe(false)
    setActive('dash-2', true)
    expect(isActive('dash-1')).toBe(true)
    expect(isActive('dash-2')).toBe(true)
  })

  it('drives a reactive computed consumer (the widget syncGroup pattern)', async () => {
    const { toggle, isActive } = useCrosshairSync()
    const syncGroupId = 'dash-9'
    // Mirrors MultiSensorWidget.crosshairSyncGroup
    const crosshairSyncGroup = computed(() =>
      isActive(syncGroupId) ? syncGroupId : undefined,
    )
    expect(crosshairSyncGroup.value).toBeUndefined()
    toggle(syncGroupId)
    await nextTick()
    expect(crosshairSyncGroup.value).toBe('dash-9')
    toggle(syncGroupId)
    await nextTick()
    expect(crosshairSyncGroup.value).toBeUndefined()
  })

  it('persists active groups to localStorage', () => {
    const { toggle } = useCrosshairSync()
    toggle('dash-1')
    toggle('dash-2')
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    expect(stored).toEqual(expect.arrayContaining(['dash-1', 'dash-2']))
    expect(stored).toHaveLength(2)
  })

  it('loads previously persisted groups on module init', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(['dash-restored']))
    // Reset the module registry so the init-time load() re-runs against localStorage.
    vi.resetModules()
    const mod = await import('@/composables/useCrosshairSync')
    expect(mod.useCrosshairSync().isActive('dash-restored')).toBe(true)
    vi.resetModules()
  })
})
