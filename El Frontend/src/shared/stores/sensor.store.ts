/**
 * Sensor Store
 *
 * Handles sensor-related WebSocket events.
 * Mirrors server-side sensor_handler.py and sensor_health_job.py.
 *
 * Server-centric architecture:
 * ESP32 → MQTT (kaiser/{esp_id}/sensor/data) → Server → WS (sensor_data) → this store
 * Server (maintenance job) → WS (sensor_health) → this store
 *
 * Cross-store dependency: Receives devices array from esp.store.ts via dispatcher.
 *
 * Sensor Data Processing (Phase 6 HYBRID LOGIC):
 * 1. Known multi-value sensors → Group by GPIO using registry
 * 2. Unknown multi-value → Dynamic detection when multiple types on same GPIO
 * 3. Single-value sensors → Unchanged behavior
 *
 * IMPORTANT: ALL sensor processing/logic happens on the SERVER.
 * The frontend only receives pre-processed values and updates the UI.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { createLogger } from '@/utils/logger'
import {
  getDeviceTypeFromSensorType,
  getMultiValueDeviceConfigBySensorType,
  VIRTUAL_SENSOR_META,
  SENSOR_TYPE_CONFIG,
} from '@/utils/sensorDefaults'
import type { ESPDevice } from '@/api/esp'
import type { MockSensor, MultiValueEntry, QualityLevel, SensorHealthEvent } from '@/types'

// Virtual sensor types (server-computed) that must never be merged into physical sensors,
// even when they share gpio=0 with I2C sensors like SHT31.
const VIRTUAL_SENSOR_TYPES = new Set(Object.keys(VIRTUAL_SENSOR_META).map(k => k.toLowerCase()))

const logger = createLogger('SensorStore')

/** Payload shape for sensor_data WebSocket events */
interface SensorDataPayload {
  esp_id?: string
  device_id?: string
  gpio: number
  sensor_type: string
  value: number
  unit: string
  quality?: QualityLevel
  timestamp?: number
  sample_count?: number
  adc_stddev?: number
  stable?: boolean
  ec_stddev?: number
  temp_compensated?: boolean
  temp_source?: string
  temp_compensation_value?: number
  // Address-based matching for multi-sensor GPIOs (Phase 3)
  config_id?: string
  i2c_address?: number
  onewire_address?: string
}

/** Message wrapper for sensor_data events */
interface SensorDataMessage {
  data: SensorDataPayload
}

/** Message wrapper for sensor_health events */
interface SensorHealthMessage {
  data: SensorHealthEvent
}

type DevicePatchFn = (device: ESPDevice) => ESPDevice
type ApplyDevicePatch = (espId: string, patchFn: DevicePatchFn) => boolean

function normalizeSensorType(sensorType: string | undefined | null): string {
  return (sensorType ?? '').trim().toLowerCase()
}

function resolveMultiValueKey(
  multiValues: Record<string, MultiValueEntry>,
  incomingSensorType: string,
): string {
  const normalizedIncoming = normalizeSensorType(incomingSensorType)
  const existingKey = Object.keys(multiValues).find(
    key => normalizeSensorType(key) === normalizedIncoming,
  )
  return existingKey ?? incomingSensorType
}

/**
 * Normalize raw timestamp from server WebSocket event to ISO string.
 *
 * Returns null when timestamp is missing or invalid — no Fake-NOW fallback.
 * Callers must keep the previous valid last_read when this returns null.
 *
 * Server sends esp32_timestamp_raw which can be in seconds OR milliseconds.
 * Mirrors server-side logic: if > 1e10, treat as milliseconds; else seconds.
 * (sensor_handler.py line 315-322)
 */
function normalizeRawTimestamp(ts: number | undefined | null): string | null {
  if (!ts) return null
  const ms = ts > 1e10 ? ts : ts * 1000
  if (ms < 946684800000 || ms > 4102444800000) return null
  return new Date(ms).toISOString()
}

