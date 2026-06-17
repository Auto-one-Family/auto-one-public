/**
 * Auth Store Unit Tests
 *
 * Tests for authentication state management, login, logout,
 * token handling, and role-based access control.
 */

import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '@/shared/stores/auth.store'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'
import { mockUser, mockTokens } from '../../mocks/handlers'

// =============================================================================
// MSW Server Lifecycle
// =============================================================================
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

// =============================================================================
// MOCK WEBSOCKET SERVICE
// =============================================================================

vi.mock('@/services/websocket', () => ({
  websocketService: {
    disconnect: vi.fn(),
    connect: vi.fn(),
    isConnected: vi.fn(() => false)
  }
}))

// =============================================================================
// INITIAL STATE
// =============================================================================

describe('Auth Store - Initial State', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('has null user on initialization', () => {
    const store = useAuthStore()
    expect(store.user).toBeNull()
  })

  it('has null tokens when localStorage is empty', () => {
    const store = useAuthStore()
    expect(store.accessToken).toBeNull()
    expect(store.refreshToken).toBeNull()
  })

  it('reads tokens from localStorage on initialization', () => {
    localStorage.setItem('el_frontend_access_token', 'stored-access-token')
    localStorage.setItem('el_frontend_refresh_token', 'stored-refresh-token')

    const store = useAuthStore()
    expect(store.accessToken).toBe('stored-access-token')
    expect(store.refreshToken).toBe('stored-refresh-token')
  })

  it('has isLoading false initially', () => {
    const store = useAuthStore()
    expect(store.isLoading).toBe(false)
  })

  it('has setupRequired null initially', () => {
    const store = useAuthStore()
    expect(store.setupRequired).toBeNull()
  })

  it('has no error initially', () => {
    const store = useAuthStore()
    expect(store.error).toBeNull()
  })
})

// =============================================================================
// COMPUTED GETTERS
// =============================================================================

describe('Auth Store - Computed Getters', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  describe('isAuthenticated', () => {
    it('returns false when no token and no user', () => {
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('returns false when token exists but no user', () => {
      localStorage.setItem('el_frontend_access_token', 'some-token')
      const store = useAuthStore()
      expect(store.isAuthenticated).toBe(false)
    })

    it('returns true when both token and user exist', () => {
      localStorage.setItem('el_frontend_access_token', 'some-token')
      const store = useAuthStore()
      store.user = { ...mockUser, id: '1' }
      expect(store.isAuthenticated).toBe(true)
    })
  })

  describe('isAdmin', () => {
    it('returns false when no user', () => {
      const store = useAuthStore()
      expect(store.isAdmin).toBe(false)
    })

    it('returns true for admin role', () => {
      const store = useAuthStore()
      store.user = { ...mockUser, id: '1', role: 'admin' }
      expect(store.isAdmin).toBe(true)
    })

    it('returns false for operator role', () => {
      const store = useAuthStore()
      store.user = { ...mockUser, id: '1', role: 'operator' }
      expect(store.isAdmin).toBe(false)
    })

    it('returns false for viewer role', () => {
      const store = useAuthStore()
      store.user = { ...mockUser, id: '1', role: 'viewer' }
      expect(store.isAdmin).toBe(false)
    })
  })

  describe('isOperator', () => {
    it('returns false when no user', () => {
      const store = useAuthStore()
      expect(store.isOperator).toBe(false)
    })

    it('returns true for admin role', () => {
      const store = useAuthStore()
      store.user = { ...mockUser, id: '1', role: 'admin' }
      expect(store.isOperator).toBe(true)
    })

    it('returns true for operator role', () => {
      const store = useAuthStore()
      store.user = { ...mockUser, id: '1', role: 'operator' }
      expect(store.isOperator).toBe(true)
    })

    it('returns false for viewer role', () => {
      const store = useAuthStore()
      store.user = { ...mockUser, id: '1', role: 'viewer' }
      expect(store.isOperator).toBe(false)
    })
  })
})

// =============================================================================
// CHECK AUTH STATUS
// =============================================================================

describe('Auth Store - checkAuthStatus', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('sets setupRequired to true when server indicates setup needed', async () => {
    server.use(
      http.get('/api/v1/auth/status', () => {
        return HttpResponse.json({
          setup_required: true,
          user_count: 0
        })
      })
    )

    const store = useAuthStore()
    await store.checkAuthStatus()

    expect(store.setupRequired).toBe(true)
  })

  it('clears tokens when setup is required', async () => {
    localStorage.setItem('el_frontend_access_token', 'old-token')
    localStorage.setItem('el_frontend_refresh_token', 'old-refresh')

    server.use(
      http.get('/api/v1/auth/status', () => {
        return HttpResponse.json({
          setup_required: true,
          user_count: 0
        })
      })
    )

    const store = useAuthStore()
    await store.checkAuthStatus()

    expect(store.accessToken).toBeNull()
    expect(store.refreshToken).toBeNull()
    expect(localStorage.getItem('el_frontend_access_token')).toBeNull()
  })

  it('fetches user when token exists and setup not required', async () => {
    localStorage.setItem('el_frontend_access_token', 'mock-access-token')

    const store = useAuthStore()
    await store.checkAuthStatus()

    expect(store.setupRequired).toBe(false)
    expect(store.user).not.toBeNull()
    expect(store.user?.username).toBe('testuser')
  })

  it('clears auth on token validation failure without refresh token', async () => {
    localStorage.setItem('el_frontend_access_token', 'invalid-token')

    server.use(
      http.get('/api/v1/auth/me', () => {
        return HttpResponse.json(
          { detail: 'Invalid token' },
          { status: 401 }
        )
      })
    )

    const store = useAuthStore()
    await store.checkAuthStatus()

    expect(store.user).toBeNull()
    expect(store.accessToken).toBeNull()
  })

  it('sets isLoading during auth check', async () => {
    const store = useAuthStore()

    const checkPromise = store.checkAuthStatus()
    expect(store.isLoading).toBe(true)

    await checkPromise
    expect(store.isLoading).toBe(false)
  })
})

