import { describe, expect, it } from 'vitest'
import {
  clampPlanMeasureValue,
  getPlanMeasureInputSpec,
} from '@/components/plan-timeline/planMeasureInput'
import { getSensorUnit } from '@/utils/sensorDefaults'

describe('planMeasureInput', () => {
  it('should use µS/cm for target_ec matching sensorDefaults SSOT', () => {
    const spec = getPlanMeasureInputSpec('target_ec')
    expect(spec).not.toBeNull()
    expect(spec?.unit).toBe('µS/cm')
    expect(spec?.unit).toBe(getSensorUnit('ec'))
    expect(spec?.max).toBe(5000)
    expect(spec?.min).toBe(0)
  })

  it('should accept typical nutrient EC targets around 1400 µS/cm', () => {
    expect(clampPlanMeasureValue('target_ec', 1400)).toBe(1400)
    expect(clampPlanMeasureValue('target_ec', 1394.9)).toBe(1394.9)
  })

  it('should clamp EC above physical max without treating as mS', () => {
    expect(clampPlanMeasureValue('target_ec', 6000)).toBe(5000)
    // Legacy mS-scale 1.4 must NOT be accepted as "valid max" anymore
    expect(getPlanMeasureInputSpec('target_ec')?.max).toBeGreaterThan(5)
  })

  it('should keep pH bounds 0–14', () => {
    const spec = getPlanMeasureInputSpec('target_ph')
    expect(spec?.min).toBe(0)
    expect(spec?.max).toBe(14)
    expect(clampPlanMeasureValue('target_ph', 5.9)).toBe(5.9)
  })
})
