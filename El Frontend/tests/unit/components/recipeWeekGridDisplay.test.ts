import { describe, it, expect } from 'vitest'
import {
  buildRecipeGridColumns,
  buildWeekGridCell,
  combineSolutionMgPerL,
  elementalPartsToOxidNpk,
  formatMgPerLDisplay,
  formatOxidNpkRatio,
  formatTargetGoals,
  formatTargetGoalsLine,
  normalizeOxidNpkToTargetN,
  oxidLabelToElementalNpk,
  phaseDisplayLabel,
  phaseKeyFromSegment,
  phaseOxidLabel,
} from '@/components/plan-timeline/recipeWeekGridDisplay'
import type { StockMixRecipe } from '@/api/stockMixRecipes'
import type { PlanSegment } from '@/types/planSegment'

function seg(partial: Partial<PlanSegment> & Pick<PlanSegment, 'measure' | 'from_ts'>): PlanSegment {
  return {
    id: partial.id ?? 's1',
    zone_id: partial.zone_id ?? 'zone-a',
    domain: partial.domain ?? 'nutrient_solution',
    measure: partial.measure,
    value: partial.value ?? null,
    recipe_ref: partial.recipe_ref ?? null,
    from_ts: partial.from_ts,
    to_ts: partial.to_ts ?? null,
    interp: 'step',
    phase_ref: partial.phase_ref ?? null,
    status: 'planned',
    tolerance: null,
    created_at: '',
    updated_at: '',
  }
}

function recipe(partial: Partial<StockMixRecipe> & { dose_role: string }): StockMixRecipe {
  return {
    id: 'r1',
    label: 'test',
    coverage: 'phase_specific',
    nutrient_phase: 'uebergang-vorbluete',
    components: [],
    metadata: { dose_ml_per_l: { part_a: 4, part_b: 4 } },
    active: true,
    created_at: '',
    updated_at: '',
    ...partial,
  }
}

/** Real Übergang 8-6-12 stock values from DB (g/L elemental). */
const UEBERGANG_A = {
  n: 13.5625,
  p: 0,
  k: 0,
  ca: 16.259338,
  mg: 0,
  s: 0,
  unit: 'g_per_l_stock',
  computed: true,
}

const UEBERGANG_B = {
  n: 7.5,
  p: 6.110688,
  k: 22.265875,
  ca: 0,
  mg: 5.68366,
  s: 7.775,
  unit: 'g_per_l_stock',
  computed: true,
}