// =============================================================================
// LOGIN
// =============================================================================

describe('Auth Store - login', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('stores tokens and user on successful login', async () => {
    const store = useAuthStore()

    await store.login({
      username: 'testuser',
      password: 'password123'
    })

    expect(store.accessToken).toBe(mockTokens.access_token)
    expect(store.refreshToken).toBe(mockTokens.refresh_token)
    expect(store.user?.username).toBe('testuser')
  })

  it('persists tokens to localStorage', async () => {
    const store = useAuthStore()

    await store.login({
      username: 'testuser',
      password: 'password123'
    })

    expect(localStorage.getItem('el_frontend_access_token')).toBe(mockTokens.access_token)
    expect(localStorage.getItem('el_frontend_refresh_token')).toBe(mockTokens.refresh_token)
  })

  it('throws and sets error on invalid credentials', async () => {
    const store = useAuthStore()

    await expect(
      store.login({
        username: 'wronguser',
        password: 'wrongpass'
      })
    ).rejects.toThrow()

    // 401 wird in uiApiError einheitlich als Session ungültig formuliert (auch Login)
    expect(store.error).toBe('Sitzung nicht mehr gültig. Bitte erneut anmelden.')
    expect(store.user).toBeNull()
    expect(store.accessToken).toBeNull()
  })

  it('sets isLoading during login attempt', async () => {
    const store = useAuthStore()

    const loginPromise = store.login({
      username: 'testuser',
      password: 'password123'
    })

    expect(store.isLoading).toBe(true)
    await loginPromise
    expect(store.isLoading).toBe(false)
  })

  it('clears previous error on new login attempt', async () => {
    const store = useAuthStore()
    store.error = 'Previous error'

    await store.login({
      username: 'testuser',
      password: 'password123'
    })

    expect(store.error).toBeNull()
  })
})

// =============================================================================
// SETUP (First Admin Creation)
// =============================================================================

describe('Auth Store - setup', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('creates admin user and stores tokens', async () => {
    const store = useAuthStore()

    await store.setup({
      username: 'newadmin',
      email: 'admin@example.com',
      password: 'securepass123',
      full_name: 'New Admin'
    })

    expect(store.accessToken).toBe(mockTokens.access_token)
    expect(store.refreshToken).toBe(mockTokens.refresh_token)
    expect(store.user).not.toBeNull()
  })

  it('sets setupRequired to false after successful setup', async () => {
    const store = useAuthStore()
    store.setupRequired = true

    await store.setup({
      username: 'newadmin',
      email: 'admin@example.com',
      password: 'securepass123'
    })

    expect(store.setupRequired).toBe(false)
  })

  it('sets isLoading during setup', async () => {
    const store = useAuthStore()

    const setupPromise = store.setup({
      username: 'newadmin',
      email: 'admin@example.com',
      password: 'securepass123'
    })

    expect(store.isLoading).toBe(true)
    await setupPromise
    expect(store.isLoading).toBe(false)
  })
})

