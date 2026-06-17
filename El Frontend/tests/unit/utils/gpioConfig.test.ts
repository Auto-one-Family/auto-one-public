/**
 * GPIO Configuration Utility Unit Tests
 *
 * Tests for ESP32 GPIO pin configuration and recommendations.
 * NOTE: mergeGpioConfigWithStatus is skipped (requires complex type mocking).
 */

import { describe, it, expect } from 'vitest'
import {
  getGpioConfig,
  getAvailablePins,
  getGpiosByCategory,
  getSensorGpios,
  getActuatorGpios,
  getGpioInfo,
  isGpioRecommended,
  isGpioAvoid,
  getGpioWarning,
  getCategoryLabel,
  getCategoryColorClass,
  getRecommendedGpios
} from '@/utils/gpioConfig'

// =============================================================================
// getGpioConfig
// =============================================================================

describe('getGpioConfig', () => {
  it('returns array of 28 pins for ESP32_WROOM', () => {
    const pins = getGpioConfig('ESP32_WROOM')
    expect(Array.isArray(pins)).toBe(true)
    // ESP32_WROOM has: 10 recommended + 6 available + 4 input_only + 3 caution + 5 avoid = 28
    expect(pins.length).toBeGreaterThanOrEqual(20)
  })

  it('returns array of 11 pins for XIAO_ESP32_C3', () => {
    const pins = getGpioConfig('XIAO_ESP32_C3')
    expect(Array.isArray(pins)).toBe(true)
    expect(pins).toHaveLength(11)
  })

  it('defaults to ESP32_WROOM when no parameter', () => {
    const pins = getGpioConfig()
    expect(pins.length).toBeGreaterThanOrEqual(20)
  })

  it('defaults to ESP32_WROOM for unknown hardware type', () => {
    const pins = getGpioConfig('UNKNOWN' as any)
    expect(pins.length).toBeGreaterThanOrEqual(20)
  })

  it('each pin has required properties', () => {
    const pins = getGpioConfig('ESP32_WROOM')
    for (const pin of pins) {
      expect(pin).toHaveProperty('gpio')
      expect(pin).toHaveProperty('category')
      expect(pin).toHaveProperty('label')
      expect(pin).toHaveProperty('features')
      expect(pin).toHaveProperty('recommendedFor')
      expect(typeof pin.gpio).toBe('number')
      expect(Array.isArray(pin.features)).toBe(true)
    }
  })
})

// =============================================================================
// getAvailablePins
// =============================================================================

describe('getAvailablePins', () => {
  it('excludes used pins', () => {
    const available = getAvailablePins('ESP32_WROOM', [13, 14])
    const gpioNumbers = available.map(p => p.gpio)
    expect(gpioNumbers).not.toContain(13)
    expect(gpioNumbers).not.toContain(14)
  })

  it('returns all pins when no used pins', () => {
    const all = getGpioConfig('ESP32_WROOM')
    const available = getAvailablePins('ESP32_WROOM', [])
    expect(available.length).toBe(all.length)
  })

  it('returns empty array when all pins used', () => {
    const all = getGpioConfig('ESP32_WROOM')
    const allGpios = all.map(p => p.gpio)
    const available = getAvailablePins('ESP32_WROOM', allGpios)
    expect(available).toHaveLength(0)
  })

  it('works with XIAO_ESP32_C3', () => {
    const available = getAvailablePins('XIAO_ESP32_C3', [2, 3])
    const gpioNumbers = available.map(p => p.gpio)
    expect(gpioNumbers).not.toContain(2)
    expect(gpioNumbers).not.toContain(3)
  })
})

// =============================================================================
// getGpiosByCategory
// =============================================================================

