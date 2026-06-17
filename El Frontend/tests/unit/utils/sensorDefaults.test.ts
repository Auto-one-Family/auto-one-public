/**
 * Sensor Defaults Utility Unit Tests
 *
 * Tests for sensor type configuration, units, validation, and multi-value device helpers.
 */

import { describe, it, expect } from 'vitest'
import {
  SENSOR_TYPE_CONFIG,
  SENSOR_CATEGORIES,
  getSensorUnit,
  getSensorDefault,
  getSensorConfig,
  getSensorLabel,
  isValidSensorValue,
  getSensorTypeOptions,
  formatSensorValueWithUnit,
  MULTI_VALUE_DEVICES,
  isMultiValueSensorType,
  getDeviceTypeFromSensorType,
  getSensorTypesForDevice,
  inferInterfaceType,
  getDefaultI2CAddress,
  formatSubzoneKpiLine,
  getSensorAggCategory,
  getAggCategoryGaugeRange,
  ZONE_TILE_AUTO_SENSOR_PRIORITY,
  computeAirVpdKpaFromTempRh,
  computeZoneVpdKpaFromKpiSensorTypes,
  getZoneTileSensorPriority,
} from '@/utils/sensorDefaults'

// =============================================================================
// SENSOR_TYPE_CONFIG
// =============================================================================

describe('SENSOR_TYPE_CONFIG', () => {
  it('has DS18B20 with unit °C', () => {
    expect(SENSOR_TYPE_CONFIG['DS18B20']?.unit).toBe('°C')
  })

  it('has pH with unit pH (NOT °C - critical bug fix)', () => {
    expect(SENSOR_TYPE_CONFIG['pH']?.unit).toBe('pH')
    expect(SENSOR_TYPE_CONFIG['pH']?.unit).not.toBe('°C')
  })

  it('has valid min/max values for DS18B20', () => {
    const config = SENSOR_TYPE_CONFIG['DS18B20']
    expect(config?.min).toBe(-55)
    expect(config?.max).toBe(125)
  })

  it('has valid min/max values for pH', () => {
    const config = SENSOR_TYPE_CONFIG['pH']
    expect(config?.min).toBe(0)
    expect(config?.max).toBe(14)
  })

  it('has category for each sensor type', () => {
    expect(SENSOR_TYPE_CONFIG['DS18B20']?.category).toBe('temperature')
    expect(SENSOR_TYPE_CONFIG['pH']?.category).toBe('water')
    expect(SENSOR_TYPE_CONFIG['sht31_humidity']?.category).toBe('air')
  })
})

// =============================================================================
// SENSOR_CATEGORIES
// =============================================================================

describe('SENSOR_CATEGORIES', () => {
  it('has 6 categories', () => {
    expect(Object.keys(SENSOR_CATEGORIES)).toHaveLength(6)
  })

  it('each category has name, icon, and order', () => {
    for (const category of Object.values(SENSOR_CATEGORIES)) {
      expect(category).toHaveProperty('name')
      expect(category).toHaveProperty('icon')
      expect(category).toHaveProperty('order')
      expect(typeof category.name).toBe('string')
      expect(typeof category.icon).toBe('string')
      expect(typeof category.order).toBe('number')
    }
  })

  it('has temperature category', () => {
    expect(SENSOR_CATEGORIES['temperature']?.name).toBe('Temperatur')
  })

  it('has water category', () => {
    expect(SENSOR_CATEGORIES['water']?.name).toBe('Wasser')
  })
})

// =============================================================================
// getSensorUnit
// =============================================================================

describe('getSensorUnit', () => {
  it('returns °C for DS18B20', () => {
    expect(getSensorUnit('DS18B20')).toBe('°C')
  })

  it('returns pH for pH sensor', () => {
    expect(getSensorUnit('pH')).toBe('pH')
  })

  it('returns raw for unknown type', () => {
    expect(getSensorUnit('unknown')).toBe('raw')
  })

  it('returns µS/cm for EC sensor', () => {
    expect(getSensorUnit('EC')).toBe('µS/cm')
  })

  it('returns %RH for humidity', () => {
    expect(getSensorUnit('sht31_humidity')).toBe('%RH')
  })
})

