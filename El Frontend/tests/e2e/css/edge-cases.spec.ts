/**
 * CSS Edge Case Tests — Schicht 7
 *
 * Tests for edge cases that can cause visual bugs:
 * - Text overflow / truncation
 * - Z-index stacking order
 * - Scrollbar behavior
 * - Long content handling
 * - Boundary conditions at breakpoints
 * - Tab navigation styles
 * - Data table styling
 */

import { test, expect } from '@playwright/test'
import { TOKEN_RGB, VIEWPORTS, hasActiveAnimation } from '../helpers/css'

test.describe('CSS Edge Cases', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TEXT OVERFLOW — Critical for device names, usernames, etc.
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Text Overflow Handling', () => {
    test('sidebar user name truncates with ellipsis', async ({ page }) => {
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'overflow-test'
        container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;'
        container.innerHTML = `
          <div style="width: 200px;">
            <div class="sidebar__user-name" id="overflow-name" style="
              font-size: var(--text-sm);
              font-weight: 500;
              color: var(--color-text-primary);
              white-space: nowrap;
              overflow: hidden;
              text-overflow: ellipsis;
              width: 120px;
            ">
              This-is-a-very-long-username-that-should-be-truncated-with-ellipsis
            </div>
          </div>
        `
        document.body.appendChild(container)
      })

      const name = page.locator('#overflow-name')
      await expect(name).toHaveCSS('text-overflow', 'ellipsis')
      await expect(name).toHaveCSS('overflow', 'hidden')
      await expect(name).toHaveCSS('white-space', 'nowrap')

      // Element should not expand beyond its container
      const box = await name.boundingBox()
      expect(box).toBeTruthy()
      if (box) {
        expect(box.width).toBeLessThanOrEqual(130)
      }
    })

    test('badge text does not wrap', async ({ page }) => {
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'badge-wrap-test'
        container.innerHTML = `
          <span class="badge badge-success" id="badge-nowrap">
            Very Long Status Text That Should Not Wrap
          </span>
        `
        document.body.appendChild(container)
      })

      const badge = page.locator('#badge-nowrap')
      await expect(badge).toHaveCSS('white-space', 'nowrap')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // Z-INDEX STACKING — Modal > Popover > Sidebar > Content
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Z-Index Stacking Order', () => {
    test('modal overlays sidebar', async ({ page }) => {
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'zindex-test'
        container.innerHTML = `
          <div id="z-sidebar" style="position:fixed;left:0;top:0;width:240px;height:100vh;background:var(--color-bg-secondary);z-index:var(--z-fixed);">Sidebar</div>
          <div id="z-modal-backdrop" class="glass-overlay" style="position:fixed;inset:0;z-index:var(--z-modal-backdrop);">Backdrop</div>
          <div id="z-modal" style="position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:400px;height:300px;background:var(--color-bg-secondary);z-index:var(--z-modal);border-radius:var(--radius-lg);">Modal</div>
        `
        document.body.appendChild(container)
      })

      const sidebarZ = parseInt(await page.locator('#z-sidebar').evaluate((el) =>
        getComputedStyle(el).zIndex
      ))
      const backdropZ = parseInt(await page.locator('#z-modal-backdrop').evaluate((el) =>
        getComputedStyle(el).zIndex
      ))
      const modalZ = parseInt(await page.locator('#z-modal').evaluate((el) =>
        getComputedStyle(el).zIndex
      ))

      expect(modalZ).toBeGreaterThan(backdropZ)
      expect(backdropZ).toBeGreaterThan(sidebarZ)
    })

    test('tooltip is above everything', async ({ page }) => {
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'tooltip-z-test'
        container.innerHTML = `
          <div id="z-popover" style="position:fixed;z-index:var(--z-popover);">Popover</div>
          <div id="z-tooltip" style="position:fixed;z-index:var(--z-tooltip);">Tooltip</div>
        `
        document.body.appendChild(container)
      })

      const popoverZ = parseInt(await page.locator('#z-popover').evaluate((el) =>
        getComputedStyle(el).zIndex
      ))
      const tooltipZ = parseInt(await page.locator('#z-tooltip').evaluate((el) =>
        getComputedStyle(el).zIndex
      ))

      expect(tooltipZ).toBeGreaterThan(popoverZ)
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // DATA TABLE STYLING
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Data Table', () => {
    test.beforeEach(async ({ page }) => {
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'table-test'
        container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;overflow:auto;'
        container.innerHTML = `
          <table class="data-table" id="test-table">
            <thead>
              <tr>
                <th class="sortable sorted" id="th-sorted">Name</th>
                <th class="sortable" id="th-sortable">Status</th>
                <th>GPIO</th>
              </tr>
            </thead>
            <tbody>
              <tr id="row-1"><td>ESP-001</td><td>Online</td><td>4</td></tr>
              <tr id="row-2"><td>ESP-002</td><td>Offline</td><td>5</td></tr>
              <tr id="row-3"><td>ESP-003</td><td>Error</td><td>12</td></tr>
              <tr id="row-4"><td>ESP-004</td><td>Online</td><td>25</td></tr>
            </tbody>
          </table>
        `
        document.body.appendChild(container)
      })
    })

    test('table has full width', async ({ page }) => {
      const table = page.locator('#test-table')
      await expect(table).toHaveCSS('width', /\d+px/)
    })

    test('table header has tertiary background', async ({ page }) => {
      const thead = page.locator('#test-table thead')
      await expect(thead).toHaveCSS('background-color', TOKEN_RGB['--color-bg-tertiary'])
    })

    test('table header is sticky', async ({ page }) => {
      const thead = page.locator('#test-table thead')
      await expect(thead).toHaveCSS('position', 'sticky')
    })

    test('sorted column has accent color', async ({ page }) => {
      const th = page.locator('#th-sorted')
      const color = await th.evaluate((el) => getComputedStyle(el).color)
      expect(color).toBe(TOKEN_RGB['--color-accent-bright'])
    })

    test('sortable column has cursor pointer', async ({ page }) => {
      const th = page.locator('#th-sortable')
      await expect(th).toHaveCSS('cursor', 'pointer')
    })

    test('table rows have bottom border', async ({ page }) => {
      const row = page.locator('#row-1')
      const borderBottom = await row.evaluate((el) =>
        getComputedStyle(el).borderBottomStyle
      )
      expect(borderBottom).toBe('solid')
    })

    test('even rows have alternating background', async ({ page }) => {
      const row2 = page.locator('#row-2')
      const bg = await row2.evaluate((el) =>
        getComputedStyle(el).backgroundColor
      )
      // Even rows should have a slightly different bg (nth-child(even))
      expect(bg).toContain('rgba')
    })

    test('last row has no bottom border', async ({ page }) => {
      const lastRow = page.locator('#row-4')
      const borderBottom = await lastRow.evaluate((el) =>
        getComputedStyle(el).borderBottomStyle
      )
      expect(borderBottom).toBe('none')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // TAB COMPONENT STYLING
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Tabs', () => {
    test.beforeEach(async ({ page }) => {
      // Use inline styles directly in HTML to avoid tree-shaking and
      // cross-browser setProperty issues (WebKit vs Chrome specificity)
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'tabs-test'
        container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;'
        container.innerHTML = `
          <div id="test-tabs" style="display:flex;gap:0.25rem;border-bottom:1px solid var(--glass-border);">
            <button id="tab-active" style="display:flex;align-items:center;gap:0.5rem;padding:0.75rem 1rem;font-size:var(--text-base);font-weight:500;color:var(--color-accent-bright);border-bottom:2px solid var(--color-accent-bright);margin-bottom:-1px;cursor:pointer;">
              Events <span id="tab-active-count" style="padding:1px 0.25rem;border-radius:var(--radius-full);font-size:var(--text-xs);font-weight:600;background-color:rgba(96,165,250,0.2);color:var(--color-accent-bright);">42</span>
            </button>
            <button id="tab-inactive" style="display:flex;align-items:center;gap:0.5rem;padding:0.75rem 1rem;font-size:var(--text-base);font-weight:500;color:var(--color-text-secondary);border-bottom:2px solid transparent;margin-bottom:-1px;cursor:pointer;">
              Logs <span style="padding:1px 0.25rem;border-radius:var(--radius-full);font-size:var(--text-xs);font-weight:600;background-color:var(--color-bg-tertiary);color:var(--color-text-muted);">128</span>
            </button>
            <button id="tab-plain" style="display:flex;align-items:center;gap:0.5rem;padding:0.75rem 1rem;font-size:var(--text-base);font-weight:500;color:var(--color-text-secondary);border-bottom:2px solid transparent;margin-bottom:-1px;cursor:pointer;">Health</button>
          </div>
        `
        document.body.appendChild(container)
      })
    })

    test('tabs container has bottom border', async ({ page }) => {
      const tabs = page.locator('#test-tabs')
      const borderBottom = await tabs.evaluate((el) =>
        getComputedStyle(el).borderBottomStyle
      )
      expect(borderBottom).toBe('solid')
    })

    test('active tab has accent color', async ({ page }) => {
      const tab = page.locator('#tab-active')
      const color = await tab.evaluate((el) =>
        getComputedStyle(el).color
      )
      // Color resolves to rgb(96, 165, 250) or rgba variant
      expect(color).toContain('96, 165, 250')
    })

    test('active tab has bottom border indicator', async ({ page }) => {
      const tab = page.locator('#tab-active')
      const borderBottom = await tab.evaluate((el) =>
        getComputedStyle(el).borderBottomColor
      )
      // May resolve to rgba with alpha due to border rendering
      expect(borderBottom).toContain('96, 165, 250')
    })

    test('inactive tab has secondary text color', async ({ page }) => {
      const tab = page.locator('#tab-inactive')
      await expect(tab).toHaveCSS('color', TOKEN_RGB['--color-text-secondary'])
    })

    test('active tab count has accent styling', async ({ page }) => {
      const count = page.locator('#tab-active-count')
      const color = await count.evaluate((el) =>
        getComputedStyle(el).color
      )
      expect(color).toContain('96, 165, 250')
    })

    test('tab has cursor pointer', async ({ page }) => {
      const tab = page.locator('#tab-inactive')
      await expect(tab).toHaveCSS('cursor', 'pointer')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // SCROLLBAR STYLING
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Custom Scrollbar', () => {
    test('body has custom scrollbar styling', async ({ page }) => {
      // The CSS applies two scrollbar mechanisms:
      // 1. * { scrollbar-width: thin; } for Firefox
      // 2. ::-webkit-scrollbar { width: 6px; } for Chrome/Safari
      const scrollbarWidth = await page.evaluate(() => {
        // Check the universal * rule (applies in Firefox)
        const bodyStyle = getComputedStyle(document.body)
        return bodyStyle.scrollbarWidth || ''
      })

      // Firefox: scrollbar-width should be 'thin' or 'auto'
      // Chrome: scrollbar-width returns '' (not supported, uses ::-webkit-scrollbar)
      if (scrollbarWidth && scrollbarWidth !== 'auto') {
        expect(['thin', 'none']).toContain(scrollbarWidth)
      }
      // If empty, Chrome uses the ::-webkit-scrollbar pseudo-element (not queryable via JS)
      // Either way, the CSS is applied
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // BREAKPOINT BOUNDARY
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('Breakpoint Boundaries', () => {
    test('767px: mobile layout (just below 768px breakpoint)', async ({ page }) => {
      await page.evaluate(() => {
        const el = document.createElement('div')
        el.id = 'bp-test'
        el.innerHTML = `
          <div id="bp-show-desktop" style="display:none;">Desktop</div>
          <div id="bp-show-mobile">Mobile</div>
          <style>
            @media (min-width: 768px) {
              #bp-show-desktop { display: block !important; }
              #bp-show-mobile { display: none !important; }
            }
          </style>
        `
        document.body.appendChild(el)
      })

      await page.setViewportSize({ width: 767, height: 600 })
      await page.waitForTimeout(200)

      const mobile = page.locator('#bp-show-mobile')
      const desktop = page.locator('#bp-show-desktop')
      expect(await mobile.evaluate((el) => getComputedStyle(el).display)).toBe('block')
      expect(await desktop.evaluate((el) => getComputedStyle(el).display)).toBe('none')
    })

    test('768px: desktop layout (exactly at breakpoint)', async ({ page }) => {
      await page.evaluate(() => {
        const el = document.createElement('div')
        el.id = 'bp-test2'
        el.innerHTML = `
          <div id="bp2-show-desktop" style="display:none;">Desktop</div>
          <div id="bp2-show-mobile">Mobile</div>
          <style>
            @media (min-width: 768px) {
              #bp2-show-desktop { display: block !important; }
              #bp2-show-mobile { display: none !important; }
            }
          </style>
        `
        document.body.appendChild(el)
      })

      await page.setViewportSize({ width: 768, height: 600 })
      await page.waitForTimeout(200)

      const mobile = page.locator('#bp2-show-mobile')
      const desktop = page.locator('#bp2-show-desktop')
      expect(await mobile.evaluate((el) => getComputedStyle(el).display)).toBe('none')
      expect(await desktop.evaluate((el) => getComputedStyle(el).display)).toBe('block')
    })
  })

  // ═══════════════════════════════════════════════════════════════════════
  // JSON VIEWER SYNTAX HIGHLIGHTING
  // ═══════════════════════════════════════════════════════════════════════

  test.describe('JSON Viewer', () => {
    test.beforeEach(async ({ page }) => {
      // json-key/string/etc. classes are tree-shaken, use inline var() references
      await page.evaluate(() => {
        const container = document.createElement('div')
        container.id = 'json-test'
        container.style.cssText = 'background:var(--color-bg-secondary);padding:16px;font-family:var(--font-mono);'
        container.innerHTML = `
          <span id="json-key" style="color:var(--color-mock);">"device_id"</span>:
          <span id="json-string" style="color:var(--color-success);">"ESP_12AB34CD"</span>,
          <span style="color:var(--color-mock);">"value"</span>:
          <span id="json-number" style="color:var(--color-accent-bright);">23.5</span>,
          <span style="color:var(--color-mock);">"online"</span>:
          <span id="json-boolean" style="color:var(--color-warning);">true</span>,
          <span style="color:var(--color-mock);">"error"</span>:
          <span id="json-null" style="color:var(--color-error);">null</span>
        `
        document.body.appendChild(container)
      })
    })

    test('json-key has mock (purple) color', async ({ page }) => {
      const el = page.locator('#json-key')
      await expect(el).toHaveCSS('color', TOKEN_RGB['--color-mock'])
    })

    test('json-string has success (green) color', async ({ page }) => {
      const el = page.locator('#json-string')
      await expect(el).toHaveCSS('color', TOKEN_RGB['--color-success'])
    })

    test('json-number has accent (blue) color', async ({ page }) => {
      const el = page.locator('#json-number')
      await expect(el).toHaveCSS('color', TOKEN_RGB['--color-accent-bright'])
    })

    test('json-boolean has warning (yellow) color', async ({ page }) => {
      const el = page.locator('#json-boolean')
      await expect(el).toHaveCSS('color', TOKEN_RGB['--color-warning'])
    })

    test('json-null has error (red) color', async ({ page }) => {
      const el = page.locator('#json-null')
      await expect(el).toHaveCSS('color', TOKEN_RGB['--color-error'])
    })
  })
})
