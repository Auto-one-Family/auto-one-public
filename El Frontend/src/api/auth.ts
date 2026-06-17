import api from './index'
import type {
  AuthStatusResponse,
  LoginRequest,
  LoginResponse,
  SetupRequest,
  SetupResponse,
  RefreshResponse,
  User,
} from '@/types'

export const authApi = {
  /**
   * Check if initial setup is required
   */
  async getStatus(): Promise<AuthStatusResponse> {
    const response = await api.get<AuthStatusResponse>('/auth/status')
    return response.data
  },

  /**
   * Login with username/email and password
   * Server returns: { success, message, tokens: { access_token, ... }, user }
   */
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const response = await api.post<LoginResponse>('/auth/login', credentials)
    return response.data
  },

  /**
   * Initial admin setup (first run only)
   * Server returns: { success, message, tokens: { access_token, ... }, user }
   */
  async setup(data: SetupRequest): Promise<SetupResponse> {
    const response = await api.post<SetupResponse>('/auth/setup', data)
    return response.data
  },

  /**
   * Refresh access token using refresh token
   * Server returns: { success, message, tokens: { access_token, ... } }
   */
  async refresh(refreshToken: string): Promise<RefreshResponse> {
    const response = await api.post<RefreshResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    })
    return response.data
  },

  /**
   * Get current user info
   * Server returns User directly (NOT wrapped in { data: User })
   */
  async me(): Promise<User> {
    const response = await api.get<User>('/auth/me')
    return response.data
  },

  /**
   * Logout (invalidate tokens)
   */
  async logout(logoutAll: boolean = false): Promise<void> {
    await api.post('/auth/logout', { all_devices: logoutAll })
  },
}