// =============================================================================
// getSensorDefault
// =============================================================================

describe('getSensorDefault', () => {
  it('returns 20.0 for DS18B20', () => {
    expect(getSensorDefault('DS18B20')).toBe(20.0)
  })

  it('returns 7.0 for pH', () => {
    expect(getSensorDefault('pH')).toBe(7.0)
  })

  it('returns 0 for unknown type', () => {
    expect(getSensorDefault('unknown')).toBe(0)
  })

  it('returns 1200 for EC sensor', () => {
    expect(getSensorDefault('EC')).toBe(1200)
  })

  it('returns 50.0 for humidity', () => {
    expect(getSensorDefault('sht31_humidity')).toBe(50.0)
  })
})

// =============================================================================
// getSensorConfig
// =============================================================================

describe('getSensorConfig', () => {
  it('returns full config object for DS18B20', () => {
    const config = getSensorConfig('DS18B20')
    expect(config).toBeDefined()
    expect(config?.label).toBe('Temperatur')
    expect(config?.unit).toBe('°C')
    expect(config?.min).toBe(-55)
    expect(config?.max).toBe(125)
    expect(config?.decimals).toBe(1)
    expect(config?.icon).toBe('Thermometer')
    expect(config?.defaultValue).toBe(20.0)
    expect(config?.category).toBe('temperature')
  })

  it('returns undefined for unknown type', () => {
    expect(getSensorConfig('unknown')).toBeUndefined()
  })

  it('returns config for lowercase variant', () => {
    const config = getSensorConfig('ds18b20')
    expect(config).toBeDefined()
    expect(config?.unit).toBe('°C')
  })

  // Phase C: BMP280/BME280 lowercase value-types (API sends lowercase sensor_type)
  it('returns config for bmp280_temp with Datasheet min/max', () => {
    const config = getSensorConfig('bmp280_temp')
    expect(config).toBeDefined()
    expect(config?.unit).toBe('°C')
    expect(config?.min).toBe(-40)
    expect(config?.max).toBe(85)
    expect(config?.label).toBe('BMP280 Temperatur')
  })

  it('returns config for bmp280_pressure with Datasheet min/max', () => {
    const config = getSensorConfig('bmp280_pressure')
    expect(config).toBeDefined()
    expect(config?.unit).toBe('hPa')
    expect(config?.min).toBe(300)
    expect(config?.max).toBe(1100)
    expect(config?.label).toBe('BMP280 Druck')
  })

  it('returns config for bme280_temp', () => {
    const config = getSensorConfig('bme280_temp')
    expect(config).toBeDefined()
    expect(config?.unit).toBe('°C')
    expect(config?.min).toBe(-40)
    expect(config?.max).toBe(85)
    expect(config?.label).toBe('BME280 Temperatur')
  })

  it('returns config for bme280_humidity', () => {
    const config = getSensorConfig('bme280_humidity')
    expect(config).toBeDefined()
    expect(config?.unit).toBe('%RH')
    expect(config?.min).toBe(0)
    expect(config?.max).toBe(100)
    expect(config?.label).toBe('BME280 Feuchte')
  })

  it('returns config for bme280_pressure', () => {
    const config = getSensorConfig('bme280_pressure')
    expect(config).toBeDefined()
    expect(config?.unit).toBe('hPa')
    expect(config?.min).toBe(300)
    expect(config?.max).toBe(1100)
    expect(config?.label).toBe('BME280 Druck')
  })
})

// =============================================================================
// getSensorLabel
// =============================================================================

describe('getSensorLabel', () => {
  it('returns label for DS18B20', () => {
    expect(getSensorLabel('DS18B20')).toBe('Temperatur')
  })

  it('returns label for pH', () => {
    expect(getSensorLabel('pH')).toBe('pH-Wert')
  })

  it('returns original type for unknown', () => {
    expect(getSensorLabel('unknown')).toBe('unknown')
  })

  it('returns label for multi-value sensor', () => {
    expect(getSensorLabel('sht31_temp')).toBe('Temperatur')
  })
})

// =============================================================================
// isValidSensorValue
// =============================================================================

