import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../mocks/server'

type Metrics = {
  refresh_count: number
  retry_success_count: number
  retry_fail_count: number
  redirect_count: number
}

const mockState = vi.hoisted(() => {
  return {
    authStore: {
      accessToken: 'expired-access-token' as string | null,
      refreshToken: 'valid-refresh-token' as string | null,
      refreshTokens: vi.fn<() => Promise<void>>(),
      clearAuth: vi.fn(),
    },
  }
})

vi.mock('@/shared/stores/auth.store', () => ({
  useAuthStore: () => mockState.authStore,
}))

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    delay(ms).then(() => {
      throw new Error(`Timeout nach ${ms}ms (potenzieller Deadlock)`)
    }),
  ])
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

describe('API Token-Refresh Concurrency', () => {
  beforeEach(() => {
    vi.resetModules()
    mockState.authStore.accessToken = 'expired-access-token'
    mockState.authStore.refreshToken = 'valid-refresh-token'
    mockState.authStore.refreshTokens.mockReset()
    mockState.authStore.clearAuth.mockReset()
    window.history.replaceState({}, '', '/hardware')
  })

  it('Erfolgspfad: genau ein Refresh bei N=3/10/20 und alle Retries erfolgreich', async () => {
    const results: Array<{ load: number; metrics: Metrics }> = []
    const { get } = await import('@/api/index')

    for (const load of [3, 10, 20]) {
      const metrics: Metrics = {
        refresh_count: 0,
        retry_success_count: 0,
        retry_fail_count: 0,
        redirect_count: 0,
      }

      mockState.authStore.accessToken = 'expired-access-token'
      mockState.authStore.refreshToken = 'valid-refresh-token'
      mockState.authStore.clearAuth.mockReset()
      mockState.authStore.refreshTokens.mockImplementation(async () => {
        metrics.refresh_count += 1
        await delay(25)
        mockState.authStore.accessToken = 'fresh-access-token'
        mockState.authStore.refreshToken = 'fresh-refresh-token'
      })

      server.use(
        http.get('/api/v1/protected/concurrency', ({ request }) => {
          const auth = request.headers.get('authorization')
          if (auth === 'Bearer fresh-access-token') {
            metrics.retry_success_count += 1
            return HttpResponse.json({ ok: true }, { status: 200 })
          }
          metrics.retry_fail_count += 1
          return HttpResponse.json({ detail: 'token expired' }, { status: 401 })
        })
      )

      const parallelRequests = Array.from({ length: load }, (_, i) =>
        get<{ ok: boolean }>(`/protected/concurrency?i=${i}`)
      )

      const settled = await withTimeout(Promise.allSettled(parallelRequests), 4000)
      const fulfilled = settled.filter((entry) => entry.status === 'fulfilled')
      const rejected = settled.filter((entry) => entry.status === 'rejected')

      expect(rejected).toHaveLength(0)
      expect(fulfilled).toHaveLength(load)
      expect(metrics.refresh_count).toBe(1)
      expect(metrics.retry_success_count).toBe(load)
      expect(metrics.retry_fail_count).toBe(load)
      expect(mockState.authStore.clearAuth).not.toHaveBeenCalled()

      results.push({ load, metrics })
    }

    expect(results.find((r) => r.load === 10)?.metrics.refresh_count).toBe(1)
  })

  it('Fehlerpfad: N=10 verworfen, Session-Clear + Redirect deterministisch', async () => {
    const metrics: Metrics = {
      refresh_count: 0,
      retry_success_count: 0,
      retry_fail_count: 0,
      redirect_count: 0,
    }

    const { get } = await import('@/api/index')

    mockState.authStore.accessToken = 'expired-access-token'
    mockState.authStore.refreshToken = 'invalid-refresh-token'
    mockState.authStore.refreshTokens.mockImplementation(async () => {
      metrics.refresh_count += 1
      await delay(20)
      throw new Error('refresh failed')
    })
    mockState.authStore.clearAuth.mockImplementation(() => {
      mockState.authStore.accessToken = null
      mockState.authStore.refreshToken = null
    })

    server.use(
      http.get('/api/v1/protected/concurrency', () => {
        metrics.retry_fail_count += 1
        return HttpResponse.json({ detail: 'unauthorized' }, { status: 401 })
      })
    )

    const parallelRequests = Array.from({ length: 10 }, (_, i) =>
      get(`/protected/concurrency?i=${i}`)
    )
    const settled = await withTimeout(Promise.allSettled(parallelRequests), 4000)

    const fulfilled = settled.filter((entry) => entry.status === 'fulfilled')
    const rejected = settled.filter((entry) => entry.status === 'rejected')

    expect(fulfilled).toHaveLength(0)
    expect(rejected).toHaveLength(10)
    expect(metrics.refresh_count).toBe(1)
    expect(metrics.retry_fail_count).toBe(10)
    expect(mockState.authStore.clearAuth).toHaveBeenCalledTimes(1)

    if (window.location.pathname === '/login') {
      metrics.redirect_count = 1
    }
    expect(metrics.redirect_count).toBe(1)
  })
})