function buildMeasurementMetadata(data: SensorDataPayload): Record<string, unknown> | null {
  const metadata: Record<string, unknown> = {}
  if (data.sample_count != null) metadata.sample_count = data.sample_count
  if (data.adc_stddev != null) metadata.adc_stddev = data.adc_stddev
  if (data.stable != null) metadata.stable = data.stable
  if (data.ec_stddev != null) metadata.ec_stddev = data.ec_stddev
  if (data.temp_compensated != null) metadata.temp_compensated = data.temp_compensated
  if (data.temp_source != null) metadata.temp_source = data.temp_source
  if (data.temp_compensation_value != null) {
    metadata.temp_compensation_value = data.temp_compensation_value
  }
  return Object.keys(metadata).length > 0 ? metadata : null
}

function applyMeasurementMetadata(
  sensor: MockSensor,
  data: SensorDataPayload,
): void {
  const metadata = buildMeasurementMetadata(data)
  if (metadata) {
    sensor.metadata = { ...(sensor.metadata ?? {}), ...metadata }
  }
}

function parseSensorTimestampMs(raw: unknown): number | null {
  if (typeof raw !== 'number' || Number.isNaN(raw)) return null
  return raw > 1_000_000_000_000 ? raw : raw * 1000
}

// ============================================================================
// Helper: Get worst quality from multi-values
// ============================================================================
function getWorstQuality(values: MultiValueEntry[]): QualityLevel {
  const qualityOrder: QualityLevel[] = ['excellent', 'good', 'fair', 'poor', 'bad', 'stale', 'error']

  let worstIndex = 0
  for (const value of values) {
    const index = qualityOrder.indexOf(value.quality)
    if (index > worstIndex) {
      worstIndex = index
    }
  }

  return qualityOrder[worstIndex]
}

// ============================================================================
// Helper: Match sensor to incoming WS event data
// Supports config_id (primary), address-based (I2C/OneWire), and legacy fallback
// ============================================================================
function matchSensorToEvent(sensor: MockSensor, data: SensorDataPayload): boolean {
  // Primary: config_id match (most unique key)
  if (data.config_id && sensor.config_id) {
    return sensor.config_id === data.config_id
  }

  // Base: gpio + sensor_type must match
  if (
    sensor.gpio !== data.gpio ||
    normalizeSensorType(sensor.sensor_type) !== normalizeSensorType(data.sensor_type)
  ) {
    return false
  }

  // Address differentiation when available
  if (data.i2c_address != null && sensor.i2c_address != null) {
    return sensor.i2c_address === data.i2c_address
  }
  if (data.onewire_address && sensor.onewire_address) {
    return sensor.onewire_address === data.onewire_address
  }

  // Legacy: no address in event → first match (backward compatibility)
  return true
}

