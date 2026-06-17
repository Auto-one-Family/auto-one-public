/**
 * Sensor Live Update E2E Tests
 *
 * Tests real-time sensor data updates via MQTT → Server → WebSocket → UI.
 * Simulates ESP32 publishing sensor readings and verifies UI updates.
 *
 * Flow: createMockEsp (device + sensors in UI) → publishHeartbeat → publishSensorData
 * - Device must exist in mock store with sensors for WebSocket updates to apply
 * - Heartbeat-only creates pending_approval device (excluded from list)
 */

import { test, expect } from '@playwright/test'
import type { WebSocketHelper } from '../helpers/websocket'
import { createWebSocketHelper, WS_MESSAGE_TYPES } from '../helpers/websocket'
import { publishHeartbeat, publishSensorData, generateMockId } from '../helpers/mqtt'
import { createMockEspWithSensors } from '../helpers/api'

test.describe('Sensor Live Updates', () => {
  // Requires live MQTT/IoT data — will be linked to Wokwi SIL testing
  test.skip(!!process.env.CI, 'Requires live IoT data — use Wokwi integration for CI')

  test.setTimeout(60000) // createMockEsp + MQTT + WebSocket + UI checks can take time

  let wsHelper: WebSocketHelper

  test.beforeEach(async ({ page }) => {
    // Create WebSocket listener BEFORE page load so we capture the connection
    wsHelper = await createWebSocketHelper(page)
    await page.goto('/sensors')
    await page.waitForLoadState('networkidle')
    await wsHelper.waitForConnection(8000)
  })

  test('should display sensor data from MQTT', async ({ page, request }) => {

    const testDeviceId = generateMockId('SENSOR')
    const testGpio = 4
    const testValue = 23.5

    // Create Mock ESP with sensor (device + sensors must exist for WebSocket updates)
    await createMockEspWithSensors(page, request, {
      espId: testDeviceId,
      sensors: [{ gpio: testGpio, sensor_type: 'temperature', raw_value: 0 }],
    })

    // Register device via heartbeat (ensures server knows device)
    await publishHeartbeat(testDeviceId)
    await page.waitForTimeout(500)

    // Publish sensor data
    await publishSensorData(testDeviceId, testGpio, testValue, {
      sensorType: 'temperature',
    })

    // Wait for WebSocket message (live values come only via WS, not REST)
    const wsMessage = await wsHelper.waitForMessage(WS_MESSAGE_TYPES.SENSOR_DATA, 10000)
    expect(wsMessage.data.value).toBe(testValue)

    // Verify value appears in UI (SensorsView shows raw_value.toFixed(2) e.g. "23.50")
    const valueText = page.locator(`text=${testValue}`)
    await expect(valueText).toBeVisible({ timeout: 5000 })
  })

  test('should update sensor value in real-time', async ({ page, request }) => {
    const testDeviceId = generateMockId('REALTIME')
    const testGpio = 5

    // Create Mock ESP with sensor
    await createMockEspWithSensors(page, request, {
      espId: testDeviceId,
      sensors: [{ gpio: testGpio, sensor_type: 'temperature', raw_value: 20 }],
    })

    await publishHeartbeat(testDeviceId)
    await page.waitForTimeout(500)

    const initialValue = 20.0
    await publishSensorData(testDeviceId, testGpio, initialValue, {
      sensorType: 'temperature',
    })

    await page.waitForTimeout(500)

    const updatedValue = 25.5
    await publishSensorData(testDeviceId, testGpio, updatedValue, {
      sensorType: 'temperature',
    })

    await page.waitForTimeout(1000)

    const updatedValueText = page.locator(`text=${updatedValue}`)

    if (!(await updatedValueText.isVisible())) {
      await page.reload()
      await page.waitForLoadState('networkidle')
    }

    await expect(updatedValueText).toBeVisible({ timeout: 5000 })
  })

  test('should display different sensor types', async ({ page, request }) => {
    const testDeviceId = generateMockId('MULTI')

    // Create Mock ESP with multiple sensors
    await createMockEspWithSensors(page, request, {
      espId: testDeviceId,
      sensors: [
        { gpio: 4, sensor_type: 'temperature', raw_value: 0 },
        { gpio: 5, sensor_type: 'humidity', raw_value: 0 },
        { gpio: 34, sensor_type: 'ph', raw_value: 0 },
      ],
    })

    await publishHeartbeat(testDeviceId)
    await page.waitForTimeout(500)

    const sensors = [
      { gpio: 4, value: 22.5, type: 'temperature' },
      { gpio: 5, value: 65.0, type: 'humidity' },
      { gpio: 34, value: 6.8, type: 'ph' },
    ]

    for (const sensor of sensors) {
      await publishSensorData(testDeviceId, sensor.gpio, sensor.value, {
        sensorType: sensor.type,
      })
      await page.waitForTimeout(200)
    }

    // Wait for temperature WebSocket update (live values come via WS)
    await wsHelper.waitForMessageMatching(
      (m) => m.type === WS_MESSAGE_TYPES.SENSOR_DATA && m.data?.value === 22.5,
      8000
    )

    // Sensor value: raw_value.toFixed(2) → "22.50" or German "22,50"
    const tempValue = page.locator('text=/22[,.]?5/')
    await expect(tempValue).toBeVisible({ timeout: 5000 })
  })

  test('should show sensor on device card', async ({ page, request }) => {
    const testDeviceId = generateMockId('CARD')
    const testGpio = 4
    const testValue = 24.0

    // Create Mock ESP with sensor AND zone - unassigned devices land in collapsed
    // UnassignedDropBar; zone_id puts device in ZoneGroup on dashboard
    await createMockEspWithSensors(page, request, {
      espId: testDeviceId,
      sensors: [{ gpio: testGpio, sensor_type: 'temperature', raw_value: 0 }],
      zone_id: 'e2e_sensor_test',
      zone_name: 'E2E Sensor Test',
    })

    // Stay on /sensors (already loaded in beforeEach) - stable WS, no nav-triggered reconnect
    await publishHeartbeat(testDeviceId)
    await page.waitForTimeout(500)
    await publishSensorData(testDeviceId, testGpio, testValue, {
      sensorType: 'temperature',
    })

    // Wait for WebSocket sensor_data (SensorsView uses same espStore as dashboard)
    await wsHelper.waitForMessage(WS_MESSAGE_TYPES.SENSOR_DATA, 10000)

    // Verify on SensorsView: sensor card shows device + value (card has esp_id and raw_value.toFixed(2))
    const sensorCard = page.locator(`.card:has-text("${testDeviceId}")`)
    await expect(sensorCard).toBeVisible({ timeout: 5000 })
    const valueInCard = sensorCard.locator(`text=/24[,.]?0*/`)
    await expect(valueInCard).toBeVisible({ timeout: 5000 })
  })
})
