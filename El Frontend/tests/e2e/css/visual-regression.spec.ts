/**
 * Visual Regression Tests — Schicht 5
 *
 * Captures baseline screenshots of critical pages and components.
 * On subsequent runs, compares against baselines to detect unintended visual changes.
 *
 * First run: `npx playwright test tests/e2e/css/visual-regression.spec.ts --update-snapshots`
 * Subsequent runs: `npx playwright test tests/e2e/css/visual-regression.spec.ts`
 *
 * Screenshots are stored in: tests/e2e/__screenshots__/{projectName}/...
 *
 * Configuration:
 * - animations: disabled (stable screenshots)
 * - maxDiffPixelRatio: 0.01 (1% tolerance for font rendering)
 * - mask: applied to dynamic content (timestamps, counts)
 */

import { test, expect } from '@playwright/test'

// ═══════════════════════════════════════════════════════════════════════════
// LOGIN PAGE — Public, always available
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Visual Regression — Login Page', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('login page full screenshot', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    // Wait for fonts to load
    await page.waitForTimeout(1000)

    await expect(page).toHaveScreenshot('login-page-full.png', {
      fullPage: true,
      animations: 'disabled',
    })
  })

  test('login card screenshot', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    const card = page.locator('.login-card, .glass-panel').first()
    if (await card.count() > 0) {
      await expect(card).toHaveScreenshot('login-card.png', {
        animations: 'disabled',
      })
    }
  })

  test('login form fields screenshot', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    const form = page.locator('.login-form, form').first()
    if (await form.count() > 0) {
      await expect(form).toHaveScreenshot('login-form.png', {
        animations: 'disabled',
      })
    }
  })

  test('login header/logo screenshot', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    const header = page.locator('.login-header').first()
    if (await header.count() > 0) {
      await expect(header).toHaveScreenshot('login-header.png', {
        animations: 'disabled',
      })
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// AUTHENTICATED PAGES — Requires running backend
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Visual Regression — Authenticated Pages', () => {
  test.beforeEach(async ({ page }) => {
    try {
      await page.goto('/')
      await page.waitForLoadState('domcontentloaded')
      if (page.url().includes('/login')) {
        test.skip()
      }
    } catch {
      test.skip()
    }
  })

  test('dashboard full screenshot', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)

    await expect(page).toHaveScreenshot('dashboard-full.png', {
      fullPage: true,
      animations: 'disabled',
      // Mask dynamic counters and timestamps
      mask: [
        page.locator('.status-pill__count'),
        page.locator('time, [data-timestamp]'),
      ],
    })
  })

  test('sidebar screenshot', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    const sidebar = page.locator('.sidebar, aside').first()
    if (await sidebar.count() > 0) {
      await expect(sidebar).toHaveScreenshot('sidebar.png', {
        animations: 'disabled',
      })
    }
  })

  test('sensors view screenshot', async ({ page }) => {
    await page.goto('/sensors')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)

    await expect(page).toHaveScreenshot('sensors-view.png', {
      fullPage: true,
      animations: 'disabled',
      mask: [
        page.locator('.status-pill__count'),
        page.locator('time, [data-timestamp]'),
      ],
    })
  })

  test('logic view screenshot', async ({ page }) => {
    await page.goto('/logic')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1500)

    await expect(page).toHaveScreenshot('logic-view.png', {
      fullPage: true,
      animations: 'disabled',
    })
  })

  test('settings view screenshot', async ({ page }) => {
    await page.goto('/settings')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(1000)

    await expect(page).toHaveScreenshot('settings-view.png', {
      fullPage: true,
      animations: 'disabled',
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// COMPONENT SNAPSHOTS — Isolated via injected elements
// ═══════════════════════════════════════════════════════════════════════════

test.describe('Visual Regression — Component Snapshots', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test.beforeEach(async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('domcontentloaded')
    await page.waitForTimeout(500)
  })

  test('button variants screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'button-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:flex;flex-direction:column;gap:16px;align-items:flex-start;'
      container.innerHTML = `
        <button class="btn btn-primary">Primary Button</button>
        <button class="btn btn-secondary">Secondary Button</button>
        <button class="btn btn-danger">Danger Button</button>
        <button class="btn btn-success">Success Button</button>
        <button class="btn btn-ghost">Ghost Button</button>
        <button class="btn btn-primary btn-sm">Small Primary</button>
        <button class="btn btn-primary btn-lg">Large Primary</button>
        <button class="btn btn-primary" disabled>Disabled Primary</button>
      `
      document.body.appendChild(container)
    })

    await expect(page.locator('#button-snapshot')).toHaveScreenshot('button-variants.png', {
      animations: 'disabled',
    })
  })

  test('badge variants screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'badge-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start;'
      container.innerHTML = `
        <span class="badge badge-success">Online</span>
        <span class="badge badge-warning">Warning</span>
        <span class="badge badge-danger">Error</span>
        <span class="badge badge-info">Info</span>
        <span class="badge badge-gray">Offline</span>
        <span class="badge badge-mock">Mock ESP</span>
        <span class="badge badge-real">Real ESP</span>
      `
      document.body.appendChild(container)
    })

    await expect(page.locator('#badge-snapshot')).toHaveScreenshot('badge-variants.png', {
      animations: 'disabled',
    })
  })

  test('status dots screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'status-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:flex;gap:24px;align-items:center;'
      container.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;">
          <div class="status-dot status-online"></div><span style="color:var(--color-text-secondary);">Online</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div class="status-dot status-offline"></div><span style="color:var(--color-text-secondary);">Offline</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div class="status-dot status-error"></div><span style="color:var(--color-text-secondary);">Error</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px;">
          <div class="status-dot status-warning"></div><span style="color:var(--color-text-secondary);">Warning</span>
        </div>
      `
      document.body.appendChild(container)
    })

    await expect(page.locator('#status-snapshot')).toHaveScreenshot('status-dots.png', {
      animations: 'disabled',
    })
  })

  test('card variants screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'card-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:grid;grid-template-columns:1fr 1fr;gap:16px;'
      container.innerHTML = `
        <div class="card">
          <div class="card-header" style="color:var(--color-text-primary);">Standard Card</div>
          <div class="card-body" style="color:var(--color-text-secondary);">Card body content</div>
          <div class="card-footer" style="color:var(--color-text-muted);">Footer</div>
        </div>
        <div class="card-glass" style="padding:16px;">
          <div style="color:var(--color-text-primary);">Glass Card</div>
          <div style="color:var(--color-text-secondary);margin-top:8px;">With backdrop blur</div>
        </div>
      `
      document.body.appendChild(container)
    })

    await expect(page.locator('#card-snapshot')).toHaveScreenshot('card-variants.png', {
      animations: 'disabled',
    })
  })

  test('skeleton loading states screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'skeleton-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:flex;flex-direction:column;gap:16px;'
      container.innerHTML = `
        <div class="skeleton skeleton-text" style="width:300px;"></div>
        <div class="skeleton skeleton-text-sm" style="width:200px;"></div>
        <div class="skeleton skeleton-card" style="width:400px;"></div>
        <div class="skeleton skeleton-circle" style="width:48px;height:48px;"></div>
      `
      document.body.appendChild(container)
    })

    // Use higher tolerance for animated skeletons
    await expect(page.locator('#skeleton-snapshot')).toHaveScreenshot('skeleton-states.png', {
      animations: 'disabled',
      maxDiffPixelRatio: 0.02,
    })
  })

  test('empty and error states screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'states-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:flex;flex-direction:column;gap:24px;'
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon" style="font-size:24px;">📦</div>
          <div class="empty-state-title">Keine Daten vorhanden</div>
          <div class="empty-state-description">Verbinden Sie Ihre ersten Geräte, um Daten anzuzeigen.</div>
          <button class="btn btn-primary btn-sm">Gerät hinzufügen</button>
        </div>
        <div class="error-state">
          <span class="error-state-icon" style="font-size:20px;">⚠️</span>
          <span class="error-state-message">Verbindung zum Server fehlgeschlagen. Bitte versuchen Sie es erneut.</span>
        </div>
      `
      document.body.appendChild(container)
    })

    await expect(page.locator('#states-snapshot')).toHaveScreenshot('empty-error-states.png', {
      animations: 'disabled',
    })
  })

  test('form elements screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'form-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:flex;flex-direction:column;gap:16px;max-width:400px;'
      container.innerHTML = `
        <div>
          <label class="label">Gerätename</label>
          <input class="input" placeholder="z.B. Greenhouse ESP32" value="Greenhouse-A1" />
        </div>
        <div>
          <label class="label">Beschreibung</label>
          <input class="input" placeholder="Optional..." />
        </div>
        <div>
          <label class="label">Fehlerhaftes Feld</label>
          <input class="input input-error" value="Ungültiger Wert" />
        </div>
        <div>
          <label class="label">Deaktiviertes Feld</label>
          <input class="input" disabled value="Gesperrt" />
        </div>
      `
      document.body.appendChild(container)
    })

    await expect(page.locator('#form-snapshot')).toHaveScreenshot('form-elements.png', {
      animations: 'disabled',
    })
  })

  test('typography scale screenshot', async ({ page }) => {
    await page.evaluate(() => {
      const container = document.createElement('div')
      container.id = 'typo-snapshot'
      container.style.cssText = 'position:fixed;inset:0;z-index:99999;background:var(--color-bg-primary);padding:40px;display:flex;flex-direction:column;gap:8px;'
      container.innerHTML = `
        <span style="font-size:var(--text-display);color:var(--color-text-primary);font-weight:700;">Display (2rem)</span>
        <span style="font-size:var(--text-2xl);color:var(--color-text-primary);font-weight:600;">2XL (1.5rem)</span>
        <span style="font-size:var(--text-xl);color:var(--color-text-primary);font-weight:600;">XL (1.25rem)</span>
        <span style="font-size:var(--text-lg);color:var(--color-text-primary);font-weight:500;">LG (1rem)</span>
        <span style="font-size:var(--text-base);color:var(--color-text-secondary);">Base (0.875rem) — Body text</span>
        <span style="font-size:var(--text-sm);color:var(--color-text-secondary);">SM (0.75rem) — Labels</span>
        <span style="font-size:var(--text-xs);color:var(--color-text-muted);">XS (0.6875rem) — Micro labels</span>
        <span style="font-family:var(--font-mono);font-size:var(--text-sm);color:var(--color-text-secondary);">Mono — JetBrains Mono</span>
      `
      document.body.appendChild(container)
    })

    await expect(page.locator('#typo-snapshot')).toHaveScreenshot('typography-scale.png', {
      animations: 'disabled',
    })
  })
})