export const useSensorStore = defineStore('sensor', () => {

  // =========================================================================
  // ATC Degraded State (atc_degraded error_event from server)
  // Key: "espId:gpio:sensorType", Value: timestamp (ms) when degraded event was received
  // =========================================================================
  const atcDegradedMap = ref<Map<string, number>>(new Map())

  function handleAtcDegraded(data: Record<string, unknown>): void {
    const espId = data.esp_id as string | undefined
    const gpio = data.gpio as number | undefined
    const sensorType = data.sensor_type as string | undefined
    if (!espId || gpio === undefined || !sensorType) return
    const key = `${espId}:${gpio}:${normalizeSensorType(sensorType)}`
    atcDegradedMap.value = new Map(atcDegradedMap.value).set(key, Date.now())
  }

  function getAtcDegradedTimestamp(espId: string, gpio: number, sensorType: string): number | undefined {
    const key = `${espId}:${gpio}:${normalizeSensorType(sensorType)}`
    return atcDegradedMap.value.get(key)
  }

  // =========================================================================
  // Sensor Data Handler
  // =========================================================================

  /**
   * Handle sensor_data WebSocket event.
   * Updates sensor value in corresponding device for live updates.
   *
   * Post-Fix1: Backend delivers separate sensor_config entries per value type
   * (e.g., sht31_temp and sht31_humidity as two distinct entries).
   * Priority: exact match by gpio + sensor_type first (handles multi-value correctly).
   * Fallback: legacy multi-value merge logic for backward compatibility.
   */
  function handleSensorData(
    message: SensorDataMessage,
    applyDevicePatch: ApplyDevicePatch,
  ): void {
    const data = message.data
    const eventReceivedAtIso = new Date().toISOString()
    const espId = data.esp_id || data.device_id
    const gpio = data.gpio
    const sensorType = data.sensor_type

    if (!espId || gpio === undefined) return

    const patched = applyDevicePatch(espId, (device) => {
      if (!device.sensors) return device
      const sensorTsMs = parseSensorTimestampMs(data.timestamp)
      const offlineInfo = (device as unknown as { offlineInfo?: { timestamp?: number } }).offlineInfo
      const offlineSinceMs = typeof offlineInfo?.timestamp === 'number' ? offlineInfo.timestamp : null
      // AUT-481 P2: only drop pre-offline samples while the device is still offline.
      // After esp_health online, offlineInfo is cleared — but guard against races where
      // sensor_data arrives before the online transition during LWT flaps.
      const deviceStillOffline = device.status === 'offline' || device.connected === false
      if (
        deviceStillOffline &&
        sensorTsMs !== null &&
        offlineSinceMs !== null &&
        sensorTsMs < offlineSinceMs
      ) {
        logger.debug(`Ignoring stale sensor_data for ${espId}:${gpio} (${sensorType}) after offline epoch`)
        return device
      }

      const sensors = (device.sensors as MockSensor[]).map((sensor) => ({
        ...sensor,
        multi_values: sensor.multi_values ? { ...sensor.multi_values } : sensor.multi_values,
      }))

      // Post-Fix1: Find exact match by config_id, address, or gpio+sensor_type.
      // Handles multi-sensor GPIOs (e.g. 2x DS18B20) via address-based matching.
      const exactMatch = sensors.find(s => matchSensorToEvent(s, data))

      if (exactMatch) {
        if (data.value !== undefined) exactMatch.raw_value = data.value
        if (data.quality) exactMatch.quality = data.quality
        if (data.unit) exactMatch.unit = data.unit
        const ts = normalizeRawTimestamp(data.timestamp)
        if (ts !== null) exactMatch.last_read = ts
        exactMatch.last_event_at = eventReceivedAtIso
        applyMeasurementMetadata(exactMatch, data)
        return { ...device, sensors }
      }

      // Fallback: legacy multi-value merge for sensors not yet in array
      const knownDeviceType = getDeviceTypeFromSensorType(sensorType)
      if (knownDeviceType) {
        handleKnownMultiValueSensor(sensors, data, knownDeviceType, eventReceivedAtIso)
        return { ...device, sensors }
      }

      // Virtual sensors (e.g. vpd) are server-computed and must never be merged into
      // physical I2C sensors that share gpio=0. They are always standalone satellites.
      if (VIRTUAL_SENSOR_TYPES.has(normalizeSensorType(sensorType))) {
        handleVirtualSensorData(sensors, data, eventReceivedAtIso)
        return { ...device, sensors }
      }

      // Dynamic multi-value detection (different type on same GPIO)
      const existingSensor = sensors.find(s => s.gpio === gpio)
      if (
        existingSensor &&
        normalizeSensorType(existingSensor.sensor_type) !== normalizeSensorType(sensorType) &&
        !existingSensor.is_multi_value
      ) {
        handleDynamicMultiValueSensor(existingSensor, data, eventReceivedAtIso)
        return { ...device, sensors }
      }

      // Single-value sensor (or first value of unknown multi-value)
      handleSingleValueSensorData(sensors, data, eventReceivedAtIso)
      return { ...device, sensors }
    })

    if (!patched) {
      logger.debug(`sensor_data: Device not found for ${espId}`)
    }
  }

  // ════════════════════════════════════════════════════════════════════════════
  // HANDLER 1: KNOWN MULTI-VALUE (Registry-based)
  // ════════════════════════════════════════════════════════════════════════════
  function handleKnownMultiValueSensor(
    sensors: MockSensor[],
    data: SensorDataPayload,
    deviceType: string,
    eventReceivedAtIso: string,
  ): void {
    let sensor = sensors.find(s => s.gpio === data.gpio)
    const deviceConfig = getMultiValueDeviceConfigBySensorType(data.sensor_type)

    if (!sensor) {
      sensor = {
        gpio: data.gpio,
        sensor_type: data.sensor_type,
        name: deviceConfig?.label ?? data.sensor_type,
        raw_value: data.value,
        unit: data.unit,
        quality: data.quality ?? 'good',
        raw_mode: true,
        last_read: normalizeRawTimestamp(data.timestamp),
        last_event_at: eventReceivedAtIso,
        device_type: deviceType,
        is_multi_value: true,
        multi_values: {}
      }
      sensors.push(sensor)
    }

    if (!sensor.multi_values) {
      sensor.multi_values = {}
      sensor.is_multi_value = true
      sensor.device_type = deviceType
    }

    const multiValueKey = resolveMultiValueKey(sensor.multi_values, data.sensor_type)
    sensor.multi_values[multiValueKey] = {
      value: data.value,
      unit: data.unit,
      quality: data.quality ?? 'good',
      timestamp: Date.now(),
      sensorType: data.sensor_type
    }

    if (deviceConfig) {
      const primaryType = deviceConfig.values[0]?.sensorType
      if (sensor.multi_values[primaryType]) {
        sensor.raw_value = sensor.multi_values[primaryType].value
        sensor.unit = sensor.multi_values[primaryType].unit
      }
    }

    sensor.quality = getWorstQuality(Object.values(sensor.multi_values))
    const knownTs = normalizeRawTimestamp(data.timestamp)
    if (knownTs !== null) sensor.last_read = knownTs
    sensor.last_event_at = eventReceivedAtIso
  }

  // ════════════════════════════════════════════════════════════════════════════
  // HANDLER 2: DYNAMIC MULTI-VALUE (Auto-detected)
  // ════════════════════════════════════════════════════════════════════════════
  function handleDynamicMultiValueSensor(
    existingSensor: MockSensor,
    data: SensorDataPayload,
    eventReceivedAtIso: string,
  ): void {
    if (!existingSensor.is_multi_value) {
      existingSensor.is_multi_value = true
      existingSensor.device_type = null
      existingSensor.multi_values = existingSensor.raw_value == null
        ? {}
        : {
            [existingSensor.sensor_type]: {
              value: existingSensor.raw_value,
              unit: existingSensor.unit,
              quality: existingSensor.quality,
              timestamp: Date.now(),
              sensorType: existingSensor.sensor_type
            }
          }
      existingSensor.name = `Multi-Sensor GPIO ${existingSensor.gpio}`
    }

    const multiValueKey = resolveMultiValueKey(existingSensor.multi_values!, data.sensor_type)
    existingSensor.multi_values![multiValueKey] = {
      value: data.value,
      unit: data.unit,
      quality: data.quality ?? 'good',
      timestamp: Date.now(),
      sensorType: data.sensor_type
    }

    existingSensor.quality = getWorstQuality(Object.values(existingSensor.multi_values!))
    const dynTs = normalizeRawTimestamp(data.timestamp)
    if (dynTs !== null) existingSensor.last_read = dynTs
    existingSensor.last_event_at = eventReceivedAtIso
  }

  // ════════════════════════════════════════════════════════════════════════════
  // HANDLER 3: VIRTUAL SENSOR (server-computed, always standalone)
  // ════════════════════════════════════════════════════════════════════════════
  function handleVirtualSensorData(
    sensors: MockSensor[],
    data: SensorDataPayload,
    eventReceivedAtIso: string,
  ): void {
    const normalizedType = normalizeSensorType(data.sensor_type)
    const existing = sensors.find(s => normalizeSensorType(s.sensor_type) === normalizedType)

    if (existing) {
      if (data.value !== undefined) existing.raw_value = data.value
      if (data.quality) existing.quality = data.quality
      if (data.unit) existing.unit = data.unit
      const ts = normalizeRawTimestamp(data.timestamp)
      if (ts !== null) existing.last_read = ts
      existing.last_event_at = eventReceivedAtIso
      applyMeasurementMetadata(existing, data)
    } else {
      // VPD sensor config may not be in the store yet (created lazily server-side).
      // Add it as a standalone satellite so it gets its own card immediately.
      const config = SENSOR_TYPE_CONFIG[data.sensor_type]
      sensors.push({
        gpio: data.gpio,
        sensor_type: data.sensor_type,
        name: config?.label ?? data.sensor_type,
        raw_value: data.value,
        unit: data.unit || config?.unit || '',
        quality: data.quality ?? 'good',
        raw_mode: false,
        last_read: normalizeRawTimestamp(data.timestamp),
        last_event_at: eventReceivedAtIso,
        interface_type: 'VIRTUAL',
        is_multi_value: false,
        multi_values: null,
      })
    }
  }

  // ════════════════════════════════════════════════════════════════════════════
  // HANDLER 4: SINGLE-VALUE (unchanged behavior)
  // ════════════════════════════════════════════════════════════════════════════
  function handleSingleValueSensorData(
    sensors: MockSensor[],
    data: SensorDataPayload,
    eventReceivedAtIso: string,
  ): void {
    const sensor = sensors.find(s => matchSensorToEvent(s, data))

    if (sensor) {
      if (data.value !== undefined) sensor.raw_value = data.value
      if (data.quality) sensor.quality = data.quality
      if (data.unit) sensor.unit = data.unit
      const singleTs = normalizeRawTimestamp(data.timestamp)
      if (singleTs !== null) sensor.last_read = singleTs
      sensor.last_event_at = eventReceivedAtIso
    }
  }

  // =========================================================================
  // Sensor Health Handler
  // =========================================================================

  /**
   * Handle sensor_health WebSocket event.
   * Updates sensor stale status from server maintenance job.
   * Server: maintenance/jobs/sensor_health.py
   */
  function handleSensorHealth(
    message: SensorHealthMessage,
    applyDevicePatch: ApplyDevicePatch,
  ): void {
    const event = message.data as SensorHealthEvent

    if (!event.esp_id || event.gpio === undefined) {
      logger.warn('sensor_health missing esp_id or gpio')
      return
    }

    const patched = applyDevicePatch(event.esp_id, (device) => {
      if (!device.sensors) {
        logger.debug(`sensor_health: Device ${event.esp_id} has no sensors`)
        return device
      }

      const sensors = (device.sensors as Array<{
        gpio: number
        sensor_type?: string
        is_stale?: boolean
        stale_reason?: string
        last_reading_at?: string | null
        operating_mode?: string
        timeout_seconds?: number
        freshness_hours?: number | null
      }>).map((sensor) => ({ ...sensor }))

      // Match by gpio AND sensor_type to avoid contaminating sibling sensors on the same GPIO
      // (e.g. moisture+ec both on GPIO 33 — without sensor_type filter, one event clobbers the other)
      const sensorIndex = sensors.findIndex(
        s => s.gpio === event.gpio && normalizeSensorType(s.sensor_type) === normalizeSensorType(event.sensor_type),
      )
      if (sensorIndex === -1) {
        logger.debug(`sensor_health: Sensor GPIO ${event.gpio} (${event.sensor_type}) not found on ${event.esp_id}`)
        return device
      }

      const sensor = sensors[sensorIndex]
      sensor.is_stale = event.is_stale
      sensor.stale_reason = event.stale_reason
      sensor.last_reading_at = event.last_reading_at
      sensor.operating_mode = event.operating_mode
      sensor.timeout_seconds = event.timeout_seconds
      if (event.freshness_hours != null) {
        sensor.freshness_hours = event.freshness_hours
      }

      if (event.is_stale) {
        logger.warn(`Sensor stale: ${event.esp_id} GPIO ${event.gpio} ` +
          `(${event.sensor_type}) - ${event.stale_reason}, ` +
          `overdue by ${event.seconds_overdue}s`
        )
      } else {
        logger.debug(`Sensor health updated: ${event.esp_id} GPIO ${event.gpio} ` +
          `is_stale=${event.is_stale}`
        )
      }

      return { ...device, sensors: sensors as unknown as MockSensor[] }
    })

    if (!patched) {
      logger.debug(`sensor_health: Device not found: ${event.esp_id}`)
    }
  }

  return {
    handleSensorData,
    handleSensorHealth,
    handleAtcDegraded,
    getAtcDegradedTimestamp,
    atcDegradedMap,
  }
})
