/**
 * Badge CSS Tests — Schicht 2
 *
 * Verifies badge variants: success, warning, danger, info, gray, mock, real
 * Tests: background-color, text color, border-radius (pill), font-size, padding
 */

import { test, expect } from '@playwright/test'
import { TOKEN_RGB } from '../helpers/css'

test.describe('Badge Styles', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    // Inject test badges into the page
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'badge-test-container'
      container.style.padding = '20px'
      container.innerHTML = `
        <span class="badge badge-success" id="badge-success">Online</span>
        <span class="badge badge-warning" id="badge-warning">Warning</span>
        <span class="badge badge-danger" id="badge-danger">Error</span>
        <span class="badge badge-info" id="badge-info">Info</span>
        <span class="badge badge-gray" id="badge-gray">Offline</span>
        <span class="badge badge-mock" id="badge-mock">Mock</span>
        <span class="badge badge-real" id="badge-real">Real</span>
      `
      document.body.appendChild(container)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // BASE BADGE
  // ═══════════════════════════════════════════════════════════════════════

  test('badge has inline-flex display', async ({ page }) => {
    const badge = page.locator('#badge-success')
    await expect(badge).toHaveCSS('display', 'inline-flex')
  })

  test('badge has pill shape (border-radius full)', async ({ page }) => {
    const badge = page.locator('#badge-success')
    const radius = await badge.evaluate((el) =>
      getComputedStyle(el).borderRadius
    )
    // radius-full = 9999px
    expect(parseFloat(radius)).toBeGreaterThanOrEqual(9999)
  })

  test('badge has small font-size', async ({ page }) => {
    const badge = page.locator('#badge-success')
    const fontSize = parseFloat(await badge.evaluate((el) =>
      getComputedStyle(el).fontSize
    ))
    // text-xs = 11px
    expect(fontSize).toBeLessThanOrEqual(14)
  })

  test('badge has font-weight 600', async ({ page }) => {
    const badge = page.locator('#badge-success')
    await expect(badge).toHaveCSS('font-weight', '600')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // COLOR VARIANTS
  // ═══════════════════════════════════════════════════════════════════════

  test('badge-success has green text', async ({ page }) => {
    const badge = page.locator('#badge-success')
    await expect(badge).toHaveCSS('color', TOKEN_RGB['--color-success'])
  })

  test('badge-success has semi-transparent green background', async ({ page }) => {
    const badge = page.locator('#badge-success')
    const bg = await badge.evaluate((el) =>
      getComputedStyle(el).backgroundColor
    )
    expect(bg).toContain('rgba')
    // Should contain green channel (52, 211, 153 with alpha ~0.12)
    expect(bg).toMatch(/rgba\(\s*52\s*,\s*211\s*,\s*153/)
  })

  test('badge-warning has yellow text', async ({ page }) => {
    const badge = page.locator('#badge-warning')
    await expect(badge).toHaveCSS('color', TOKEN_RGB['--color-warning'])
  })

  test('badge-danger has red text', async ({ page }) => {
    const badge = page.locator('#badge-danger')
    await expect(badge).toHaveCSS('color', TOKEN_RGB['--color-error'])
  })

  test('badge-info has blue text', async ({ page }) => {
    const badge = page.locator('#badge-info')
    await expect(badge).toHaveCSS('color', TOKEN_RGB['--color-info'])
  })

  test('badge-gray has secondary text color', async ({ page }) => {
    const badge = page.locator('#badge-gray')
    await expect(badge).toHaveCSS('color', TOKEN_RGB['--color-text-secondary'])
  })

  test('badge-mock has purple text and border', async ({ page }) => {
    const badge = page.locator('#badge-mock')
    await expect(badge).toHaveCSS('color', TOKEN_RGB['--color-mock'])

    // Mock badge should have a border
    const borderStyle = await badge.evaluate((el) =>
      getComputedStyle(el).borderStyle
    )
    expect(borderStyle).not.toBe('none')
  })

  test('badge-real has cyan text and border', async ({ page }) => {
    const badge = page.locator('#badge-real')
    await expect(badge).toHaveCSS('color', TOKEN_RGB['--color-real'])

    // Real badge should have a border
    const borderStyle = await badge.evaluate((el) =>
      getComputedStyle(el).borderStyle
    )
    expect(borderStyle).not.toBe('none')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // VISUAL DISTINCTIVENESS
  // ═══════════════════════════════════════════════════════════════════════

  test('all badge variants have distinct text colors', async ({ page }) => {
    const variants = [
      'badge-success',
      'badge-warning',
      'badge-danger',
      'badge-info',
      'badge-mock',
      'badge-real',
    ]

    const colors = new Set<string>()
    for (const variant of variants) {
      const color = await page.locator(`#${variant}`).evaluate((el) =>
        getComputedStyle(el).color
      )
      colors.add(color)
    }

    // All variants should have unique colors
    expect(colors.size).toBe(variants.length)
  })
})
