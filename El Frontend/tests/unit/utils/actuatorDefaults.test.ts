/**
 * Actuator Defaults Utility Unit Tests
 *
 * Tests for actuator type configuration, categories, and helper functions.
 */

import { describe, it, expect } from 'vitest'
import {
  ACTUATOR_TYPE_CONFIG,
  ACTUATOR_CATEGORIES,
  getActuatorConfig,
  getActuatorLabel,
  getActuatorTypeOptions,
  isPwmActuator,
  supportsAuxGpio,
  supportsInvertedLogic,
  getActuatorSafetyDefaults,
  getActuatorIcon,
  getActuatorTypesByCategory
} from '@/utils/actuatorDefaults'

// =============================================================================
// ACTUATOR_TYPE_CONFIG
// =============================================================================

describe('ACTUATOR_TYPE_CONFIG', () => {
  it('has 4 actuator types', () => {
    expect(Object.keys(ACTUATOR_TYPE_CONFIG)).toHaveLength(4)
    expect(ACTUATOR_TYPE_CONFIG).toHaveProperty('pump')
    expect(ACTUATOR_TYPE_CONFIG).toHaveProperty('valve')
    expect(ACTUATOR_TYPE_CONFIG).toHaveProperty('relay')
    expect(ACTUATOR_TYPE_CONFIG).toHaveProperty('pwm')
  })

  it('pump is not PWM', () => {
    expect(ACTUATOR_TYPE_CONFIG['pump'].isPwm).toBe(false)
  })

  it('pwm is PWM', () => {
    expect(ACTUATOR_TYPE_CONFIG['pwm'].isPwm).toBe(true)
  })

  it('pump has max runtime of 3600 seconds', () => {
    expect(ACTUATOR_TYPE_CONFIG['pump'].maxRuntimeSeconds).toBe(3600)
  })

  it('pump has cooldown of 30 seconds', () => {
    expect(ACTUATOR_TYPE_CONFIG['pump'].cooldownSeconds).toBe(30)
  })

  it('relay has no max runtime', () => {
    expect(ACTUATOR_TYPE_CONFIG['relay'].maxRuntimeSeconds).toBe(0)
  })

  it('each type has required properties', () => {
    for (const config of Object.values(ACTUATOR_TYPE_CONFIG)) {
      expect(config).toHaveProperty('label')
      expect(config).toHaveProperty('icon')
      expect(config).toHaveProperty('description')
      expect(config).toHaveProperty('category')
      expect(config).toHaveProperty('isPwm')
      expect(config).toHaveProperty('defaultValue')
      expect(config).toHaveProperty('maxRuntimeSeconds')
      expect(config).toHaveProperty('cooldownSeconds')
      expect(config).toHaveProperty('supportsAuxGpio')
      expect(config).toHaveProperty('supportsInvertedLogic')
    }
  })
})

// =============================================================================
// ACTUATOR_CATEGORIES
// =============================================================================

describe('ACTUATOR_CATEGORIES', () => {
  it('has 4 categories', () => {
    expect(Object.keys(ACTUATOR_CATEGORIES)).toHaveLength(4)
  })

  it('each category has name, icon, and order', () => {
    for (const category of Object.values(ACTUATOR_CATEGORIES)) {
      expect(category).toHaveProperty('name')
      expect(category).toHaveProperty('icon')
      expect(category).toHaveProperty('order')
      expect(typeof category.name).toBe('string')
      expect(typeof category.icon).toBe('string')
      expect(typeof category.order).toBe('number')
    }
  })

  it('has pump category', () => {
    expect(ACTUATOR_CATEGORIES['pump']?.name).toBe('Pumpen')
  })

  it('has valve category', () => {
    expect(ACTUATOR_CATEGORIES['valve']?.name).toBe('Ventile')
  })

  it('has relay category', () => {
    expect(ACTUATOR_CATEGORIES['relay']?.name).toBe('Relais')
  })

  it('has pwm category', () => {
    expect(ACTUATOR_CATEGORIES['pwm']?.name).toBe('PWM')
  })
})

// =============================================================================
// getActuatorConfig
// =============================================================================

