import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import { useIntentSignalsStore } from '@/shared/stores/intentSignals.store'
import { useEspStore } from '@/stores/esp'
import { websocketService } from '@/services/websocket'
import { createLogger } from '@/utils/logger'
import type { User, LoginRequest, SetupRequest } from '@/types'

const logger = createLogger('AuthStore')

const TOKEN_KEY = 'el_frontend_access_token'
const REFRESH_TOKEN_KEY = 'el_frontend_refresh_token'

export const useAuthStore = defineStore('auth', () => {
  // State
  const user = ref<User | null>(null)
  const accessToken = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const refreshToken = ref<string | null>(localStorage.getItem(REFRESH_TOKEN_KEY))
  const isLoading = ref(false)
  const setupRequired = ref<boolean | null>(null)
  const error = ref<string | null>(null)

  // Getters
  const isAuthenticated = computed(() => !!accessToken.value && !!user.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isOperator = computed(() => ['admin', 'operator'].includes(user.value?.role || ''))
  // TODO: bei Capability-Epic durch hasCapability('monitor.view') ersetzen
  const isViewer = computed(() => user.value?.role === 'viewer')

  async function ensureRealtimeConnected(): Promise<void> {
    // After login/re-auth we need a deterministic reconnect so stores
    // (esp/actuator/logic) receive live WS events again without page reload.
    try {
      websocketService.disconnect()
      await websocketService.connect()
    } catch (err) {
      logger.error('Realtime reconnect after auth failed', err)
    }
  }

  async function ensureInitialStateLoaded(): Promise<void> {
    try {
      await useEspStore().fetchAll()
    } catch (err) {
      logger.error('Initial ESP state load after auth failed', err)
    }
  }

  // Actions
  async function checkAuthStatus(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      // First check if setup is required
      const status = await authApi.getStatus()
      setupRequired.value = status.setup_required

      // If setup is required, clear any stale tokens from previous sessions
      if (status.setup_required) {
        clearAuth()
        return
      }

      // If we have a token, try to get user info
      if (accessToken.value) {
        try {
          user.value = await authApi.me()
          await ensureRealtimeConnected()
          await useEspStore().ensureRealtimeHandlers()
          await ensureInitialStateLoaded()
        } catch {
          // Token might be expired, try refresh ONCE
          if (refreshToken.value) {
            try {
              await refreshTokens()
              await ensureRealtimeConnected()
              await useEspStore().ensureRealtimeHandlers()
              await ensureInitialStateLoaded()
            } catch {
              // Refresh also failed - clear auth silently, don't throw
              clearAuth()
            }
          } else {
            clearAuth()
          }
        }
      }
    } catch (err) {
      logger.error('Failed to check auth status', err)
      error.value = 'Failed to check authentication status'
    } finally {
      isLoading.value = false
    }
  }

  async function login(credentials: LoginRequest): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await authApi.login(credentials)
      // Server returns { tokens: { access_token, ... }, user }
      setTokens(response.tokens.access_token, response.tokens.refresh_token)
      // User is included in login response
      user.value = response.user
      await ensureRealtimeConnected()
      await useEspStore().ensureRealtimeHandlers()
      await ensureInitialStateLoaded()
    } catch (err: unknown) {
      error.value = formatUiApiError(toUiApiError(err, 'Login fehlgeschlagen'))
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function setup(data: SetupRequest): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const response = await authApi.setup(data)
      // Server returns { tokens: { access_token, ... }, user }
      setTokens(response.tokens.access_token, response.tokens.refresh_token)
      // User is included in setup response
      user.value = response.user
      setupRequired.value = false
      await ensureRealtimeConnected()
      await useEspStore().ensureRealtimeHandlers()
      await ensureInitialStateLoaded()
    } catch (err: unknown) {
      error.value = formatUiApiError(toUiApiError(err, 'Setup fehlgeschlagen'))
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function refreshTokens(): Promise<void> {
    if (!refreshToken.value) {
      throw new Error('No refresh token available')
    }

    try {
      const response = await authApi.refresh(refreshToken.value)
      // Server returns { tokens: { access_token, ... } }
      setTokens(response.tokens.access_token, response.tokens.refresh_token)
      // Refresh response doesn't include user, fetch separately
      user.value = await authApi.me()
    } catch (err) {
      clearAuth()
      throw err
    }
  }

  async function logout(logoutAll: boolean = false): Promise<void> {
    isLoading.value = true

    try {
      await authApi.logout(logoutAll)
    } catch (err) {
      logger.error('Logout API call failed', err)
    } finally {
      // Cleanup WebSocket connection before clearing auth
      // This ensures proper resource cleanup and prevents memory leaks
      websocketService.disconnect()

      useIntentSignalsStore().clearAll()

      clearAuth()
      isLoading.value = false
    }
  }

  function setTokens(access: string, refresh: string): void {
    accessToken.value = access
    refreshToken.value = refresh
    localStorage.setItem(TOKEN_KEY, access)
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh)
  }

  function clearAuth(): void {
    user.value = null
    accessToken.value = null
    refreshToken.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }

  return {
    // State
    user,
    accessToken,
    refreshToken,
    isLoading,
    setupRequired,
    error,

    // Getters
    isAuthenticated,
    isAdmin,
    isOperator,
    isViewer,

    // Actions
    checkAuthStatus,
    login,
    setup,
    refreshTokens,
    logout,
    clearAuth,
  }
})
