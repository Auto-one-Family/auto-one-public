/**
 * Card CSS Tests — Schicht 2
 *
 * Verifies card component styles:
 * - .card: background, border, radius, hover state
 * - .card-glass: backdrop-filter blur
 * - .card-header, .card-body, .card-footer: padding, borders
 * - .iridescent-border: gradient border effect
 */

import { test, expect } from '@playwright/test'
import { TOKEN_RGB } from '../helpers/css'

test.describe('Card Styles', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    // Inject test cards
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'card-test-container'
      container.style.padding = '20px'
      container.innerHTML = `
        <div class="card" id="card-standard">
          <div class="card-header" id="card-header">Header</div>
          <div class="card-body" id="card-body">Body</div>
          <div class="card-footer" id="card-footer">Footer</div>
        </div>
        <div class="card-glass" id="card-glass">Glass Card</div>
        <div class="iridescent-border" id="card-iridescent" style="padding: 16px;">Iridescent</div>
      `
      document.body.appendChild(container)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // STANDARD CARD
  // ═══════════════════════════════════════════════════════════════════════

  test('.card has secondary background', async ({ page }) => {
    const card = page.locator('#card-standard')
    await expect(card).toHaveCSS('background-color', TOKEN_RGB['--color-bg-secondary'])
  })

  test('.card has glass border', async ({ page }) => {
    const card = page.locator('#card-standard')
    const borderStyle = await card.evaluate((el) =>
      getComputedStyle(el).borderStyle
    )
    expect(borderStyle).toBe('solid')

    const borderColor = await card.evaluate((el) =>
      getComputedStyle(el).borderColor
    )
    expect(borderColor).toContain('rgba')
  })

  test('.card has radius-lg (16px)', async ({ page }) => {
    const card = page.locator('#card-standard')
    const radius = await card.evaluate((el) =>
      getComputedStyle(el).borderRadius
    )
    expect(parseFloat(radius)).toBe(16)
  })

  test('.card has transition for hover animation', async ({ page }) => {
    const card = page.locator('#card-standard')
    const transition = await card.evaluate((el) =>
      getComputedStyle(el).transitionProperty
    )
    // Should have transition on border-color and/or box-shadow
    expect(transition).not.toBe('none')
    expect(transition).not.toBe('')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // CARD SECTIONS
  // ═══════════════════════════════════════════════════════════════════════

  test('.card-header has padding and bottom border', async ({ page }) => {
    const header = page.locator('#card-header')
    const padding = parseFloat(await header.evaluate((el) =>
      getComputedStyle(el).paddingTop
    ))
    expect(padding).toBeGreaterThan(0)

    const borderBottom = await header.evaluate((el) =>
      getComputedStyle(el).borderBottomStyle
    )
    expect(borderBottom).toBe('solid')
  })

  test('.card-body has padding', async ({ page }) => {
    const body = page.locator('#card-body')
    const padding = parseFloat(await body.evaluate((el) =>
      getComputedStyle(el).paddingTop
    ))
    expect(padding).toBeGreaterThan(0)
  })

  test('.card-footer has tertiary background', async ({ page }) => {
    const footer = page.locator('#card-footer')
    const bg = await footer.evaluate((el) =>
      getComputedStyle(el).backgroundColor
    )
    expect(bg).toBe(TOKEN_RGB['--color-bg-tertiary'])

    // Footer has top border
    const borderTop = await footer.evaluate((el) =>
      getComputedStyle(el).borderTopStyle
    )
    expect(borderTop).toBe('solid')
  })

  test('.card-footer has bottom border-radius matching card', async ({ page }) => {
    const footer = page.locator('#card-footer')
    const radius = await footer.evaluate((el) => {
      const style = getComputedStyle(el)
      return {
        bottomLeft: style.borderBottomLeftRadius,
        bottomRight: style.borderBottomRightRadius,
      }
    })
    // Should have radius on bottom corners to match card
    expect(parseFloat(radius.bottomLeft)).toBeGreaterThan(0)
    expect(parseFloat(radius.bottomRight)).toBeGreaterThan(0)
  })

  // ═══════════════════════════════════════════════════════════════════════
  // GLASS CARD
  // ═══════════════════════════════════════════════════════════════════════

  test('.card-glass has backdrop-filter blur', async ({ page }) => {
    const glass = page.locator('#card-glass')
    const backdrop = await glass.evaluate((el) => {
      const style = getComputedStyle(el)
      return style.backdropFilter || style.webkitBackdropFilter || ''
    })
    expect(backdrop).toContain('blur')
  })

  test('.card-glass has semi-transparent background', async ({ page }) => {
    const glass = page.locator('#card-glass')
    const bg = await glass.evaluate((el) =>
      getComputedStyle(el).backgroundColor
    )
    expect(bg).toContain('rgba')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // IRIDESCENT BORDER
  // ═══════════════════════════════════════════════════════════════════════

  test('.iridescent-border has gradient border via background', async ({ page }) => {
    const iridescent = page.locator('#card-iridescent')
    const bgImage = await iridescent.evaluate((el) =>
      getComputedStyle(el).backgroundImage
    )
    // Should have gradient in the background (used for border-box trick)
    expect(bgImage).toContain('linear-gradient')
  })

  test('.iridescent-border has transparent border', async ({ page }) => {
    const iridescent = page.locator('#card-iridescent')
    const borderStyle = await iridescent.evaluate((el) =>
      getComputedStyle(el).borderStyle
    )
    expect(borderStyle).toBe('solid')
  })
})