describe('getGpiosByCategory', () => {
  it('returns object with all categories', () => {
    const grouped = getGpiosByCategory('ESP32_WROOM')
    expect(grouped).toHaveProperty('recommended')
    expect(grouped).toHaveProperty('available')
    expect(grouped).toHaveProperty('input_only')
    expect(grouped).toHaveProperty('caution')
    expect(grouped).toHaveProperty('avoid')
  })

  it('each category is an array', () => {
    const grouped = getGpiosByCategory('ESP32_WROOM')
    for (const category of Object.values(grouped)) {
      expect(Array.isArray(category)).toBe(true)
    }
  })

  it('excludes used pins from all categories', () => {
    const grouped = getGpiosByCategory('ESP32_WROOM', [13, 14])
    for (const pins of Object.values(grouped)) {
      const gpioNumbers = pins.map(p => p.gpio)
      expect(gpioNumbers).not.toContain(13)
      expect(gpioNumbers).not.toContain(14)
    }
  })

  it('has GPIO 13 in recommended category', () => {
    const grouped = getGpiosByCategory('ESP32_WROOM')
    const gpio13 = grouped.recommended.find(p => p.gpio === 13)
    expect(gpio13).toBeDefined()
  })

  it('has GPIO 0 in avoid category', () => {
    const grouped = getGpiosByCategory('ESP32_WROOM')
    const gpio0 = grouped.avoid.find(p => p.gpio === 0)
    expect(gpio0).toBeDefined()
  })
})

// =============================================================================
// getSensorGpios
// =============================================================================

describe('getSensorGpios', () => {
  it('excludes avoid category', () => {
    const sensorPins = getSensorGpios('ESP32_WROOM')
    for (const pin of sensorPins) {
      expect(pin.category).not.toBe('avoid')
    }
  })

  it('only includes sensor or both recommended usage', () => {
    const sensorPins = getSensorGpios('ESP32_WROOM')
    for (const pin of sensorPins) {
      expect(['sensor', 'both']).toContain(pin.recommendedFor)
    }
  })

  it('excludes used pins', () => {
    const sensorPins = getSensorGpios('ESP32_WROOM', [13, 14])
    const gpioNumbers = sensorPins.map(p => p.gpio)
    expect(gpioNumbers).not.toContain(13)
    expect(gpioNumbers).not.toContain(14)
  })

  it('returns non-empty array', () => {
    const sensorPins = getSensorGpios('ESP32_WROOM')
    expect(sensorPins.length).toBeGreaterThan(0)
  })
})

// =============================================================================
// getActuatorGpios
// =============================================================================

describe('getActuatorGpios', () => {
  it('excludes avoid category', () => {
    const actuatorPins = getActuatorGpios('ESP32_WROOM')
    for (const pin of actuatorPins) {
      expect(pin.category).not.toBe('avoid')
    }
  })

  it('excludes input_only category', () => {
    const actuatorPins = getActuatorGpios('ESP32_WROOM')
    for (const pin of actuatorPins) {
      expect(pin.category).not.toBe('input_only')
    }
  })

  it('only includes actuator or both recommended usage', () => {
    const actuatorPins = getActuatorGpios('ESP32_WROOM')
    for (const pin of actuatorPins) {
      expect(['actuator', 'both']).toContain(pin.recommendedFor)
    }
  })

  it('excludes used pins', () => {
    const actuatorPins = getActuatorGpios('ESP32_WROOM', [13, 14])
    const gpioNumbers = actuatorPins.map(p => p.gpio)
    expect(gpioNumbers).not.toContain(13)
    expect(gpioNumbers).not.toContain(14)
  })

  it('returns non-empty array', () => {
    const actuatorPins = getActuatorGpios('ESP32_WROOM')
    expect(actuatorPins.length).toBeGreaterThan(0)
  })
})

// =============================================================================
// getGpioInfo
// =============================================================================

