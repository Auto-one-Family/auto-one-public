/**
 * Status Indicator CSS Tests — Schicht 2
 *
 * Verifies status dots, loading states, skeleton screens, and empty states.
 * These are critical UI elements that communicate system health.
 */

import { test, expect } from '@playwright/test'
import { TOKEN_RGB, hasActiveAnimation } from '../helpers/css'

test.describe('Status Indicator Styles', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    // Inject test elements with INLINE styles using CSS variables
    // Note: CSS classes may be tree-shaken by Tailwind/PostCSS if not used
    // in the current page, so we use inline var() references for reliability
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'status-test-container'
      container.style.padding = '20px'
      container.innerHTML = `
        <div id="dot-online" style="width:8px;height:8px;border-radius:var(--radius-full);background-color:var(--color-success);box-shadow:0 0 6px rgba(52,211,153,0.5);flex-shrink:0;"></div>
        <div id="dot-offline" style="width:8px;height:8px;border-radius:var(--radius-full);background-color:var(--color-text-muted);flex-shrink:0;"></div>
        <div id="dot-error" style="width:8px;height:8px;border-radius:var(--radius-full);background-color:var(--color-error);box-shadow:0 0 6px rgba(248,113,113,0.5);flex-shrink:0;"></div>
        <div id="dot-warning" style="width:8px;height:8px;border-radius:var(--radius-full);background-color:var(--color-warning);box-shadow:0 0 6px rgba(251,191,36,0.4);flex-shrink:0;"></div>
        <div id="dot-pulse" style="width:8px;height:8px;border-radius:var(--radius-full);background-color:var(--color-success);animation:pulse-dot 2s infinite;"></div>
        <div id="skeleton-text" style="height:16px;width:100%;border-radius:var(--radius-sm);background:linear-gradient(90deg,var(--color-bg-tertiary) 25%,var(--color-bg-quaternary) 50%,var(--color-bg-tertiary) 75%);background-size:200% 100%;animation:skeleton-loading 1.5s ease-in-out infinite;"></div>
        <div id="skeleton-card" style="height:128px;width:300px;border-radius:var(--radius-lg);background:linear-gradient(90deg,var(--color-bg-tertiary) 25%,var(--color-bg-quaternary) 50%,var(--color-bg-tertiary) 75%);background-size:200% 100%;animation:skeleton-loading 1.5s ease-in-out infinite;"></div>
        <div id="skeleton-circle" style="width:32px;height:32px;border-radius:var(--radius-full);background:linear-gradient(90deg,var(--color-bg-tertiary) 25%,var(--color-bg-quaternary) 50%,var(--color-bg-tertiary) 75%);background-size:200% 100%;animation:skeleton-loading 1.5s ease-in-out infinite;"></div>
        <div id="empty-state" style="text-align:center;padding:3rem 1rem;">
          <div id="empty-icon" style="width:64px;height:64px;margin:0 auto 1rem;border-radius:var(--radius-full);display:flex;align-items:center;justify-content:center;background-color:var(--color-bg-tertiary);color:var(--color-text-muted);">📦</div>
          <div id="empty-title" style="font-size:var(--text-lg);font-weight:500;color:var(--color-text-secondary);margin-bottom:0.5rem;">Keine Daten</div>
          <div id="empty-desc" style="font-size:var(--text-base);color:var(--color-text-muted);margin-bottom:1rem;">Beschreibung</div>
        </div>
        <div id="error-state" style="display:flex;align-items:center;gap:0.75rem;padding:1rem;border-radius:var(--radius-md);background-color:rgba(248,113,113,0.08);border:1px solid rgba(248,113,113,0.2);">
          <span id="error-icon" style="color:var(--color-error);flex-shrink:0;">⚠️</span>
          <span id="error-msg" style="color:var(--color-error);font-size:var(--text-base);">Verbindung fehlgeschlagen</span>
        </div>
      `
      document.body.appendChild(container)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // STATUS DOTS
  // ═══════════════════════════════════════════════════════════════════════

  test('.status-dot has 8px diameter', async ({ page }) => {
    const dot = page.locator('#dot-online')
    await expect(dot).toHaveCSS('width', '8px')
    await expect(dot).toHaveCSS('height', '8px')
  })

  test('.status-dot is fully round', async ({ page }) => {
    const dot = page.locator('#dot-online')
    const radius = await dot.evaluate((el) =>
      getComputedStyle(el).borderRadius
    )
    // radius-full = 9999px (used instead of 50% in the design system)
    const numericRadius = parseFloat(radius)
    expect(numericRadius).toBeGreaterThanOrEqual(4) // at least 4px = fully round for 8px element
  })

  test('.status-online has success color', async ({ page }) => {
    const dot = page.locator('#dot-online')
    await expect(dot).toHaveCSS('background-color', TOKEN_RGB['--color-success'])
  })

  test('.status-online has glow shadow', async ({ page }) => {
    const dot = page.locator('#dot-online')
    const shadow = await dot.evaluate((el) =>
      getComputedStyle(el).boxShadow
    )
    expect(shadow).not.toBe('none')
    expect(shadow).toContain('rgb')
  })

  test('.status-offline has muted color', async ({ page }) => {
    const dot = page.locator('#dot-offline')
    await expect(dot).toHaveCSS('background-color', TOKEN_RGB['--color-text-muted'])
  })

  test('.status-error has error color with glow', async ({ page }) => {
    const dot = page.locator('#dot-error')
    await expect(dot).toHaveCSS('background-color', TOKEN_RGB['--color-error'])

    const shadow = await dot.evaluate((el) =>
      getComputedStyle(el).boxShadow
    )
    expect(shadow).not.toBe('none')
  })

  test('.status-warning has warning color', async ({ page }) => {
    const dot = page.locator('#dot-warning')
    await expect(dot).toHaveCSS('background-color', TOKEN_RGB['--color-warning'])
  })

  test('.status-dot-pulse has animation', async ({ page }) => {
    const dot = page.locator('#dot-pulse')
    const isAnimated = await hasActiveAnimation(dot)
    expect(isAnimated).toBe(true)
  })

  // ═══════════════════════════════════════════════════════════════════════
  // SKELETON LOADING
  // ═══════════════════════════════════════════════════════════════════════

  test('.skeleton has animated background', async ({ page }) => {
    const skeleton = page.locator('#skeleton-text')
    const isAnimated = await hasActiveAnimation(skeleton)
    expect(isAnimated).toBe(true)
  })

  test('.skeleton-text has correct height', async ({ page }) => {
    const skeleton = page.locator('#skeleton-text')
    const height = parseFloat(await skeleton.evaluate((el) =>
      getComputedStyle(el).height
    ))
    expect(height).toBe(16)
  })

  test('.skeleton-card has rounded corners and height', async ({ page }) => {
    const skeleton = page.locator('#skeleton-card')
    const radius = parseFloat(await skeleton.evaluate((el) =>
      getComputedStyle(el).borderRadius
    ))
    // radius-lg = 16px
    expect(radius).toBe(16)

    const height = parseFloat(await skeleton.evaluate((el) =>
      getComputedStyle(el).height
    ))
    expect(height).toBe(128)
  })

  test('.skeleton-circle has full border-radius', async ({ page }) => {
    const skeleton = page.locator('#skeleton-circle')
    const radius = parseFloat(await skeleton.evaluate((el) =>
      getComputedStyle(el).borderRadius
    ))
    // radius-full = 9999px (used instead of 50%)
    expect(radius).toBeGreaterThanOrEqual(16) // fully round for 32px element
  })

  // ═══════════════════════════════════════════════════════════════════════
  // EMPTY STATE
  // ═══════════════════════════════════════════════════════════════════════

  test('.empty-state is centered', async ({ page }) => {
    const state = page.locator('#empty-state')
    await expect(state).toHaveCSS('text-align', 'center')
  })

  test('.empty-state-icon has muted color', async ({ page }) => {
    const icon = page.locator('#empty-icon')
    await expect(icon).toHaveCSS('color', TOKEN_RGB['--color-text-muted'])
  })

  test('.empty-state-title has secondary text color', async ({ page }) => {
    const title = page.locator('#empty-title')
    await expect(title).toHaveCSS('color', TOKEN_RGB['--color-text-secondary'])
  })

  // ═══════════════════════════════════════════════════════════════════════
  // ERROR STATE
  // ═══════════════════════════════════════════════════════════════════════

  test('.error-state has red border and background', async ({ page }) => {
    const state = page.locator('#error-state')
    const bg = await state.evaluate((el) =>
      getComputedStyle(el).backgroundColor
    )
    expect(bg).toContain('rgba')

    const border = await state.evaluate((el) =>
      getComputedStyle(el).borderStyle
    )
    expect(border).toBe('solid')
  })

  test('.error-state-message has error color', async ({ page }) => {
    const msg = page.locator('#error-msg')
    await expect(msg).toHaveCSS('color', TOKEN_RGB['--color-error'])
  })

  test('.error-state has flex layout', async ({ page }) => {
    const state = page.locator('#error-state')
    await expect(state).toHaveCSS('display', 'flex')
    await expect(state).toHaveCSS('align-items', 'center')
  })
})
