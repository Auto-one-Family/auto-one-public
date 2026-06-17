/**
 * API Helper for Playwright E2E Tests
 *
 * Provides authenticated API calls via Playwright request API (Node context).
 * Uses localStorage token from the app (set by global-setup).
 *
 * Pattern: Global setup logs in → token in storageState → tests reuse auth.
 * API calls use standalone request fixture (not page.request) to avoid
 * "Target page/context/browser closed" when test times out.
 *
 * VORAUSSETZUNG: Backend muss unter localhost:8000 erreichbar sein.
 * Run: docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --wait
 */

import type { APIRequestContext, Page } from '@playwright/test'

const TOKEN_KEY = 'el_frontend_access_token'
const REFRESH_TOKEN_KEY = 'el_frontend_refresh_token'

/** API base URL - backend port (E2E: 8000). Matches global-setup login. */
function getApiBase(pageUrl: string): string {
  if (process.env.PLAYWRIGHT_API_BASE) {
    try {
      return new URL(process.env.PLAYWRIGHT_API_BASE).origin
    } catch {
      return process.env.PLAYWRIGHT_API_BASE.replace(/\/api\/v1\/?$/i, '')
    }
  }

  try {
    const resolved = new URL(pageUrl)
    if (resolved.protocol.startsWith('http')) {
      resolved.port = '8000'
      return resolved.origin
    }
  } catch {
    // Fallback below
  }

  return 'http://localhost:8000'
}

interface LoginResponse {
  tokens: {
    access_token: string
    refresh_token: string
  }
}

async function getAuthToken(
  page: Page,
  request: APIRequestContext,
  apiBase: string
): Promise<string> {
  const localStorageToken = await page
    .evaluate((key: string) => localStorage.getItem(key), TOKEN_KEY)
    .catch(() => null)

  if (localStorageToken) {
    return localStorageToken
  }

  const username = process.env.E2E_TEST_USER || 'admin'
  const password = process.env.E2E_TEST_PASSWORD || ''
  const response = await request.post(`${apiBase}/api/v1/auth/login`, {
    headers: { 'Content-Type': 'application/json' },
    data: { username, password },
    timeout: 15000,
  })

  let authResponse = response
  if (!authResponse.ok()) {
    const setupResponse = await request.post(`${apiBase}/api/v1/auth/setup`, {
      headers: { 'Content-Type': 'application/json' },
      data: {
        username,
        email: process.env.E2E_TEST_EMAIL || 'admin@example.com',
        password,
        full_name: 'E2E Test Admin',
      },
      timeout: 15000,
    })

    authResponse = setupResponse
  }

  if (!authResponse.ok()) {
    const errorText = await authResponse.text()
    throw new Error(`API login/setup failed at ${apiBase}: ${authResponse.status()} - ${errorText}`)
  }

  const payload = await authResponse.json() as LoginResponse

  await page.evaluate(
    ({
      tokenKey,
      refreshTokenKey,
      accessToken,
      refreshToken,
    }: {
      tokenKey: string
      refreshTokenKey: string
      accessToken: string
      refreshToken: string
    }) => {
      localStorage.setItem(tokenKey, accessToken)
      localStorage.setItem(refreshTokenKey, refreshToken)
    },
    {
      tokenKey: TOKEN_KEY,
      refreshTokenKey: REFRESH_TOKEN_KEY,
      accessToken: payload.tokens.access_token,
      refreshToken: payload.tokens.refresh_token,
    }
  ).catch(() => {})

  return payload.tokens.access_token
}

export interface CreateMockEspOptions {
  espId: string
  sensors?: Array<{
    gpio: number
    sensor_type: string
    name?: string
    raw_value?: number
  }>
  actuators?: Array<{
    gpio: number
    actuator_type: string
    name?: string
  }>
  zone_id?: string
  zone_name?: string
  auto_heartbeat?: boolean
}

/**
 * Create a Mock ESP via debug API.
 * Requires: page must have navigated to the app (token in localStorage).
 *
 * Uses standalone request fixture (not page.request) to avoid "Target page/context
 * closed" when test times out - the API call is independent of browser lifecycle.
 *
 * Backend must be reachable at localhost:8000. If not, fail fast (15s timeout).
 */
export async function createMockEspWithSensors(
  page: Page,
  request: APIRequestContext,
  options: CreateMockEspOptions
): Promise<{ esp_id: string; success: boolean }> {
  if (!options || typeof options !== 'object' || !options.espId) {
    throw new Error('createMockEspWithSensors: options must be { espId: string, sensors?: [], actuators?: [] }')
  }

  const backendBase = getApiBase(page.url())
  const apiBase = `${backendBase}/api/v1`

  const token = await getAuthToken(page, request, backendBase)

  const sensors = (options.sensors || []).map((s) => ({
    gpio: s.gpio,
    sensor_type: s.sensor_type,
    name: s.name ?? `GPIO ${s.gpio}`,
    raw_value: s.raw_value ?? 0,
  }))

  const actuators = (options.actuators || []).map((a) => ({
    gpio: a.gpio,
    actuator_type: a.actuator_type,
    name: a.name ?? `GPIO ${a.gpio}`,
  }))

  const payload = {
    esp_id: options.espId,
    zone_id: options.zone_id,
    zone_name: options.zone_name,
    sensors,
    actuators,
    auto_heartbeat: options.auto_heartbeat ?? false,
    heartbeat_interval_seconds: 60,
  }

  try {
    const response = await request.post(`${apiBase}/debug/mock-esp`, {
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      data: payload,
      timeout: 15000, // Fail fast if backend unreachable (avoid 30s test timeout race)
    })

    if (!response.ok()) {
      const text = await response.text()
      throw new Error(`createMockEsp failed: ${response.status()} - ${text}`)
    }

    const data = (await response.json()) as { esp_id: string }
    return { esp_id: data.esp_id, success: true }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err)
    if (msg.includes('ECONNREFUSED') || msg.includes('Timeout') || msg.includes('ENOTFOUND')) {
      throw new Error(
        `Backend not reachable at ${apiBase.replace('/api/v1', '')}. ` +
          'Run: docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --wait'
      )
    }
    throw err
  }
}

/**
 * Delete a Mock ESP via debug API.
 * Use in afterEach/afterAll for cleanup.
 */
export async function deleteMockEsp(
  page: Page,
  request: APIRequestContext,
  espId: string
): Promise<void> {
  const backendBase = getApiBase(page.url())
  const apiBase = `${backendBase}/api/v1`

  const token = await getAuthToken(page, request, backendBase).catch(() => null)
  if (!token) return

  await request.delete(`${apiBase}/debug/mock-esp/${espId}`, {
    headers: { Authorization: `Bearer ${token}` },
    timeout: 5000,
  })
}
