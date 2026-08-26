/**
 * E2E Tests für CalibrationWizard (Sprint-W16 / AUT-9)
 *
 * Testet:
 *   1. Happy Path: Select → Point1 → Point2 → Confirm → Finalizing → Done (Success)
 *   2. Timeout Path: Select → Submit → Finalizing → Timeout → Error-UI
 *   3. Resume Path: Set sessionStorage draft → Reload → Resume → Finalize → Done
 *
 * Mocks: All API routes via page.route(), WebSocket via page.routeWebSocket()
 */

import { test, expect, type Page } from '@playwright/test'

// ─── Mock: Auth ────────────────────────────────────────────────────────────────

function mockAuthRoutes(page: Page): void {
  page.route('**/api/v1/auth/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ setup_required: false }),
    })
  })

  page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'test-admin-id',
        username: 'admin',
        email: 'admin@test.local',
        role: 'admin',
        full_name: 'Test Admin',
        is_active: true,
      }),
    })
  })

  page.route('**/api/v1/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        tokens: {
          access_token: 'fake-refreshed-token',
          refresh_token: 'fake-refreshed-refresh',
        },
      }),
    })
  })
}

// ─── Mock: ESP Devices ─────────────────────────────────────────────────────────

const TEST_ESP = {
  esp_id: 'TEST_ESP_001',
  device_id: 'TEST_ESP_001',
  name: 'Test-ESP pH',
  is_online: true,
  is_mock: false,
  zone_id: 'zone_test',
  zone_name: 'Testzone',
  sensor_count: 1,
  actuator_count: 0,
  sensors: [
    {
      gpio: 5,
      sensor_type: 'ph',
      name: 'pH Sensor',
      is_active: true,
      subzone_id: null,
    },
  ],
  actuators: [],
  system_state: { free_heap: 100000, uptime_seconds: 3600 },
  hardware_type: 'real',
}

function mockEspRoutes(page: Page): void {
  // Specific routes FIRST (Playwright matches first registered route)
  page.route('**/api/v1/esp/devices/pending', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, devices: [] }),
    })
  })

  page.route('**/api/v1/esp/devices/*/sensors', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: TEST_ESP.sensors }),
    })
  })

  page.route('**/api/v1/esp/devices/*/actuators', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })

  page.route('**/api/v1/esp/devices/*/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { status: 'healthy' } }),
    })
  })

  page.route('**/api/v1/esp/devices/*/alert-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: {} }),
    })
  })

  // General device list route LAST
  page.route('**/api/v1/esp/devices**', async (route) => {
    const url = route.request().url()
    // Only handle the list endpoint, not sub-resources
    if (
      url.match(/\/esp\/devices(\?|$)/) &&
      route.request().method() === 'GET'
    ) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: [TEST_ESP] }),
      })
    } else {
      await route.continue()
    }
  })

  page.route('**/api/v1/debug/mock-esp**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })
}

// ─── Mock: Zones + catch-all ───────────────────────────────────────────────────

function mockMiscRoutes(page: Page): void {
  page.route('**/api/v1/zones**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: [{ id: 'zone_test', name: 'Testzone', order: 0 }],
      }),
    })
  })

  page.route('**/api/v1/sensors/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })

  page.route('**/api/v1/actuators/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })

  page.route('**/api/v1/dashboard**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })

  page.route('**/api/v1/logic/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })

  page.route('**/api/v1/notifications**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [], total: 0, unread_count: 0 }),
    })
  })

  page.route('**/api/v1/alerts**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [], stats: { total: 0, active: 0, acknowledged: 0 } }),
    })
  })

  page.route('**/api/v1/plugins**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })
}

// ─── Mock: Calibration API ─────────────────────────────────────────────────────

let sessionPointCount = 0
let sessionStatus = 'active'

