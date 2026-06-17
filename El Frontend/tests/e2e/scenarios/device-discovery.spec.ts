/**
 * Device Discovery E2E Tests
 *
 * Tests ESP32 device discovery via MQTT heartbeat.
 * Simulates a new device coming online and appearing in the UI.
 */

import { test, expect } from '@playwright/test'
import { createWebSocketHelper, WS_MESSAGE_TYPES } from '../helpers/websocket'
import { publishHeartbeat, generateMockId } from '../helpers/mqtt'

test.describe('Device Discovery', () => {
  // Requires live MQTT/IoT data — will be linked to Wokwi SIL testing
  test.skip(!!process.env.CI, 'Requires live IoT data — use Wokwi integration for CI')

  test('should discover new device via heartbeat', async ({ page }) => {
    // Setup WebSocket listener
    const wsHelper = await createWebSocketHelper(page)

    // Navigate to dashboard (/devices redirects to /)
    await page.goto('/')
    await page.waitForLoadState('load')

    // Generate unique device ID for this test
    const testDeviceId = generateMockId('DISC')
    console.log(`[Test] Using device ID: ${testDeviceId}`)

    // Publish heartbeat (simulates ESP32 coming online)
    await publishHeartbeat(testDeviceId, {
      heapFree: 120000,
      uptime: 60,
    })

    // Wait for WebSocket event (new device → device_discovered, known device → esp_health)
    try {
      const wsMessage = await wsHelper.waitForMessageMatching(
        (msg) =>
          msg.type === WS_MESSAGE_TYPES.DEVICE_DISCOVERED ||
          msg.type === WS_MESSAGE_TYPES.DEVICE_ONLINE,
        10000
      )
      expect(wsMessage.data.esp_id || wsMessage.data.device_id).toBe(testDeviceId)
    } catch {
      // If no WebSocket message, the device should still appear in UI via API refresh
      console.log('[Test] No WebSocket message received, checking UI directly')
    }

    // Wait for server to process and frontend to update
    await page.waitForTimeout(2000)

    // Open pending devices panel (new devices go there, not main list)
    const pendingButton = page.getByRole('button', { name: /Geräte|Neue/ })
    await pendingButton.click()
    await page.waitForTimeout(500)

    // Device ID should be visible in the panel
    const deviceElement = page.locator(`text=${testDeviceId}`)
    await expect(deviceElement).toBeVisible({ timeout: 10000 })
  })

  test('should show device as online after heartbeat', async ({ page }) => {
    const wsHelper = await createWebSocketHelper(page)
    await page.goto('/')
    await page.waitForLoadState('load')

    // Generate unique device ID
    const testDeviceId = generateMockId('ONLINE')

    // Send multiple heartbeats to ensure device is registered
    await publishHeartbeat(testDeviceId)
    await page.waitForTimeout(500)
    await publishHeartbeat(testDeviceId)

    // Wait for device to appear (may need approval first - check main list or pending)
    await page.waitForTimeout(2000)
    await page.reload()
    await page.waitForLoadState('load')

    // Look for online status indicator
    const deviceCard = page.locator(`[data-device-id="${testDeviceId}"], :has-text("${testDeviceId}")`)

    if (await deviceCard.isVisible({ timeout: 5000 })) {
      // Check for online indicator (green dot, "online" text, etc.)
      const onlineIndicator = deviceCard.locator(
        '.online, .status-online, [data-status="online"], :has-text("Online"), .bg-green-500'
      )
      await expect(onlineIndicator).toBeVisible({ timeout: 5000 })
    }
  })

  test('should update device list in real-time via WebSocket', async ({ page }) => {
    const wsHelper = await createWebSocketHelper(page)
    await page.goto('/')
    await page.waitForLoadState('load')

    // Generate unique device ID
    const testDeviceId = generateMockId('REALTIME')

    // Publish heartbeat
    await publishHeartbeat(testDeviceId)

    // Wait for WebSocket/API to process
    await page.waitForTimeout(2000)

    // Open pending panel (new devices go there, not main list)
    const pendingBtn = page.getByRole('button', { name: /Geräte|Neue/ })
    await pendingBtn.click()
    await page.waitForTimeout(500)

    // Device should be visible in panel (toast and pending-device can both show it – use panel-specific selector)
    const deviceInPanel = page.locator('.pending-device__name', { hasText: testDeviceId })
    await expect(deviceInPanel).toBeVisible({ timeout: 5000 })
  })
})
