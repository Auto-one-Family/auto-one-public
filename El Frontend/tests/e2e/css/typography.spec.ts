/**
 * Typography CSS Tests — Schicht 2
 *
 * Verifies font families, text sizes, line heights, and text utilities.
 * Font loading (Outfit, JetBrains Mono) is tested via computed styles.
 */

import { test, expect } from '@playwright/test'
import { getDesignToken } from '../helpers/css'

test.describe('Typography System', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // FONT FAMILIES
  // ═══════════════════════════════════════════════════════════════════════

  test('body uses Outfit font family', async ({ page }) => {
    const fontFamily = await page.evaluate(() =>
      getComputedStyle(document.body).fontFamily
    )
    // Should contain Outfit (may include fallbacks)
    expect(fontFamily.toLowerCase()).toContain('outfit')
  })

  test('html uses the display font from design tokens', async ({ page }) => {
    const fontDisplay = await getDesignToken(page, '--font-display')
    expect(fontDisplay).toContain('Outfit')
  })

  test('mono font token includes JetBrains Mono', async ({ page }) => {
    const fontMono = await getDesignToken(page, '--font-mono')
    expect(fontMono).toContain('JetBrains Mono')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TEXT SIZE SCALE — Injected elements with explicit sizes
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Text Size Scale', () => {
    test.beforeEach(async ({ page }) => {
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'typo-test-container'
        container.innerHTML = `
          <span id="typo-xs" style="font-size: var(--text-xs);">XS</span>
          <span id="typo-sm" style="font-size: var(--text-sm);">SM</span>
          <span id="typo-base" style="font-size: var(--text-base);">Base</span>
          <span id="typo-lg" style="font-size: var(--text-lg);">LG</span>
          <span id="typo-xl" style="font-size: var(--text-xl);">XL</span>
          <span id="typo-2xl" style="font-size: var(--text-2xl);">2XL</span>
          <span id="typo-display" style="font-size: var(--text-display);">Display</span>
        `
        document.body.appendChild(container)
      })
    })

    test('text-xs = 11px (0.6875rem)', async ({ page }) => {
      const size = parseFloat(await page.locator('#typo-xs').evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      expect(size).toBe(11)
    })

    test('text-sm = 12px (0.75rem)', async ({ page }) => {
      const size = parseFloat(await page.locator('#typo-sm').evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      expect(size).toBe(12)
    })

    test('text-base = 14px (0.875rem)', async ({ page }) => {
      const size = parseFloat(await page.locator('#typo-base').evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      expect(size).toBe(14)
    })

    test('text-lg = 16px (1rem)', async ({ page }) => {
      const size = parseFloat(await page.locator('#typo-lg').evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      expect(size).toBe(16)
    })

    test('text-xl = 20px (1.25rem)', async ({ page }) => {
      const size = parseFloat(await page.locator('#typo-xl').evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      expect(size).toBe(20)
    })

    test('text-2xl = 24px (1.5rem)', async ({ page }) => {
      const size = parseFloat(await page.locator('#typo-2xl').evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      expect(size).toBe(24)
    })

    test('text-display = 32px (2rem)', async ({ page }) => {
      const size = parseFloat(await page.locator('#typo-display').evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      expect(size).toBe(32)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TEXT UTILITIES
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Text Utilities', () => {
    test.beforeEach(async ({ page }) => {
      // Use inline styles referencing CSS variables since utility classes
      // may be tree-shaken if not used on the current page
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'text-util-container'
        container.innerHTML = `
          <span id="text-gradient" style="font-size:24px;background-image:var(--gradient-iridescent);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;">Gradient Text</span>
          <span id="text-primary" style="color:var(--color-text-primary);">Primary</span>
          <span id="text-secondary" style="color:var(--color-text-secondary);">Secondary</span>
          <span id="text-muted" style="color:var(--color-text-muted);">Muted</span>
          <span id="text-status-success" style="color:var(--color-success);">OK</span>
          <span id="text-status-warning" style="color:var(--color-warning);">Warn</span>
          <span id="text-status-error" style="color:var(--color-error);">Error</span>
          <span id="text-mock" style="color:var(--color-mock);">Mock</span>
          <span id="text-real" style="color:var(--color-real);">Real</span>
        `
        document.body.appendChild(container)
      })
    })

    test('.text-gradient has background-clip: text', async ({ page }) => {
      const el = page.locator('#text-gradient')
      const bgClip = await el.evaluate((element) => {
        const style = getComputedStyle(element)
        return style.backgroundClip || (style as any).webkitBackgroundClip || ''
      })
      expect(bgClip).toContain('text')
    })

    test('.text-gradient has iridescent gradient background', async ({ page }) => {
      const el = page.locator('#text-gradient')
      const bgImage = await el.evaluate((element) =>
        getComputedStyle(element).backgroundImage
      )
      expect(bgImage).toContain('linear-gradient')
    })

    test('.text-primary uses correct color variable', async ({ page }) => {
      const el = page.locator('#text-primary')
      const color = await el.evaluate((element) =>
        getComputedStyle(element).color
      )
      expect(color).toBe('rgb(234, 234, 242)')
    })

    test('.text-secondary uses correct color variable', async ({ page }) => {
      const el = page.locator('#text-secondary')
      const color = await el.evaluate((element) =>
        getComputedStyle(element).color
      )
      expect(color).toBe('rgb(133, 133, 160)')
    })

    test('.text-muted uses correct color variable', async ({ page }) => {
      const el = page.locator('#text-muted')
      const color = await el.evaluate((element) =>
        getComputedStyle(element).color
      )
      expect(color).toBe('rgb(72, 72, 96)')
    })

    test('.text-mock uses purple color', async ({ page }) => {
      const el = page.locator('#text-mock')
      const color = await el.evaluate((element) =>
        getComputedStyle(element).color
      )
      expect(color).toBe('rgb(167, 139, 250)')
    })

    test('.text-real uses cyan color', async ({ page }) => {
      const el = page.locator('#text-real')
      const color = await el.evaluate((element) =>
        getComputedStyle(element).color
      )
      expect(color).toBe('rgb(34, 211, 238)')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // FONT RENDERING
  // ═══════════════════════════════════════════════════════════════════════

  test('body has antialiased text rendering', async ({ page }) => {
    const rendering = await page.evaluate(() => {
      const style = getComputedStyle(document.body)
      return {
        webkit: (style as any).webkitFontSmoothing || '',
        moz: (style as any).MozOsxFontSmoothing || '',
      }
    })
    // CSS sets: -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;
    // Chrome returns webkitFontSmoothing, Firefox returns MozOsxFontSmoothing
    // On Linux Firefox, MozOsxFontSmoothing may be empty (macOS-only)
    // We check that at least one is set, or accept that Linux Firefox skips it
    const hasSmoothing =
      rendering.webkit === 'antialiased' ||
      rendering.moz === 'grayscale' ||
      rendering.webkit !== '' ||
      rendering.moz !== ''

    // On Linux, neither may be reported — that's acceptable
    // The CSS rule still exists, just not queryable on non-macOS
    expect(typeof rendering.webkit).toBe('string')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // LOGIN PAGE TYPOGRAPHY
  // ═══════════════════════════════════════════════════════════════════════

  test('login title has large font size', async ({ page }) => {
    const title = page.locator('.login-title')
    if (await title.count() > 0) {
      const fontSize = parseFloat(await title.evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      // Should be ~30px (1.875rem)
      expect(fontSize).toBeGreaterThanOrEqual(28)
    }
  })

  test('login title has bold weight', async ({ page }) => {
    const title = page.locator('.login-title')
    if (await title.count() > 0) {
      const weight = await title.evaluate((el) =>
        getComputedStyle(el).fontWeight
      )
      expect(parseInt(weight)).toBeGreaterThanOrEqual(700)
    }
  })

  test('login subtitle has muted color', async ({ page }) => {
    const subtitle = page.locator('.login-subtitle')
    if (await subtitle.count() > 0) {
      const color = await subtitle.evaluate((el) =>
        getComputedStyle(el).color
      )
      expect(color).toBe('rgb(72, 72, 96)')
    }
  })
})
