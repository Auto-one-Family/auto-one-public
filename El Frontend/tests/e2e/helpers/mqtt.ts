/**
 * MQTT Helper for Playwright E2E Tests
 *
 * Provides utilities to publish MQTT messages via docker exec mosquitto_pub.
 * This simulates ESP32 devices sending data to the server.
 *
 * Topic Structure: kaiser/{kaiser_id}/esp/{esp_id}/{category}/{gpio}/{action}
 * Default Kaiser ID: "god"
 */

import { exec } from 'child_process'
import { promisify } from 'util'

const execAsync = promisify(exec)

// Default broker container name
const MQTT_CONTAINER = 'automationone-mqtt'

// Default Kaiser ID
const DEFAULT_KAISER_ID = 'god'

// Delay after publish to ensure broker processes message
const POST_PUBLISH_DELAY_MS = 150

/**
 * Helper function to sleep
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * Execute mosquitto_pub via docker exec
 */
async function mqttPublish(topic: string, payload: object): Promise<void> {
  const payloadStr = JSON.stringify(payload).replace(/"/g, '\\"')

  // Use docker exec to publish via mosquitto_pub
  const cmd = `docker exec ${MQTT_CONTAINER} mosquitto_pub -h localhost -t "${topic}" -m "${payloadStr}"`

  try {
    await execAsync(cmd)
    console.log(`[MQTT Helper] Published to ${topic}`)
  } catch (error) {
    console.error(`[MQTT Helper] Failed to publish to ${topic}:`, error)
    throw error
  }

  // Small delay to ensure broker processes message
  await sleep(POST_PUBLISH_DELAY_MS)
}

/**
 * Publish heartbeat message (simulates ESP32 online)
 *
 * Topic: kaiser/{kaiser_id}/esp/{esp_id}/system/heartbeat
 */
export async function publishHeartbeat(
  espId: string,
  options: {
    heapFree?: number
    uptime?: number
    kaiserId?: string
  } = {}
): Promise<void> {
  const {
    heapFree = 98304,
    uptime = 3600,
    kaiserId = DEFAULT_KAISER_ID,
  } = options

  const topic = `kaiser/${kaiserId}/esp/${espId}/system/heartbeat`
  const payload = {
    ts: Math.floor(Date.now() / 1000),
    esp_id: espId,
    heap_free: heapFree,
    uptime: uptime, // Server expects "uptime" (heartbeat_handler._validate_payload)
    wifi_rssi: -45,
    system_state: 'OPERATIONAL',
  }

  await mqttPublish(topic, payload)
}

/**
 * Publish sensor data (simulates ESP32 reporting sensor reading)
 *
 * Topic: kaiser/{kaiser_id}/esp/{esp_id}/sensor/{gpio}/data
 *
 * Required fields per sensor_handler._validate_payload():
 * - ts, esp_id, gpio, sensor_type, raw, raw_mode
 */
export async function publishSensorData(
  espId: string,
  gpio: number,
  value: number,
  options: {
    sensorType?: string
    rawMode?: boolean
    kaiserId?: string
  } = {}
): Promise<void> {
  const {
    sensorType = 'temperature',
    rawMode = true,
    kaiserId = DEFAULT_KAISER_ID,
  } = options

  const topic = `kaiser/${kaiserId}/esp/${espId}/sensor/${gpio}/data`
  // raw_mode=true: ESP sends raw reading. For temp/humidity/ph (direct values), raw = value.
  // Server uses raw for raw_value; display_value = processed_value ?? raw_value.
  const payload = {
    ts: Math.floor(Date.now() / 1000),
    esp_id: espId,
    gpio: gpio,
    sensor_type: sensorType,
    raw: value, // Direct value (celsius, %, pH) for E2E simulation
    value: value,
    unit: sensorType === 'temperature' ? '\u00b0C' : sensorType === 'humidity' ? '%' : '',
    raw_mode: rawMode,
    quality: 'good',
  }

  await mqttPublish(topic, payload)
}

/**
 * Publish actuator response (simulates ESP32 confirming command)
 *
 * Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/response
 */
export async function publishActuatorResponse(
  espId: string,
  gpio: number,
  command: 'ON' | 'OFF' | 'PWM' | 'TOGGLE',
  success: boolean,
  options: {
    value?: number
    message?: string
    duration?: number
    correlationId?: string
    kaiserId?: string
  } = {}
): Promise<void> {
  const {
    value = command === 'ON' ? 1.0 : 0.0,
    message = success ? 'Command executed' : 'Command failed',
    duration = 0,
    correlationId,
    kaiserId = DEFAULT_KAISER_ID,
  } = options

  const topic = `kaiser/${kaiserId}/esp/${espId}/actuator/${gpio}/response`
  const payload: Record<string, unknown> = {
    ts: Math.floor(Date.now() / 1000),
    esp_id: espId,
    gpio: gpio,
    command: command,
    value: value,
    success: success,
    message: message,
    duration: duration,
  }

  if (correlationId) {
    payload.correlation_id = correlationId
  }

  await mqttPublish(topic, payload)
}

/**
 * Publish actuator alert (simulates ESP32 emergency/safety alert)
 *
 * Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/{gpio}/alert
 *
 * Alert Types:
 * - emergency_stop: Manual or automatic emergency stop
 * - runtime_protection: Actuator exceeded max runtime
 * - safety_violation: Safety constraint violated
 * - hardware_error: Hardware malfunction
 */
export async function publishActuatorAlert(
  espId: string,
  gpio: number,
  alertType: 'emergency_stop' | 'runtime_protection' | 'safety_violation' | 'hardware_error',
  options: {
    message?: string
    zoneId?: string
    kaiserId?: string
  } = {}
): Promise<void> {
  const {
    message = `Alert: ${alertType}`,
    zoneId,
    kaiserId = DEFAULT_KAISER_ID,
  } = options

  const topic = `kaiser/${kaiserId}/esp/${espId}/actuator/${gpio}/alert`
  const payload: Record<string, unknown> = {
    ts: Math.floor(Date.now() / 1000),
    esp_id: espId,
    gpio: gpio,
    alert_type: alertType,
    message: message,
  }

  if (zoneId) {
    payload.zone_id = zoneId
  }

  await mqttPublish(topic, payload)
}

/**
 * Publish emergency stop (system-wide, gpio=255)
 *
 * Topic: kaiser/{kaiser_id}/esp/{esp_id}/actuator/255/alert
 */
export async function publishEmergencyStop(
  espId: string,
  options: {
    message?: string
    kaiserId?: string
  } = {}
): Promise<void> {
  const { message = 'Emergency stop triggered', kaiserId = DEFAULT_KAISER_ID } = options

  await publishActuatorAlert(espId, 255, 'emergency_stop', {
    message,
    kaiserId,
  })
}

/**
 * Generate a valid ESP device ID
 * Pattern: ESP_[A-F0-9]{6,8}
 */
export function generateEspId(): string {
  const hex = Math.random().toString(16).substring(2, 10).toUpperCase()
  return `ESP_${hex.padStart(8, '0').substring(0, 8)}`
}

/**
 * Generate a valid MOCK device ID for tests
 * Pattern: MOCK_[A-Z0-9]+
 */
export function generateMockId(prefix = ''): string {
  const suffix = Math.random().toString(36).substring(2, 10).toUpperCase()
  return `MOCK_${prefix}${suffix}`
}
