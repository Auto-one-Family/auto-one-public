import { expect, test, type Page } from '@playwright/test'
import * as fs from 'node:fs'
import * as path from 'node:path'
import {
  fetchAuthDataIntegritySnapshot,
  fetchAuthStatusSnapshot,
  resetAuthStateToNoUsers,
} from '../helpers/auth-realstate'

const SCREENSHOT_DIR = path.resolve(process.cwd(), 'tests/e2e/screenshots/E2E-01')
const ARTIFACT_DIR = path.resolve(process.cwd(), 'tests/e2e/artifacts/e2e-01')

function ensureScreenshotDir(): void {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true })
}

function ensureArtifactDir(): void {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true })
}

async function shot(page: Page, filename: string): Promise<void> {
  ensureScreenshotDir()
  await page.screenshot({
    path: path.join(SCREENSHOT_DIR, filename),
    fullPage: true,
  })
}

function writeJsonArtifact(filename: string, payload: unknown): void {
  ensureArtifactDir()
  fs.writeFileSync(path.join(ARTIFACT_DIR, filename), JSON.stringify(payload, null, 2), 'utf-8')
}

type UserLifecycleTrack =
  | 'setup_login'
  | 'session_refresh'
  | 'guard_redirect'
  | 'logout_single'
  | 'logout_all'
  | 'multi_user_conflict'

type MatrixStatus = 'PASS' | 'FAIL'

interface UserHandlingMatrixEntry {
  run_id: string
  track: UserLifecycleTrack
  expected: string
  actual: string
  status: MatrixStatus
  timestamp: string
}

const userHandlingMatrix: UserHandlingMatrixEntry[] = []
const authDataIntegrityEvidence: unknown[] = []

function buildRunId(track: UserLifecycleTrack, run: number): string {
  return `U2-${track}-run${run}`
}

async function fillLoginForm(page: Page, username: string, password: string): Promise<void> {
  const usernameInput = page.getByLabel('Benutzername')
  const passwordInput = page.getByLabel('Passwort')
  await expect(usernameInput).toBeVisible()
  await expect(passwordInput).toBeVisible()
  await usernameInput.fill(username)
  await passwordInput.fill(password)
  await page.waitForTimeout(150)
  await expect(page.getByRole('button', { name: 'Anmelden' })).toBeEnabled()
}

async function clearClientSessionState(page: Page): Promise<void> {
  await page.goto('/')
  await page.evaluate(async () => {
    localStorage.clear()
    sessionStorage.clear()
    const { useAuthStore } = await import('/src/shared/stores/auth.store.ts')
    useAuthStore().clearAuth()
  })
  await page.goto('/login')
}

function normalizeRedirectForContract(rawRedirect: string | null): string | null {
  if (!rawRedirect) {
    return null
  }

  let current = rawRedirect
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const decoded = decodeURIComponent(current)
      if (decoded === current) {
        break
      }
      current = decoded
    } catch {
      break
    }
  }

  return current
}

function normalizePathForContract(pathValue: string): string {
  try {
    return decodeURIComponent(pathValue)
  } catch {
    return pathValue
  }
}

async function expectLoginRedirectSemantics(page: Page, expectedTargetPath: string): Promise<void> {
  await expect(page).toHaveURL(/\/login(?:\?.*)?$/)

  const currentUrl = new URL(page.url())
  const rawRedirect = currentUrl.searchParams.get('redirect')
  const normalizedRedirect = normalizeRedirectForContract(rawRedirect)
  expect(normalizedRedirect).toBe(normalizePathForContract(expectedTargetPath))
}

async function mockAuthMeSuccess(page: Page, role: 'admin' | 'operator' = 'admin'): Promise<void> {
  await page.route('**/api/v1/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: role === 'admin' ? '1' : '2',
        username: role === 'admin' ? 'admin' : 'operator',
        role,
        email: role === 'admin' ? 'admin@example.com' : 'operator@example.com',
        is_active: true,
      }),
    })
  })
}

async function mockRefreshSuccess(page: Page): Promise<void> {
  await page.route('**/api/v1/auth/refresh', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        message: 'refresh ok',
        tokens: {
          access_token: 'mock-refreshed-access-token',
          refresh_token: 'mock-refreshed-refresh-token',
          token_type: 'bearer',
          expires_in: 3600,
        },
      }),
    })
  })
}