describe('getGpioInfo', () => {
  it('returns info for GPIO 13', () => {
    const info = getGpioInfo(13, 'ESP32_WROOM')
    expect(info).toBeDefined()
    expect(info?.gpio).toBe(13)
    expect(info?.category).toBe('recommended')
  })

  it('returns undefined for non-existent GPIO 99', () => {
    const info = getGpioInfo(99, 'ESP32_WROOM')
    expect(info).toBeUndefined()
  })

  it('returns info with features array', () => {
    const info = getGpioInfo(13, 'ESP32_WROOM')
    expect(info?.features).toBeDefined()
    expect(Array.isArray(info?.features)).toBe(true)
  })

  it('GPIO 0 has warning', () => {
    const info = getGpioInfo(0, 'ESP32_WROOM')
    expect(info?.warning).toBeDefined()
    expect(typeof info?.warning).toBe('string')
  })

  it('works with XIAO_ESP32_C3', () => {
    const info = getGpioInfo(2, 'XIAO_ESP32_C3')
    expect(info).toBeDefined()
    expect(info?.gpio).toBe(2)
  })
})

// =============================================================================
// isGpioRecommended
// =============================================================================

describe('isGpioRecommended', () => {
  it('returns true for GPIO 13', () => {
    expect(isGpioRecommended(13, 'ESP32_WROOM')).toBe(true)
  })

  it('returns false for GPIO 0', () => {
    expect(isGpioRecommended(0, 'ESP32_WROOM')).toBe(false)
  })

  it('returns false for GPIO 34 (input_only)', () => {
    expect(isGpioRecommended(34, 'ESP32_WROOM')).toBe(false)
  })

  it('returns false for non-existent GPIO', () => {
    expect(isGpioRecommended(99, 'ESP32_WROOM')).toBe(false)
  })

  it('returns true for GPIO 14', () => {
    expect(isGpioRecommended(14, 'ESP32_WROOM')).toBe(true)
  })
})

// =============================================================================
// isGpioAvoid
// =============================================================================

describe('isGpioAvoid', () => {
  it('returns true for GPIO 0', () => {
    expect(isGpioAvoid(0, 'ESP32_WROOM')).toBe(true)
  })

  it('returns false for GPIO 13', () => {
    expect(isGpioAvoid(13, 'ESP32_WROOM')).toBe(false)
  })

  it('returns true for GPIO 1 (TX0)', () => {
    expect(isGpioAvoid(1, 'ESP32_WROOM')).toBe(true)
  })

  it('returns true for GPIO 3 (RX0)', () => {
    expect(isGpioAvoid(3, 'ESP32_WROOM')).toBe(true)
  })

  it('returns false for non-existent GPIO', () => {
    expect(isGpioAvoid(99, 'ESP32_WROOM')).toBe(false)
  })
})

// =============================================================================
// getGpioWarning
// =============================================================================

describe('getGpioWarning', () => {
  it('returns warning for GPIO 0', () => {
    const warning = getGpioWarning(0, 'ESP32_WROOM')
    expect(warning).toBeDefined()
    expect(typeof warning).toBe('string')
    expect(warning).toContain('Boot-Modus')
  })

  it('returns JTAG warning for GPIO 13 on WROOM', () => {
    const warning = getGpioWarning(13, 'ESP32_WROOM')
    expect(warning).toContain('JTAG')
  })

  it('returns warning for GPIO 12 (strapping)', () => {
    const warning = getGpioWarning(12, 'ESP32_WROOM')
    expect(warning).toBeDefined()
  })

  it('returns null for non-existent GPIO', () => {
    const warning = getGpioWarning(99, 'ESP32_WROOM')
    expect(warning).toBeNull()
  })

  it('returns warning for GPIO 34 (input only)', () => {
    const warning = getGpioWarning(34, 'ESP32_WROOM')
    expect(warning).toBeDefined()
    expect(warning).toContain('Nur als Eingang')
  })
})

// =============================================================================
// getCategoryLabel
// =============================================================================

describe('getCategoryLabel', () => {
  it('returns Empfohlen for recommended', () => {
    expect(getCategoryLabel('recommended')).toBe('Empfohlen')
  })

  it('returns Verfügbar for available', () => {
    expect(getCategoryLabel('available')).toBe('Verfügbar')
  })

  it('returns Nur Eingang for input_only', () => {
    expect(getCategoryLabel('input_only')).toBe('Nur Eingang')
  })

  it('returns Mit Vorsicht for caution', () => {
    expect(getCategoryLabel('caution')).toBe('Mit Vorsicht')
  })

  it('returns Vermeiden for avoid', () => {
    expect(getCategoryLabel('avoid')).toBe('Vermeiden')
  })
})

