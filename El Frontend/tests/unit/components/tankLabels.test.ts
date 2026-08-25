import { describe, expect, it } from 'vitest'
import {
  NUTRIENT_BATCH_ENTRY_TYPES,
  NUTRIENT_BATCH_ENTRY_TYPE_LABELS,
  showsComponents,
  showsMeasurements,
  showsRecipeLabel,
} from '@/components/plants/tankLabels'

describe('tankLabels', () => {
  it('should label every server entry_type without inventing extras', () => {
    expect(Object.keys(NUTRIENT_BATCH_ENTRY_TYPE_LABELS).sort()).toEqual(
      [...NUTRIENT_BATCH_ENTRY_TYPES].sort(),
    )
    expect(NUTRIENT_BATCH_ENTRY_TYPE_LABELS.full_reset).toBe('Neuansatz')
    expect(NUTRIENT_BATCH_ENTRY_TYPE_LABELS.system_incident).toBe('Anlagen-Vorfall')
  })

  it('should show components only for Neuansatz and Nachdosierung', () => {
    expect(showsComponents('full_reset')).toBe(true)
    expect(showsComponents('top_up_dose')).toBe(true)
    expect(showsComponents('withdrawal')).toBe(false)
    expect(showsComponents('remeasurement_only')).toBe(false)
    expect(showsComponents('system_incident')).toBe(false)
  })

  it('should expose measurement fields for Nachmessung and Vorfall', () => {
    expect(showsMeasurements('remeasurement_only')).toBe(true)
    expect(showsMeasurements('system_incident')).toBe(true)
    expect(showsRecipeLabel('system_incident')).toBe(true)
  })
})