function mockCalibrationRoutes(page: Page): void {
  sessionPointCount = 0
  sessionStatus = 'active'

  // IMPORTANT: Playwright matches last-registered-first.
  // Register catch-all FIRST, specific routes LAST for correct priority.

  // Catch-all for session GET/DELETE (lowest priority)
  page.route('**/api/v1/calibration/sessions/**', async (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'session_test',
          esp_id: 'TEST_ESP_001',
          gpio: 5,
          sensor_type: 'ph',
          status: sessionStatus,
          method: 'ph_2point',
          expected_points: 2,
          points_collected: sessionPointCount,
          calibration_points: { points: [] },
          calibration_result:
            sessionStatus === 'applied'
              ? { offset: 0.1, slope: -59.16, slope_deviation_pct: 2.1 }
              : null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          completed_at: sessionStatus === 'applied' ? new Date().toISOString() : null,
          failure_reason: null,
        }),
      })
    } else if (method === 'DELETE') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'discarded' }),
      })
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true }),
      })
    }
  })

  // Create session (POST /sessions)
  page.route('**/api/v1/calibration/sessions', async (route) => {
    if (route.request().method() === 'POST') {
      sessionPointCount = 0
      sessionStatus = 'active'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'session_test',
          esp_id: 'TEST_ESP_001',
          gpio: 5,
          sensor_type: 'ph',
          status: 'active',
          method: 'ph_2point',
          expected_points: 2,
          points_collected: 0,
          calibration_points: { points: [] },
          calibration_result: null,
          correlation_id: 'corr_test',
          initiated_by: 'playwright-test',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      })
    } else {
      await route.continue()
    }
  })

  // Apply session (highest priority for this sub-route)
  page.route('**/api/v1/calibration/sessions/*/apply', async (route) => {
    if (route.request().method() === 'POST') {
      sessionStatus = 'applied'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'session_test',
          status: 'applied',
          calibration_result: { offset: 0.1, slope: -59.16 },
        }),
      })
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    }
  })

  // Finalize session
  page.route('**/api/v1/calibration/sessions/*/finalize', async (route) => {
    if (route.request().method() === 'POST') {
      sessionStatus = 'finalizing'
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'session_test',
          status: 'finalizing',
          calibration_result: { offset: 0.1, slope: -59.16 },
        }),
      })
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    }
  })

  // Add point (highest priority)
  page.route('**/api/v1/calibration/sessions/*/points', async (route) => {
    if (route.request().method() === 'POST') {
      sessionPointCount += 1
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'session_test',
          esp_id: 'TEST_ESP_001',
          gpio: 5,
          sensor_type: 'ph',
          status: 'active',
          method: 'ph_2point',
          expected_points: 2,
          points_collected: sessionPointCount,
          calibration_points: { points: [] },
          calibration_result: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      })
    } else {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    }
  })
}

// ─── Mock: Sensor Measurement Trigger ──────────────────────────────────────────

function mockMeasurementRoute(page: Page): void {
  page.route('**/api/v1/sensors/*/5/measure', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          request_id: `req_${Date.now()}`,
          message: 'Measurement triggered',
        }),
      })
    } else {
      await route.continue()
    }
  })
}

// ─── WebSocket Mock ────────────────────────────────────────────────────────────

/**
 * Injects a WebSocket interceptor into the page context BEFORE the app loads.
 * Captures all WebSocket instances so we can dispatch messages from tests.
 */
async function setupWebSocketMock(
  page: Page,
): Promise<{ sendCalibrationMeasurement: (raw: number) => Promise<void> }> {
  await page.addInitScript(() => {
    const OriginalWebSocket = window.WebSocket
    ;(window as any).__test_ws_instances = [] as WebSocket[]
    ;(window as any).WebSocket = class MockedWebSocket extends OriginalWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        super(url, protocols)
        ;(window as any).__test_ws_instances.push(this)
      }
    }
  })

  return {
    async sendCalibrationMeasurement(raw: number) {
      const messagePayload = JSON.stringify({
        type: 'calibration_measurement_received',
        correlation_id: `corr_${Date.now()}`,
        data: {
          esp_id: 'TEST_ESP_001',
          gpio: 5,
          raw_value: raw,
          raw: raw,
          quality: 'good',
          intent_id: `intent_${Date.now()}`,
          correlation_id: `corr_${Date.now()}`,
          session_id: 'session_test',
        },
      })

      await page.evaluate((data) => {
        const instances = (window as any).__test_ws_instances as WebSocket[]
        if (instances.length === 0) {
          console.warn('[E2E] No WebSocket instances found')
          return
        }
        const event = new MessageEvent('message', { data })
        for (const ws of instances) {
          // Call onmessage handler directly (property handler, not addEventListener)
          if (typeof ws.onmessage === 'function') {
            ws.onmessage(event)
            return
          }
        }
        console.warn('[E2E] No WebSocket with onmessage handler found')
      }, messagePayload)
    },
  }
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

