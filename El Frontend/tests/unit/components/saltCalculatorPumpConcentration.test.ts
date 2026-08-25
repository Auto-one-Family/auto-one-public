import { describe, expect, it } from 'vitest'
import { resolveDisplayConcentration } from '@/components/plants/saltCalculatorPumpConcentration'

describe('resolveDisplayConcentration (AUT-1375 A1.1)', () => {
  it('should prefer pump SSOT over Assist fields', () => {
    expect(resolveDisplayConcentration(100.885, 4, 4)).toBe(100.885)
  })

  it('should fall back to Assist A/B when pump unset', () => {
    expect(resolveDisplayConcentration(null, 221.4545, 4)).toBe(221.4545)
  })

  it('should fall back to legacy Assist concentration', () => {
    expect(resolveDisplayConcentration(undefined, null, 100)).toBe(100)
  })

  it('should return null when all sources empty (UI shows nicht kalibriert)', () => {
    expect(resolveDisplayConcentration(null, null, null)).toBeNull()
    expect(resolveDisplayConcentration(0, -1, undefined)).toBeNull()
  })
})
