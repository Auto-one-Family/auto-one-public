/**
 * Touch Hardware CSS Tests — Pi touchscreen targets on /hardware path
 *
 * Verifies ON/OFF controls meet WCAG 2.1 target size (44×44px) and
 * DeviceMiniCard typography under coarse pointer at Pi viewports.
 *
 * Credentials: E2E_TEST_USER=e2e_admin E2E_TEST_PASSWORD=E2eTouch123!
 * (Pi DB — not admin/Admin123#)
 */

import { test, expect, type Page } from '@playwright/test'
import { createMockEspWithSensors, deleteMockEsp } from '../helpers/api'

const ZONE_ID = 'e2e_gewaechshaus'
const ZONE_NAME = 'Gewächshaus'

const VIEWPORTS = [
  { label: '1280×800', width: 1280, height: 800 },
  { label: '800×480', width: 800, height: 480 },
] as const

function uniqueId(prefix: string): string {
  return `MOCK_TOUCH${prefix}${Date.now().toString(36).toUpperCase()}`
}

async function enableTouchDensity(page: Page): Promise<void> {
  await page.evaluate(() => {
    document.documentElement.setAttribute('data-ui-density', 'touch')
  })
}

async function navigateToDeviceDetail(page: Page, espId: string): Promise<void> {
  await page.goto(`/hardware/${ZONE_ID}/${espId}`)
  await page.waitForLoadState('load')
  await expect(page.locator('.orbital-overlay')).toBeVisible({ timeout: 15000 })
  // Level-2 flip animation uses scale(0.85→1) — wait before measuring bounding boxes
  await page.waitForTimeout(800)
}

async function assertMinTouchTarget(locator: ReturnType<Page['locator']>, label: string): Promise<void> {
  await expect(locator).toBeVisible({ timeout: 10000 })
  // offsetWidth/Height: layout box (pre-transform) — modal enter uses scale(0.95) briefly
  const size = await locator.evaluate((el) => ({
    width: el.offsetWidth,
    height: el.offsetHeight,
  }))
  expect(size.width, `${label} width`).toBeGreaterThanOrEqual(44)
  expect(size.height, `${label} height`).toBeGreaterThanOrEqual(44)
}

/** Satellite toggle: measure the touch-target wrapper (flex-safe). */
async function assertSatelliteToggle(page: Page): Promise<void> {
  const wrap = page.locator('.actuator-satellite__toggle-wrap')
  await assertMinTouchTarget(wrap, 'ActuatorSatellite toggle wrap')
}

test.describe('Touch Hardware — ON/OFF controls', () => {
  test.skip(!!process.env.CI, 'Requires live backend — use docker compose e2e-up')
  test.describe.configure({ mode: 'serial' })
  test.setTimeout(90000)

  let espId: string

  test.beforeEach(async ({ page, request }) => {
    await page.goto('/hardware')
    await page.waitForLoadState('load')

    espId = uniqueId('HW')
    await createMockEspWithSensors(page, request, {
      espId,
      zone_id: ZONE_ID,
      zone_name: ZONE_NAME,
      sensors: [{ gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5, name: 'Bodentemp' }],
      actuators: [{ gpio: 16, actuator_type: 'relay', name: 'Pumpe' }],
      auto_heartbeat: true,
    })

    await page.reload()
    await page.waitForLoadState('load')
    await page.waitForTimeout(1500)
  })

  test.afterEach(async ({ page, request }) => {
    if (espId) {
      await deleteMockEsp(page, request, espId).catch(() => {})
    }
  })

  for (const viewport of VIEWPORTS) {
    test(`ON/OFF controls ≥44px at ${viewport.label}`, async ({ page }) => {
      await page.setViewportSize({ width: viewport.width, height: viewport.height })
      await enableTouchDensity(page)
      await page.waitForTimeout(300)

      // Level 1: mock cards show "Mock #XXXX" (last 4 chars of espId)
      const mockLabel = `#${espId.slice(-4)}`
      const deviceCard = page.locator('.device-mini-card').filter({ hasText: mockLabel })
      await expect(deviceCard).toBeVisible({ timeout: 15000 })

      // Device name typography under coarse pointer
      const deviceName = deviceCard.locator('.esp-card-base__name')
      const nameFontSize = await deviceName.evaluate((el) =>
        parseFloat(getComputedStyle(el).fontSize)
      )
      expect(nameFontSize).toBeGreaterThanOrEqual(13)

      await navigateToDeviceDetail(page, espId)

      // ActuatorSatellite inline toggle (wrapper carries touch-target)
      await assertSatelliteToggle(page)

      // Sensor config panel
      await page.locator('.sensor-satellite').first().click()
      await expect(page.getByTestId('sensor-config-enable-toggle')).toBeVisible({ timeout: 10000 })
      await page.waitForTimeout(500) // BaseModal enter animation (scale 0.95→1)
      await assertMinTouchTarget(
        page.getByTestId('sensor-config-enable-toggle'),
        'SensorConfigPanel enable toggle'
      )

      // Close wizard and open actuator config
      await page.keyboard.press('Escape')
      await page.waitForTimeout(500)

      await page.locator('.actuator-satellite__label').first().click()
      await expect(page.getByTestId('actuator-config-power-toggle')).toBeVisible({ timeout: 10000 })
      await page.waitForTimeout(500) // BaseModal enter animation
      await assertMinTouchTarget(
        page.getByTestId('actuator-config-power-toggle'),
        'ActuatorConfigPanel power toggle'
      )
      await assertMinTouchTarget(
        page.getByTestId('actuator-config-enabled-toggle'),
        'ActuatorConfigPanel enabled toggle'
      )
    })
  }
})
