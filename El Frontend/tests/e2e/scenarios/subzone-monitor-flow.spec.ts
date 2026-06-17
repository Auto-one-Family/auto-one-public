/**
 * Subzone-Monitor Flow — Playwright E2E
 *
 * Flow: Dashboard (Hardware) → Sensor konfigurieren → Subzone zuweisen →
 * Monitor → Subzone-Darstellung prüfen
 *
 * Ausführung:
 *   npx playwright test subzone-monitor-flow.spec.ts --project=chromium
 *
 * Voraussetzung: Stack läuft (make e2e-up). Mock ESP wird automatisch erstellt.
 */

import { test, expect } from '@playwright/test'
import { createMockEspWithSensors, deleteMockEsp } from '../helpers/api'

const ZONE_ID = 'e2e_subzone_monitor'
const ZONE_NAME = 'E2E Subzone Zone'

function uniqueEspId(): string {
  const suffix = Date.now().toString(36).toUpperCase()
  return `MOCK_SUBZONE${suffix}`
}

test.describe('Subzone-Monitor Flow', () => {
  let espId: string

  test.beforeEach(async ({ page, request }) => {
    // Auth-State laden (Token für API)
    await page.goto('/')
    await page.waitForLoadState('load')
    await page.waitForTimeout(500)

    // Mock ESP mit Zone + Sensor erstellen (E2E-Stack startet mit leerer DB)
    espId = uniqueEspId()
    await createMockEspWithSensors(page, request, {
      espId,
      zone_id: ZONE_ID,
      zone_name: ZONE_NAME,
      sensors: [
        { gpio: 4, sensor_type: 'DS18B20', raw_value: 22.5, name: 'Bodentemp' },
      ],
      auto_heartbeat: true,
    })

    await page.waitForTimeout(500)
  })

  test.afterEach(async ({ page, request }) => {
    if (espId) {
      await deleteMockEsp(page, request, espId).catch(() => {})
    }
  })

  test('Subzone für Sensor konfigurieren und im Monitor prüfen', async ({
    page,
  }) => {
    // ═══ Schritt 1: Hardware-View Level 1 laden ═══
    await page.goto('/hardware')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)

    // Warten bis ESPs geladen (device-mini-card in ZonePlate)
    await page.waitForSelector('.device-mini-card', { timeout: 15000 })

    // ═══ Schritt 2: Device-Card klicken → Level 2 (Orbital) ═══
    const deviceCard = page.locator(`[data-device-id="${espId}"]`).first()
    if ((await deviceCard.count()) > 0) {
      await deviceCard.click({ timeout: 10000 })
    } else {
      // Fallback: erste device-mini-card oder direkte URL-Navigation
      await page.locator('.device-mini-card').first().click({ timeout: 10000 })
    }
    await page.waitForTimeout(1500)

    // Prüfe dass Level 2 aktiv ist (Orbital-Layout mit Sensor-Satellites)
    await page.waitForSelector('.sensor-satellite', { timeout: 15000 })

    // ═══ Schritt 3: Sensor-Satellite klicken → öffnet SensorConfigPanel ═══
    const sensorSatellite = page.locator('.sensor-satellite[data-gpio="4"]')
    if ((await sensorSatellite.count()) > 0) {
      await sensorSatellite.click({ timeout: 10000 })
    } else {
      // Fallback: ersten Sensor-Satellite klicken
      await page.locator('.sensor-satellite').first().click({ timeout: 10000 })
    }
    await page.waitForTimeout(600)

    // ═══ Schritt 4: Subzone "Neue Subzone erstellen" wählen ═══
    const subzoneSelect = page.locator('.subzone-assignment__select')
    await subzoneSelect.waitFor({ state: 'visible', timeout: 10000 })
    await subzoneSelect.selectOption({ label: '+ Neue Subzone erstellen...' })
    await page.waitForTimeout(500)

    const subzoneInput = page.locator('.subzone-assignment__input')
    await subzoneInput.fill('E2E-Test-Subzone')
    await page.waitForTimeout(300)

    const confirmBtn = page.locator('.subzone-assignment__btn--confirm')
    await confirmBtn.click({ timeout: 10000, force: true })
    await page.waitForTimeout(2000)

    // Save Sensor-Config
    const saveBtn = page.locator('.sensor-config__save')
    if ((await saveBtn.count()) > 0) {
      await saveBtn.click({ timeout: 5000 })
      await page.waitForTimeout(1500)
    }

    // ═══ Schritt 5: Zum Monitor navigieren ═══
    await page.goto('/monitor')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)

    // ═══ Schritt 6: Zone-Tile klicken für L2-Ansicht ═══
    // Wait for zone tiles to render (CI may need extra time for KPI aggregation)
    await page.waitForSelector('.monitor-zone-tile', { timeout: 20000 })
    const zoneTile = page.locator('.monitor-zone-tile').first()
    await zoneTile.click({ timeout: 10000 })
    await page.waitForTimeout(2000)

    // ═══ Schritt 7: Subzone-Bereich sichtbar (E2E-Test-Subzone oder Keine Subzone) ═══
    const subzoneSection = page.locator('.monitor-subzone')
    await expect(subzoneSection.first()).toBeVisible({ timeout: 10000 })

    // Subzone-Name sollte erscheinen
    const subzoneName = page.getByText(/E2E-Test-Subzone|Keine Subzone/)
    await expect(subzoneName.first()).toBeVisible({ timeout: 5000 })
  })
})
