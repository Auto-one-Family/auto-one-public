import { describe, it, expect } from 'vitest'
import { formatStockConcentrationStatus } from '@/components/plants/stockConcentrationStatus'

describe('formatStockConcentrationStatus', () => {
  it('should show pending remeasure without identity when concentration is null', () => {
    const s = formatStockConcentrationStatus({ concentration: null })
    expect(s.kind).toBe('pending_remeasure')
    expect(s.label).toBe('Konzentration: wird bei nächster Dosierung neu gemessen')
    expect(s.shortLabel).toBe('wird neu gemessen')
  })

  it('should append recipe and date when pending with identity', () => {
    const s = formatStockConcentrationStatus({
      concentration: null,
      recipeLabel: 'Übergang 8-6-12 Teil B',
      stockPreparedAt: '2026-07-27T08:00:00.000Z',
    })
    expect(s.kind).toBe('pending_remeasure')
    expect(s.label).toContain('wird bei nächster Dosierung neu gemessen')
    expect(s.label).toContain('Übergang 8-6-12 Teil B')
    expect(s.shortLabel).toContain('wird neu gemessen')
    expect(s.shortLabel).toContain('Übergang 8-6-12 Teil B')
  })

  it('should show measured without inventing recipe when identity missing', () => {
    const s = formatStockConcentrationStatus({ concentration: 12.5 })
    expect(s.kind).toBe('measured')
    expect(s.label).toBe('gemessen')
    expect(s.shortLabel).toBe('gemessen')
  })

  it('should show measured with recipe and date when identity present', () => {
    const s = formatStockConcentrationStatus({
      concentration: 12.5,
      recipeLabel: 'Veg Teil A',
      stockPreparedAt: '2026-07-27T10:15:00.000Z',
    })
    expect(s.kind).toBe('measured')
    expect(s.label).toContain('gemessen')
    expect(s.label).toContain('Veg Teil A')
    expect(s.shortLabel).toBe(s.label)
  })
})
