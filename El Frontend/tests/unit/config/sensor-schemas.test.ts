/**
 * Tests for sensor/actuator schema configuration.
 * Verifies schema definitions, fallback behavior, and field structures.
 */

import { describe, it, expect } from 'vitest'
import { getSensorSchema, getActuatorSchema } from '@/config/sensor-schemas'
import type { FormSchema, FormFieldSchema } from '@/types/form-schema'

describe('sensor-schemas', () => {
  describe('getSensorSchema', () => {
    it('returns DS18B20 schema with correct groups', () => {
      const schema = getSensorSchema('DS18B20')
      expect(schema.groups).toHaveLength(3)
      expect(schema.groups[0].title).toBe('Hardware')
      expect(schema.groups[1].title).toBe('Measurement')
      expect(schema.groups[2].title).toBe('Thresholds')
    })

    it('DS18B20 hardware group has gpio-select and interface fields', () => {
      const schema = getSensorSchema('DS18B20')
      const hwFields = schema.groups[0].fields
      expect(hwFields.some(f => f.key === 'gpio' && f.type === 'gpio-select')).toBe(true)
      expect(hwFields.some(f => f.key === 'interface_type' && f.disabled)).toBe(true)
    })

    it('DS18B20 thresholds group starts collapsed', () => {
      const schema = getSensorSchema('DS18B20')
      expect(schema.groups[2].collapsed).toBe(true)
    })

    it('returns SHT31 schema with I2C fields', () => {
      const schema = getSensorSchema('SHT31')
      const hwFields = schema.groups[0].fields
      // SHT31 is an I2C sensor - it uses i2c_address and i2c_bus, no dedicated GPIO pins
      expect(hwFields.some(f => f.key === 'i2c_address')).toBe(true)
      expect(hwFields.some(f => f.key === 'i2c_bus')).toBe(true)
      expect(hwFields.some(f => f.key === 'interface_type')).toBe(true)
    })

    it('returns pH schema with calibration group', () => {
      const schema = getSensorSchema('pH')
      const calibGroup = schema.groups.find(g => g.title === 'Calibration')
      expect(calibGroup).toBeDefined()
      expect(calibGroup!.fields.some(f => f.key === 'calibration_ph4')).toBe(true)
      expect(calibGroup!.fields.some(f => f.key === 'calibration_ph7')).toBe(true)
    })

    it('returns soil_moisture schema with dry/wet calibration', () => {
      const schema = getSensorSchema('soil_moisture')
      const calibGroup = schema.groups.find(g => g.title === 'Calibration')
      expect(calibGroup).toBeDefined()
      expect(calibGroup!.fields.some(f => f.key === 'dry_value')).toBe(true)
      expect(calibGroup!.fields.some(f => f.key === 'wet_value')).toBe(true)
    })

    it('returns generic schema for unknown sensor type', () => {
      const schema = getSensorSchema('UNKNOWN_SENSOR')
      expect(schema.groups).toHaveLength(2)
      expect(schema.groups[0].title).toBe('Hardware')
      expect(schema.groups[1].title).toBe('Measurement')
      // Generic schema has interface_type select with multiple options
      const interfaceField = schema.groups[0].fields.find(f => f.key === 'interface_type')
      expect(interfaceField).toBeDefined()
      expect(interfaceField!.options!.length).toBeGreaterThanOrEqual(3)
    })

    it('non-I2C schemas have required gpio field', () => {
      // DS18B20, pH, soil_moisture, and generic sensors use GPIO pins
      const gpioTypes = ['DS18B20', 'pH', 'soil_moisture', 'UNKNOWN']
      for (const t of gpioTypes) {
        const schema = getSensorSchema(t)
        const allFields = schema.groups.flatMap(g => g.fields)
        const gpioField = allFields.find(f => f.key === 'gpio')
        expect(gpioField, `${t} should have a gpio field`).toBeDefined()
        expect(gpioField!.required).toBe(true)
      }
    })

    it('I2C schemas have required i2c_address field instead of gpio', () => {
      // SHT31 is I2C: uses i2c_address as required field, no dedicated GPIO pin
      const schema = getSensorSchema('SHT31')
      const allFields = schema.groups.flatMap(g => g.fields)
      const i2cAddressField = allFields.find(f => f.key === 'i2c_address')
      expect(i2cAddressField, 'SHT31 should have an i2c_address field').toBeDefined()
      expect(i2cAddressField!.required).toBe(true)
    })
  })

  describe('getActuatorSchema', () => {
    it('returns relay schema with safety group', () => {
      const schema = getActuatorSchema('relay')
      expect(schema.groups.length).toBeGreaterThanOrEqual(2)
      const safetyGroup = schema.groups.find(g => g.title === 'Safety')
      expect(safetyGroup).toBeDefined()
      expect(safetyGroup!.collapsed).toBe(true)
    })

    it('relay has active_high toggle', () => {
      const schema = getActuatorSchema('relay')
      const allFields = schema.groups.flatMap(g => g.fields)
      const activeHigh = allFields.find(f => f.key === 'active_high')
      expect(activeHigh).toBeDefined()
      expect(activeHigh!.type).toBe('toggle')
    })

    it('returns pwm schema with frequency and duty range', () => {
      const schema = getActuatorSchema('pwm')
      const allFields = schema.groups.flatMap(g => g.fields)
      expect(allFields.some(f => f.key === 'frequency')).toBe(true)
      expect(allFields.some(f => f.key === 'duty_min')).toBe(true)
      expect(allFields.some(f => f.key === 'duty_max')).toBe(true)
    })

    it('pwm duty range fields are type range', () => {
      const schema = getActuatorSchema('pwm')
      const allFields = schema.groups.flatMap(g => g.fields)
      const dutyMin = allFields.find(f => f.key === 'duty_min')
      const dutyMax = allFields.find(f => f.key === 'duty_max')
      expect(dutyMin!.type).toBe('range')
      expect(dutyMax!.type).toBe('range')
    })

    it('returns generic schema for unknown actuator type', () => {
      const schema = getActuatorSchema('UNKNOWN_ACTUATOR')
      expect(schema.groups).toHaveLength(1)
      expect(schema.groups[0].title).toBe('Hardware')
    })
  })
})
