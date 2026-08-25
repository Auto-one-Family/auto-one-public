import { describe, it, expect } from 'vitest'
import {
  hasAnyElementPct,
  saltSourceTypeLabel,
  validateSaltCompositionWrite,
} from '@/api/saltCompositions'

describe('saltCompositions', () => {
  it('should label source types in Klartext', () => {
    expect(saltSourceTypeLabel('beleg_offen')).toBe('[BELEG offen]')
    expect(saltSourceTypeLabel('manufacturer_label')).toBe('Hersteller-Etikett')
    expect(saltSourceTypeLabel('stoichiometric')).toBe('stöchiometrisch abgeleitet')
  })

  it('should allow incomplete beleg_offen without element values', () => {
    expect(
      validateSaltCompositionWrite({
        name: 'Kristalon Rot',
        source_type: 'beleg_offen',
        n_pct: null,
        p_pct: null,
        k_pct: null,
      }),
    ).toBeNull()
  })

  it('should reject element values still marked beleg_offen', () => {
    expect(
      validateSaltCompositionWrite({
        name: 'Kristalon Rot',
        source_type: 'beleg_offen',
        n_pct: 12,
        p_pct: 12,
        k_pct: 17,
      }),
    ).toMatch(/Herkunft/)
  })

  it('should require source note for manufacturer_label with values', () => {
    expect(
      validateSaltCompositionWrite({
        name: 'Kristalon Rot',
        source_type: 'manufacturer_label',
        n_pct: 12,
        source_note: '',
      }),
    ).toMatch(/Quellenangabe/)
  })

  it('should detect any element pct', () => {
    expect(hasAnyElementPct({ n_pct: null, p_pct: 1 })).toBe(true)
    expect(hasAnyElementPct({ n_pct: null, p_pct: null })).toBe(false)
  })
})
