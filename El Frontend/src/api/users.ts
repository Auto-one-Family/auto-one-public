/**
 * User Management API
 * 
 * Provides methods to interact with user management endpoints.
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export type UserRole = 'admin' | 'operator' | 'viewer'

export interface User {
  id: number
  username: string
  email: string
  full_name: string | null
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface UserCreate {
  username: string
  email: string
  password: string
  full_name?: string
  role?: UserRole
}

export interface UserUpdate {
  email?: string
  full_name?: string
  role?: UserRole
  is_active?: boolean
}

export interface UserListResponse {
  success: boolean
  users: User[]
  total: number
}

export interface PasswordReset {
  new_password: string
}

export interface PasswordChange {
  current_password: string
  new_password: string
}

export interface MessageResponse {
  success: boolean
  message: string
}

// =============================================================================
// API Functions
// =============================================================================

export const usersApi = {
  /**
   * List all users (admin only)
   */
  async listUsers(): Promise<User[]> {
    const response = await api.get<UserListResponse>('/users')
    return response.data.users
  },

  /**
   * Get a specific user by ID
   */
  async getUser(userId: number): Promise<User> {
    const response = await api.get<User>(`/users/${userId}`)
    return response.data
  },

  /**
   * Create a new user
   */
  async createUser(data: UserCreate): Promise<User> {
    const response = await api.post<User>('/users', data)
    return response.data
  },

  /**
   * Update a user
   */
  async updateUser(userId: number, data: UserUpdate): Promise<User> {
    const response = await api.patch<User>(`/users/${userId}`, data)
    return response.data
  },

  /**
   * Delete a user
   */
  async deleteUser(userId: number): Promise<void> {
    await api.delete(`/users/${userId}`)
  },

  /**
   * Reset a user's password (admin only)
   */
  async resetPassword(userId: number, newPassword: string): Promise<MessageResponse> {
    const response = await api.post<MessageResponse>(
      `/users/${userId}/reset-password`,
      { new_password: newPassword }
    )
    return response.data
  },

  /**
   * Change own password
   */
  async changeOwnPassword(currentPassword: string, newPassword: string): Promise<MessageResponse> {
    const response = await api.patch<MessageResponse>(
      '/users/me/password',
      { current_password: currentPassword, new_password: newPassword }
    )
    return response.data
  }
}

export default usersApi





















