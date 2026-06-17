import { expect, test, type Page } from '@playwright/test'
import { createMockEspWithSensors, deleteMockEsp } from '../helpers/api'

type VisualViewport = {
  name: string
  width: number
  height: number
}

const VISUAL_VIEWPORTS: VisualViewport[] = [
  { name: '1280x720', width: 1280, height: 720 },
  { name: '1366x768', width: 1366, height: 768 },
  { name: '1536x864', width: 1536, height: 864 },
  { name: '1920x1080', width: 1920, height: 1080 },
  { name: '2560x1440', width: 2560, height: 1440 },
]

const VISUAL_ZONE_ID = 'e2e_visual_zone'
const VISUAL_ZONE_NAME = 'E2E Visual Monitor Zone'

function uniqueEspId(viewportName: string): string {
  const compactViewport = viewportName.replace(/[^0-9]/g, '')
  const suffix = Date.now().toString(36).toUpperCase()
  return `MOCK_${compactViewport}${suffix}`
}

async function settleUi(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(1200)
}

async function stabilizeSensorCardForScreenshot(
  card: ReturnType<Page['locator']>
): Promise<void> {
  await card.evaluate((element) => {
    const target = element as HTMLElement
    target.style.width = '232px'
    target.style.minWidth = '232px'
    target.style.maxWidth = '232px'
    target.style.minHeight = '188px'
    target.style.boxSizing = 'border-box'
  })
}

async function stabilizeZoneTileForScreenshot(
  tile: ReturnType<Page['locator']>
): Promise<void> {
  await tile.evaluate((element) => {
    const target = element as HTMLElement
    target.style.width = '488px'
    target.style.minWidth = '488px'
    target.style.maxWidth = '488px'
    target.style.minHeight = '276px'
    target.style.boxSizing = 'border-box'
  })
}

test.describe('AUT-34 Visual Regression - Monitor L1/L2', () => {
  test.describe.configure({ mode: 'serial' })

  for (const viewport of VISUAL_VIEWPORTS) {
    test(`captures monitor snapshots for ${viewport.name}`, async ({ page, request }) => {
      let espId = ''

      try {
        await page.setViewportSize({ width: viewport.width, height: viewport.height })
        await page.goto('/')
        await settleUi(page)

        espId = uniqueEspId(viewport.name)
        await createMockEspWithSensors(page, request, {
          espId,
          zone_id: VISUAL_ZONE_ID,
          zone_name: VISUAL_ZONE_NAME,
          auto_heartbeat: true,
          sensors: [
            {
              gpio: 4,
              sensor_type: 'DS18B20',
              name: 'Normal Temp Sensor',
              raw_value: 22.4,
            },
            {
              gpio: 5,
              sensor_type: 'ec',
              name: 'Overflow Sensor Mit Extra Langem Namen Fuer Visual Check',
              raw_value: 123456.789,
            },
          ],
        })

        await page.goto('/monitor')
        await settleUi(page)
        await expect(page.locator('.monitor-zone-tile').first()).toBeVisible({ timeout: 15000 })

        await expect(page).toHaveScreenshot(`monitor-l1-full-${viewport.name}.png`, {
          fullPage: true,
          animations: 'disabled',
          mask: [page.locator('time, [data-timestamp]')],
        })

        const zoneTile = page.locator('.monitor-zone-tile').first()
        await stabilizeZoneTileForScreenshot(zoneTile)
        await expect(zoneTile).toHaveScreenshot(`zone-tile-${viewport.name}.png`, {
          animations: 'disabled',
          maxDiffPixelRatio: 0.03,
        })

        await zoneTile.click()
        await settleUi(page)
        await expect(page.locator('.monitor-subzone').first()).toBeVisible({ timeout: 15000 })

        await expect(page).toHaveScreenshot(`monitor-l2-full-${viewport.name}.png`, {
          fullPage: true,
          animations: 'disabled',
          mask: [page.locator('time, [data-timestamp]')],
        })

        const normalSensorCard = page
          .locator('.sensor-card')
          .filter({ hasText: 'Normal Temp Sensor' })
          .first()
        await expect(normalSensorCard).toBeVisible({ timeout: 10000 })
        await stabilizeSensorCardForScreenshot(normalSensorCard)
        await expect(normalSensorCard).toHaveScreenshot(`sensor-card-normal-${viewport.name}.png`, {
          animations: 'disabled',
          maxDiffPixelRatio: 0.03,
        })

        const overflowSensorCard = page
          .locator('.sensor-card')
          .filter({ hasText: 'Overflow Sensor Mit Extra Langem Namen Fuer Visual Check' })
          .first()
        await expect(overflowSensorCard).toBeVisible({ timeout: 10000 })
        await stabilizeSensorCardForScreenshot(overflowSensorCard)
        await expect(overflowSensorCard).toHaveScreenshot(`sensor-card-overflow-${viewport.name}.png`, {
          animations: 'disabled',
          maxDiffPixelRatio: 0.03,
        })
      } finally {
        if (espId) {
          await deleteMockEsp(page, request, espId).catch(() => {})
        }
      }
    })
  }
})
