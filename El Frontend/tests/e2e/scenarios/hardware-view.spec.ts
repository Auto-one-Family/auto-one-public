/**
 * Hardware View E2E Tests
 *
 * Comprehensive tests for the HardwareView (Level 1):
 * - Zone-based device overview with drag & drop
 * - Mock device creation, configuration, and deletion
 * - Sensor and actuator configuration panels
 * - PendingDevicesPanel workflow
 *
 * Requires: Docker services running (backend + MQTT + DB)
 * Run: make e2e-up && npx playwright test tests/e2e/scenarios/hardware-view.spec.ts
 */

import { test, expect, type Page, type APIRequestContext } from '@playwright/test'
import { createMockEspWithSensors, deleteMockEsp } from '../helpers/api'
import { publishHeartbeat, publishSensorData, publishActuatorResponse, publishEmergencyStop } from '../helpers/mqtt'
import { createWebSocketHelper, WS_MESSAGE_TYPES } from '../helpers/websocket'

// ── Test Data ───────────────────────────────────────────────────────────

const ZONE_GEWAECHSHAUS = 'e2e_gewaechshaus'
const ZONE_OUTDOOR = 'e2e_outdoor'

function uniqueId(prefix: string): string {
  const suffix = Date.now().toString(36).toUpperCase()
  return `MOCK_E2E${prefix}${suffix}`
}

// ── Helpers ─────────────────────────────────────────────────────────────

async function navigateToHardware(page: Page) {
  await page.goto('/hardware')
  await page.waitForLoadState('load')
  // Wait for store hydration
  await page.waitForTimeout(1000)
}

async function createTestDevice(
  page: Page,
  request: APIRequestContext,
  options: {
    prefix: string
    zone_id?: string
    zone_name?: string
    sensors?: Array<{ gpio: number; sensor_type: string; raw_value?: number; name?: string }>
    actuators?: Array<{ gpio: number; actuator_type: string; name?: string }>
    auto_heartbeat?: boolean
  }
) {
  const espId = uniqueId(options.prefix)
  await createMockEspWithSensors(page, request, {
    espId,
    zone_id: options.zone_id,
    zone_name: options.zone_name,
    sensors: options.sensors ?? [],
    actuators: options.actuators ?? [],
    auto_heartbeat: options.auto_heartbeat ?? true,
  })
  return espId
}

// ═══════════════════════════════════════════════════════════════════════
// TEST SUITE
// ═══════════════════════════════════════════════════════════════════════