describe('getActuatorConfig', () => {
  it('returns full config for pump', () => {
    const config = getActuatorConfig('pump')
    expect(config).toBeDefined()
    expect(config?.label).toBe('Pumpe')
    expect(config?.icon).toBe('Droplet')
    expect(config?.category).toBe('pump')
    expect(config?.isPwm).toBe(false)
    expect(config?.maxRuntimeSeconds).toBe(3600)
    expect(config?.cooldownSeconds).toBe(30)
  })

  it('returns undefined for unknown type', () => {
    expect(getActuatorConfig('unknown')).toBeUndefined()
  })

  it('returns config for valve', () => {
    const config = getActuatorConfig('valve')
    expect(config).toBeDefined()
    expect(config?.supportsAuxGpio).toBe(true)
  })

  it('returns config for relay', () => {
    const config = getActuatorConfig('relay')
    expect(config).toBeDefined()
    expect(config?.label).toBe('Relais')
  })

  it('returns config for pwm', () => {
    const config = getActuatorConfig('pwm')
    expect(config).toBeDefined()
    expect(config?.isPwm).toBe(true)
    expect(config?.supportsInvertedLogic).toBe(false)
  })
})

// =============================================================================
// getActuatorLabel
// =============================================================================

describe('getActuatorLabel', () => {
  it('returns label for pump', () => {
    expect(getActuatorLabel('pump')).toBe('Pumpe')
  })

  it('returns label for valve', () => {
    expect(getActuatorLabel('valve')).toBe('Ventil')
  })

  it('returns label for relay', () => {
    expect(getActuatorLabel('relay')).toBe('Relais')
  })

  it('returns label for pwm', () => {
    expect(getActuatorLabel('pwm')).toBe('PWM')
  })

  it('returns original type for unknown', () => {
    expect(getActuatorLabel('unknown')).toBe('unknown')
  })
})

// =============================================================================
// getActuatorTypeOptions
// =============================================================================

describe('getActuatorTypeOptions', () => {
  it('returns array of 4 options', () => {
    const options = getActuatorTypeOptions()
    expect(Array.isArray(options)).toBe(true)
    expect(options).toHaveLength(4)
  })

  it('each option has value and label', () => {
    const options = getActuatorTypeOptions()
    for (const option of options) {
      expect(option).toHaveProperty('value')
      expect(option).toHaveProperty('label')
      expect(typeof option.value).toBe('string')
      expect(typeof option.label).toBe('string')
    }
  })

  it('contains pump option', () => {
    const options = getActuatorTypeOptions()
    const pump = options.find(opt => opt.value === 'pump')
    expect(pump).toBeDefined()
    expect(pump?.label).toBe('Pumpe')
  })

  it('contains valve option', () => {
    const options = getActuatorTypeOptions()
    const valve = options.find(opt => opt.value === 'valve')
    expect(valve).toBeDefined()
    expect(valve?.label).toBe('Ventil')
  })

  it('contains relay option', () => {
    const options = getActuatorTypeOptions()
    const relay = options.find(opt => opt.value === 'relay')
    expect(relay).toBeDefined()
    expect(relay?.label).toBe('Relais')
  })

  it('contains pwm option', () => {
    const options = getActuatorTypeOptions()
    const pwm = options.find(opt => opt.value === 'pwm')
    expect(pwm).toBeDefined()
    expect(pwm?.label).toBe('PWM')
  })
})

// =============================================================================
// isPwmActuator
// =============================================================================

describe('isPwmActuator', () => {
  it('returns true for pwm', () => {
    expect(isPwmActuator('pwm')).toBe(true)
  })

  it('returns false for pump', () => {
    expect(isPwmActuator('pump')).toBe(false)
  })

  it('returns false for valve', () => {
    expect(isPwmActuator('valve')).toBe(false)
  })

  it('returns false for relay', () => {
    expect(isPwmActuator('relay')).toBe(false)
  })

  it('returns false for unknown', () => {
    expect(isPwmActuator('unknown')).toBe(false)
  })
})

// =============================================================================
// supportsAuxGpio
// =============================================================================

describe('supportsAuxGpio', () => {
  it('returns true for valve', () => {
    expect(supportsAuxGpio('valve')).toBe(true)
  })

  it('returns false for pump', () => {
    expect(supportsAuxGpio('pump')).toBe(false)
  })

  it('returns false for relay', () => {
    expect(supportsAuxGpio('relay')).toBe(false)
  })

  it('returns false for pwm', () => {
    expect(supportsAuxGpio('pwm')).toBe(false)
  })

  it('returns false for unknown', () => {
    expect(supportsAuxGpio('unknown')).toBe(false)
  })
})

// =============================================================================
// supportsInvertedLogic
// =============================================================================