describe('isValidSensorValue', () => {
  it('returns true for valid DS18B20 value', () => {
    expect(isValidSensorValue('DS18B20', 25)).toBe(true)
    expect(isValidSensorValue('DS18B20', -55)).toBe(true)
    expect(isValidSensorValue('DS18B20', 125)).toBe(true)
  })

  it('returns false for out-of-range DS18B20 value', () => {
    expect(isValidSensorValue('DS18B20', 200)).toBe(false)
    expect(isValidSensorValue('DS18B20', -100)).toBe(false)
  })

  it('returns true for valid pH value', () => {
    expect(isValidSensorValue('pH', 7.0)).toBe(true)
    expect(isValidSensorValue('pH', 0)).toBe(true)
    expect(isValidSensorValue('pH', 14)).toBe(true)
  })

  it('returns false for out-of-range pH value', () => {
    expect(isValidSensorValue('pH', 15)).toBe(false)
    expect(isValidSensorValue('pH', -1)).toBe(false)
  })

  it('returns true for unknown type (always valid)', () => {
    expect(isValidSensorValue('unknown', 999)).toBe(true)
    expect(isValidSensorValue('unknown', -999)).toBe(true)
  })

  it('returns true for edge case values', () => {
    expect(isValidSensorValue('EC', 0)).toBe(true)
    expect(isValidSensorValue('EC', 5000)).toBe(true)
  })
})

// =============================================================================
// getSensorTypeOptions
// =============================================================================

describe('getSensorTypeOptions', () => {
  it('returns array of options', () => {
    const options = getSensorTypeOptions()
    expect(Array.isArray(options)).toBe(true)
    expect(options.length).toBeGreaterThan(0)
  })

  it('each option has value and label', () => {
    const options = getSensorTypeOptions()
    for (const option of options) {
      expect(option).toHaveProperty('value')
      expect(option).toHaveProperty('label')
      expect(typeof option.value).toBe('string')
      expect(typeof option.label).toBe('string')
    }
  })

  it('contains exactly one DS18B20 option (deduplicated, lowercase canonical)', () => {
    const options = getSensorTypeOptions()
    const ds18b20Options = options.filter(opt => opt.value.toLowerCase() === 'ds18b20')
    expect(ds18b20Options).toHaveLength(1)
    expect(ds18b20Options[0].value).toBe('ds18b20')
    expect(ds18b20Options[0].label).toBe('Temperatur')
  })

  it('contains pH option', () => {
    const options = getSensorTypeOptions()
    const pH = options.find(opt => opt.value === 'pH')
    expect(pH).toBeDefined()
    expect(pH?.label).toBe('pH-Wert')
  })

  it('contains exactly one SHT31 option (canonical device key sht31)', () => {
    const options = getSensorTypeOptions()
    const sht31Option = options.find(opt => opt.value === 'sht31')
    expect(sht31Option).toBeDefined()
    expect(sht31Option?.label).toBe('SHT31 (Temp + Humidity)')
    const allSht31Related = options.filter(opt =>
      ['sht31', 'SHT31', 'sht31_temp', 'sht31_humidity', 'SHT31_humidity'].includes(opt.value)
    )
    expect(allSht31Related).toHaveLength(1)
    expect(allSht31Related[0].value).toBe('sht31')
  })

  it('does not list value-types or duplicate base keys in dropdown', () => {
    const options = getSensorTypeOptions()
    const values = options.map(opt => opt.value)
    expect(values).not.toContain('sht31_temp')
    expect(values).not.toContain('sht31_humidity')
    expect(values).not.toContain('SHT31')
    expect(values).not.toContain('SHT31_humidity')
    expect(values).not.toContain('bmp280_temp')
    expect(values).not.toContain('bmp280_pressure')
    expect(values).not.toContain('bme280_temp')
    expect(values).not.toContain('bme280_humidity')
    expect(values).not.toContain('bme280_pressure')
  })

  it('contains exactly one BME280 option (canonical device key bme280)', () => {
    const options = getSensorTypeOptions()
    const bme280Option = options.find(opt => opt.value === 'bme280')
    expect(bme280Option).toBeDefined()
    expect(bme280Option?.label).toBe('BME280 (Temp + Humidity + Pressure)')
    const allBme280Related = options.filter(opt =>
      ['bme280', 'BME280', 'bme280_temp', 'bme280_humidity', 'bme280_pressure', 'BME280_humidity', 'BME280_pressure'].includes(opt.value)
    )
    expect(allBme280Related).toHaveLength(1)
    expect(allBme280Related[0].value).toBe('bme280')
  })

  it('single-value sensors still listed (ph, ec, moisture, ds18b20, flow, light, co2, analog, digital)', () => {
    const options = getSensorTypeOptions()
    const values = options.map(opt => opt.value)
    const required = ['ph', 'EC', 'moisture', 'ds18b20', 'flow', 'light', 'co2', 'analog', 'digital']
    for (const key of required) {
      const found = values.some(v => v.toLowerCase() === key.toLowerCase())
      expect(found).toBe(true)
    }
  })
})