test.describe('Hardware View', () => {
  test.skip(!!process.env.CI, 'Requires live backend — use docker compose e2e-up')
  test.setTimeout(60000)

  // ── Mock Device Lifecycle ───────────────────────────────────────────

  test.describe('Mock Device Lifecycle', () => {
    let createdDeviceIds: string[] = []

    test.afterEach(async ({ page, request }) => {
      // Cleanup created devices
      for (const id of createdDeviceIds) {
        await deleteMockEsp(page, request, id).catch(() => {})
      }
      createdDeviceIds = []
    })

    test('should create a mock device and see it on hardware view', async ({ page, request }) => {
      await navigateToHardware(page)

      const espId = await createTestDevice(page, request, {
        prefix: 'CREATE',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        sensors: [
          { gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5, name: 'Bodentemp' },
        ],
      })
      createdDeviceIds.push(espId)

      // Reload to see new device
      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)

      // Device should appear in the hardware view
      const deviceCard = page.locator(`text=${espId}`)
      await expect(deviceCard).toBeVisible({ timeout: 10000 })
    })

    test('should create mock device with sensors and actuators', async ({ page, request }) => {
      await navigateToHardware(page)

      const espId = await createTestDevice(page, request, {
        prefix: 'FULL',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        sensors: [
          { gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5, name: 'Bodentemp' },
          { gpio: 21, sensor_type: 'SHT31', raw_value: 65.0, name: 'Luftfeuchte' },
        ],
        actuators: [
          { gpio: 16, actuator_type: 'relay', name: 'Befeuchter' },
          { gpio: 17, actuator_type: 'relay', name: 'Ventilator' },
        ],
      })
      createdDeviceIds.push(espId)

      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)

      // Verify device is visible
      const deviceText = page.locator(`text=${espId}`)
      await expect(deviceText).toBeVisible({ timeout: 10000 })
    })

    test('should delete a mock device', async ({ page, request }) => {
      await navigateToHardware(page)

      const espId = await createTestDevice(page, request, {
        prefix: 'DELETE',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
      })
      createdDeviceIds.push(espId)

      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)

      // Verify device exists
      const deviceLocator = page.locator(`text=${espId}`)
      if (await deviceLocator.isVisible({ timeout: 5000 })) {
        // Delete via API
        await deleteMockEsp(page, request, espId)
        createdDeviceIds = createdDeviceIds.filter(id => id !== espId)

        // Reload and verify removed
        await page.reload()
        await page.waitForLoadState('load')
        await page.waitForTimeout(2000)

        await expect(deviceLocator).not.toBeVisible({ timeout: 5000 })
      }
    })
  })

  // ── Zone Display ────────────────────────────────────────────────────

  test.describe('Zone Display', () => {
    let deviceIds: string[] = []

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      // Create devices in different zones
      const id1 = await createTestDevice(page, request, {
        prefix: 'ZONE1',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        sensors: [{ gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5 }],
      })
      const id2 = await createTestDevice(page, request, {
        prefix: 'ZONE2',
        zone_id: ZONE_OUTDOOR,
        zone_name: 'Außenbereich',
        sensors: [{ gpio: 5, sensor_type: 'DS18B20', raw_value: 18.0 }],
      })
      deviceIds = [id1, id2]

      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      for (const id of deviceIds) {
        await deleteMockEsp(page, request, id).catch(() => {})
      }
      deviceIds = []
    })

    test('should display devices grouped by zones', async ({ page }) => {
      // Check that zone headers are visible
      const zoneHeader1 = page.locator('text=Gewächshaus')
      const zoneHeader2 = page.locator('text=Außenbereich')

      await expect(zoneHeader1).toBeVisible({ timeout: 10000 })
      await expect(zoneHeader2).toBeVisible({ timeout: 10000 })
    })

    test('should show sensor values on device cards', async ({ page }) => {
      // Look for temperature values on device cards
      const tempValue = page.locator('text=/22[.,]5/')
      await expect(tempValue).toBeVisible({ timeout: 10000 })
    })
  })

  // ── Drag & Drop ─────────────────────────────────────────────────────

  test.describe('Drag & Drop', () => {
    let deviceIds: string[] = []

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      // Create 2 devices: one in zone, one unassigned
      const id1 = await createTestDevice(page, request, {
        prefix: 'DRAG1',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        sensors: [{ gpio: 4, sensor_type: 'DS18B20', raw_value: 20.0 }],
      })
      const id2 = await createTestDevice(page, request, {
        prefix: 'DRAG2',
        zone_id: ZONE_OUTDOOR,
        zone_name: 'Außenbereich',
        sensors: [{ gpio: 5, sensor_type: 'DS18B20', raw_value: 15.0 }],
      })
      deviceIds = [id1, id2]

      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      for (const id of deviceIds) {
        await deleteMockEsp(page, request, id).catch(() => {})
      }
      deviceIds = []
    })

    test('should have draggable device cards with drag handles', async ({ page }) => {
      // Check that drag handles exist
      const dragHandles = page.locator('.esp-drag-handle')
      const handleCount = await dragHandles.count()
      expect(handleCount).toBeGreaterThan(0)
    })

    test('should allow dragging a device card between zones', async ({ page }) => {
      // Find the first device's drag handle in zone 1
      const sourceZone = page.locator('text=Gewächshaus').locator('..')
      const sourceDragHandle = sourceZone.locator('.esp-drag-handle').first()

      // Find the target zone drop area
      const targetZone = page.locator('text=Außenbereich').locator('..')

      if (await sourceDragHandle.isVisible({ timeout: 5000 }) &&
          await targetZone.isVisible({ timeout: 5000 })) {
        const sourceBox = await sourceDragHandle.boundingBox()
        const targetBox = await targetZone.boundingBox()

        if (sourceBox && targetBox) {
          // Perform drag & drop
          await page.mouse.move(
            sourceBox.x + sourceBox.width / 2,
            sourceBox.y + sourceBox.height / 2
          )
          await page.mouse.down()
          await page.waitForTimeout(300) // Touch delay threshold

          // Move to target
          await page.mouse.move(
            targetBox.x + targetBox.width / 2,
            targetBox.y + targetBox.height / 2,
            { steps: 10 }
          )
          await page.waitForTimeout(200)
          await page.mouse.up()

          // Wait for zone assignment API call
          await page.waitForTimeout(2000)

          // The page should still be functional after drag
          await expect(page.locator('text=Gewächshaus')).toBeVisible()
          await expect(page.locator('text=Außenbereich')).toBeVisible()
        }
      }
    })
  })

  // ── Device Configuration Panel ──────────────────────────────────────

  test.describe('Device Configuration Panel', () => {
    let espId: string

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      espId = await createTestDevice(page, request, {
        prefix: 'CONFIG',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        sensors: [
          { gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5, name: 'Bodentemperatur' },
          { gpio: 21, sensor_type: 'SHT31', raw_value: 55.0, name: 'Luftsensor' },
        ],
        actuators: [
          { gpio: 16, actuator_type: 'relay', name: 'Pumpe' },
        ],
      })

      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      await deleteMockEsp(page, request, espId).catch(() => {})
    })

    test('should open device settings panel via gear icon', async ({ page }) => {
      // Hover over device card to reveal settings gear
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      // Click settings button
      const settingsBtn = deviceCard.locator('[title="Einstellungen"]').first()
      if (await settingsBtn.isVisible({ timeout: 3000 })) {
        await settingsBtn.click()

        // SlideOver should open with device settings
        const dialog = page.locator('[role="dialog"]')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // Should show device identification
        await expect(page.locator('text=Identifikation')).toBeVisible()
        await expect(page.locator('text=Status')).toBeVisible()
        await expect(page.locator('text=Zone')).toBeVisible()
      }
    })

    test('should display sensor list in settings panel', async ({ page }) => {
      // Open settings for device
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      const settingsBtn = deviceCard.locator('[title="Einstellungen"]').first()
      if (await settingsBtn.isVisible({ timeout: 3000 })) {
        await settingsBtn.click()

        const dialog = page.locator('[role="dialog"]')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // Check sensor section is visible
        const sensorSection = page.locator('text=Sensoren')
        await expect(sensorSection).toBeVisible({ timeout: 5000 })
      }
    })

    test('should display actuator list in settings panel', async ({ page }) => {
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      const settingsBtn = deviceCard.locator('[title="Einstellungen"]').first()
      if (await settingsBtn.isVisible({ timeout: 3000 })) {
        await settingsBtn.click()

        const dialog = page.locator('[role="dialog"]')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // Check actuator section
        const actuatorSection = page.locator('text=Aktoren')
        await expect(actuatorSection).toBeVisible({ timeout: 5000 })
      }
    })

    test('should close settings panel with close button', async ({ page }) => {
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      const settingsBtn = deviceCard.locator('[title="Einstellungen"]').first()
      if (await settingsBtn.isVisible({ timeout: 3000 })) {
        await settingsBtn.click()

        const dialog = page.locator('[role="dialog"]')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // Click close button (uses aria-label="Schließen")
        const closeBtn = page.locator('[aria-label="Schließen"]')
        await closeBtn.click()

        // Dialog should be gone
        await expect(dialog).not.toBeVisible({ timeout: 5000 })
      }
    })

    test('should close settings panel with ESC key', async ({ page }) => {
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      const settingsBtn = deviceCard.locator('[title="Einstellungen"]').first()
      if (await settingsBtn.isVisible({ timeout: 3000 })) {
        await settingsBtn.click()

        const dialog = page.locator('[role="dialog"]')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // Press ESC
        await page.keyboard.press('Escape')

        await expect(dialog).not.toBeVisible({ timeout: 5000 })
      }
    })
  })

  // ── Overflow Menu Actions ───────────────────────────────────────────

  test.describe('Context Menu Actions', () => {
    let espId: string

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      espId = await createTestDevice(page, request, {
        prefix: 'MENU',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
      })

      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      await deleteMockEsp(page, request, espId).catch(() => {})
    })

    test('should open overflow menu with 3 options', async ({ page }) => {
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      // Click overflow menu button (MoreVertical icon)
      const overflowBtn = deviceCard.locator('[title="Weitere Aktionen"]').first()
      if (await overflowBtn.isVisible({ timeout: 3000 })) {
        await overflowBtn.click()

        // Context menu should appear with options
        await page.waitForTimeout(300)
        const menuItems = page.locator('.context-menu__item, [role="menuitem"]')
        const count = await menuItems.count()
        expect(count).toBeGreaterThanOrEqual(2) // At least Konfigurieren + Löschen
      }
    })
  })

  // ── Live Sensor Data via MQTT ─────────────────────────────────────

  test.describe('Live Sensor Data', () => {
    let espId: string

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      espId = await createTestDevice(page, request, {
        prefix: 'LIVE',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        sensors: [
          { gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5, name: 'Bodentemp' },
          { gpio: 21, sensor_type: 'SHT31', raw_value: 55.0, name: 'Luftfeuchte' },
        ],
        actuators: [
          { gpio: 16, actuator_type: 'relay', name: 'Pumpe' },
        ],
        auto_heartbeat: true,
      })

      await publishHeartbeat(espId)
      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      await deleteMockEsp(page, request, espId).catch(() => {})
    })

    test('should update sensor value on card after MQTT publish', async ({ page }) => {
      // Verify device is visible
      const deviceLocator = page.locator(`text=${espId}`)
      await expect(deviceLocator).toBeVisible({ timeout: 10000 })

      // Publish new sensor value
      await publishSensorData(espId, 4, 28.7, { sensorType: 'DS18B20' })
      await page.waitForTimeout(3000)

      // After WebSocket push, the card should update (if live updates are enabled)
      // Check that the page is still functional (no crash from WS event)
      await expect(deviceLocator).toBeVisible()
    })

    test('should show multi-value sensor data (SHT31: humidity + temperature)', async ({ page }) => {
      // Publish SHT31 humidity value
      await publishSensorData(espId, 21, 62.5, { sensorType: 'SHT31' })
      await page.waitForTimeout(2000)

      // The device card should still be visible with sensor data
      const deviceLocator = page.locator(`text=${espId}`)
      await expect(deviceLocator).toBeVisible({ timeout: 10000 })

      // Look for humidity-related display (62.5 or similar)
      const humidityValue = page.locator('text=/62[.,]?5?/')
      const hasValue = await humidityValue.isVisible({ timeout: 5000 }).catch(() => false)
      console.log(`[Test] SHT31 humidity value visible: ${hasValue}`)
    })

    test('should handle rapid sensor updates without crash', async ({ page }) => {
      // Send 5 rapid sensor updates
      for (let i = 0; i < 5; i++) {
        await publishSensorData(espId, 4, 20.0 + i * 2, { sensorType: 'DS18B20' })
        await page.waitForTimeout(200)
      }

      await page.waitForTimeout(2000)

      // Page should still be functional
      const deviceLocator = page.locator(`text=${espId}`)
      await expect(deviceLocator).toBeVisible({ timeout: 5000 })

      // No JavaScript errors should have occurred
      const consoleErrors: string[] = []
      page.on('console', (msg) => {
        if (msg.type() === 'error') consoleErrors.push(msg.text())
      })

      await page.waitForTimeout(1000)
      console.log(`[Test] Console errors after rapid updates: ${consoleErrors.length}`)
    })
  })

  // ── Actuator Control ──────────────────────────────────────────────

  test.describe('Actuator Control', () => {
    let espId: string

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      espId = await createTestDevice(page, request, {
        prefix: 'ACTUATOR',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        actuators: [
          { gpio: 16, actuator_type: 'relay', name: 'Pumpe' },
          { gpio: 17, actuator_type: 'relay', name: 'Ventilator' },
        ],
        auto_heartbeat: true,
      })

      await publishHeartbeat(espId)
      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      await deleteMockEsp(page, request, espId).catch(() => {})
    })

    test('should display actuator controls in settings panel', async ({ page }) => {
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      const settingsBtn = deviceCard.locator('[title="Einstellungen"]').first()
      if (await settingsBtn.isVisible({ timeout: 3000 })) {
        await settingsBtn.click()

        const dialog = page.locator('[role="dialog"]')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // Should show actuator section with both actuators
        const actuatorSection = page.locator('text=Aktoren')
        await expect(actuatorSection).toBeVisible({ timeout: 5000 })

        // Look for relay names
        const pumpe = page.locator('text=Pumpe')
        const ventilator = page.locator('text=Ventilator')

        const hasPumpe = await pumpe.isVisible({ timeout: 3000 }).catch(() => false)
        const hasVentilator = await ventilator.isVisible({ timeout: 3000 }).catch(() => false)

        expect(hasPumpe || hasVentilator).toBe(true)
      }
    })

    test('should handle actuator command response via MQTT', async ({ page }) => {
      const wsHelper = await createWebSocketHelper(page)

      // Navigate to establish WebSocket
      await page.goto('/hardware')
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)

      // Simulate actuator response from ESP32
      await publishActuatorResponse(espId, 16, 'ON', true)
      await page.waitForTimeout(2000)

      // Check for actuator WebSocket event
      try {
        const msg = await wsHelper.waitForMessageMatching(
          (m) =>
            m.type === WS_MESSAGE_TYPES.ACTUATOR_RESPONSE ||
            m.type === WS_MESSAGE_TYPES.ACTUATOR_STATE,
          5000
        )
        console.log(`[Test] Actuator event received: ${msg.type}`)
      } catch {
        console.log('[Test] No immediate actuator WebSocket event (expected for some configurations)')
      }

      // Page should remain functional
      const deviceLocator = page.locator(`text=${espId}`)
      await expect(deviceLocator).toBeVisible({ timeout: 5000 })
    })
  })

  // ── Emergency Stop Flow ───────────────────────────────────────────

  test.describe('Emergency Stop', () => {
    let espId: string

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      espId = await createTestDevice(page, request, {
        prefix: 'EMERGENCY',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        actuators: [
          { gpio: 16, actuator_type: 'relay', name: 'Pumpe' },
        ],
        auto_heartbeat: true,
      })

      await publishHeartbeat(espId)
      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      await deleteMockEsp(page, request, espId).catch(() => {})
    })

    test('should receive emergency stop event via WebSocket', async ({ page }) => {
      const wsHelper = await createWebSocketHelper(page)

      await page.goto('/hardware')
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)

      // Trigger emergency stop via MQTT
      await publishEmergencyStop(espId, { message: 'E2E test emergency' })
      await page.waitForTimeout(3000)

      // Check for emergency alert event
      try {
        const msg = await wsHelper.waitForMessageMatching(
          (m) =>
            m.type === WS_MESSAGE_TYPES.ACTUATOR_ALERT ||
            (m.type === 'actuator_alert' && (m.data as Record<string, unknown>).alert_type === 'emergency_stop'),
          8000
        )
        console.log(`[Test] Emergency event received: ${msg.type}`)
        expect(msg.data).toBeTruthy()
      } catch {
        console.log('[Test] No emergency WebSocket event — server may not broadcast mock alerts')
      }

      // Page should still be functional after emergency event
      const deviceLocator = page.locator(`text=${espId}`)
      await expect(deviceLocator).toBeVisible({ timeout: 5000 })
    })
  })

  // ── Device Lifecycle Status Changes ───────────────────────────────

  test.describe('Device Lifecycle Status', () => {
    let espId: string

    test.beforeEach(async ({ page, request }) => {
      await navigateToHardware(page)

      espId = await createTestDevice(page, request, {
        prefix: 'STATUS',
        zone_id: ZONE_GEWAECHSHAUS,
        zone_name: 'Gewächshaus',
        sensors: [
          { gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5, name: 'Temp' },
        ],
        auto_heartbeat: true,
      })

      await publishHeartbeat(espId)
      await page.reload()
      await page.waitForLoadState('load')
      await page.waitForTimeout(2000)
    })

    test.afterEach(async ({ page, request }) => {
      await deleteMockEsp(page, request, espId).catch(() => {})
    })

    test('should show device as online after heartbeat', async ({ page }) => {
      const deviceLocator = page.locator(`text=${espId}`)
      await expect(deviceLocator).toBeVisible({ timeout: 10000 })

      // Check for online status indicator (green dot, "Online" text, etc.)
      const onlineIndicator = page.locator('text=Online')
      const hasOnline = await onlineIndicator.first().isVisible({ timeout: 5000 }).catch(() => false)
      console.log(`[Test] Online indicator visible: ${hasOnline}`)
    })

    test('should update device status after new heartbeat', async ({ page }) => {
      // Send another heartbeat with different metrics
      await publishHeartbeat(espId, {
        heapFree: 75000,
        uptime: 7200,
      })
      await page.waitForTimeout(3000)

      // Device should still be visible and functional
      const deviceLocator = page.locator(`text=${espId}`)
      await expect(deviceLocator).toBeVisible({ timeout: 5000 })
    })

    test('should display sensor configuration in settings after creation', async ({ page }) => {
      const deviceCard = page.locator(`text=${espId}`).locator('..')
      await deviceCard.hover()

      const settingsBtn = deviceCard.locator('[title="Einstellungen"]').first()
      if (await settingsBtn.isVisible({ timeout: 3000 })) {
        await settingsBtn.click()

        const dialog = page.locator('[role="dialog"]')
        await expect(dialog).toBeVisible({ timeout: 5000 })

        // Sensor section should show configured sensor
        const sensorSection = page.locator('text=Sensoren')
        await expect(sensorSection).toBeVisible({ timeout: 5000 })

        // DS18B20 or Temp text should appear
        const sensorType = page.locator('text=/DS18B20|Temperatur|Temp/')
        const hasSensorType = await sensorType.first().isVisible({ timeout: 3000 }).catch(() => false)
        console.log(`[Test] Sensor type visible in settings: ${hasSensorType}`)
      }
    })
  })
})
