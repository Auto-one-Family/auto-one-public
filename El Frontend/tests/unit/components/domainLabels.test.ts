import { describe, it, expect } from 'vitest'
import {
  DEVICE_DOMAIN_KEYS,
  DOMAIN_LABELS,
  DOMAIN_SELECT_OPTIONS,
  getDomainLabel,
  isDeviceDomainKey,
} from '@/components/domains/domainLabels'

describe('domainLabels', () => {
  it('should expose all expected domain keys', () => {
    expect(DEVICE_DOMAIN_KEYS).toEqual([
      'luft',
      'wasser',
      'boden',
      'licht',
      'mensch',
      'pflanze',
    ])
  })

  it('should return Klarname for known domains', () => {
    expect(getDomainLabel('wasser')).toBe('Wasser')
    expect(getDomainLabel('luft')).toBe(DOMAIN_LABELS.luft)
  })

  it('should never return a technical domain key as visible label', () => {
    expect(getDomainLabel('wasser')).not.toBe('wasser')
    expect(getDomainLabel('unknown_domain')).toBe('Unbekannte Domäne')
    expect(getDomainLabel(null)).toBe('Keine Domäne')
    expect(getDomainLabel(undefined)).toBe('Keine Domäne')
  })

  it('should provide select options including empty choice', () => {
    expect(DOMAIN_SELECT_OPTIONS[0]).toEqual({ value: '', label: 'Keine Domäne' })
    expect(DOMAIN_SELECT_OPTIONS).toHaveLength(DEVICE_DOMAIN_KEYS.length + 1)
    expect(isDeviceDomainKey('boden')).toBe(true)
    expect(isDeviceDomainKey('')).toBe(false)
  })
})