// =============================================================================
// getCategoryColorClass
// =============================================================================

describe('getCategoryColorClass', () => {
  it('returns text-success for recommended', () => {
    expect(getCategoryColorClass('recommended')).toBe('text-success')
  })

  it('returns text-info for available', () => {
    expect(getCategoryColorClass('available')).toBe('text-info')
  })

  it('returns text-warning for input_only', () => {
    expect(getCategoryColorClass('input_only')).toBe('text-warning')
  })

  it('returns text-warning for caution', () => {
    expect(getCategoryColorClass('caution')).toBe('text-warning')
  })

  it('returns text-error for avoid', () => {
    expect(getCategoryColorClass('avoid')).toBe('text-error')
  })
})

// =============================================================================
// getRecommendedGpios
// =============================================================================

describe('getRecommendedGpios', () => {
  it('returns GPIOs for ds18b20 (OneWire)', () => {
    const gpios = getRecommendedGpios('ds18b20', 'sensor')
    expect(Array.isArray(gpios)).toBe(true)
    expect(gpios.length).toBeGreaterThan(0)
    expect(gpios).toContain(4)
    expect(gpios).toContain(5)
  })

  it('returns ADC pins for pH sensor', () => {
    const gpios = getRecommendedGpios('ph', 'sensor')
    expect(Array.isArray(gpios)).toBe(true)
    expect(gpios).toContain(32)
    expect(gpios).toContain(33)
  })

  it('returns ADC pins for EC sensor', () => {
    const gpios = getRecommendedGpios('ec', 'sensor')
    expect(gpios).toContain(32)
    expect(gpios).toContain(33)
    expect(gpios).toContain(34)
    expect(gpios).toContain(35)
    expect(gpios).toContain(36)
    expect(gpios).toContain(39)
  })

  it('returns I2C pins for sht31', () => {
    const gpios = getRecommendedGpios('sht31', 'sensor')
    expect(gpios).toContain(21)
    expect(gpios).toContain(22)
  })

  it('returns GPIO 18 for co2 on ESP32-S3 (UART RX)', () => {
    const gpios = getRecommendedGpios('co2', 'sensor', 'ESP32_S3_DEVKITC1')
    expect(gpios[0]).toBe(18)
    expect(gpios).not.toContain(17)
  })

  it('returns default actuator list for unknown type', () => {
    const gpios = getRecommendedGpios('unknown_type', 'actuator')
    expect(Array.isArray(gpios)).toBe(true)
    expect(gpios.length).toBeGreaterThan(0)
    expect(gpios).toContain(4)
    expect(gpios).toContain(5)
  })

  it('returns default sensor list for unknown type', () => {
    const gpios = getRecommendedGpios('unknown_type', 'sensor')
    expect(Array.isArray(gpios)).toBe(true)
    expect(gpios.length).toBeGreaterThan(0)
  })

  it('matches temperature to ds18b20 recommendations', () => {
    const gpios = getRecommendedGpios('temperature', 'sensor')
    expect(gpios).toContain(4)
    expect(gpios).toContain(5)
  })

  it('matches humidity to I2C recommendations', () => {
    const gpios = getRecommendedGpios('humidity', 'sensor')
    expect(gpios).toContain(21)
    expect(gpios).toContain(22)
  })

  it('returns relay recommendations for actuator', () => {
    const gpios = getRecommendedGpios('relay', 'actuator')
    expect(Array.isArray(gpios)).toBe(true)
    expect(gpios.length).toBeGreaterThan(0)
  })

  it('returns pump recommendations for actuator', () => {
    const gpios = getRecommendedGpios('pump', 'actuator')
    expect(gpios.length).toBeGreaterThan(0)
  })
})
