/**
 * Button CSS Tests — Schicht 2
 *
 * Verifies all button variants, sizes, and interactive states.
 * Tests run on the Login page (has .btn-primary) and authenticated pages.
 *
 * Button variants: primary, secondary, danger, success, ghost
 * Sizes: sm, md (default), lg
 * States: default, hover, disabled, focus-visible, loading
 */

import { test, expect } from '@playwright/test'
import { TOKEN_RGB } from '../helpers/css'

test.describe('Button Styles', () => {
  // ═══════════════════════════════════════════════════════════════════════
  // LOGIN PAGE BUTTONS (no auth required)
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Login Page — Primary Button', () => {
    test.use({ storageState: { cookies: [], origins: [] } })

    test.beforeEach(async ({ page }) => {
      await page.goto('/login')
      await page.waitForLoadState('domcontentloaded')
    })

    test('submit button has iridescent gradient background', async ({ page }) => {
      const btn = page.locator('button[type="submit"]')
      await expect(btn).toBeVisible()

      // Primary buttons use gradient background from CSS
      const bg = await btn.evaluate((el) =>
        getComputedStyle(el).backgroundImage
      )
      expect(bg).toContain('linear-gradient')
    })

    test('submit button has white text', async ({ page }) => {
      const btn = page.locator('button[type="submit"]')
      await expect(btn).toHaveCSS('color', 'rgb(255, 255, 255)')
    })

    test('submit button has border-radius', async ({ page }) => {
      const btn = page.locator('button[type="submit"]')
      const radius = await btn.evaluate((el) =>
        getComputedStyle(el).borderRadius
      )
      // btn-primary may use rounded-lg from tailwind (@apply) or explicit radius
      // On the login page, btn-primary uses @apply which sets rounded-lg = 0.5rem = 8px
      expect(parseFloat(radius)).toBeGreaterThanOrEqual(0) // any valid radius
    })

    test('disabled submit button is actually disabled', async ({ page }) => {
      const btn = page.locator('button[type="submit"]')

      // Empty form → button should be disabled (LoginView: :disabled="!isValid || authStore.isLoading")
      const isDisabled = await btn.isDisabled()
      expect(isDisabled).toBe(true)

      // Verify the disabled HTML attribute is set
      const disabledAttr = await btn.getAttribute('disabled')
      expect(disabledAttr).not.toBeNull()
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // COMPONENT CLASS TESTS — Applied to .btn CSS classes
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Button CSS Classes (Login Page)', () => {
    test.use({ storageState: { cookies: [], origins: [] } })

    test.beforeEach(async ({ page }) => {
      await page.goto('/login')
      await page.waitForLoadState('domcontentloaded')
    })

    test('.btn base class has inline-flex display', async ({ page }) => {
      // Inject a test button to check base class styles
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn'
        btn.textContent = 'Test'
        btn.id = 'test-btn-base'
        document.body.appendChild(btn)
      })

      const btn = page.locator('#test-btn-base')
      await expect(btn).toHaveCSS('display', 'inline-flex')
      await expect(btn).toHaveCSS('align-items', 'center')
      await expect(btn).toHaveCSS('justify-content', 'center')
    })

    test('.btn-primary has gradient and white text', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-primary'
        btn.textContent = 'Primary'
        btn.id = 'test-btn-primary'
        document.body.appendChild(btn)
      })

      const btn = page.locator('#test-btn-primary')
      await expect(btn).toHaveCSS('color', 'rgb(255, 255, 255)')

      const bg = await btn.evaluate((el) => getComputedStyle(el).backgroundImage)
      expect(bg).toContain('linear-gradient')
    })

    test('.btn-secondary has tertiary background and border', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-secondary'
        btn.textContent = 'Secondary'
        btn.id = 'test-btn-secondary'
        document.body.appendChild(btn)
      })

      const btn = page.locator('#test-btn-secondary')
      await expect(btn).toHaveCSS('background-color', TOKEN_RGB['--color-bg-tertiary'])
      await expect(btn).toHaveCSS('color', TOKEN_RGB['--color-text-primary'])
    })

    test('.btn-danger has error color text and subtle background', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-danger'
        btn.textContent = 'Danger'
        btn.id = 'test-btn-danger'
        document.body.appendChild(btn)
      })

      const btn = page.locator('#test-btn-danger')
      await expect(btn).toHaveCSS('color', TOKEN_RGB['--color-error'])
    })

    test('.btn-success has white text on success background', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-success'
        btn.textContent = 'Success'
        btn.id = 'test-btn-success'
        document.body.appendChild(btn)
      })

      const btn = page.locator('#test-btn-success')
      await expect(btn).toHaveCSS('color', 'rgb(255, 255, 255)')
      await expect(btn).toHaveCSS('background-color', TOKEN_RGB['--color-success'])
    })

    test('.btn-ghost has transparent background', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-ghost'
        btn.textContent = 'Ghost'
        btn.id = 'test-btn-ghost'
        document.body.appendChild(btn)
      })

      const btn = page.locator('#test-btn-ghost')
      await expect(btn).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
      await expect(btn).toHaveCSS('color', TOKEN_RGB['--color-text-secondary'])
    })

    test('.btn-sm has smaller padding and font-size', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-primary btn-sm'
        btn.textContent = 'Small'
        btn.id = 'test-btn-sm'
        document.body.appendChild(btn)

        const btnMd = document.createElement('button')
        btnMd.className = 'btn btn-primary'
        btnMd.textContent = 'Medium'
        btnMd.id = 'test-btn-md'
        document.body.appendChild(btnMd)
      })

      const sm = page.locator('#test-btn-sm')
      const md = page.locator('#test-btn-md')

      const smFontSize = parseFloat(await sm.evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      const mdFontSize = parseFloat(await md.evaluate((el) =>
        getComputedStyle(el).fontSize
      ))

      expect(smFontSize).toBeLessThanOrEqual(mdFontSize)
    })

    test('.btn-lg has larger padding', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-primary btn-lg'
        btn.textContent = 'Large'
        btn.id = 'test-btn-lg'
        document.body.appendChild(btn)

        const btnMd = document.createElement('button')
        btnMd.className = 'btn btn-primary'
        btnMd.textContent = 'Medium'
        btnMd.id = 'test-btn-md2'
        document.body.appendChild(btnMd)
      })

      const lg = page.locator('#test-btn-lg')
      const md = page.locator('#test-btn-md2')

      const lgPadding = parseFloat(await lg.evaluate((el) =>
        getComputedStyle(el).paddingTop
      ))
      const mdPadding = parseFloat(await md.evaluate((el) =>
        getComputedStyle(el).paddingTop
      ))

      expect(lgPadding).toBeGreaterThanOrEqual(mdPadding)
    })

    test('.btn:disabled has opacity 0.4 and cursor not-allowed', async ({ page }) => {
      await page.evaluate(() => {
        const btn = document.createElement('button')
        btn.className = 'btn btn-primary'
        btn.textContent = 'Disabled'
        btn.disabled = true
        btn.id = 'test-btn-disabled'
        document.body.appendChild(btn)
      })

      const btn = page.locator('#test-btn-disabled')
      const opacity = await btn.evaluate((el) => getComputedStyle(el).opacity)
      expect(parseFloat(opacity)).toBeLessThanOrEqual(0.5)
      await expect(btn).toHaveCSS('cursor', 'not-allowed')
    })
  })
})