async function setupAllMocks(page: Page) {
  mockAuthRoutes(page)
  // General catch-all routes FIRST (Playwright matches last-registered-first)
  mockMiscRoutes(page)
  mockEspRoutes(page)
  // Specific routes LAST (highest priority = last registered)
  mockCalibrationRoutes(page)
  mockMeasurementRoute(page)
  return setupWebSocketMock(page)
}

// ──────────────────────────────────────────────────────────────────────────────
// TEST SUITE
// ──────────────────────────────────────────────────────────────────────────────

test.describe('Calibration Wizard E2E (AUT-9)', () => {
  test.setTimeout(60000)

  test('Test 1: Happy Path - Select Sensor to Success', async ({ page }) => {
    const wsMock = await setupAllMocks(page)
    await page.goto('/calibration')
    await page.waitForLoadState('domcontentloaded')

    const wizard = page.locator('[data-testid="calibration-wizard"]')
    await expect(wizard).toBeVisible({ timeout: 15000 })

    // Step 1: Select pH sensor type
    const phCard = page.locator('.calibration-wizard__type-card', { hasText: 'pH' })
    await expect(phCard).toBeVisible()
    await phCard.click()

    // Wait for device list to appear and select GPIO 5
    const gpioChip = page.locator('.calibration-wizard__gpio-chip', { hasText: 'GPIO 5' })
    await expect(gpioChip).toBeVisible({ timeout: 5000 })
    await gpioChip.click()

    // Step 2: Capture Point 1
    const readBtn = page.locator('.calibration-step__read-btn').first()
    await expect(readBtn).toBeVisible({ timeout: 5000 })
    await readBtn.click()

    // Simulate WebSocket measurement response (give WS time to establish)
    await page.waitForTimeout(500)
    await wsMock.sendCalibrationMeasurement(125.4)

    // Capture the point (wait for isFreshMeasurement to become true)
    const captureBtn = page.locator('.calibration-step__capture-btn').first()
    await expect(captureBtn).toBeEnabled({ timeout: 8000 })
    await captureBtn.click()

    // Step 3: Capture Point 2
    const readBtn2 = page.locator('.calibration-step__read-btn').first()
    await expect(readBtn2).toBeVisible({ timeout: 5000 })
    await readBtn2.click()

    await page.waitForTimeout(500)
    await wsMock.sendCalibrationMeasurement(234.7)

    const captureBtn2 = page.locator('.calibration-step__capture-btn').first()
    await expect(captureBtn2).toBeEnabled({ timeout: 8000 })
    await captureBtn2.click()

    // Step 4: Confirm and submit
    const submitBtn = page.locator('.calibration-wizard__submit-btn', {
      hasText: 'Kalibrierung',
    })
    await expect(submitBtn).toBeVisible({ timeout: 5000 })
    await submitBtn.click()

    // Step 5: Wait for finalizing → done
    const finalizingPhase = page.locator('[data-testid="finalizing-phase"]')
    await expect(finalizingPhase).toBeVisible({ timeout: 10000 })

    const successScreen = page.locator('[data-testid="calibration-success"]')
    await expect(successScreen).toBeVisible({ timeout: 15000 })
  })

  test('Test 2: Timeout Path - Polling never reaches terminal state', async ({ page }) => {
    const wsMock = await setupAllMocks(page)

    // Override: session GET always returns 'finalizing' (never terminal)
    // Use route.fallback() for non-GET so specific routes (points, finalize, apply) still work
    page.route('**/api/v1/calibration/sessions/**', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'session_timeout',
            esp_id: 'TEST_ESP_001',
            gpio: 5,
            sensor_type: 'ph',
            status: 'finalizing',
            method: 'ph_2point',
            expected_points: 2,
            points_collected: 2,
            calibration_points: { points: [] },
            calibration_result: null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            completed_at: null,
            failure_reason: null,
          }),
        })
      } else {
        await route.fallback()
      }
    })

    await page.goto('/calibration')
    await page.waitForLoadState('domcontentloaded')

    const wizard = page.locator('[data-testid="calibration-wizard"]')
    await expect(wizard).toBeVisible({ timeout: 15000 })

    // Select pH → GPIO 5
    await page.locator('.calibration-wizard__type-card', { hasText: 'pH' }).click()
    const gpioChip = page.locator('.calibration-wizard__gpio-chip', { hasText: 'GPIO 5' })
    await expect(gpioChip).toBeVisible({ timeout: 5000 })
    await gpioChip.click()

    // Capture Point 1
    await page.locator('.calibration-step__read-btn').first().click()
    await page.waitForTimeout(500)
    await wsMock.sendCalibrationMeasurement(100.0)
    await expect(page.locator('.calibration-step__capture-btn').first()).toBeEnabled({ timeout: 8000 })
    await page.locator('.calibration-step__capture-btn').first().click()

    // Capture Point 2
    await page.locator('.calibration-step__read-btn').first().click()
    await page.waitForTimeout(500)
    await wsMock.sendCalibrationMeasurement(250.0)
    await expect(page.locator('.calibration-step__capture-btn').first()).toBeEnabled({ timeout: 8000 })
    await page.locator('.calibration-step__capture-btn').first().click()

    // Submit calibration
    await page
      .locator('.calibration-wizard__submit-btn', { hasText: 'Kalibrierung' })
      .click()

    // Wait for timeout error phase (polling 10x * 400ms = 4s + overhead)
    const errorPhase = page.locator('[data-testid="calibration-error"]')
    await expect(errorPhase).toBeVisible({ timeout: 20000 })

    // Verify timeout-related text
    const timeoutText = page.locator(
      ':text("Timeout"), :text("terminale Rueckmeldung"), :text("terminale")',
    )
    await expect(timeoutText.first()).toBeVisible({ timeout: 5000 })

  })

  test('Test 3: Resume Path - Reload preserves state via sessionStorage', async ({
    page,
  }) => {
    const wsMock = await setupAllMocks(page)

    await page.goto('/calibration')
    await page.waitForLoadState('domcontentloaded')

    const wizard = page.locator('[data-testid="calibration-wizard"]')
    await expect(wizard).toBeVisible({ timeout: 15000 })

    // Inject draft into sessionStorage (simulates a previous in-progress calibration)
    await page.evaluate(() => {
      const draft = {
        phase: 'confirm',
        selectedEspId: 'TEST_ESP_001',
        selectedGpio: 5,
        selectedSensorType: 'ph',
        ecPreset: '1413_12880',
        points: [
          { raw: 125.4, reference: 7.0, point_role: 'buffer_high', point_id: 'p1' },
          { raw: 234.7, reference: 4.0, point_role: 'buffer_low', point_id: 'p2' },
        ],
        currentSessionId: 'session_test',
      }
      sessionStorage.setItem('calibration.wizard.draft.v2', JSON.stringify(draft))
    })

    // Reload the page → draft should be restored
    await page.reload()
    await page.waitForLoadState('domcontentloaded')

    // Wizard should still be visible and in confirm phase
    await expect(wizard).toBeVisible({ timeout: 15000 })

    // The confirm phase should show the submit button
    const submitBtn = page.locator('.calibration-wizard__submit-btn', {
      hasText: 'Kalibrierung',
    })
    await expect(submitBtn).toBeVisible({ timeout: 10000 })

    // Submit and finalize
    await submitBtn.click()

    const finalizingPhase = page.locator('[data-testid="finalizing-phase"]')
    await expect(finalizingPhase).toBeVisible({ timeout: 10000 })

    const successScreen = page.locator('[data-testid="calibration-success"]')
    await expect(successScreen).toBeVisible({ timeout: 15000 })

  })
})
