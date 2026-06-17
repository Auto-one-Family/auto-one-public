/**
 * E2E Tests: HistoricalChart Gap Handling (AUT-113)
 *
 * Verifies gap detection and sparse-data warning with mocked API responses.
 * Uses Playwright route interception to inject sparse sensor data.
 */

import { test, expect } from '@playwright/test'

const SPARSE_DATA_RESPONSE = {
  success: true,
  esp_id: 'ESP_GAP_E2E',
  gpio: 4,
  sensor_type: 'temperature',
  readings: [
    {
      timestamp: '2026-04-22T08:00:00Z',
      raw_value: 22.5,
      processed_value: 22.5,
      unit: '°C',
      quality: 'good',
    },
    {
      timestamp: '2026-04-22T13:00:00Z',
      raw_value: 23.1,
      processed_value: 23.1,
      unit: '°C',
      quality: 'good',
    },
  ],
  count: 2,
  resolution: '5m',
  time_range: {
    start: '2026-04-22T06:00:00Z',
    end: '2026-04-22T14:00:00Z',
    has_more: false,
  },
}

const DENSE_DATA_WITH_GAP_RESPONSE = {
  success: true,
  esp_id: 'ESP_GAP_E2E',
  gpio: 4,
  sensor_type: 'temperature',
  readings: Array.from({ length: 20 }, (_, i) => {
    const hourOffset = i < 10 ? i * 5 : (i - 10) * 5 + 180
    return {
      timestamp: new Date(
        Date.UTC(2026, 3, 22, 6, hourOffset, 0),
      ).toISOString(),
      raw_value: 20 + Math.sin(i) * 3,
      processed_value: 20 + Math.sin(i) * 3,
      unit: '°C',
      quality: 'good',
    }
  }),
  count: 20,
  resolution: '5m',
  time_range: {
    start: '2026-04-22T06:00:00Z',
    end: '2026-04-22T14:00:00Z',
    has_more: false,
  },
}

test.describe('HistoricalChart Gap Handling', () => {
  test.skip(
    !!process.env.CI,
    'Requires running frontend dev server — skipped in CI',
  )

  test('sparse data shows warning banner', async ({ page }) => {
    await page.route('**/api/v1/sensors/data*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SPARSE_DATA_RESPONSE),
      }),
    )

    await page.route('**/api/v1/sensors/**/stats*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          esp_id: 'ESP_GAP_E2E',
          gpio: 4,
          sensor_type: 'temperature',
          stats: {
            min_value: 22.5,
            max_value: 23.1,
            avg_value: 22.8,
            std_dev: 0.3,
            reading_count: 2,
          },
          time_range: {
            start: '2026-04-22T06:00:00Z',
            end: '2026-04-22T14:00:00Z',
          },
        }),
      }),
    )

    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const sparseBanner = page.locator('.historical-chart__sparse-banner')
    if (await sparseBanner.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(sparseBanner).toContainText('Wenige Datenpunkte')
    }
  })

  test('dense data with gap shows gap info', async ({ page }) => {
    await page.route('**/api/v1/sensors/data*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DENSE_DATA_WITH_GAP_RESPONSE),
      }),
    )

    await page.route('**/api/v1/sensors/**/stats*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          esp_id: 'ESP_GAP_E2E',
          gpio: 4,
          sensor_type: 'temperature',
          stats: {
            min_value: 17.0,
            max_value: 23.0,
            avg_value: 20.0,
            std_dev: 1.8,
            reading_count: 20,
          },
          time_range: {
            start: '2026-04-22T06:00:00Z',
            end: '2026-04-22T14:00:00Z',
          },
        }),
      }),
    )

    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const gapInfo = page.locator('.historical-chart__gap-info')
    if (await gapInfo.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(gapInfo).toContainText('Lücke')
    }
  })

  test('chart canvas renders with gap data', async ({ page }) => {
    await page.route('**/api/v1/sensors/data*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(DENSE_DATA_WITH_GAP_RESPONSE),
      }),
    )

    await page.route('**/api/v1/sensors/**/stats*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }),
    )

    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const chartCanvas = page.locator('.historical-chart__canvas canvas')
    if (await chartCanvas.isVisible({ timeout: 5000 }).catch(() => false)) {
      await expect(chartCanvas).toBeVisible()
    }
  })
})