describe('supportsInvertedLogic', () => {
  it('returns true for pump', () => {
    expect(supportsInvertedLogic('pump')).toBe(true)
  })

  it('returns true for valve', () => {
    expect(supportsInvertedLogic('valve')).toBe(true)
  })

  it('returns true for relay', () => {
    expect(supportsInvertedLogic('relay')).toBe(true)
  })

  it('returns false for pwm', () => {
    expect(supportsInvertedLogic('pwm')).toBe(false)
  })

  it('returns false for unknown', () => {
    expect(supportsInvertedLogic('unknown')).toBe(false)
  })
})

// =============================================================================
// getActuatorSafetyDefaults
// =============================================================================

describe('getActuatorSafetyDefaults', () => {
  it('returns safety defaults for pump', () => {
    const safety = getActuatorSafetyDefaults('pump')
    expect(safety).toEqual({
      maxRuntime: 3600,
      cooldown: 30
    })
  })

  it('returns zero defaults for relay', () => {
    const safety = getActuatorSafetyDefaults('relay')
    expect(safety).toEqual({
      maxRuntime: 0,
      cooldown: 0
    })
  })

  it('returns zero defaults for valve', () => {
    const safety = getActuatorSafetyDefaults('valve')
    expect(safety).toEqual({
      maxRuntime: 0,
      cooldown: 0
    })
  })

  it('returns zero defaults for pwm', () => {
    const safety = getActuatorSafetyDefaults('pwm')
    expect(safety).toEqual({
      maxRuntime: 0,
      cooldown: 0
    })
  })

  it('returns zero defaults for unknown type', () => {
    const safety = getActuatorSafetyDefaults('unknown')
    expect(safety).toEqual({
      maxRuntime: 0,
      cooldown: 0
    })
  })
})

// =============================================================================
// getActuatorIcon
// =============================================================================

describe('getActuatorIcon', () => {
  it('returns icon for pump', () => {
    expect(getActuatorIcon('pump')).toBe('Droplet')
  })

  it('returns icon for valve', () => {
    expect(getActuatorIcon('valve')).toBe('Zap')
  })

  it('returns icon for relay', () => {
    expect(getActuatorIcon('relay')).toBe('Power')
  })

  it('returns icon for pwm', () => {
    expect(getActuatorIcon('pwm')).toBe('Gauge')
  })

  it('returns default icon for unknown', () => {
    expect(getActuatorIcon('unknown')).toBe('Power')
  })
})

// =============================================================================
// getActuatorTypesByCategory
// =============================================================================

describe('getActuatorTypesByCategory', () => {
  it('returns object with all 4 categories', () => {
    const grouped = getActuatorTypesByCategory()
    expect(grouped).toHaveProperty('pump')
    expect(grouped).toHaveProperty('valve')
    expect(grouped).toHaveProperty('relay')
    expect(grouped).toHaveProperty('pwm')
  })

  it('has pump in pump category', () => {
    const grouped = getActuatorTypesByCategory()
    const pumpTypes = grouped['pump']
    expect(pumpTypes).toBeDefined()
    expect(pumpTypes.length).toBeGreaterThan(0)
    const pump = pumpTypes.find(item => item.type === 'pump')
    expect(pump).toBeDefined()
    expect(pump?.config.label).toBe('Pumpe')
  })

  it('has valve in valve category', () => {
    const grouped = getActuatorTypesByCategory()
    const valveTypes = grouped['valve']
    expect(valveTypes).toBeDefined()
    const valve = valveTypes.find(item => item.type === 'valve')
    expect(valve).toBeDefined()
  })

  it('has relay in relay category', () => {
    const grouped = getActuatorTypesByCategory()
    const relayTypes = grouped['relay']
    expect(relayTypes).toBeDefined()
    const relay = relayTypes.find(item => item.type === 'relay')
    expect(relay).toBeDefined()
  })

  it('has pwm in pwm category', () => {
    const grouped = getActuatorTypesByCategory()
    const pwmTypes = grouped['pwm']
    expect(pwmTypes).toBeDefined()
    const pwm = pwmTypes.find(item => item.type === 'pwm')
    expect(pwm).toBeDefined()
  })

  it('each item has type and config', () => {
    const grouped = getActuatorTypesByCategory()
    for (const category of Object.values(grouped)) {
      for (const item of category) {
        expect(item).toHaveProperty('type')
        expect(item).toHaveProperty('config')
        expect(typeof item.type).toBe('string')
        expect(item.config).toBeDefined()
      }
    }
  })
})
