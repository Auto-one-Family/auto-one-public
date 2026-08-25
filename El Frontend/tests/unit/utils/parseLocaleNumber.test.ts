import { describe, it, expect } from 'vitest'
import {
  coerceLocaleNumberInput,
  normalizeLocaleNumberString,
  parseLocaleNumber,
  parseLocaleNumberOrNull,
} from '@/utils/parseLocaleNumber'

describe('parseLocaleNumber', () => {
  it('should normalize German comma to dot', () => {
    expect(normalizeLocaleNumberString('5,9')).toBe('5.9')
    expect(normalizeLocaleNumberString(' 1400,5 ')).toBe('1400.5')
  })

  it('should parse "5,9" as 5.9 (kein NaN)', () => {
    expect(parseLocaleNumber('5,9')).toBe(5.9)
    expect(Number.isNaN(parseLocaleNumber('5,9'))).toBe(false)
  })

  it('should parse plain dot and number passthrough', () => {
    expect(parseLocaleNumber('5.9')).toBe(5.9)
    expect(parseLocaleNumber(5.9)).toBe(5.9)
  })

  it('should return null for empty via OrNull', () => {
    expect(parseLocaleNumberOrNull('')).toBeNull()
    expect(parseLocaleNumberOrNull('5,9')).toBe(5.9)
    expect(parseLocaleNumberOrNull('abc')).toBeNull()
  })

  it('should keep incomplete decimal while typing via coerce', () => {
    expect(coerceLocaleNumberInput('5,')).toBe('5,')
    expect(coerceLocaleNumberInput('5,9')).toBe(5.9)
  })
})