describe('recipeWeekGridDisplay', () => {
  it('should map phase_ref and legacy recipe_ref labels to phase keys', () => {
    expect(phaseKeyFromSegment({ phase_ref: 'veg-frueh' })).toBe('veg-frueh')
    expect(phaseKeyFromSegment({ recipe_ref: 'Vegetation 16-7-20' })).toBe('veg-frueh')
    expect(phaseKeyFromSegment({ recipe_ref: 'Uebergang/Vorbluete 8-6-12' })).toBe(
      'uebergang-vorbluete',
    )
  })

  it('should show phase name without oxid tag as primary label', () => {
    expect(phaseDisplayLabel('uebergang-vorbluete')).toBe('Übergang/Vorblüte')
    expect(phaseDisplayLabel('uebergang-vorbluete')).not.toMatch(/8-6-12/)
    expect(phaseOxidLabel('uebergang-vorbluete')).toBe('8-6-12')
  })

  it('should convert oxid-form NPK labels to elemental N-P-K correctly', () => {
    // P₂O₅×0.4364, K₂O×0.8302 — rounded integers
    expect(oxidLabelToElementalNpk('16-7-20')).toBe('16-3-17')
    expect(oxidLabelToElementalNpk('8-6-12')).toBe('8-3-10')
    expect(oxidLabelToElementalNpk('8-11-16')).toBe('8-5-13')
    expect(7 * 0.4364).toBeCloseTo(3.0548, 3)
    expect(20 * 0.8302).toBeCloseTo(16.604, 3)
    expect(6 * 0.4364).toBeCloseTo(2.6184, 3)
    expect(12 * 0.8302).toBeCloseTo(9.9624, 3)
    expect(11 * 0.4364).toBeCloseTo(4.8004, 3)
    expect(16 * 0.8302).toBeCloseTo(13.2832, 3)
  })

  it('should combine A+B × dose into finished-solution mg/L (Übergang self-check)', () => {
    const partA = recipe({
      dose_role: 'part_a',
      computed_elements: UEBERGANG_A,
      computed_npk: { n: 13.5625, p: 0, k: 0, computed: true },
      npk_status: 'complete',
    })
    const partB = recipe({
      dose_role: 'part_b',
      computed_elements: UEBERGANG_B,
      computed_npk: { n: 7.5, p: 6.110688, k: 22.265875, computed: true },
      npk_status: 'complete',
    })
    const { mgPerL } = combineSolutionMgPerL(partA, partB)
    expect(mgPerL.n).toBeCloseTo(84.25, 1)
    expect(mgPerL.p).toBeCloseTo(24.44, 1)
    expect(mgPerL.k).toBeCloseTo(89.06, 1)
    expect(mgPerL.ca).toBeCloseTo(65.04, 1)
    expect(mgPerL.mg).toBeCloseTo(22.73, 1)
    expect(mgPerL.s).toBeCloseTo(31.1, 1)

    const cell = buildWeekGridCell({
      phaseKey: 'uebergang-vorbluete',
      resolved: true,
      partA,
      partB,
    })
    expect(cell.status).toBe('complete')
    expect(cell.suggestedNpkDisplay).toBe('8-6-12')
    // Same N-scale as suggestion (display-only); honest small delta vs 8-6-12
    expect(cell.npkRatioDisplay).toBe('8-5-10')
    expect(cell.macros.find((m) => m.key === 'n')?.display).toBe(formatMgPerLDisplay(84.25))
    expect(cell.macros.find((m) => m.key === 'p')?.display).toBe(formatMgPerLDisplay(24.442752))
    expect(cell.macros.find((m) => m.key === 'k')?.display).toBe(formatMgPerLDisplay(89.0635))
    expect(cell.macros.find((m) => m.key === 'ca')?.display).toBe(formatMgPerLDisplay(65.037352))
    expect(cell.macros.find((m) => m.key === 'mg')?.display).toBe(formatMgPerLDisplay(22.73464))
    expect(cell.macros.find((m) => m.key === 's')?.display).toBe(formatMgPerLDisplay(31.1))
    expect(cell.doseLine).toMatch(/So mischst du es/)
    expect(cell.doseLine).toMatch(/ml A/)
    // No per-stock prominent content / no berechnet badge
    expect(cell.lines.some((l) => l.startsWith('Stock A'))).toBe(false)
    expect(cell.lines.some((l) => l === 'berechnet')).toBe(false)
  })

  it('should normalize recipe oxid NPK to suggested N for digit-comparable display', () => {
    const oxid = elementalPartsToOxidNpk(21.0625, 6.110688, 22.265875)
    expect(formatOxidNpkRatio(oxid.n, oxid.p, oxid.k).display).toBe('21-14-27')
    const norm = normalizeOxidNpkToTargetN(oxid.n, oxid.p, oxid.k, 8)
    expect(formatOxidNpkRatio(norm.n, norm.p, norm.k).display).toBe('8-5-10')

    // Vegetation: unnormalized ~40-17-49 → N=16 → 16-7-20
    const vegOxid = elementalPartsToOxidNpk(39.75, 7.201013, 41.092425)
    const vegNorm = normalizeOxidNpkToTargetN(vegOxid.n, vegOxid.p, vegOxid.k, 16)
    expect(formatOxidNpkRatio(vegNorm.n, vegNorm.p, vegNorm.k).display).toBe('16-7-20')
  })

  it('should show traces only when present', () => {
    const cell = buildWeekGridCell({
      phaseKey: 'uebergang-vorbluete',
      resolved: true,
      partA: recipe({
        dose_role: 'part_a',
        computed_elements: { ...UEBERGANG_A, fe: 0.5 },
        npk_status: 'complete',
      }),
      partB: recipe({
        dose_role: 'part_b',
        computed_elements: UEBERGANG_B,
        npk_status: 'complete',
      }),
    })
    expect(cell.tracesLabel).toBe('+ Spurenelemente')
    expect(cell.tracesTitle).toMatch(/Fe/)
  })

  it('should flag incomplete when salt evidence missing', () => {
    const cell = buildWeekGridCell({
      phaseKey: 'veg-frueh',
      resolved: true,
      partA: recipe({
        dose_role: 'part_a',
        computed_elements: { n: 1, p: 0, k: 0, ca: 0, mg: 0, s: 0 },
        npk_status: 'complete',
      }),
      partB: recipe({
        dose_role: 'part_b',
        computed_elements: { n: 0, p: 0, k: 0, ca: 0, mg: 0, s: 0 },
        npk_status: 'incomplete',
        npk_missing_salts: ['Kristalon Rot'],
      }),
    })
    expect(cell.status).toBe('incomplete')
    expect(cell.warnings.some((l) => l.includes('Kristalon Rot'))).toBe(true)
  })

  it('should show keine Rezeptur hinterlegt when unresolved', () => {
    const cell = buildWeekGridCell({
      phaseKey: 'veg-frueh',
      resolved: false,
    })
    expect(cell.status).toBe('unresolved')
    expect(cell.lines[0]).toMatch(/keine Rezeptur/)
  })

  it('should build one column per EC/pH staffel with phase title and oxid tag separate', () => {
    const columns = buildRecipeGridColumns(
      [
        seg({
          id: 'ec1',
          measure: 'target_ec',
          value: 1400,
          from_ts: '2026-07-13T00:00:00.000Z',
          to_ts: '2026-07-20T00:00:00.000Z',
          phase_ref: 'veg-frueh',
        }),
        seg({
          id: 'ph1',
          measure: 'target_ph',
          value: 5.8,
          from_ts: '2026-07-13T00:00:00.000Z',
          to_ts: '2026-07-20T00:00:00.000Z',
          phase_ref: 'veg-frueh',
        }),
        seg({
          id: 'ec2',
          measure: 'target_ec',
          value: 1600,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
          phase_ref: 'uebergang-vorbluete',
        }),
      ],
      'zone-a',
    )
    expect(columns).toHaveLength(2)
    expect(columns[0].title).toBe('Vegetation')
    expect(columns[0].oxidLabel).toBe('16-7-20')
    expect(columns[0].targetEcUsCm).toBe(1400)
    expect(columns[0].targetPh).toBe(5.8)
    expect(columns[1].title).toBe('Übergang/Vorblüte')
    expect(columns[1].oxidLabel).toBe('8-6-12')
    expect(columns[1].targetEcUsCm).toBe(1600)
    const goals = formatTargetGoalsLine(columns[0]).join(' ')
    expect(goals).toMatch(/1[.\u00a0\s]?400/)
    expect(goals).toMatch(/5[,.]8/)
    const structured = formatTargetGoals(columns[0])
    expect(structured[0].label).toBe('EC')
    expect(structured[0].valueDisplay).toMatch(/1[.\u00a0\s]?400/)
    expect(structured[0].unit).toBe('µS/cm')
    expect(structured[1].label).toBe('pH')
    expect(structured[1].valueDisplay).toMatch(/5[,.]8/)
  })

  it('should not invent calendar-week columns without plan staffeln', () => {
    expect(buildRecipeGridColumns([], 'zone-a')).toEqual([])
  })
})