// =============================================================================
// LOGOUT
// =============================================================================

describe('Auth Store - logout', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('clears user and tokens on logout', async () => {
    const store = useAuthStore()
    // Set up authenticated state
    store.user = { ...mockUser, id: '1' }
    localStorage.setItem('el_frontend_access_token', 'some-token')
    localStorage.setItem('el_frontend_refresh_token', 'some-refresh')

    await store.logout()

    expect(store.user).toBeNull()
    expect(store.accessToken).toBeNull()
    expect(store.refreshToken).toBeNull()
  })

  it('removes tokens from localStorage', async () => {
    localStorage.setItem('el_frontend_access_token', 'some-token')
    localStorage.setItem('el_frontend_refresh_token', 'some-refresh')

    const store = useAuthStore()
    await store.logout()

    expect(localStorage.getItem('el_frontend_access_token')).toBeNull()
    expect(localStorage.getItem('el_frontend_refresh_token')).toBeNull()
  })

  it('disconnects websocket on logout', async () => {
    const { websocketService } = await import('@/services/websocket')

    const store = useAuthStore()
    await store.logout()

    expect(websocketService.disconnect).toHaveBeenCalled()
  })

  it('clears auth even if API call fails', async () => {
    server.use(
      http.post('/api/v1/auth/logout', () => {
        return HttpResponse.json(
          { detail: 'Server error' },
          { status: 500 }
        )
      })
    )

    localStorage.setItem('el_frontend_access_token', 'some-token')
    const store = useAuthStore()
    store.user = { ...mockUser, id: '1' }

    await store.logout()

    // Should still clear local state despite API error
    expect(store.user).toBeNull()
    expect(store.accessToken).toBeNull()
  })
})

// =============================================================================
// TOKEN REFRESH
// =============================================================================

describe('Auth Store - refreshTokens', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('throws error when no refresh token available', async () => {
    const store = useAuthStore()

    await expect(store.refreshTokens()).rejects.toThrow('No refresh token available')
  })

  it('updates tokens on successful refresh', async () => {
    localStorage.setItem('el_frontend_access_token', 'old-access')
    localStorage.setItem('el_frontend_refresh_token', 'mock-refresh-token-67890')

    const store = useAuthStore()
    await store.refreshTokens()

    expect(store.accessToken).toBe('mock-access-token-renewed')
    expect(store.refreshToken).toBe('mock-refresh-token-renewed')
  })

  it('clears auth on refresh failure', async () => {
    localStorage.setItem('el_frontend_access_token', 'old-access')
    localStorage.setItem('el_frontend_refresh_token', 'invalid-refresh-token')

    const store = useAuthStore()
    store.user = { ...mockUser, id: '1' }

    await expect(store.refreshTokens()).rejects.toThrow()

    expect(store.user).toBeNull()
    expect(store.accessToken).toBeNull()
    expect(store.refreshToken).toBeNull()
  })
})

// =============================================================================
// CLEAR AUTH (Internal Helper)
// =============================================================================

describe('Auth Store - clearAuth', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('resets all auth state to null', () => {
    const store = useAuthStore()

    // Set up state
    store.user = { ...mockUser, id: '1' }
    localStorage.setItem('el_frontend_access_token', 'token')
    localStorage.setItem('el_frontend_refresh_token', 'refresh')

    // Re-create store to pick up localStorage
    setActivePinia(createPinia())
    const freshStore = useAuthStore()
    freshStore.user = { ...mockUser, id: '1' }

    freshStore.clearAuth()

    expect(freshStore.user).toBeNull()
    expect(freshStore.accessToken).toBeNull()
    expect(freshStore.refreshToken).toBeNull()
  })

  it('clears localStorage tokens', () => {
    localStorage.setItem('el_frontend_access_token', 'token')
    localStorage.setItem('el_frontend_refresh_token', 'refresh')

    const store = useAuthStore()
    store.clearAuth()

    expect(localStorage.getItem('el_frontend_access_token')).toBeNull()
    expect(localStorage.getItem('el_frontend_refresh_token')).toBeNull()
  })
})
