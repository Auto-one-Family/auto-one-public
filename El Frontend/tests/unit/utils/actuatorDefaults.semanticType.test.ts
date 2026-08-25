/**
 * AUT-1302: semantic actuator type resolution (hardware_type preferred).
 */
import { describe, it, expect } from 'vitest'
import {
  resolveActuatorSemanticType,
  isPumpActuatorType,
} from '@/utils/actuatorDefaults'

describe('resolveActuatorSemanticType (AUT-1302)', () => {
  it('should prefer hardware_type over actuator_type', () => {
    expect(resolveActuatorSemanticType('digital', 'pump')).toBe('pump')
    expect(resolveActuatorSemanticType('digital', 'relay')).toBe('relay')
  })

  it('should fall back to actuator_type when hardware_type is null/empty', () => {
    expect(resolveActuatorSemanticType('pump', null)).toBe('pump')
    expect(resolveActuatorSemanticType('valve', undefined)).toBe('valve')
    expect(resolveActuatorSemanticType('relay', '')).toBe('relay')
  })

  it('should return empty string when both missing', () => {
    expect(resolveActuatorSemanticType(null, null)).toBe('')
  })
})

describe('isPumpActuatorType (AUT-1302)', () => {
  it('should be true for live digital+pump rows', () => {
    expect(isPumpActuatorType('digital', 'pump')).toBe(true)
  })

  it('should be true for direct pump token', () => {
    expect(isPumpActuatorType('pump', null)).toBe(true)
  })

  it('should be false for relay / valve', () => {
    expect(isPumpActuatorType('digital', 'relay')).toBe(false)
    expect(isPumpActuatorType('valve', null)).toBe(false)
  })
})
