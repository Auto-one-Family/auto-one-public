/**
 * Plugins API Client
 *
 * Handles AutoOps plugin management: list, detail, execute, config, history.
 * Server endpoints: /v1/plugins/*
 *
 * @see El Servador/god_kaiser_server/src/api/v1/plugins.py
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface PluginDTO {
  plugin_id: string
  display_name: string
  description: string
  category: string
  is_enabled: boolean
  config: Record<string, unknown>
  config_schema: Record<string, unknown>
  capabilities: string[]
  last_execution?: PluginExecutionDTO | null
  created_at?: string | null
  updated_at?: string | null
}

export interface PluginDetailDTO extends PluginDTO {
  recent_executions: PluginExecutionDTO[]
}

export interface PluginExecutionDTO {
  id: string
  execution_id?: string
  plugin_id: string
  started_at: string | null
  updated_at?: string | null
  finished_at?: string | null
  status: 'queued' | 'accepted' | 'started' | 'running' | 'partial' | 'success' | 'completed' | 'error' | 'failure' | 'failed' | 'timeout' | 'cancelled'
  message?: string | null
  progress_percent?: number | null
  step?: string | null
  error_code?: string | number | null
  triggered_by: string
  triggered_by_user?: number | null
  correlation_id?: string | null
  result: Record<string, unknown> | null
  error_message: string | null
  duration_seconds: number | null
}

export interface PluginConfigDTO {
  plugin_id: string
  config: Record<string, unknown>
  updated_at: string | null
}

export interface PluginToggleDTO {
  plugin_id: string
  is_enabled: boolean
}

export interface ExecutePluginRequest {
  config_overrides?: Record<string, unknown>
}

export interface UpdatePluginConfigRequest {
  config: Record<string, unknown>
}

export interface PluginExecutionStatusEvent {
  execution_id: string
  plugin_id: string
  status: string
  message?: string
  started_at?: string
  updated_at?: string
  finished_at?: string
  progress_percent?: number
  step?: string
  error_code?: string | number
  error_message?: string
  triggered_by?: string
  correlation_id?: string
}

// =============================================================================
// Plugins API
// =============================================================================

export const pluginsApi = {
  /**
   * List all registered plugins
   */
  async list(): Promise<PluginDTO[]> {
    const response = await api.get<PluginDTO[]>('/plugins')
    return response.data
  },

  /**
   * Get plugin details including recent executions
   */
  async getDetail(pluginId: string): Promise<PluginDetailDTO> {
    const response = await api.get<PluginDetailDTO>(`/plugins/${pluginId}`)
    return response.data
  },

  /**
   * Execute a plugin manually
   */
  async execute(
    pluginId: string,
    request?: ExecutePluginRequest,
  ): Promise<PluginExecutionDTO> {
    const response = await api.post<PluginExecutionDTO>(
      `/plugins/${pluginId}/execute`,
      request ?? {},
    )
    const payload = response.data
    return {
      ...payload,
      execution_id: payload.execution_id ?? payload.id,
      updated_at: payload.updated_at ?? payload.started_at ?? null,
    }
  },

  /**
   * Update plugin runtime configuration
   */
  async updateConfig(
    pluginId: string,
    request: UpdatePluginConfigRequest,
  ): Promise<PluginConfigDTO> {
    const response = await api.put<PluginConfigDTO>(
      `/plugins/${pluginId}/config`,
      request,
    )
    return response.data
  },

  /**
   * Get plugin execution history
   */
  async getHistory(
    pluginId: string,
    limit: number = 50,
  ): Promise<PluginExecutionDTO[]> {
    const response = await api.get<PluginExecutionDTO[]>(
      `/plugins/${pluginId}/history`,
      { params: { limit } },
    )
    return response.data.map((entry) => ({
      ...entry,
      execution_id: entry.execution_id ?? entry.id,
      updated_at: entry.updated_at ?? entry.finished_at ?? entry.started_at ?? null,
    }))
  },

  /**
   * Optional endpoint for currently running executions.
   * Falls back to plugin list hydration in the store if unsupported.
   */
  async getRunningExecutions(): Promise<PluginExecutionDTO[]> {
    const response = await api.get<PluginExecutionDTO[]>('/plugins/executions', {
      params: { status: 'running' },
    })
    return response.data.map((entry) => ({
      ...entry,
      execution_id: entry.execution_id ?? entry.id,
      updated_at: entry.updated_at ?? entry.finished_at ?? entry.started_at ?? null,
    }))
  },

  /**
   * Enable a plugin
   */
  async enable(pluginId: string): Promise<PluginToggleDTO> {
    const response = await api.post<PluginToggleDTO>(
      `/plugins/${pluginId}/enable`,
    )
    return response.data
  },

  /**
   * Disable a plugin
   */
  async disable(pluginId: string): Promise<PluginToggleDTO> {
    const response = await api.post<PluginToggleDTO>(
      `/plugins/${pluginId}/disable`,
    )
    return response.data
  },
}
