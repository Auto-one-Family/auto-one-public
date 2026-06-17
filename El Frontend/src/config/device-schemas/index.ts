/**
 * Device Schema Registry
 *
 * Maps device types (sensor_type / actuator_type) to their JSON Schema definitions.
 * Schemas define type-specific metadata fields for the config panels.
 */

// ── Base Schema ──
import baseSchema from './base.schema.json'

// ── Sensor Schemas ──
import sht31Schema from './sensor/sht31.schema.json'
import bmp280Schema from './sensor/bmp280.schema.json'
import ds18b20Schema from './sensor/ds18b20.schema.json'
import moistureSchema from './sensor/moisture.schema.json'
import phSchema from './sensor/ph.schema.json'
import ecSchema from './sensor/ec.schema.json'
import lightSchema from './sensor/light.schema.json'

// ── Actuator Schemas ──
import relaySchema from './actuator/relay.schema.json'
import pwmSchema from './actuator/pwm.schema.json'

// =============================================================================
// Types
// =============================================================================

export interface SchemaProperty {
  type: string
  title: string
  description?: string
  default?: unknown
  enum?: unknown[]
  minimum?: number
  maximum?: number
  format?: string
  readOnly?: boolean
  'ui:widget'?: string
}

export interface DeviceSchema {
  $id: string
  allOf?: Array<{ $ref: string }>
  type?: string
  properties: Record<string, SchemaProperty>
}

export interface ResolvedSchema {
  deviceType: string
  category: 'sensor' | 'actuator'
  baseProperties: Record<string, SchemaProperty>
  deviceProperties: Record<string, SchemaProperty>
}

// =============================================================================
// Registry
// =============================================================================

const SENSOR_SCHEMAS: Record<string, DeviceSchema> = {
  sht31: sht31Schema as unknown as DeviceSchema,
  bmp280: bmp280Schema as unknown as DeviceSchema,
  ds18b20: ds18b20Schema as unknown as DeviceSchema,
  moisture: moistureSchema as unknown as DeviceSchema,
  ph: phSchema as unknown as DeviceSchema,
  ec: ecSchema as unknown as DeviceSchema,
  light: lightSchema as unknown as DeviceSchema,
}

const ACTUATOR_SCHEMAS: Record<string, DeviceSchema> = {
  relay: relaySchema as unknown as DeviceSchema,
  pwm: pwmSchema as unknown as DeviceSchema,
}

const BASE_SCHEMA = baseSchema as unknown as DeviceSchema

// =============================================================================
// Public API
// =============================================================================

/**
 * Normalize a sensor type to its base device type for schema lookup.
 * Multi-value sensors use suffixed types (sht31_temp, sht31_humidity, bmp280_pressure)
 * but schemas are registered under the base device type (sht31, bmp280).
 */
const SENSOR_TYPE_TO_BASE: Record<string, string> = {
  sht31_temp: 'sht31',
  sht31_humidity: 'sht31',
  bmp280_temp: 'bmp280',
  bmp280_pressure: 'bmp280',
  mhz19_co2: 'mhz19',
  scd30_co2: 'scd30',
}

function resolveBaseType(deviceType: string): string {
  return SENSOR_TYPE_TO_BASE[deviceType] ?? deviceType
}

/**
 * Get the resolved schema for a device type.
 * Returns base properties + device-specific properties merged.
 * Returns null if no schema exists for the given type.
 * Automatically resolves multi-value sensor types (e.g. sht31_temp → sht31).
 */
export function getSchemaForDevice(
  deviceType: string,
  category: 'sensor' | 'actuator'
): ResolvedSchema | null {
  const registry = category === 'sensor' ? SENSOR_SCHEMAS : ACTUATOR_SCHEMAS
  const baseType = category === 'sensor' ? resolveBaseType(deviceType) : deviceType
  const schema = registry[baseType]

  if (!schema) return null

  return {
    deviceType: baseType,
    category,
    baseProperties: { ...BASE_SCHEMA.properties },
    deviceProperties: { ...schema.properties },
  }
}

/**
 * Get all registered schemas.
 */
export function getAllSchemas(): ResolvedSchema[] {
  const result: ResolvedSchema[] = []

  for (const [type, schema] of Object.entries(SENSOR_SCHEMAS)) {
    result.push({
      deviceType: type,
      category: 'sensor',
      baseProperties: { ...BASE_SCHEMA.properties },
      deviceProperties: { ...schema.properties },
    })
  }

  for (const [type, schema] of Object.entries(ACTUATOR_SCHEMAS)) {
    result.push({
      deviceType: type,
      category: 'actuator',
      baseProperties: { ...BASE_SCHEMA.properties },
      deviceProperties: { ...schema.properties },
    })
  }

  return result
}

/**
 * Get list of device types that have schemas.
 */
export function getRegisteredDeviceTypes(): {
  sensors: string[]
  actuators: string[]
} {
  return {
    sensors: Object.keys(SENSOR_SCHEMAS),
    actuators: Object.keys(ACTUATOR_SCHEMAS),
  }
}

/**
 * Check if a device type has a registered schema.
 */
export function hasSchema(deviceType: string, category: 'sensor' | 'actuator'): boolean {
  const registry = category === 'sensor' ? SENSOR_SCHEMAS : ACTUATOR_SCHEMAS
  return deviceType in registry
}
