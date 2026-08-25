import { describe, expect, it } from 'vitest'
import { PLANT_PHASES } from '@/types'
import {
  displayGrowthPhase,
  normalizeGrowthPhase,
} from '@/utils/growthPhaseVocabulary'

describe('growthPhaseVocabulary', () => {
  it('should map legacy zone-context strings onto the plant vocabulary', () => {
    expect(normalizeGrowthPhase('flower_week_5')).toBe('bluete-bulk')
    expect(normalizeGrowthPhase('vegetative')).toBe('veg-frueh')
    expect(normalizeGrowthPhase('pre_flower')).toBe('uebergang-vorbluete')
    expect(normalizeGrowthPhase('harvest')).toBe('harvested')
    expect(normalizeGrowthPhase('not-a-phase')).toBeNull()
  })

  it('should keep every canonical plant phase as identity', () => {
    for (const phase of PLANT_PHASES) {
      expect(normalizeGrowthPhase(phase)).toBe(phase)
    }
  })

  it('should show German labels for mapped and canonical keys', () => {
    expect(displayGrowthPhase('flower_week_5')).toBe('Blüte – Bulk')
    expect(displayGrowthPhase('veg-frueh')).toBe('Vegetativ (früh)')
  })
})
