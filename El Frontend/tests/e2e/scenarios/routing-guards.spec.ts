import { test, expect } from '@playwright/test'

test.describe('Routing und Guards', () => {
  test('leitet unbekannte Route auf not-found', async ({ page }) => {
    await page.goto('/route-die-es-nicht-gibt')
    await expect(page).toHaveURL(/\/not-found(\?.*)?$/)
    await expect(page.getByText('Route nicht gefunden')).toBeVisible()
  })
})

test.describe('Routing und Guards ohne bestehende Session', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('leitet setup-required bei protected Route auf /setup', async ({ page }) => {
    await page.route('**/api/v1/auth/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          setup_required: true,
          user_count: 0,
        }),
      })
    })

    await page.goto('/hardware')

    await expect(page).toHaveURL(/\/setup$/)
  })

  test('leitet non-admin bei Admin-Route auf /access-denied', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('el_frontend_access_token', 'fake-token')
      localStorage.setItem('el_frontend_refresh_token', 'fake-refresh')
    })

    await page.route('**/api/v1/auth/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          setup_required: false,
          user_count: 1,
        }),
      })
    })

    await page.route('**/api/v1/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'op-1',
          username: 'operator',
          email: 'operator@example.com',
          role: 'operator',
          is_active: true,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        }),
      })
    })

    await page.goto('/system-monitor')

    await expect(page).toHaveURL(/\/access-denied(?:\?.*)?$/)
    const currentUrl = new URL(page.url())
    expect(currentUrl.pathname).toBe('/access-denied')
    expect(currentUrl.searchParams.get('from')).toBe('/system-monitor')
    await expect(page.getByText('Zugriff verweigert')).toBeVisible()
  })
})