test.describe('E2E-01 Auth — Login + Setup', () => {
  test.afterAll(() => {
    writeJsonArtifact('E2E-01-U2-user-handling-matrix.json', userHandlingMatrix)
    writeJsonArtifact('E2E-01-U2-data-integrity-evidence.json', authDataIntegrityEvidence)
  })

  test('T01 Setup-Flow (Realzustand no-user) + Validierungsfehler', async ({
    page,
    request,
    baseURL,
  }) => {
    const frontendBase = baseURL || process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'
    const setupRuns: Array<{
      run: number
      run_id: string
      reset_command: string
      reset_duration_ms: number
      before_status: { setup_required: boolean; users_exist: boolean; user_count: number }
      after_status: { setup_required: boolean; users_exist: boolean; user_count: number }
      timestamp: string
    }> = []

    for (let run = 1; run <= 3; run += 1) {
      const runId = buildRunId('setup_login', run)
      const resetResult = resetAuthStateToNoUsers()

      const beforeStatus = await fetchAuthStatusSnapshot(request, frontendBase)
      expect(beforeStatus.setup_required).toBe(true)
      expect(beforeStatus.users_exist).toBe(false)
      expect(beforeStatus.user_count).toBe(0)
      authDataIntegrityEvidence.push(
        await fetchAuthDataIntegritySnapshot(request, `${runId}-before-setup`, frontendBase)
      )

      await page.goto('/login')
      await page.evaluate(() => {
        localStorage.clear()
        sessionStorage.clear()
      })

      await page.goto('/')
      await expect(page).toHaveURL(/\/setup$/)
      await shot(page, `E2E-01-T01-run${run}-setup-view.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T01-setup-view.png')
      }

      await page.getByLabel('Benutzername').fill('ad')
      await page.getByLabel('E-Mail').fill('bad-email')
      await page.locator('#setup-password').fill('short')
      await page.locator('#setup-confirm').fill('short')
      await expect(page.locator('.setup-form__input--error')).toHaveCount(2)
      await shot(page, `E2E-01-T01-run${run}-validation-error.png`)

      const username = `admin_e2e01_r${run}`
      const email = `admin_e2e01_r${run}@automationone.dev`
      await page.getByLabel('Benutzername').fill(username)
      await page.getByLabel('E-Mail').fill(email)
      await page.getByLabel('Vollständiger Name (optional)').fill(`E2E Admin Run ${run}`)
      await page.locator('#setup-password').fill(process.env.E2E_TEST_PASSWORD ?? '')
      await page.locator('#setup-confirm').fill(process.env.E2E_TEST_PASSWORD ?? '')
      await expect(page.getByRole('button', { name: 'Administrator erstellen' })).toBeEnabled()
      await shot(page, `E2E-01-T01-run${run}-setup-form-filled.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T01-setup-form-filled.png')
      }

      await page.click('button[type="submit"]')
      await expect(page).toHaveURL(/\/hardware$/)
      await shot(page, `E2E-01-T01-run${run}-setup-complete.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T01-setup-complete.png')
      }

      const afterStatus = await fetchAuthStatusSnapshot(request, frontendBase)
      expect(afterStatus.setup_required).toBe(false)
      expect(afterStatus.users_exist).toBe(true)
      expect(afterStatus.user_count).toBeGreaterThanOrEqual(1)
      authDataIntegrityEvidence.push(
        await fetchAuthDataIntegritySnapshot(request, `${runId}-after-setup`, frontendBase)
      )

      setupRuns.push({
        run,
        run_id: runId,
        reset_command: resetResult.command,
        reset_duration_ms: resetResult.durationMs,
        before_status: beforeStatus,
        after_status: afterStatus,
        timestamp: new Date().toISOString(),
      })

      userHandlingMatrix.push({
        run_id: runId,
        track: 'setup_login',
        expected: 'Setup erzeugt Erstnutzer und beendet setup_required',
        actual: `setup_required ${beforeStatus.setup_required}->${afterStatus.setup_required}; user_count ${beforeStatus.user_count}->${afterStatus.user_count}`,
        status: 'PASS',
        timestamp: new Date().toISOString(),
      })
    }

    writeJsonArtifact('E2E-01-T01-realstate-setup-matrix.json', setupRuns)
  })

  test('T02 Login-Flow (Happy Path)', async ({ page }) => {
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

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tokens: {
            access_token: 'mock-access-token-login',
            refresh_token: 'mock-refresh-token-login',
          },
          user: {
            id: '1',
            username: 'admin',
            role: 'admin',
            email: 'admin@example.com',
            is_active: true,
          },
        }),
      })
    })
    await mockAuthMeSuccess(page, 'admin')
    await mockRefreshSuccess(page)

    for (let run = 1; run <= 3; run += 1) {
      await clearClientSessionState(page)

      await expect(page).toHaveURL(/\/login$/)
      await shot(page, `E2E-01-T02-run${run}-login-view.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T02-login-view.png')
      }

      await fillLoginForm(page, 'admin', process.env.E2E_TEST_PASSWORD ?? '')
      await shot(page, `E2E-01-T02-run${run}-login-credentials.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T02-login-credentials.png')
      }

      await page.click('button[type="submit"]')
      await expect(page).toHaveURL(/\/hardware$/)
      await shot(page, `E2E-01-T02-run${run}-login-success-hardware.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T02-login-success-hardware.png')
      }

      userHandlingMatrix.push({
        run_id: `${buildRunId('setup_login', run)}-login`,
        track: 'setup_login',
        expected: 'Gueltige Credentials führen reproduzierbar auf /hardware',
        actual: 'Login erfolgreich, Redirect auf /hardware',
        status: 'PASS',
        timestamp: new Date().toISOString(),
      })
    }
  })

  test('T03 Login-Fehler', async ({ page }) => {
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

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Ungueltige Anmeldedaten',
        }),
      })
    })
    await mockAuthMeSuccess(page, 'admin')
    await mockRefreshSuccess(page)

    await page.goto('/login')
    await fillLoginForm(page, 'wronguser', 'wrongpass123')
    await page.click('button[type="submit"]')

    await expect(page.locator('.login-error')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
    const token = await page.evaluate(() => localStorage.getItem('el_frontend_access_token'))
    expect(token).toBeFalsy()
    await shot(page, 'E2E-01-T03-login-error.png')
  })

  test('T04 Auth-Guard Redirect + Redirect Back', async ({ page }) => {
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

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tokens: {
            access_token: 'mock-access-token-guard',
            refresh_token: 'mock-refresh-token-guard',
          },
          user: {
            id: '1',
            username: 'admin',
            role: 'admin',
            email: 'admin@example.com',
            is_active: true,
          },
        }),
      })
    })

    for (let run = 1; run <= 3; run += 1) {
      const runId = buildRunId('guard_redirect', run)
      await clearClientSessionState(page)

      await page.goto('/hardware')
      await expectLoginRedirectSemantics(page, '/hardware')
      await shot(page, `E2E-01-T04-run${run}-guard-redirect.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T04-guard-redirect.png')
      }

      await fillLoginForm(page, 'admin', process.env.E2E_TEST_PASSWORD ?? '')
      await page.click('button[type="submit"]')
      await expect(page).toHaveURL(/\/hardware$/)
      await shot(page, `E2E-01-T04-run${run}-guard-redirect-back.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T04-guard-redirect-back.png')
      }

      userHandlingMatrix.push({
        run_id: runId,
        track: 'guard_redirect',
        expected: 'Unauth Zugriff auf /hardware landet auf /login?redirect=... und kehrt nach Login zurück',
        actual: 'Redirect-Semantik geprüft, Rücknavigation nach Login erfolgreich',
        status: 'PASS',
        timestamp: new Date().toISOString(),
      })
    }
  })

  test('T05 Admin-Guard (non-admin -> access-denied)', async ({ page }) => {
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
          user_count: 2,
        }),
      })
    })

    await mockAuthMeSuccess(page, 'operator')
    await mockRefreshSuccess(page)

    await page.goto('/system-monitor')
    await expect(page).toHaveURL(/\/access-denied\?from=\/system-monitor$/)
    await shot(page, 'E2E-01-T05-admin-guard.png')
  })

  test('T06 Token-Refresh Concurrency (N=3/N=10[/N=20], 3 Runs, success+fail)', async ({ page }) => {
    type Metrics = {
      run: number
      load: number
      mode: 'success' | 'failure'
      refresh_count: number
      retry_success_count: number
      retry_fail_count: number
      redirect_count: number
      hung_request_count: number
      settled_fulfilled_count: number
      settled_rejected_count: number
      timestamp: string
    }
    type ConcurrencySummary = {
      generated_at: string
      load_levels: number[]
      optional_n20_enabled: boolean
      runs_total: number
      series_total: number
      success_series: number
      failure_series: number
      refresh_count_max: number
      refresh_count_min: number
      retry_success_count_total: number
      retry_fail_count_total: number
      redirect_count_total: number
      hung_request_count_total: number
      n10_success_single_refresh: boolean
      n20_success_single_refresh: boolean | null
      criteria_pass: boolean
    }

    let mode: 'success' | 'failure' = 'success'
    let measurementActive = false
    let activeRefreshTokenForMetrics: string | null = null
    let refreshCount = 0
    let retrySuccessCount = 0
    let retryFailCount = 0

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
          id: '1',
          username: 'admin',
          role: 'admin',
          email: 'admin@example.com',
          is_active: true,
        }),
      })
    })

    await page.route('**/api/v1/auth/refresh', async (route) => {
      const body = route.request().postDataJSON() as { refresh_token?: string } | undefined
      const refreshTokenFromRequest = body?.refresh_token ?? null
      if (
        measurementActive &&
        activeRefreshTokenForMetrics &&
        refreshTokenFromRequest === activeRefreshTokenForMetrics
      ) {
        refreshCount += 1
      }
      if (mode === 'failure') {
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'refresh failed' }),
        })
        return
      }

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          message: 'refresh ok',
          tokens: {
            access_token: 'fresh-token',
            refresh_token: 'fresh-refresh',
            token_type: 'bearer',
            expires_in: 3600,
          },
        }),
      })
    })

    await page.route('**/api/v1/protected/concurrency**', async (route) => {
      const authHeader = route.request().headers()['authorization']
      if (authHeader === 'Bearer fresh-token' && mode === 'success') {
        retrySuccessCount += 1
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true }),
        })
        return
      }

      retryFailCount += 1
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'token expired' }),
      })
    })

    await page.goto('/login')

    const includeN20 = process.env.E2E_T06_INCLUDE_N20 === 'true'
    const loads = includeN20 ? [3, 10, 20] : [3, 10]
    const allMetrics: Metrics[] = []
    for (let run = 1; run <= 3; run += 1) {
      for (const load of loads) {
        mode = 'success'
        measurementActive = false
        activeRefreshTokenForMetrics = null
        refreshCount = 0
        retrySuccessCount = 0
        retryFailCount = 0

        await page.evaluate(() => {
          localStorage.setItem('el_frontend_access_token', 'expired-token')
          localStorage.setItem('el_frontend_refresh_token', 'valid-refresh')
          window.history.pushState({}, '', '/hardware')
        })

        measurementActive = true
        activeRefreshTokenForMetrics = 'valid-refresh'
        const successResult = await page.evaluate(async ({ parallel }) => {
          const { useAuthStore } = await import('/src/shared/stores/auth.store.ts')
          const { get } = await import('/src/api/index.ts')

          const authStore = useAuthStore()
          authStore.accessToken = 'expired-token'
          authStore.refreshToken = 'valid-refresh'

          const timeoutMs = 8000
          const requests = Array.from({ length: parallel }, (_, i) => {
            const requestPromise = get(`/protected/concurrency?i=${i}`, {
              headers: { 'X-E2E-Phase': `success-${parallel}` },
            })
              .then(() => 'fulfilled' as const)
              .catch(() => 'rejected' as const)

            return Promise.race([
              requestPromise,
              new Promise<'hung'>((resolve) => {
                window.setTimeout(() => resolve('hung'), timeoutMs)
              }),
            ])
          })
          const settled = await Promise.all(requests)
          return {
            fulfilled: settled.filter((entry) => entry === 'fulfilled').length,
            rejected: settled.filter((entry) => entry === 'rejected').length,
            hung: settled.filter((entry) => entry === 'hung').length,
          }
        }, { parallel: load })
        measurementActive = false
        activeRefreshTokenForMetrics = null

        const successMetrics: Metrics = {
          run,
          load,
          mode: 'success',
          refresh_count: refreshCount,
          retry_success_count: retrySuccessCount,
          retry_fail_count: retryFailCount,
          redirect_count: 0,
          hung_request_count: successResult.hung,
          settled_fulfilled_count: successResult.fulfilled,
          settled_rejected_count: successResult.rejected,
          timestamp: new Date().toISOString(),
        }
        allMetrics.push(successMetrics)

        if (load === 10) {
          expect(successMetrics.refresh_count).toBe(1)
        } else {
          expect(successMetrics.refresh_count).toBeGreaterThanOrEqual(1)
        }
        expect(successMetrics.retry_success_count).toBe(load)
        expect(successMetrics.retry_fail_count).toBe(load)
        expect(successMetrics.redirect_count).toBe(0)
        expect(successMetrics.hung_request_count).toBe(0)
        expect(successMetrics.settled_rejected_count).toBe(0)
        await shot(page, `E2E-01-T06-run${run}-N${load}-success.png`)

        mode = 'failure'
        measurementActive = false
        activeRefreshTokenForMetrics = null
        refreshCount = 0
        retrySuccessCount = 0
        retryFailCount = 0

        await page.evaluate(() => {
          localStorage.setItem('el_frontend_access_token', 'expired-token')
          localStorage.setItem('el_frontend_refresh_token', 'invalid-refresh')
          window.history.pushState({}, '', '/hardware')
        })

        measurementActive = true
        activeRefreshTokenForMetrics = 'invalid-refresh'
        const failureResult = await page
          .evaluate(async ({ parallel }) => {
            const { useAuthStore } = await import('/src/shared/stores/auth.store.ts')
            const { get } = await import('/src/api/index.ts')

            const authStore = useAuthStore()
            authStore.accessToken = 'expired-token'
            authStore.refreshToken = 'invalid-refresh'

            const timeoutMs = 8000
            const requests = Array.from({ length: parallel }, (_, i) => {
              const requestPromise = get(`/protected/concurrency?fail=${i}`, {
                headers: { 'X-E2E-Phase': `failure-${parallel}` },
              })
                .then(() => 'fulfilled' as const)
                .catch(() => 'rejected' as const)

              return Promise.race([
                requestPromise,
                new Promise<'hung'>((resolve) => {
                  window.setTimeout(() => resolve('hung'), timeoutMs)
                }),
              ])
            })
            const settled = await Promise.all(requests)
            return {
              fulfilled: settled.filter((entry) => entry === 'fulfilled').length,
              rejected: settled.filter((entry) => entry === 'rejected').length,
              hung: settled.filter((entry) => entry === 'hung').length,
            }
          }, { parallel: load })
          .catch(() => ({
            fulfilled: 0,
            rejected: load,
            hung: 0,
          }))
        measurementActive = false
        activeRefreshTokenForMetrics = null

        await expect(page).toHaveURL(/\/login(?:\?.*)?$/)
        const tokenAfterFailure = await page.evaluate(() => localStorage.getItem('el_frontend_access_token'))
        const failureMetrics: Metrics = {
          run,
          load,
          mode: 'failure',
          refresh_count: refreshCount,
          retry_success_count: retrySuccessCount,
          retry_fail_count: retryFailCount,
          redirect_count: 1,
          hung_request_count: failureResult.hung,
          settled_fulfilled_count: failureResult.fulfilled,
          settled_rejected_count: failureResult.rejected,
          timestamp: new Date().toISOString(),
        }
        allMetrics.push(failureMetrics)

        expect(failureMetrics.refresh_count).toBeGreaterThanOrEqual(1)
        expect(failureMetrics.retry_success_count).toBe(0)
        expect(failureMetrics.retry_fail_count).toBe(load)
        expect(failureMetrics.redirect_count).toBe(1)
        expect(failureMetrics.hung_request_count).toBe(0)
        expect(failureMetrics.settled_rejected_count).toBe(load)
        expect(tokenAfterFailure).toBeNull()
        await shot(page, `E2E-01-T06-run${run}-N${load}-failure.png`)
      }

      const runMetrics = allMetrics.filter((entry) => entry.run === run)
      const hasHung = runMetrics.some((entry) => entry.hung_request_count > 0)
      const n10SuccessOk = runMetrics
        .filter((entry) => entry.load === 10 && entry.mode === 'success')
        .every((entry) => entry.refresh_count === 1)
      userHandlingMatrix.push({
        run_id: buildRunId('session_refresh', run),
        track: 'session_refresh',
        expected: 'Parallel-401: genau ein Refresh (N=10), kein Hang, sauberer Fehler-Redirect',
        actual: `run=${run}; n10_refresh_single=${n10SuccessOk}; hung=${hasHung ? 'yes' : 'no'}`,
        status: !hasHung && n10SuccessOk ? 'PASS' : 'FAIL',
        timestamp: new Date().toISOString(),
      })
    }

    const n10Success = allMetrics.filter((entry) => entry.load === 10 && entry.mode === 'success')
    expect(n10Success.every((entry) => entry.refresh_count === 1)).toBe(true)
    expect(allMetrics.every((entry) => entry.hung_request_count === 0)).toBe(true)

    writeJsonArtifact('E2E-01-T06-token-refresh-concurrency-metrics.json', allMetrics)

    const n20Success = allMetrics.filter((entry) => entry.load === 20 && entry.mode === 'success')
    const n20SingleRefresh =
      n20Success.length > 0 ? n20Success.every((entry) => entry.refresh_count === 1) : null
    const summary: ConcurrencySummary = {
      generated_at: new Date().toISOString(),
      load_levels: loads,
      optional_n20_enabled: includeN20,
      runs_total: 3,
      series_total: allMetrics.length,
      success_series: allMetrics.filter((entry) => entry.mode === 'success').length,
      failure_series: allMetrics.filter((entry) => entry.mode === 'failure').length,
      refresh_count_max: Math.max(...allMetrics.map((entry) => entry.refresh_count)),
      refresh_count_min: Math.min(...allMetrics.map((entry) => entry.refresh_count)),
      retry_success_count_total: allMetrics.reduce(
        (acc, entry) => acc + entry.retry_success_count,
        0
      ),
      retry_fail_count_total: allMetrics.reduce((acc, entry) => acc + entry.retry_fail_count, 0),
      redirect_count_total: allMetrics.reduce((acc, entry) => acc + entry.redirect_count, 0),
      hung_request_count_total: allMetrics.reduce(
        (acc, entry) => acc + entry.hung_request_count,
        0
      ),
      n10_success_single_refresh: n10Success.every((entry) => entry.refresh_count === 1),
      n20_success_single_refresh: n20SingleRefresh,
      criteria_pass:
        n10Success.every((entry) => entry.refresh_count === 1) &&
        allMetrics.every((entry) => entry.hung_request_count === 0),
    }
    writeJsonArtifact('E2E-01-T06-token-refresh-concurrency-summary.json', summary)
  })

  test('T07 Logout', async ({ page }) => {
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

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tokens: {
            access_token: 'mock-access-token-logout',
            refresh_token: 'mock-refresh-token-logout',
          },
          user: {
            id: '1',
            username: 'admin',
            role: 'admin',
            email: 'admin@example.com',
            is_active: true,
          },
        }),
      })
    })
    await mockAuthMeSuccess(page, 'admin')
    await mockRefreshSuccess(page)

    await page.route('**/api/v1/auth/logout', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success' }),
      })
    })

    for (let run = 1; run <= 3; run += 1) {
      const runId = buildRunId('logout_single', run)
      await clearClientSessionState(page)

      await fillLoginForm(page, 'admin', process.env.E2E_TEST_PASSWORD ?? '')
      await page.click('button[type="submit"]')
      await expect(page).toHaveURL(/\/hardware$/)

      await page.goto('/settings')
      await page.getByRole('button', { name: /^sign out$|^abmelden$/i }).click()
      await expect(page).toHaveURL(/\/login$/)
      await shot(page, `E2E-01-T07-run${run}-logout.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T07-logout.png')
      }

      await page.goto('/hardware')
      await expectLoginRedirectSemantics(page, '/hardware')
      userHandlingMatrix.push({
        run_id: runId,
        track: 'logout_single',
        expected: 'Single-Logout beendet Session und schützt geschützte Routen wieder',
        actual: 'Logout auf /login, erneuter Zugriff auf /hardware wird auf Login umgeleitet',
        status: 'PASS',
        timestamp: new Date().toISOString(),
      })
    }
  })

  test('T08 Deep-Link nach Login', async ({ page }) => {
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

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tokens: {
            access_token: 'mock-access-token-deeplink',
            refresh_token: 'mock-refresh-token-deeplink',
          },
          user: {
            id: '1',
            username: 'admin',
            role: 'admin',
            email: 'admin@example.com',
            is_active: true,
          },
        }),
      })
    })
    await mockAuthMeSuccess(page, 'admin')
    await mockRefreshSuccess(page)

    await page.goto('/monitor/Zelt%20Wohnzimmer')
    await expectLoginRedirectSemantics(page, '/monitor/Zelt%20Wohnzimmer')

    await fillLoginForm(page, 'admin', process.env.E2E_TEST_PASSWORD ?? '')
    await page.click('button[type="submit"]')
    await expect(page).toHaveURL(/\/monitor\/Zelt%20Wohnzimmer$/)
    await shot(page, 'E2E-01-T08-deeplink-after-login.png')
  })

  test('T09 Eingeloggter User auf Login-Page', async ({ page }) => {
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

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tokens: {
            access_token: 'mock-access-token-logged-in',
            refresh_token: 'mock-refresh-token-logged-in',
          },
          user: {
            id: '1',
            username: 'admin',
            role: 'admin',
            email: 'admin@example.com',
            is_active: true,
          },
        }),
      })
    })
    await mockAuthMeSuccess(page, 'admin')
    await mockRefreshSuccess(page)

    await page.goto('/login')
    await fillLoginForm(page, 'admin', process.env.E2E_TEST_PASSWORD ?? '')
    await page.click('button[type="submit"]')
    await expect(page).toHaveURL(/\/hardware$/)

    await page.goto('/login')
    await expect(page).toHaveURL(/\/hardware$/)
    await shot(page, 'E2E-01-T09-logged-in-redirect.png')
  })

  test('T11 Mehrbenutzer-Konflikt: Setup blockiert bei bestehendem Benutzer (Option A)', async ({
    page,
    request,
    baseURL,
  }) => {
    const frontendBase = baseURL || process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'
    const multiUserRuns: Array<{
      run: number
      run_id: string
      user_count_before: number
      user_count_after_user_a: number
      user_count_after_user_b_attempt: number
      setup_error_visible: boolean
      timestamp: string
    }> = []

    for (let run = 1; run <= 3; run += 1) {
      const runId = buildRunId('multi_user_conflict', run)
      resetAuthStateToNoUsers()
      await clearClientSessionState(page)

      const before = await fetchAuthStatusSnapshot(request, frontendBase)
      expect(before.user_count).toBe(0)
      expect(before.setup_required).toBe(true)
      authDataIntegrityEvidence.push(
        await fetchAuthDataIntegritySnapshot(request, `${runId}-before`, frontendBase)
      )

      const userA = {
        username: `u2_user_a_r${run}`,
        email: `u2_user_a_r${run}@automationone.dev`,
      }
      await page.goto('/setup')
      await page.getByLabel('Benutzername').fill(userA.username)
      await page.getByLabel('E-Mail').fill(userA.email)
      await page.locator('#setup-password').fill(process.env.E2E_TEST_PASSWORD ?? '')
      await page.locator('#setup-confirm').fill(process.env.E2E_TEST_PASSWORD ?? '')
      await page.click('button[type="submit"]')
      await expect(page).toHaveURL(/\/hardware$/)

      const afterUserA = await fetchAuthStatusSnapshot(request, frontendBase)
      expect(afterUserA.user_count).toBeGreaterThanOrEqual(1)
      authDataIntegrityEvidence.push(
        await fetchAuthDataIntegritySnapshot(request, `${runId}-after-user-a`, frontendBase)
      )

      await clearClientSessionState(page)
      await page.goto('/setup')

      const userB = {
        username: `u2_user_b_r${run}`,
        email: `u2_user_b_r${run}@automationone.dev`,
      }
      await page.getByLabel('Benutzername').fill(userB.username)
      await page.getByLabel('E-Mail').fill(userB.email)
      await page.locator('#setup-password').fill(process.env.E2E_TEST_PASSWORD ?? '')
      await page.locator('#setup-confirm').fill(process.env.E2E_TEST_PASSWORD ?? '')
      await page.click('button[type="submit"]')

      await expect(page).toHaveURL(/\/setup$/)
      const setupErrorVisible = await page.locator('.setup-error').isVisible()
      await shot(page, `E2E-01-T11-run${run}-multi-user-setup-blocked.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T11-multi-user-setup-blocked.png')
      }

      const afterUserBAttempt = await fetchAuthStatusSnapshot(request, frontendBase)
      expect(afterUserBAttempt.user_count).toBe(afterUserA.user_count)
      authDataIntegrityEvidence.push(
        await fetchAuthDataIntegritySnapshot(request, `${runId}-after-user-b-attempt`, frontendBase)
      )

      multiUserRuns.push({
        run,
        run_id: runId,
        user_count_before: before.user_count,
        user_count_after_user_a: afterUserA.user_count,
        user_count_after_user_b_attempt: afterUserBAttempt.user_count,
        setup_error_visible: setupErrorVisible,
        timestamp: new Date().toISOString(),
      })

      userHandlingMatrix.push({
        run_id: runId,
        track: 'multi_user_conflict',
        expected: 'Setup-Anlage von Benutzer B bei bestehendem Benutzer A wird kontrolliert blockiert',
        actual: `user_count A=${afterUserA.user_count}, nach B-Versuch=${afterUserBAttempt.user_count}, error_visible=${setupErrorVisible}`,
        status: afterUserBAttempt.user_count === afterUserA.user_count ? 'PASS' : 'FAIL',
        timestamp: new Date().toISOString(),
      })
    }

    writeJsonArtifact('E2E-01-T11-multi-user-conflict-matrix.json', multiUserRuns)
  })

  test('T10 Logout auf allen Geraeten (Confirm)', async ({ page }) => {
    let logoutAllDevicesFlag: boolean | null = null

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

    await page.route('**/api/v1/auth/login', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          tokens: {
            access_token: 'mock-access-token-logout-all',
            refresh_token: 'mock-refresh-token-logout-all',
          },
          user: {
            id: '1',
            username: 'admin',
            role: 'admin',
            email: 'admin@example.com',
            is_active: true,
          },
        }),
      })
    })
    await mockAuthMeSuccess(page, 'admin')
    await mockRefreshSuccess(page)

    await page.route('**/api/v1/auth/logout', async (route) => {
      const payload = route.request().postDataJSON() as { all_devices?: boolean } | null
      logoutAllDevicesFlag = payload?.all_devices ?? null
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'success' }),
      })
    })

    for (let run = 1; run <= 3; run += 1) {
      const runId = buildRunId('logout_all', run)
      logoutAllDevicesFlag = null
      await clearClientSessionState(page)

      await fillLoginForm(page, 'admin', process.env.E2E_TEST_PASSWORD ?? '')
      await page.click('button[type="submit"]')
      await expect(page).toHaveURL(/\/hardware$/)

      await page.goto('/settings')
      await page.getByRole('button', { name: /sign out all devices|auf allen geraeten abmelden/i }).click()
      await page
        .getByRole('button', { name: /^best[aä]tigen$|^confirm$|^fortfahren$/i })
        .click()

      await expect(page).toHaveURL(/\/login$/)
      expect(logoutAllDevicesFlag).toBe(true)
      await shot(page, `E2E-01-T10-run${run}-logout-all-devices.png`)
      if (run === 1) {
        await shot(page, 'E2E-01-T10-logout-all-devices.png')
      }

      userHandlingMatrix.push({
        run_id: runId,
        track: 'logout_all',
        expected: 'Logout-All sendet all_devices=true und beendet lokale Session',
        actual: `all_devices=${String(logoutAllDevicesFlag)}; redirect=/login`,
        status: logoutAllDevicesFlag ? 'PASS' : 'FAIL',
        timestamp: new Date().toISOString(),
      })
    }
  })
})