// =============================================================================
// formatSensorValueWithUnit
// =============================================================================

describe('formatSensorValueWithUnit', () => {
  it('formats DS18B20 value with de-DE locale', () => {
    expect(formatSensorValueWithUnit(23.5, 'DS18B20')).toBe('23,5 °C')
  })

  it('formats pH value with de-DE locale', () => {
    expect(formatSensorValueWithUnit(7.0, 'pH')).toBe('7,00 pH')
  })

  it('returns dash for null value', () => {
    expect(formatSensorValueWithUnit(null, 'DS18B20')).toBe('-')
  })

  it('returns dash for undefined value', () => {
    expect(formatSensorValueWithUnit(undefined as any, 'DS18B20')).toBe('-')
  })

  it('formats humidity value with de-DE locale', () => {
    expect(formatSensorValueWithUnit(65.5, 'sht31_humidity')).toBe('65,5 %RH')
  })

  it('formats EC value with thousands separator (AUT-26)', () => {
    expect(formatSensorValueWithUnit(1200, 'EC')).toBe('1.200 µS/cm')
  })

  it('formats unknown type without config', () => {
    const result = formatSensorValueWithUnit(42, 'unknown')
    expect(result).toBe('42')
  })
})

// =============================================================================
// MULTI_VALUE_DEVICES
// =============================================================================

describe('MULTI_VALUE_DEVICES', () => {
  it('has sht31 with 2 sensor types', () => {
    expect(MULTI_VALUE_DEVICES['sht31']).toBeDefined()
    expect(MULTI_VALUE_DEVICES['sht31'].sensorTypes).toHaveLength(2)
    expect(MULTI_VALUE_DEVICES['sht31'].sensorTypes).toContain('sht31_temp')
    expect(MULTI_VALUE_DEVICES['sht31'].sensorTypes).toContain('sht31_humidity')
  })

  it('has bme280 with BME280 in sensorTypes', () => {
    expect(MULTI_VALUE_DEVICES['bme280']).toBeDefined()
    expect(MULTI_VALUE_DEVICES['bme280'].sensorTypes).toContain('BME280')
  })

  it('each device has required properties', () => {
    for (const [key, device] of Object.entries(MULTI_VALUE_DEVICES)) {
      expect(device.deviceType).toBe(key)
      expect(device.label).toBeDefined()
      expect(Array.isArray(device.sensorTypes)).toBe(true)
      expect(Array.isArray(device.values)).toBe(true)
      expect(device.icon).toBeDefined()
      expect(device.interface).toBeDefined()
    }
  })
})

// =============================================================================
// isMultiValueSensorType
// =============================================================================

describe('isMultiValueSensorType', () => {
  it('returns true for sht31_temp', () => {
    expect(isMultiValueSensorType('sht31_temp')).toBe(true)
  })

  it('returns true for SHT31 (base type)', () => {
    expect(isMultiValueSensorType('SHT31')).toBe(true)
  })

  it('returns true for BME280', () => {
    expect(isMultiValueSensorType('BME280')).toBe(true)
  })

  it('returns false for ds18b20 (single-value)', () => {
    expect(isMultiValueSensorType('ds18b20')).toBe(false)
  })

  it('returns false for unknown type', () => {
    expect(isMultiValueSensorType('unknown')).toBe(false)
  })

  it('returns true for bme280_humidity', () => {
    expect(isMultiValueSensorType('bme280_humidity')).toBe(true)
  })
})

