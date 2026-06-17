/**
 * Tests for useCommandPalette composable.
 * Verifies category support, fuzzy search, registration, and navigation.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useCommandPalette, type CommandItem } from '@/composables/useCommandPalette'

function createCommand(overrides: Partial<CommandItem> = {}): CommandItem {
  return {
    id: 'test:cmd',
    label: 'Test Command',
    category: 'actions',
    action: () => {},
    ...overrides,
  }
}

describe('useCommandPalette', () => {
  let palette: ReturnType<typeof useCommandPalette>

  beforeEach(() => {
    palette = useCommandPalette()
    // Clear all commands - unregisterByPrefix('') removes nothing since no ID starts with ''
    // Use specific prefixes or register fresh
    palette.unregisterByPrefix('test:')
    palette.unregisterByPrefix('nav:')
    palette.unregisterByPrefix('device:')
    palette.unregisterByPrefix('rule:')
    palette.unregisterByPrefix('sensor:')
    palette.unregisterByPrefix('cmd:')
    palette.unregisterByPrefix('action:')
    palette.resetQuery()
  })

  // ── Registration ──

  it('registers commands', () => {
    palette.registerCommands([createCommand()])
    expect(palette.filteredCommands.value.length).toBeGreaterThanOrEqual(1)
  })

  it('replaces commands with same ID', () => {
    palette.registerCommands([createCommand({ label: 'First' })])
    palette.registerCommands([createCommand({ label: 'Second' })])
    const found = palette.filteredCommands.value.find(c => c.id === 'test:cmd')
    expect(found).toBeDefined()
    expect(found!.label).toBe('Second')
  })

  it('unregisters commands by prefix', () => {
    palette.registerCommands([
      createCommand({ id: 'nav:home' }),
      createCommand({ id: 'nav:settings' }),
      createCommand({ id: 'device:esp1' }),
    ])
    palette.unregisterByPrefix('nav:')
    const navItems = palette.filteredCommands.value.filter(c => c.id.startsWith('nav:'))
    expect(navItems.length).toBe(0)
    const deviceItems = palette.filteredCommands.value.filter(c => c.id === 'device:esp1')
    expect(deviceItems.length).toBe(1)
  })

  // ── Categories (Phase 5.4) ──

  it('supports rules category', () => {
    palette.registerCommands([
      createCommand({ id: 'rule:temp', category: 'rules', label: 'Regel: Temperatur' }),
    ])
    expect(palette.groupedCommands.value['rules']).toBeDefined()
    expect(palette.groupedCommands.value['rules'].length).toBeGreaterThanOrEqual(1)
  })

  it('supports sensors category', () => {
    palette.registerCommands([
      createCommand({ id: 'sensor:ds18b20', category: 'sensors', label: 'DS18B20' }),
    ])
    expect(palette.groupedCommands.value['sensors']).toBeDefined()
    expect(palette.groupedCommands.value['sensors'].length).toBeGreaterThanOrEqual(1)
  })

  it('has German labels for all categories', () => {
    expect(palette.categoryLabels['navigation']).toBe('Navigation')
    expect(palette.categoryLabels['devices']).toBe('Geräte')
    expect(palette.categoryLabels['actions']).toBe('Aktionen')
    expect(palette.categoryLabels['rules']).toBe('Regeln')
    expect(palette.categoryLabels['sensors']).toBe('Sensoren')
  })

  it('groups commands by category', () => {
    palette.registerCommands([
      createCommand({ id: 'nav:1', category: 'navigation', label: 'Dashboard' }),
      createCommand({ id: 'rule:1', category: 'rules', label: 'Regel 1' }),
      createCommand({ id: 'rule:2', category: 'rules', label: 'Regel 2' }),
      createCommand({ id: 'sensor:1', category: 'sensors', label: 'DS18B20' }),
    ])
    const groups = palette.groupedCommands.value
    expect(groups['navigation']?.some(c => c.id === 'nav:1')).toBe(true)
    expect(groups['rules']?.filter(c => c.id.startsWith('rule:')).length).toBe(2)
    expect(groups['sensors']?.some(c => c.id === 'sensor:1')).toBe(true)
  })

  // ── Fuzzy Search ──

  it('filters by label with fuzzy match', () => {
    palette.registerCommands([
      createCommand({ id: 'test:dash', label: 'Dashboard' }),
      createCommand({ id: 'test:set', label: 'Settings' }),
    ])
    palette.query.value = 'dash'
    const results = palette.filteredCommands.value
    expect(results.some(c => c.label === 'Dashboard')).toBe(true)
    expect(results.some(c => c.label === 'Settings')).toBe(false)
  })

  it('filters by searchTerms', () => {
    palette.registerCommands([
      createCommand({ id: 'test:ds', label: 'DS18B20', searchTerms: ['temperature', 'dallas'] }),
      createCommand({ id: 'test:sht', label: 'SHT31', searchTerms: ['humidity'] }),
    ])
    palette.query.value = 'temperature'
    const results = palette.filteredCommands.value
    expect(results.some(c => c.id === 'test:ds')).toBe(true)
    expect(results.some(c => c.id === 'test:sht')).toBe(false)
  })

  it('returns commands when query is empty', () => {
    palette.registerCommands([
      createCommand({ id: 'test:1' }),
      createCommand({ id: 'test:2' }),
    ])
    palette.query.value = ''
    expect(palette.filteredCommands.value.length).toBeGreaterThanOrEqual(2)
  })

  it('limits results to MAX_RESULTS (10)', () => {
    const cmds = Array.from({ length: 15 }, (_, i) =>
      createCommand({ id: `cmd:${i}`, label: `Command ${i}` })
    )
    palette.registerCommands(cmds)
    expect(palette.filteredCommands.value.length).toBeLessThanOrEqual(10)
  })

  // ── Navigation ──

  it('resets query', () => {
    palette.query.value = 'test'
    palette.resetQuery()
    expect(palette.query.value).toBe('')
  })

  it('moveSelection changes selectedIndex.value', () => {
    palette.registerCommands([
      createCommand({ id: 'test:1' }),
      createCommand({ id: 'test:2' }),
      createCommand({ id: 'test:3' }),
    ])
    palette.query.value = ''
    palette.selectedIndex.value = 0
    palette.moveSelection(1)
    expect(palette.selectedIndex.value).toBeGreaterThanOrEqual(1)
  })

  it('does not go below 0', () => {
    palette.registerCommands([createCommand({ id: 'test:1' })])
    palette.selectedIndex.value = 0
    palette.moveSelection(-1)
    expect(palette.selectedIndex.value).toBe(0)
  })

  // ── Execute ──

  it('executeSelected returns the selected item', () => {
    let executed = false
    palette.registerCommands([
      createCommand({ id: 'test:exec', action: () => { executed = true } }),
    ])
    // Find the index of our command
    const idx = palette.filteredCommands.value.findIndex(c => c.id === 'test:exec')
    palette.selectedIndex.value = idx
    const result = palette.executeSelected()
    expect(result).not.toBeNull()
    expect(result!.id).toBe('test:exec')
    expect(executed).toBe(true)
  })
})
