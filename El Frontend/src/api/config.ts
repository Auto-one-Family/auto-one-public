/**
 * System Configuration API
 * 
 * Provides methods to interact with system configuration endpoints.
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface ConfigEntry {
  id: string
  config_key: string
  config_value: unknown
  config_type: string
  description: string | null
  is_secret: boolean
  created_at: string
  updated_at: string
}

export interface ConfigListResponse {
  success: boolean
  configs: ConfigEntry[]
  total: number
}

// =============================================================================
// API Functions
// =============================================================================

export const configApi = {
  /**
   * List all system configuration entries
   */
  async listConfig(configType?: string): Promise<ConfigEntry[]> {
    const params = configType ? `?config_type=${configType}` : ''
    const response = await api.get<ConfigListResponse>(`/debug/config${params}`)
    return response.data.configs
  },

  /**
   * Update a configuration value
   */
  async updateConfig(configKey: string, configValue: unknown): Promise<ConfigEntry> {
    const response = await api.patch<ConfigEntry>(
      `/debug/config/${configKey}`,
      { config_value: configValue }
    )
    return response.data
  }
}

export default configApi





















