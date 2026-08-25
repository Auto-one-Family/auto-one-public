import { describe, it, expect } from 'vitest'
import {
  formatMeasuredFreshWaterOrigin,
  volumeZugabeSourceLabel,
} from '@/utils/volumeZugabeSourceDisplay'

describe('volumeZugabeSourceDisplay', () => {
  it('should label manual | measured | none', () => {
    expect(volumeZugabeSourceLabel('manual')).toBe('manuell')
    expect(volumeZugabeSourceLabel('measured')).toBe('gemessen')
    expect(volumeZugabeSourceLabel('none')).toBe('keine')
  })

  it('should format measured origin with rule name and volume', () => {
    const text = formatMeasuredFreshWaterOrigin({
      ruleName: 'Frischwasser',
      volumeL: 4.2,
      occurredAt: '2026-07-26T10:00:00.000Z',
    })
    expect(text).toContain('gemessen')
    expect(text).toContain('Frischwasser')
    expect(text).toContain('4.2')
  })
})
