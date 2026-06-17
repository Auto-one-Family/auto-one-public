import { test, expect, type APIRequestContext, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { createMockEspWithSensors, deleteMockEsp } from '../helpers/api'

const TOKEN_KEY = 'el_frontend_access_token'
const SCREENSHOT_DIR = path.resolve(process.cwd(), 'tests/e2e/artifacts/e2e-03')

function uniqueId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`
}

function uniqueMockEspId(prefix: string): string {
  const normalized = prefix.replace(/[^A-Za-z0-9]/g, '').toUpperCase()
  const suffix = Math.random().toString(36).slice(2, 8).toUpperCase()
  return `MOCK_${normalized}${suffix}`
}

function ensureScreenshotDir(): void {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
  }
}

async function shot(page: Page, filename: string): Promise<void> {
  ensureScreenshotDir()
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, filename),
    fullPage: true,
  })
}

async function getToken(page: Page): Promise<string> {
  const token = await page.evaluate((key: string) => localStorage.getItem(key), TOKEN_KEY)
  if (!token) {
    throw new Error('Kein Auth-Token in localStorage gefunden. E2E-Login/GlobalSetup prüfen.')
  }
  return token
}

async function createZone(page: Page, request: APIRequestContext, zoneId: string, zoneName: string): Promise<void> {
  const token = await getToken(page)
  const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://localhost:8000'
  const response = await request.post(`${apiBase}/api/v1/zones`, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    data: {
      zone_id: zoneId,
      name: zoneName,
      description: 'Playwright E2E-03 Testzone',
    },
  })
  if (!response.ok() && response.status() !== 409) {
    throw new Error(`Zone-Erstellung fehlgeschlagen (${zoneId}): ${response.status()} ${await response.text()}`)
  }
}

async function deleteZone(page: Page, request: APIRequestContext, zoneId: string): Promise<void> {
  const token = await getToken(page)
  const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://localhost:8000'
  await request.delete(`${apiBase}/api/v1/zones/${zoneId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

async function openL2(page: Page, zoneId: string, espId: string): Promise<void> {
  await page.goto(`/hardware/${encodeURIComponent(zoneId)}/${encodeURIComponent(espId)}`)
  await page.waitForLoadState('load')
  await page.waitForTimeout(1500)
  await expect(page).toHaveURL(new RegExp(`/hardware/${zoneId}/${espId}`))
}

async function closeTopDialog(page: Page): Promise<void> {
  const closeBtn = page.locator('[role="dialog"] button[aria-label="Schließen"]').first()
  if (await closeBtn.isVisible().catch(() => false)) {
    await closeBtn.click()
    await page.waitForTimeout(400)
  }
}

async function openSensorByText(page: Page, text: string): Promise<void> {
  const sensor = page.locator('[data-satellite-type="sensor"]').filter({ hasText: text }).first()
  await sensor.scrollIntoViewIfNeeded()
  await sensor.click()
  await expect(page.locator('[role="dialog"]').first()).toBeVisible()
}

async function openActuatorByGpio(page: Page, gpio: number): Promise<void> {
  const actuator = page.locator(`[data-satellite-type="actuator"][data-gpio="${gpio}"]`).first()
  await actuator.scrollIntoViewIfNeeded()
  await actuator.click()
  await expect(page.locator('[role="dialog"]').first()).toBeVisible()
}

test.describe('E2E-03 Hardware L2 Device-Detail und Config-Panels', () => {
  test.skip(!!process.env.CI, 'Live-E2E mit lokaler Umgebung und Screenshots')
  test.setTimeout(240000)

  test('führt T01-T15 aus und erstellt 24 Screenshots', async ({ page, request }) => {
    const createdDevices: string[] = []
    const createdZones: string[] = []

    const zoneId = uniqueId('e2e03_zone')
    const zoneName = 'E2E03 Device Detail Zone'
    const espMain = uniqueMockEspId('L2MAIN')
    const espOffline = uniqueMockEspId('L2OFF')

    try {
      await page.goto('/hardware')
      await page.waitForLoadState('load')
      await page.waitForTimeout(1200)

      await createZone(page, request, zoneId, zoneName)
      createdZones.push(zoneId)

      await createMockEspWithSensors(page, request, {
        espId: espMain,
        zone_id: zoneId,
        zone_name: zoneName,
        auto_heartbeat: true,
        sensors: [
          { gpio: 32, sensor_type: 'moisture', raw_value: 1840, name: 'Bodenfeuchte Beet A' },
          { gpio: 0, sensor_type: 'vpd', raw_value: 1.18, name: 'VPD Virtual' },
          { gpio: 21, sensor_type: 'sht31_temp', raw_value: 24.6, name: 'SHT31 Klima Temp' },
          { gpio: 21, sensor_type: 'sht31_humidity', raw_value: 59.4, name: 'SHT31 Klima Feuchte' },
          { gpio: 4, sensor_type: 'ds18b20', raw_value: 22.2, name: 'DS18B20 Nährlösung' },
        ],
        actuators: [
          { gpio: 16, actuator_type: 'relay', name: 'Relais Main' },
          { gpio: 17, actuator_type: 'pwm', name: 'Lüfter PWM' },
          { gpio: 18, actuator_type: 'valve', name: 'Ventil A' },
          { gpio: 19, actuator_type: 'pump', name: 'Pumpe A' },
        ],
      })
      createdDevices.push(espMain)

      await createMockEspWithSensors(page, request, {
        espId: espOffline,
        zone_id: zoneId,
        zone_name: zoneName,
        auto_heartbeat: false,
        sensors: [{ gpio: 5, sensor_type: 'ds18b20', raw_value: 19.1, name: 'Offline Temp' }],
        actuators: [{ gpio: 23, actuator_type: 'relay', name: 'Offline Relais' }],
      })
      createdDevices.push(espOffline)

      await openL2(page, zoneId, espMain)

      // T01
      await shot(page, 'E2E-03-T01-orbital-layout.png')
      await expect.soft(page.locator('[data-satellite-type="sensor"]').first()).toBeVisible()
      await expect.soft(page.locator('[data-satellite-type="actuator"]').first()).toBeVisible()

      // T02
      await openSensorByText(page, 'SHT31')
      await shot(page, 'E2E-03-T02-sensor-config-panel.png')
      await expect.soft(page.locator('.sensor-config__section-title', { hasText: 'Grundeinstellungen' })).toBeVisible()
      await closeTopDialog(page)

      // T03
      await openSensorByText(page, 'Bodenfeuchte')
      await shot(page, 'E2E-03-T03-moisture-config.png')
      await expect.soft(page.locator('text=Kalibrierung').first()).toBeVisible()
      await closeTopDialog(page)

      // T04
      await openSensorByText(page, 'VPD')
      await shot(page, 'E2E-03-T04-vpd-config.png')
      await expect.soft(page.locator('[role="dialog"]').first()).toContainText('VPD')
      await closeTopDialog(page)

      // T05
      await openSensorByText(page, 'SHT31')
      await shot(page, 'E2E-03-T05-sht31-config.png')
      await expect.soft(page.locator('text=I2C-Adresse').first()).toBeVisible()
      await closeTopDialog(page)

      // T06
      await openSensorByText(page, 'DS18B20')
      await shot(page, 'E2E-03-T06-ds18b20-config.png')
      await expect.soft(page.locator('text=OneWire').first()).toBeVisible()
      await closeTopDialog(page)

      // T07
      await openSensorByText(page, 'DS18B20')
      const thresholdInput = page.locator('.sensor-config__threshold-inputs input').first()
      await thresholdInput.fill('10')
      await shot(page, 'E2E-03-T07-sensor-config-changed.png')
      await page.getByRole('button', { name: 'Speichern' }).first().click()
      await page.waitForTimeout(1200)
      await shot(page, 'E2E-03-T07-sensor-config-saved.png')

      // T08
      await openActuatorByGpio(page, 16)
      await shot(page, 'E2E-03-T08-actuator-config-panel.png')
      await expect.soft(page.locator('.actuator-config__state-text').first()).toBeVisible()

      // T09
      await shot(page, 'E2E-03-T09-actuator-before-command.png')
      const toggleBtn = page.locator('.actuator-config__toggle-btn').first()
      await toggleBtn.click()
      await page.waitForTimeout(1200)
      await shot(page, 'E2E-03-T09-actuator-after-on.png')
      if (await toggleBtn.isVisible().catch(() => false)) {
        await toggleBtn.click()
        await page.waitForTimeout(1200)
      }
      await shot(page, 'E2E-03-T09-actuator-after-off.png')
      await closeTopDialog(page)

      // T10
      await openActuatorByGpio(page, 17)
      const pwmSlider = page.locator('.actuator-config__pwm-slider').first()
      await pwmSlider.fill('50')
      await page.waitForTimeout(800)
      await shot(page, 'E2E-03-T10-pwm-value-set.png')
      await closeTopDialog(page)

      // T11 (globaler Not-Aus mit Confirm Dialog)
      const emergencyBtn = page.locator('button[aria-label*="Not-Aus"]').first()
      await emergencyBtn.click()
      await shot(page, 'E2E-03-T11-emergency-stop-button.png')
      await expect.soft(page.locator('.emergency-dialog').first()).toBeVisible()
      await shot(page, 'E2E-03-T11-emergency-confirm.png')
      await page.locator('.emergency-dialog button', { hasText: 'Abbrechen' }).click()
      await page.waitForTimeout(500)
      await shot(page, 'E2E-03-T11-emergency-executed.png')

      // T12 (Sidebar DnD -> AddSensorModal)
      const sidebarItem = page.locator('.component-item--sensor').first()
      const orbitalTarget = page.locator(`[data-esp-id="${espMain}"]`).first()
      const sourceBox = await sidebarItem.boundingBox()
      const targetBox = await orbitalTarget.boundingBox()
      if (sourceBox && targetBox) {
        await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
        await page.mouse.down()
        await page.waitForTimeout(200)
        await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + targetBox.height / 2, { steps: 12 })
        await page.mouse.up()
        await page.waitForTimeout(1000)
      }
      await shot(page, 'E2E-03-T12-orbital-dnd-add.png')
      const addSensorModal = page.getByRole('dialog').filter({ hasText: 'Sensor hinzufügen' }).first()
      if (await addSensorModal.isVisible().catch(() => false)) {
        await addSensorModal.locator('button[aria-label="Schließen"]').click().catch(() => {})
      }

      // T13
      await openSensorByText(page, 'Bodenfeuchte')
      await shot(page, 'E2E-03-T13-config-push.png')
      await closeTopDialog(page)

      // T14
      await openActuatorByGpio(page, 19)
      await shot(page, 'E2E-03-T14-config-pump.png')
      await closeTopDialog(page)

      await openActuatorByGpio(page, 18)
      await shot(page, 'E2E-03-T14-config-valve.png')
      await closeTopDialog(page)

      await openActuatorByGpio(page, 17)
      await shot(page, 'E2E-03-T14-config-pwm.png')
      await closeTopDialog(page)

      await openActuatorByGpio(page, 16)
      await shot(page, 'E2E-03-T14-config-relay.png')
      await closeTopDialog(page)

      // T15
      await page.locator('.device-header-bar__back').first().click()
      await page.waitForLoadState('load')
      await page.waitForTimeout(1000)
      await shot(page, 'E2E-03-T15-back-to-L1.png')
      await expect.soft(page).toHaveURL(new RegExp('/hardware'))
    } finally {
      for (const id of createdDevices) {
        await deleteMockEsp(page, request, id).catch(() => {})
      }
      for (const id of createdZones) {
        await deleteZone(page, request, id).catch(() => {})
      }
    }
  })
})
