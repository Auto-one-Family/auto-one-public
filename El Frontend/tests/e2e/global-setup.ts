/**
 * Playwright Global Setup
 *
 * Authenticates once before all tests and saves the auth state.
 * All tests then reuse this state via storageState config.
 *
 * Auth flow:
 * 1. Check if auth state already exists and is valid
 * 2. If not, perform login via API
 * 3. Save tokens to localStorage format for Playwright
 *
 * Token Keys (from auth.ts):
 * - el_frontend_access_token
 * - el_frontend_refresh_token
 */

import { chromium, FullConfig } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'

// ES module: __dirname equivalent
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Storage state file path
const AUTH_STATE_PATH = path.join(__dirname, '../../.playwright/auth-state.json')

// E2E test credentials (should match test user in database)
// Server conftest.py uses: admin/[E2E_TEST_PASSWORD] or via setup endpoint
const E2E_CREDENTIALS = {
  username: process.env.E2E_TEST_USER || 'admin',
  password: process.env.E2E_TEST_PASSWORD || '',
}

// Token keys (must match auth.ts)
const TOKEN_KEY = 'el_frontend_access_token'
const REFRESH_TOKEN_KEY = 'el_frontend_refresh_token'

interface AuthTokens {
  access_token: string
  refresh_token: string
}

interface AuthResponse {
  tokens: AuthTokens
  user: {
    id: string
    username: string
    role: string
  }
}

/**
 * Perform API login and get tokens
 */
async function performLogin(baseURL: string): Promise<AuthTokens> {
  const loginUrl = `${baseURL.replace('5173', '8000')}/api/v1/auth/login`

  console.log(`[Global Setup] Logging in at ${loginUrl}`)

  const response = await fetch(loginUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(E2E_CREDENTIALS),
  })

  if (!response.ok) {
    // Try setup endpoint if login fails (fresh database, no users yet)
    if (response.status === 401 || response.status === 404 || response.status === 500) {
      console.log(`[Global Setup] Login failed (${response.status}), trying setup endpoint...`)
      return performSetup(baseURL)
    }

    const error = await response.text()
    throw new Error(`Login failed: ${response.status} - ${error}`)
  }

  const data: AuthResponse = await response.json()
  console.log(`[Global Setup] Logged in as ${data.user.username} (${data.user.role})`)

  return data.tokens
}

/**
 * Perform initial setup if no users exist
 */
async function performSetup(baseURL: string): Promise<AuthTokens> {
  const setupUrl = `${baseURL.replace('5173', '8000')}/api/v1/auth/setup`

  console.log(`[Global Setup] Creating initial admin at ${setupUrl}`)

  const response = await fetch(setupUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      username: E2E_CREDENTIALS.username,
      email: process.env.E2E_TEST_EMAIL || 'admin@example.com',
      password: E2E_CREDENTIALS.password,
      full_name: 'E2E Test Admin',
    }),
  })

  if (!response.ok) {
    const error = await response.text()
    throw new Error(`Setup failed: ${response.status} - ${error}`)
  }

  const data: AuthResponse = await response.json()
  console.log(`[Global Setup] Created admin user: ${data.user.username}`)

  return data.tokens
}

/**
 * Global setup function
 */
async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0].use.baseURL || 'http://localhost:5173'

  console.log('[Global Setup] Starting E2E authentication setup')

  const tokens = await performLogin(baseURL)

  // Create browser to save storage state
  const browser = await chromium.launch()
  const context = await browser.newContext()
  const page = await context.newPage()

  // Navigate to the app to set localStorage
  await page.goto(baseURL)

  // Set tokens in localStorage
  await page.evaluate(
    ({ accessToken, refreshToken, tokenKey, refreshTokenKey }) => {
      localStorage.setItem(tokenKey, accessToken)
      localStorage.setItem(refreshTokenKey, refreshToken)
    },
    {
      accessToken: tokens.access_token,
      refreshToken: tokens.refresh_token,
      tokenKey: TOKEN_KEY,
      refreshTokenKey: REFRESH_TOKEN_KEY,
    }
  )

  // Ensure .playwright directory exists
  const dir = path.dirname(AUTH_STATE_PATH)
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }

  // Save storage state
  await context.storageState({ path: AUTH_STATE_PATH })

  console.log(`[Global Setup] Auth state saved to ${AUTH_STATE_PATH}`)

  await browser.close()
}

export default globalSetup
