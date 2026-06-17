/**
 * Subzone Helper Utilities Unit Tests
 *
 * Tests for normalizeSubzoneId and slugifyGerman functions.
 * Covers German umlaut transliteration, edge cases, and slug formatting.
 */

import { describe, it, expect } from 'vitest'
import { normalizeSubzoneId, slugifyGerman } from '@/utils/subzoneHelpers'

// =============================================================================
// normalizeSubzoneId
// =============================================================================

describe('normalizeSubzoneId', () => {
  it('returns null for null input', () => {
    expect(normalizeSubzoneId(null)).toBeNull()
  })

  it('returns null for undefined input', () => {
    expect(normalizeSubzoneId(undefined)).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(normalizeSubzoneId('')).toBeNull()
  })

  it('returns null for __none__ sentinel', () => {
    expect(normalizeSubzoneId('__none__')).toBeNull()
  })

  it('returns null for whitespace-only string', () => {
    expect(normalizeSubzoneId('   ')).toBeNull()
  })

  it('returns trimmed string for valid input', () => {
    expect(normalizeSubzoneId('  innen  ')).toBe('innen')
  })

  it('passes through valid subzone ids', () => {
    expect(normalizeSubzoneId('aussen')).toBe('aussen')
  })
})

// =============================================================================
// slugifyGerman — Umlaut Transliteration
// =============================================================================

describe('slugifyGerman', () => {
  describe('German umlaut transliteration', () => {
    it('transliterates lowercase ae to ae', () => {
      expect(slugifyGerman('Aerger')).toBe('aerger')
    })

    it('transliterates lowercase oe to oe', () => {
      expect(slugifyGerman('Hoehe')).toBe('hoehe')
    })

    it('transliterates lowercase ue to ue', () => {
      expect(slugifyGerman('Gruen')).toBe('gruen')
    })

    it('transliterates ss to ss', () => {
      expect(slugifyGerman('Aussen')).toBe('aussen')
    })

    it('transliterates uppercase Ae to ae (after lowercasing)', () => {
      expect(slugifyGerman('Ae')).toBe('ae')
    })

    it('transliterates uppercase Oe to oe (after lowercasing)', () => {
      expect(slugifyGerman('Oe')).toBe('oe')
    })

    it('transliterates uppercase Ue to ue (after lowercasing)', () => {
      expect(slugifyGerman('Ue')).toBe('ue')
    })
  })

  describe('combined transliteration', () => {
    it('handles multiple umlauts in one word', () => {
      expect(slugifyGerman('Uebergroesse')).toBe('uebergroesse')
    })

    it('handles Naehrloesung example from docstring', () => {
      expect(slugifyGerman('Naehrloesung')).toBe('naehrloesung')
    })

    it('handles words without umlauts', () => {
      expect(slugifyGerman('Innen')).toBe('innen')
    })
  })

  describe('slug formatting', () => {
    it('replaces spaces with underscores', () => {
      expect(slugifyGerman('Pflanze 1')).toBe('pflanze_1')
    })

    it('replaces multiple spaces with single underscore', () => {
      expect(slugifyGerman('Pflanze   Eins')).toBe('pflanze_eins')
    })

    it('handles Gewaechshaus Alpha example from docstring', () => {
      expect(slugifyGerman('Gewaechshaus Alpha')).toBe('gewaechshaus_alpha')
    })

    it('strips leading underscores', () => {
      expect(slugifyGerman(' Test')).toBe('test')
    })

    it('strips trailing underscores', () => {
      expect(slugifyGerman('Test ')).toBe('test')
    })

    it('replaces special characters with underscores', () => {
      expect(slugifyGerman('Zone-A/B')).toBe('zone_a_b')
    })

    it('lowercases all characters', () => {
      expect(slugifyGerman('OBERSTES STOCKWERK')).toBe('oberstes_stockwerk')
    })
  })

  describe('edge cases', () => {
    it('returns empty string for empty input', () => {
      expect(slugifyGerman('')).toBe('')
    })

    it('returns empty string for only special characters', () => {
      expect(slugifyGerman('---')).toBe('')
    })

    it('returns empty string for only whitespace', () => {
      expect(slugifyGerman('   ')).toBe('')
    })

    it('handles single character', () => {
      expect(slugifyGerman('A')).toBe('a')
    })

    it('handles numeric input', () => {
      expect(slugifyGerman('Zone 42')).toBe('zone_42')
    })
  })
})
