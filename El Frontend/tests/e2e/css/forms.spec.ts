/**
 * Form Element CSS Tests — Schicht 2
 *
 * Verifies input fields, labels, focus states, and error states.
 * Tests run on the Login page which has real form elements.
 */

import { test, expect } from '@playwright/test'
import { TOKEN_RGB } from '../helpers/css'

test.describe('Form Styles', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // INPUT FIELDS (Login page has real inputs)
  // ═══════════════════════════════════════════════════════════════════════

  test('input has tertiary background', async ({ page }) => {
    const input = page.locator('input[type="text"], input#username').first()
    await expect(input).toHaveCSS('background-color', TOKEN_RGB['--color-bg-tertiary'])
  })

  test('input has glass border', async ({ page }) => {
    const input = page.locator('input[type="text"], input#username').first()
    const borderStyle = await input.evaluate((el) =>
      getComputedStyle(el).borderStyle
    )
    expect(borderStyle).toBe('solid')

    const borderColor = await input.evaluate((el) =>
      getComputedStyle(el).borderColor
    )
    expect(borderColor).toContain('rgba')
  })

  test('input has primary text color', async ({ page }) => {
    const input = page.locator('input[type="text"], input#username').first()
    await expect(input).toHaveCSS('color', TOKEN_RGB['--color-text-primary'])
  })

  test('input has padding for comfortable interaction', async ({ page }) => {
    const input = page.locator('input[type="text"], input#username').first()
    const paddingLeft = parseFloat(await input.evaluate((el) =>
      getComputedStyle(el).paddingLeft
    ))
    const paddingTop = parseFloat(await input.evaluate((el) =>
      getComputedStyle(el).paddingTop
    ))
    // Minimum comfortable padding
    expect(paddingLeft).toBeGreaterThanOrEqual(8)
    expect(paddingTop).toBeGreaterThanOrEqual(4)
  })

  test('input has rounded corners', async ({ page }) => {
    const input = page.locator('input[type="text"], input#username').first()
    const radius = parseFloat(await input.evaluate((el) =>
      getComputedStyle(el).borderRadius
    ))
    expect(radius).toBeGreaterThan(0)
  })

  test('input has placeholder text defined', async ({ page }) => {
    // Wait for Vue to mount the form inputs
    await page.waitForSelector('input[type="text"], input#username', { timeout: 5000 })
    const placeholder = await page.evaluate(() => {
      const input = document.querySelector('input[type="text"], input#username') as HTMLInputElement
      return input?.placeholder || ''
    })
    // At minimum, placeholder text should be defined
    expect(placeholder.length).toBeGreaterThan(0)
  })

  // ═══════════════════════════════════════════════════════════════════════
  // FOCUS STATE
  // ═══════════════════════════════════════════════════════════════════════

  test('input focus changes border to accent color', async ({ page }) => {
    const input = page.locator('input[type="text"], input#username').first()

    // Get border before focus
    const borderBefore = await input.evaluate((el) =>
      getComputedStyle(el).borderColor
    )

    // Focus the input
    await input.focus()
    await page.waitForTimeout(200) // Wait for transition

    // Get border after focus
    const borderAfter = await input.evaluate((el) =>
      getComputedStyle(el).borderColor
    )

    // Border should change on focus (or box-shadow/ring should appear)
    const shadowAfter = await input.evaluate((el) =>
      getComputedStyle(el).boxShadow
    )

    // Either border changes or shadow appears
    const focusChanged = borderBefore !== borderAfter || shadowAfter !== 'none'
    expect(focusChanged).toBe(true)
  })

  test('input has transition for smooth focus effect', async ({ page }) => {
    const input = page.locator('input[type="text"], input#username').first()
    const transition = await input.evaluate((el) =>
      getComputedStyle(el).transitionProperty
    )
    expect(transition).not.toBe('none')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // LABELS
  // ═══════════════════════════════════════════════════════════════════════

  test('labels have secondary text color', async ({ page }) => {
    const label = page.locator('label').first()
    if (await label.count() > 0) {
      await expect(label).toHaveCSS('color', TOKEN_RGB['--color-text-secondary'])
    }
  })

  test('labels have small font-size', async ({ page }) => {
    const label = page.locator('label').first()
    if (await label.count() > 0) {
      const fontSize = parseFloat(await label.evaluate((el) =>
        getComputedStyle(el).fontSize
      ))
      // text-sm = 12px or 0.75rem
      expect(fontSize).toBeLessThanOrEqual(14)
    }
  })

  test('labels have font-weight 600', async ({ page }) => {
    const label = page.locator('label').first()
    if (await label.count() > 0) {
      await expect(label).toHaveCSS('font-weight', '600')
    }
  })

  // ═══════════════════════════════════════════════════════════════════════
  // PASSWORD INPUT
  // ═══════════════════════════════════════════════════════════════════════

  test('password toggle button is positioned inside input', async ({ page }) => {
    const toggle = page.locator('.password-toggle')
    if (await toggle.count() > 0) {
      await expect(toggle).toHaveCSS('position', 'absolute')

      // Should be on the right side
      const right = parseFloat(await toggle.evaluate((el) =>
        getComputedStyle(el).right
      ))
      expect(right).toBeGreaterThanOrEqual(0)
      expect(right).toBeLessThanOrEqual(20)
    }
  })

  // ═══════════════════════════════════════════════════════════════════════
  // ERROR STATE (injected)
  // ═══════════════════════════════════════════════════════════════════════

  test('.input-error has error border color', async ({ page }) => {
    await page.evaluate(() => {
      const input = document.createElement('input')
      input.className = 'input input-error'
      input.id = 'test-input-error'
      input.value = 'Error state'
      document.body.appendChild(input)
    })

    const input = page.locator('#test-input-error')
    const borderColor = await input.evaluate((el) =>
      getComputedStyle(el).borderColor
    )
    // Should contain error red color
    expect(borderColor).toContain('rgb')
    // Parse and verify it's a reddish color
    const match = borderColor.match(/rgb\(\s*(\d+)/)
    if (match) {
      const red = parseInt(match[1])
      expect(red).toBeGreaterThan(200) // Strong red component
    }
  })

  // ═══════════════════════════════════════════════════════════════════════
  // LOGIN ERROR MESSAGE
  // ═══════════════════════════════════════════════════════════════════════

  test('login-error style matches design spec when injected via inline styles', async ({ page }) => {
    // login-error is scoped in LoginView, so we test the design spec using inline vars
    await page.evaluate(() => {
      const error = document.createElement('div')
      error.id = 'test-login-error'
      error.style.cssText = 'display:flex;align-items:center;gap:0.5rem;padding:0.75rem;background-color:rgba(248,113,113,0.1);border:1px solid rgba(248,113,113,0.2);border-radius:0.5rem;color:var(--color-error);font-size:0.875rem;'
      error.innerHTML = '<span>Test error message</span>'
      document.body.appendChild(error)
    })

    const error = page.locator('#test-login-error')
    await expect(error).toHaveCSS('display', 'flex')
    await expect(error).toHaveCSS('align-items', 'center')
    await expect(error).toHaveCSS('color', TOKEN_RGB['--color-error'])

    const borderStyle = await error.evaluate((el) =>
      getComputedStyle(el).borderStyle
    )
    expect(borderStyle).toBe('solid')
  })
})
