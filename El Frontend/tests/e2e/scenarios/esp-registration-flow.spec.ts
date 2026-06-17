/**
 * ESP Registration Flow - Playwright User-Simulation
 *
 * Simuliert den kompletten User-Flow: Login -> Dashboard -> Pending-Panel öffnen -> ESP genehmigen.
 * Macht Screenshots auf jedem Schritt für Nachvollziehbarkeit.
 *
 * Ausführung:
 *   npx playwright test esp-registration-flow.spec.ts --project=chromium
 *
 * Screenshots landen in: logs/frontend/playwright/esp-registration-flow/
 */

import { test } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SCREENSHOT_DIR = path.join(
  __dirname,
  '../../../../logs/frontend/playwright/esp-registration-flow'
)

function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
  }
}

test.use({ storageState: { cookies: [], origins: [] } })

test.describe('ESP Registrierungs-Flow (User-Simulation)', () => {
  // Requires live ESP32/MQTT data — will be linked to Wokwi SIL testing
  test.skip(!!process.env.CI, 'Requires live IoT data — use Wokwi integration for CI')

  test('Vollständiger Flow: Login -> Pending öffnen -> ESP genehmigen', async ({
    page,
  }) => {
    ensureScreenshotDir()
    const step = (n: number, name: string) =>
      path.join(SCREENSHOT_DIR, `${String(n).padStart(2, '0')}-${name}.png`)

    // ═══ Schritt 1: Login-Seite ═══
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: step(1, 'landing-or-login') })

    // Falls Login nötig: Credentials eingeben (wie User)
    const loginInput = page.locator(
      'input[name="username"], input[type="text"][placeholder*="Nutzer"], input[type="text"]'
    )
    if ((await loginInput.count()) > 0) {
      await page.fill('input[name="username"], input[type="text"]', 'admin')
      await page.fill('input[name="password"], input[type="password"]', process.env.E2E_TEST_PASSWORD ?? '')
      await page.screenshot({ path: step(2, 'login-form-filled') })
      await page.click('button[type="submit"]')
      await page.waitForURL(/\/(dashboard)?(\?.*)?$/, { timeout: 15000 })
    }

    await page.waitForLoadState('networkidle')
    await page.screenshot({ path: step(3, 'dashboard-after-login') })

    // ═══ Schritt 4: Pending-Panel öffnen (Geräte-Button) ═══
    const pendingBtn = page.getByRole('button', {
      name: /Geräte|Neue|Wartend/i,
    })
    await pendingBtn.click({ timeout: 10000 })
    await page.waitForTimeout(800)
    await page.screenshot({ path: step(4, 'pending-panel-open') })

    // ═══ Schritt 5: Prüfen ob Pending-Devices da sind ═══
    const pendingList = page.locator('.pending-device, .pending-panel__list')
    const hasDevices = (await pendingList.locator('.pending-device').count()) > 0

    if (hasDevices) {
      await page.screenshot({ path: step(5, 'pending-devices-list') })

      // ═══ Schritt 6: Ersten ESP genehmigen (Genehmigen-Button) ═══
      const approveBtn = page.locator(
        '.pending-device__btn--approve, button:has-text("Genehmigen")'
      ).first()
      // Panel ist fixed-positioned – JS-Click um Viewport-Probleme zu umgehen
      await approveBtn.evaluate((el: HTMLElement) => el.click())
      await page.waitForTimeout(1500)
      await page.screenshot({ path: step(6, 'after-approval') })

      // Panel schließen (Backdrop-Klick oder Schließen-Button; Panel ist fixed)
      const closeBtn = page.locator('.pending-panel__close')
      if ((await closeBtn.count()) > 0) {
        await closeBtn.evaluate((el: HTMLElement) => el.click())
        await page.waitForTimeout(500)
      }
    } else {
      await page.screenshot({ path: step(5, 'pending-empty') })
    }

    await page.screenshot({ path: step(7, 'dashboard-final') })
  })
})