// =============================================================================
// getDeviceTypeFromSensorType
// =============================================================================

describe('getDeviceTypeFromSensorType', () => {
  it('returns sht31 for sht31_temp', () => {
    expect(getDeviceTypeFromSensorType('sht31_temp')).toBe('sht31')
  })

  it('returns sht31 for SHT31 (uppercase base type)', () => {
    expect(getDeviceTypeFromSensorType('SHT31')).toBe('sht31')
  })

  it('returns bme280 for BME280', () => {
    expect(getDeviceTypeFromSensorType('BME280')).toBe('bme280')
  })

  it('returns null for ds18b20 (single-value)', () => {
    expect(getDeviceTypeFromSensorType('ds18b20')).toBeNull()
  })

  it('returns null for unknown type', () => {
    expect(getDeviceTypeFromSensorType('unknown')).toBeNull()
  })

  it('returns sht31 for sht31_humidity', () => {
    expect(getDeviceTypeFromSensorType('sht31_humidity')).toBe('sht31')
  })

  it('returns bme280 for bme280_pressure', () => {
    expect(getDeviceTypeFromSensorType('bme280_pressure')).toBe('bme280')
  })
})

// =============================================================================
// getSensorTypesForDevice
// =============================================================================

describe('getSensorTypesForDevice', () => {
  it('returns sensor types for sht31', () => {
    const types = getSensorTypesForDevice('sht31')
    expect(types).toHaveLength(2)
    expect(types).toContain('sht31_temp')
    expect(types).toContain('sht31_humidity')
  })

  it('returns empty array for unknown device', () => {
    expect(getSensorTypesForDevice('unknown')).toEqual([])
  })

  it('returns sensor types for bme280', () => {
    const types = getSensorTypesForDevice('bme280')
    expect(types.length).toBeGreaterThan(0)
    expect(types).toContain('BME280')
  })

  it('returns sensor types for bmp280', () => {
    const types = getSensorTypesForDevice('bmp280')
    expect(types).toHaveLength(2)
    expect(types).toContain('bmp280_pressure')
    expect(types).toContain('bmp280_temp')
  })
})

// =============================================================================
// inferInterfaceType
// =============================================================================

describe('inferInterfaceType', () => {
  it('returns ONEWIRE for ds18b20', () => {
    expect(inferInterfaceType('ds18b20')).toBe('ONEWIRE')
  })

  it('returns I2C for sht31_temp', () => {
    expect(inferInterfaceType('sht31_temp')).toBe('I2C')
  })

  it('returns I2C for bme280', () => {
    expect(inferInterfaceType('bme280')).toBe('I2C')
  })

  it('returns ANALOG for pH', () => {
    expect(inferInterfaceType('pH')).toBe('ANALOG')
  })

  it('returns UART for co2 and mhz19_co2', () => {
    expect(inferInterfaceType('co2')).toBe('UART')
    expect(inferInterfaceType('mhz19_co2')).toBe('UART')
  })

  it('returns ANALOG for unknown type (default)', () => {
    expect(inferInterfaceType('unknown')).toBe('ANALOG')
  })

  it('is case-insensitive', () => {
    expect(inferInterfaceType('DS18B20')).toBe('ONEWIRE')
    expect(inferInterfaceType('SHT31')).toBe('I2C')
  })

  it('returns I2C for bh1750', () => {
    expect(inferInterfaceType('bh1750')).toBe('I2C')
  })

  it('returns I2C for veml7700', () => {
    expect(inferInterfaceType('veml7700')).toBe('I2C')
  })
})

// =============================================================================
// getDefaultI2CAddress
// =============================================================================

describe('getDefaultI2CAddress', () => {
  it('returns 0x44 (68 decimal) for sht31_temp', () => {
    expect(getDefaultI2CAddress('sht31_temp')).toBe(0x44)
  })

  it('returns 0x76 for bme280', () => {
    expect(getDefaultI2CAddress('bme280_pressure')).toBe(0x76)
  })

  it('returns null for ds18b20 (not I2C)', () => {
    expect(getDefaultI2CAddress('ds18b20')).toBeNull()
  })

  it('returns null for unknown type', () => {
    expect(getDefaultI2CAddress('unknown')).toBeNull()
  })

  it('returns null for analog sensor', () => {
    expect(getDefaultI2CAddress('pH')).toBeNull()
  })

  it('returns 0x76 for bmp280', () => {
    expect(getDefaultI2CAddress('bmp280_temp')).toBe(0x76)
  })
})

