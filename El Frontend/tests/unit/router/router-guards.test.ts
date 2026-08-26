import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { User } from '@/types'

vi.mock('@/shared/design/layout/AppShell.vue', () => ({
  default: { name: 'AppShellStub', template: '<div><router-view /></div>' },
}))
vi.mock('@/views/LoginView.vue', () => ({
  default: { name: 'LoginViewStub', template: '<div>login</div>' },
}))
vi.mock('@/views/SetupView.vue', () => ({
  default: { name: 'SetupViewStub', template: '<div>setup</div>' },
}))
vi.mock('@/views/HardwareView.vue', () => ({
  default: { name: 'HardwareViewStub', template: '<div>hardware</div>' },
}))
vi.mock('@/views/SystemMonitorView.vue', () => ({
  default: { name: 'SystemMonitorViewStub', template: '<div>system-monitor</div>' },
}))
vi.mock('@/views/AccessDeniedView.vue', () => ({
  default: { name: 'AccessDeniedViewStub', template: '<div>access-denied</div>' },
}))
vi.mock('@/views/NotFoundView.vue', () => ({
  default: { name: 'NotFoundViewStub', template: '<div>not-found</div>' },
}))

import router from '@/router'
import { useAuthStore } from '@/shared/stores/auth.store'

function makeUser(role: User['role']): User {
  return {
    id: 'u-test',
    username: 'test-user',
    email: 'test@example.com',
    full_name: null,
    role,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

async function navigate(path: string): Promise<void> {
  await router.push(path).catch(() => undefined)
  await Promise.resolve()
}

describe('Router Guards', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.restoreAllMocks()
    await navigate('/login')
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('leitet unauthenticated protected routes auf /login mit redirect um', async () => {
    const authStore = useAuthStore()
    authStore.setupRequired = false
    authStore.clearAuth()

    await navigate('/monitor/zone-a')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/monitor/zone-a')
  })

  it('leitet bei setupRequired auf /setup um', async () => {
    const authStore = useAuthStore()
    authStore.setupRequired = true

    await navigate('/hardware')

    expect(router.currentRoute.value.name).toBe('setup')
  })

  it('leitet non-admin bei Admin-Route auf /access-denied um', async () => {
    const authStore = useAuthStore()
    authStore.setupRequired = false
    authStore.accessToken = 'token-operator'
    authStore.user = makeUser('operator')

    await navigate('/system-monitor')

    expect(router.currentRoute.value.name).toBe('access-denied')
    expect(router.currentRoute.value.query.from).toBe('/system-monitor')
  })

  it('leitet authentifizierte User von /login auf /hardware um', async () => {
    const authStore = useAuthStore()
    authStore.setupRequired = false
    authStore.accessToken = 'token-admin'
    authStore.user = makeUser('admin')

    await navigate('/hardware')
    await navigate('/login')

    expect(router.currentRoute.value.name).toBe('hardware')
  })

  it('faengt checkAuthStatus-Fehler ab und nutzt Login-Recovery fuer protected route', async () => {
    const authStore = useAuthStore()
    authStore.setupRequired = null
    authStore.clearAuth()
    vi.spyOn(authStore, 'checkAuthStatus').mockRejectedValueOnce(new Error('auth check failed'))

    await navigate('/hardware')

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/hardware')
  })

  it('schreibt Legacy-Redirect-Telemetrie bei alten Pfaden', async () => {
    const authStore = useAuthStore()
    authStore.setupRequired = false
    authStore.accessToken = 'token-admin'
    authStore.user = makeUser('admin')

    await navigate('/database')

    const raw = localStorage.getItem('router.legacyRedirectTelemetry.v1')
    expect(raw).toBeTruthy()
    const telemetry = JSON.parse(raw as string) as Record<string, { count: number }>
    expect(telemetry['/database']).toBeTruthy()
    expect(telemetry['/database'].count).toBeGreaterThan(0)
  })
})
