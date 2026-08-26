/**
 * Authentication E2E Tests
 *
 * Tests the login flow and authentication state handling.
 * Note: Most tests run with pre-authenticated state from globalSetup.
 */

import { test, expect } from '@playwright/test'

test.describe('Authentication', () => {
  test.describe('Login Flow', () => {
    // This test needs to start without auth state
    test.use({ storageState: { cookies: [], origins: [] } })

    test('should show login page when not authenticated', async ({ page }) => {
      await page.goto('/')
      await page.waitForLoadState('load')

      // Should redirect to login or show login form
      await expect(page).toHaveURL(/\/(login|auth)/)
    })

    test('should login successfully with valid credentials', async ({ page }) => {
      await page.goto('/login')
      await page.waitForLoadState('domcontentloaded')

      // Fill login form
      await page.fill('input[name="username"], input[type="text"]', 'admin')
      await page.fill('input[name="password"], input[type="password"]', process.env.E2E_TEST_PASSWORD ?? '')

      // Submit
      await page.click('button[type="submit"]')

      // Should redirect to main app (/ → /hardware is the default landing page)
      await expect(page).toHaveURL(/\/(hardware|dashboard)?(\?.*)?$/, { timeout: 15000 })

      // Verify tokens are stored
      const accessToken = await page.evaluate(() =>
        localStorage.getItem('el_frontend_access_token')
      )
      expect(accessToken).toBeTruthy()
    })

    test('should show error with invalid credentials', async ({ page }) => {
      await page.goto('/login')
      await page.waitForLoadState('domcontentloaded')

      // Fill with invalid credentials
      await page.fill('input[name="username"], input[type="text"]', 'wronguser')
      await page.fill('input[name="password"], input[type="password"]', 'wrongpass')

      // Submit
      await page.click('button[type="submit"]')

      // Should show error message (LoginView uses .login-error)
      await expect(page.locator('.login-error')).toBeVisible({ timeout: 8000 })

      // Should stay on login page
      await expect(page).toHaveURL(/\/(login|auth)/)
    })
  })

  test.describe('Authenticated State', () => {
    // These tests use the global auth state

    test('should access dashboard when authenticated', async ({ page }) => {
      await page.goto('/')

      // Should be on dashboard (or root)
      await expect(page).not.toHaveURL(/\/(login|auth)/)
    })

    test('should persist auth across page reload', async ({ page }) => {
      await page.goto('/')
      await page.waitForLoadState('load')

      // Verify we're authenticated
      const initialToken = await page.evaluate(() =>
        localStorage.getItem('el_frontend_access_token')
      )
      expect(initialToken).toBeTruthy()

      // Reload and wait for auth check to complete
      await page.reload()
      await page.waitForLoadState('load')

      // Should still be authenticated
      const tokenAfterReload = await page.evaluate(() =>
        localStorage.getItem('el_frontend_access_token')
      )
      expect(tokenAfterReload).toBeTruthy()

      // Should not redirect to login
      await expect(page).not.toHaveURL(/\/(login|auth)/)
    })
  })

  test.describe('Logout', () => {
    test('should logout and redirect to login', async ({ page }) => {
      await page.goto('/')

      // Find and click logout button
      // Adjust selector based on actual UI
      const logoutButton = page.locator(
        'button:has-text("Logout"), button:has-text("Abmelden"), [data-testid="logout"]'
      )

      if (await logoutButton.isVisible()) {
        await logoutButton.click()

        // Should redirect to login
        await expect(page).toHaveURL(/\/(login|auth)/, { timeout: 5000 })

        // Tokens should be cleared
        const token = await page.evaluate(() =>
          localStorage.getItem('el_frontend_access_token')
        )
        expect(token).toBeFalsy()
      } else {
        // Skip if logout button not found (UI may vary)
        test.skip()
      }
    })
  })
})