// =============================================================================
// formatSubzoneKpiLine / getSensorAggCategory (L2 vs zone aggregation SSOT)
// =============================================================================

describe('getSensorAggCategory', () => {
  it('maps humidity, pressure, co2 to distinct categories', () => {
    expect(getSensorAggCategory('sht31_humidity')).toBe('humidity')
    expect(getSensorAggCategory('bmp280_pressure')).toBe('pressure')
    expect(getSensorAggCategory('co2')).toBe('co2')
  })

  it('maps vpd to other', () => {
    expect(getSensorAggCategory('vpd')).toBe('other')
  })
})

describe('formatSubzoneKpiLine', () => {
  const good = (type: string, value: number) => ({
    sensor_type: type,
    raw_value: value,
    unit: '',
    quality: 'good',
  })

  it('does not mix RH, pressure, and CO2 into one average', () => {
    const line = formatSubzoneKpiLine([
      good('sht31_humidity', 55),
      good('bmp280_pressure', 1010),
      good('co2', 900),
    ])
    expect(line).toBe('55%RH · 1010hPa · 900ppm')
  })

  it('skips stale readings', () => {
    const line = formatSubzoneKpiLine([
      good('sht31_temp', 22),
      { sensor_type: 'sht31_humidity', raw_value: 40, unit: '', quality: 'stale' },
    ])
    expect(line).toMatch(/22[,.]0?°C/)
  })

  it('skips vpd (other category)', () => {
    const line = formatSubzoneKpiLine([{ sensor_type: 'vpd', raw_value: 1.2, unit: 'kPa', quality: 'good' }])
    expect(line).toBe('')
  })
})

// =============================================================================
// getAggCategoryGaugeRange / ZONE_TILE_AUTO_SENSOR_PRIORITY (L1 zone-tile MVP)
// =============================================================================

describe('getAggCategoryGaugeRange', () => {
  it('returns min/max for temperature', () => {
    expect(getAggCategoryGaugeRange('temperature')).toEqual({ min: -20, max: 55 })
  })

  it('returns null for other', () => {
    expect(getAggCategoryGaugeRange('other')).toBeNull()
  })
})

describe('ZONE_TILE_AUTO_SENSOR_PRIORITY', () => {
  it('does not include vpd token (VPD not in zone Ø aggregation)', () => {
    expect(ZONE_TILE_AUTO_SENSOR_PRIORITY.some(t => t === 'vpd')).toBe(false)
    expect(ZONE_TILE_AUTO_SENSOR_PRIORITY.slice(0, 2)).toEqual(['temp', 'humi'])
  })
})

describe('computeAirVpdKpaFromTempRh / computeZoneVpdKpaFromKpiSensorTypes', () => {
  it('computes VPD from T and RH (snapshot)', () => {
    const v = computeAirVpdKpaFromTempRh(22, 55)
    expect(v).not.toBeNull()
    expect(v!).toBeGreaterThan(0.9)
    expect(v!).toBeLessThan(1.5)
  })

  it('returns null without both KPI buckets', () => {
    expect(computeZoneVpdKpaFromKpiSensorTypes([{ type: 'temperature', avg: 22, count: 1 }])).toBeNull()
  })

  it('computes zone VPD from Ø temperature + humidity rows', () => {
    const v = computeZoneVpdKpaFromKpiSensorTypes([
      { type: 'temperature', avg: 22, count: 2 },
      { type: 'humidity', avg: 55, count: 2 },
    ])
    expect(v).not.toBeNull()
    expect(v!).toBeGreaterThan(0.9)
    expect(v!).toBeLessThan(1.5)
  })
})

describe('getZoneTileSensorPriority', () => {
  it('orders temp before soil', () => {
    expect(getZoneTileSensorPriority('soil_moisture')).toBeGreaterThan(getZoneTileSensorPriority('sht31_temp'))
  })
})
