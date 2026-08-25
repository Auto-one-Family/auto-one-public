import { describe, it, expect } from 'vitest'
import {
  gramsFromRecipe,
  diluteScaleFactor,
  effectiveGPerL,
  effectiveDoseMlPerL,
  resolveHandlingHint,
  concentrationFromDeltaEc,
  doseDurationSeconds,
  pairScaleFactor,
  resolveAbSplitWarning,
  STOCK_MIX_AB_SPLIT_WARNING,
} from '@/components/esp/recipeMixerCalcs'

describe('recipeMixerCalcs', () => {
  it('should compute grams via Dreisatz g = g/L × V_ml / 1000', () => {
    expect(gramsFromRecipe(10, 1000)).toBe(10)
    expect(gramsFromRecipe(2.5, 500)).toBe(1.25)
    expect(gramsFromRecipe(0, 1000)).toBe(0)
  })

  it('should compute F3 Veg-A Calcinit 150 g/L for 1000 ml as 150 g', () => {
    // AUT-1361: recipe target_g_per_l → gramsFromRecipe (user tippt keine g/L)
    expect(gramsFromRecipe(150, 1000)).toBe(150)
    expect(gramsFromRecipe(87.5, 1000)).toBe(87.5)
    expect(gramsFromRecipe(137.5, 2000)).toBe(275)
  })

  it('should reject invalid vessel or negative g/L for grams', () => {
    expect(gramsFromRecipe(10, 0)).toBeNull()
    expect(gramsFromRecipe(-1, 1000)).toBeNull()
    expect(gramsFromRecipe(Number.NaN, 1000)).toBeNull()
  })

  it('should auto-recompute Veg-B dilute without exposing factors to caller math', () => {
    // AUT-1362: internal 200/250 → scale 0.8; Kristalon 137.5 → 110; dose 4 → 5
    const scale = diluteScaleFactor(250, 200)
    expect(scale).toBeCloseTo(0.8)
    expect(effectiveGPerL(137.5, scale)).toBeCloseTo(110)
    expect(effectiveGPerL(87.5, scale)).toBeCloseTo(70)
    expect(gramsFromRecipe(effectiveGPerL(137.5, scale)!, 1000)).toBeCloseTo(110)
    expect(effectiveDoseMlPerL(4, scale)).toBeCloseTo(5)
    expect(effectiveGPerL(137.5, null)).toBe(137.5)
    expect(effectiveDoseMlPerL(4, null)).toBe(4)
  })

  it('should resolve handling_hint Klartext (metadata first, then role fallback)', () => {
    expect(resolveHandlingHint('part_a', { handling_hint: 'Nur umrühren.' })).toBe('Nur umrühren.')
    expect(resolveHandlingHint('part_b', {})).toMatch(/Warmes Wasser/)
    expect(resolveHandlingHint('ph_down', null)).toMatch(/Säure/)
    const hint = resolveHandlingHint('part_b', {})
    for (const banned of ['250×', '200×', 'Wachauge', '22,5', 'Arbeits-pH']) {
      expect(hint).not.toContain(banned)
    }
  })

  it('should compute concentration from ΔEC × V / dose_ml', () => {
    // +200 µS in 100 L after 50 ml → (200×100)/50 = 400
    expect(concentrationFromDeltaEc(800, 1000, 100, 50)).toBe(400)
  })

  it('should reject non-positive volume or dose for concentration', () => {
    expect(concentrationFromDeltaEc(800, 1000, 0, 50)).toBeNull()
    expect(concentrationFromDeltaEc(800, 1000, 100, 0)).toBeNull()
  })

  it('should ceil dose duration from flow rate', () => {
    expect(doseDurationSeconds(10, 2.5)).toBe(4)
    expect(doseDurationSeconds(1, 2)).toBe(1)
    expect(doseDurationSeconds(10, 0)).toBeNull()
  })

  it('should scale pair factor against seed (~100 default)', () => {
    expect(pairScaleFactor(120, 100)).toBe(1.2)
    expect(pairScaleFactor(150, null)).toBe(1.5)
    expect(pairScaleFactor(0, 100)).toBeNull()
  })

  it('should warn when Calcinit is outside part_a (AUT-1403 soft A/B split)', () => {
    expect(resolveAbSplitWarning('part_b', ['Calcinit'])).toBe(STOCK_MIX_AB_SPLIT_WARNING)
    expect(resolveAbSplitWarning('ph_down', ['Calcinit'])).toBe(STOCK_MIX_AB_SPLIT_WARNING)
    expect(resolveAbSplitWarning('part_a', ['Calcinit'])).toBeNull()
  })

  it('should warn when sulfate/phosphate salt lands in part_a (AUT-1403)', () => {
    expect(resolveAbSplitWarning('part_a', ['MgSO₄·7H₂O'])).toBe(STOCK_MIX_AB_SPLIT_WARNING)
    expect(resolveAbSplitWarning('part_a', ['Kristalon Rot'])).toBe(STOCK_MIX_AB_SPLIT_WARNING)
    expect(resolveAbSplitWarning('part_a', ['MKP'])).toBe(STOCK_MIX_AB_SPLIT_WARNING)
    expect(
      resolveAbSplitWarning('part_b', ['MgSO₄·7H₂O', 'Kristalon Rot', 'MKP']),
    ).toBeNull()
  })
})
