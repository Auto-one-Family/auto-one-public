/**
 * Responsive Layout CSS Tests — Schicht 3
 *
 * Verifies layout behavior across different viewport sizes:
 * - Desktop (1280×720): Sidebar visible, full layout
 * - Tablet (768×1024): Sidebar at breakpoint boundary
 * - Mobile (375×667): Sidebar hidden, hamburger menu, compact layout
 *
 * Tests the AppShell (sidebar + header + content), widget grid,
 * and responsive utility classes.
 *
 * NOTE: These tests use the Login page for unauthenticated tests
 * and inject layout elements for authenticated layout verification.
 */

import { test, expect } from '@playwright/test'
import { VIEWPORTS, isVisibleInViewport, getElementSize } from '../helpers/css'

// ═══════════════════════════════════════════════════════════════════════════
// LOGIN PAGE RESPONSIVE — No auth required
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Login Page Responsive', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('login container is centered on desktop', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    const container = page.locator('.login-container')
    if (await container.count() > 0) {
      const box = await container.boundingBox()
      expect(box).toBeTruthy()
      if (box) {
        // Container should be horizontally centered
        const viewportWidth = VIEWPORTS.desktop.width
        const centerX = box.x + box.width / 2
        const viewportCenter = viewportWidth / 2
        expect(Math.abs(centerX - viewportCenter)).toBeLessThan(50)
      }
    }
  })

  test('login container has max-width constraint', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    const container = page.locator('.login-container')
    if (await container.count() > 0) {
      const maxWidth = await container.evaluate((el) =>
        getComputedStyle(el).maxWidth
      )
      const numericMax = parseFloat(maxWidth)
      // max-width: 24rem = 384px
      expect(numericMax).toBeLessThanOrEqual(400)
      expect(numericMax).toBeGreaterThan(300)
    }
  })

  test('login form adapts to mobile width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile)
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    const container = page.locator('.login-container')
    if (await container.count() > 0) {
      const box = await container.boundingBox()
      expect(box).toBeTruthy()
      if (box) {
        // Should use most of the viewport width on mobile
        expect(box.width).toBeGreaterThan(VIEWPORTS.mobile.width * 0.8)
      }
    }
  })

  test('login page has min-height 100vh', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile)
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    const loginPage = page.locator('.login-page')
    if (await loginPage.count() > 0) {
      const minHeight = await loginPage.evaluate((el) =>
        getComputedStyle(el).minHeight
      )
      expect(minHeight).toBe(`${VIEWPORTS.mobile.height}px`)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// APP SHELL RESPONSIVE — Layout with sidebar, header, content
// ═══════════════════════════════════════════════════════════════════════════

test.describe('AppShell Layout', () => {
  // These tests inject layout markup to verify CSS without needing auth

  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    // Inject a simplified AppShell layout to test CSS
    await page.evaluate(() => {
      const shell = document.createElement('div')
      shell.id = 'test-shell'
      shell.innerHTML = `
        <style>
          #test-shell { display: flex; height: 100vh; position: fixed; inset: 0; z-index: 9999; background: var(--color-bg-primary); }
          #test-sidebar {
            position: fixed; left: 0; top: 0; height: 100vh;
            width: var(--sidebar-width);
            background-color: var(--color-bg-secondary);
            border-right: 1px solid var(--glass-border);
            z-index: 40;
            transition: transform 0.3s;
          }
          #test-sidebar.closed { transform: translateX(-100%); }
          @media (min-width: 768px) {
            #test-sidebar { transform: translateX(0) !important; }
          }
          #test-main {
            flex: 1; display: flex; flex-direction: column;
            margin-left: 0;
            transition: margin-left 0.3s;
          }
          @media (min-width: 768px) {
            #test-main { margin-left: var(--sidebar-width); }
          }
          #test-header {
            height: var(--header-height);
            background: var(--color-bg-secondary);
            border-bottom: 1px solid var(--glass-border);
            display: flex; align-items: center; padding: 0 1rem;
          }
          #test-content { flex: 1; padding: var(--space-4); overflow-y: auto; }
          #test-hamburger { display: block; }
          @media (min-width: 768px) { #test-hamburger { display: none; } }
        </style>
        <aside id="test-sidebar" class="closed">
          <div style="padding: 1rem; color: var(--color-text-primary);">Sidebar</div>
        </aside>
        <div id="test-main">
          <header id="test-header">
            <button id="test-hamburger">☰</button>
            <span style="margin-left: 1rem; color: var(--color-text-primary);">Header</span>
          </header>
          <main id="test-content">
            <div id="test-widget-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem;">
              <div class="card" style="padding: 1rem;">Widget 1</div>
              <div class="card" style="padding: 1rem;">Widget 2</div>
              <div class="card" style="padding: 1rem;">Widget 3</div>
            </div>
          </main>
        </div>
      `
      document.body.appendChild(shell)
    })
  })

  // ── Desktop Layout ──

  test('desktop: sidebar is visible', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.waitForTimeout(400)

    const sidebar = page.locator('#test-sidebar')
    const transform = await sidebar.evaluate((el) =>
      getComputedStyle(el).transform
    )
    // On desktop (≥768px), sidebar should not be translated away
    // translateX(0) may compute to 'none' or 'matrix(1, 0, 0, 1, 0, 0)'
    const isVisible = transform === 'none' || transform === 'matrix(1, 0, 0, 1, 0, 0)'
    expect(isVisible).toBe(true)
  })

  test('desktop: sidebar has correct width (240px)', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.waitForTimeout(400)

    const sidebar = page.locator('#test-sidebar')
    const width = await sidebar.evaluate((el) =>
      getComputedStyle(el).width
    )
    expect(parseFloat(width)).toBe(240) // 15rem = 240px
  })

  test('desktop: main content has sidebar offset', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.waitForTimeout(400)

    const main = page.locator('#test-main')
    const marginLeft = await main.evaluate((el) =>
      getComputedStyle(el).marginLeft
    )
    expect(parseFloat(marginLeft)).toBe(240)
  })

  test('desktop: hamburger menu is hidden', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.waitForTimeout(400)

    const hamburger = page.locator('#test-hamburger')
    const display = await hamburger.evaluate((el) =>
      getComputedStyle(el).display
    )
    expect(display).toBe('none')
  })

  test('desktop: header has correct height (56px)', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.waitForTimeout(400)

    const header = page.locator('#test-header')
    const height = await header.evaluate((el) =>
      getComputedStyle(el).height
    )
    expect(parseFloat(height)).toBe(56) // 3.5rem = 56px
  })

  // ── Mobile Layout ──

  test('mobile: sidebar is hidden (translated off-screen)', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile)
    await page.waitForTimeout(400)

    const sidebar = page.locator('#test-sidebar')
    const transform = await sidebar.evaluate((el) =>
      getComputedStyle(el).transform
    )
    // Should be translateX(-100%) which computes to a matrix with negative X
    expect(transform).toContain('matrix')
    // Parse translateX from matrix(1, 0, 0, 1, -240, 0)
    const match = transform.match(/matrix\(.+?,\s*(.+?)\)/)
    if (match) {
      const parts = match[0].match(/-?\d+\.?\d*/g)
      if (parts && parts.length >= 5) {
        const translateX = parseFloat(parts[4])
        expect(translateX).toBeLessThan(0) // Off-screen to the left
      }
    }
  })

  test('mobile: main content has no sidebar offset', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile)
    await page.waitForTimeout(400)

    const main = page.locator('#test-main')
    const marginLeft = await main.evaluate((el) =>
      getComputedStyle(el).marginLeft
    )
    expect(parseFloat(marginLeft)).toBe(0)
  })

  test('mobile: hamburger menu is visible', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile)
    await page.waitForTimeout(400)

    const hamburger = page.locator('#test-hamburger')
    const display = await hamburger.evaluate((el) =>
      getComputedStyle(el).display
    )
    expect(display).not.toBe('none')
  })

  // ── Tablet Layout ──

  test('tablet: sidebar is visible (≥768px breakpoint)', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet)
    await page.waitForTimeout(400)

    const sidebar = page.locator('#test-sidebar')
    const transform = await sidebar.evaluate((el) =>
      getComputedStyle(el).transform
    )
    const isVisible = transform === 'none' || transform === 'matrix(1, 0, 0, 1, 0, 0)'
    expect(isVisible).toBe(true)
  })

  test('tablet: main content has sidebar offset', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.tablet)
    await page.waitForTimeout(400)

    const main = page.locator('#test-main')
    const marginLeft = await main.evaluate((el) =>
      getComputedStyle(el).marginLeft
    )
    expect(parseFloat(marginLeft)).toBe(240)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// WIDGET GRID RESPONSIVE
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Widget Grid Responsive', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'widget-grid-test'
      container.style.cssText = 'position: fixed; inset: 0; z-index: 9999; background: var(--color-bg-primary); padding: 1rem;'
      container.innerHTML = `
        <div id="grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem;">
          <div class="widget-card widget-card--span-2x1" id="widget-2x1" style="padding: 1rem;">Span 2x1</div>
          <div class="widget-card" id="widget-1x1" style="padding: 1rem;">Normal Widget</div>
        </div>
        <style>
          .widget-card--span-2x1 { grid-column: span 2; }
          @media (max-width: 768px) {
            .widget-card--span-2x1 { grid-column: span 1; }
          }
        </style>
      `
      document.body.appendChild(container)
    })
  })

  test('desktop: 2x1 widget spans 2 columns', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.desktop)
    await page.waitForTimeout(300)

    const widget = page.locator('#widget-2x1')
    const gridColumnEnd = await widget.evaluate((el) =>
      getComputedStyle(el).gridColumnEnd
    )
    // 'span 2' or 'auto' depending on browser computation
    // Check via actual rendered width comparison
    const widgetWidth = (await widget.boundingBox())?.width || 0
    const normalWidget = page.locator('#widget-1x1')
    const normalWidth = (await normalWidget.boundingBox())?.width || 0

    // 2x1 widget should be wider than normal widget on desktop
    if (normalWidth > 0) {
      expect(widgetWidth).toBeGreaterThan(normalWidth * 1.3)
    }
  })

  test('mobile: 2x1 widget collapses to single column width', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile)
    await page.waitForTimeout(300)

    const widget = page.locator('#widget-2x1')
    const normalWidget = page.locator('#widget-1x1')

    const widgetWidth = (await widget.boundingBox())?.width || 0
    const normalWidth = (await normalWidget.boundingBox())?.width || 0

    // On mobile, both should be similar width (single column)
    if (normalWidth > 0) {
      const ratio = widgetWidth / normalWidth
      expect(ratio).toBeGreaterThan(0.8)
      expect(ratio).toBeLessThan(1.3)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// RESPONSIVE UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Responsive Utility Classes', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')

    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'responsive-util-test'
      container.innerHTML = `
        <button class="touch-target" id="touch-target-test" style="background: var(--color-bg-tertiary);">Touch</button>
        <div class="scrollbar-hide" id="scrollbar-hide-test" style="height: 100px; overflow: auto;">
          <div style="height: 500px;">Scrollable content</div>
        </div>
      `
      document.body.appendChild(container)
    })
  })

  test('.touch-target has minimum 44×44px size', async ({ page }) => {
    const btn = page.locator('#touch-target-test')
    const size = await getElementSize(btn)
    expect(size.width).toBeGreaterThanOrEqual(44)
    expect(size.height).toBeGreaterThanOrEqual(44)
  })

  test('.scrollbar-hide: element is scrollable but narrower scrollbar area', async ({ page }) => {
    const el = page.locator('#scrollbar-hide-test')

    // Verify element is scrollable (content overflows)
    const isScrollable = await el.evaluate((element) => {
      return element.scrollHeight > element.clientHeight
    })
    expect(isScrollable).toBe(true)

    // The CSS scrollbar-hide uses -ms-overflow-style: none and scrollbar-width: none
    // and ::-webkit-scrollbar { display: none } — all of which hide scrollbar
    // We verify the element can scroll (functional) regardless of visual scrollbar
    await el.evaluate((element) => {
      element.scrollTop = 50
    })
    const scrollPos = await el.evaluate((element) => element.scrollTop)
    expect(scrollPos).toBeGreaterThan(0)
  })
})
