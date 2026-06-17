/**
 * Load Testing API
 * 
 * Provides methods to interact with load testing endpoints.
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface BulkCreateRequest {
  count: number
  prefix?: string
  with_sensors?: number
  with_actuators?: number
}

export interface BulkCreateResponse {
  success: boolean
  created_count: number
  esp_ids: string[]
  message: string
}

export interface SimulationRequest {
  esp_ids?: string[]
  interval_ms?: number
  duration_seconds?: number
}

export interface SimulationResponse {
  success: boolean
  message: string
  active_simulations: number
  simulation_id?: string
}

export interface MetricsResponse {
  success: boolean
  mock_esp_count: number
  total_sensors: number
  total_actuators: number
  messages_published: number
  uptime_seconds: number
}

export interface LoadTestCapabilities {
  max_bulk_count: number
  max_sensors_per_device: number
  max_actuators_per_device: number
  min_interval_ms: number
  max_interval_ms: number
  min_duration_seconds: number
  max_duration_seconds: number
}

export interface LoadTestPreflightRequest {
  bulk_count: number
  sensors_per_device: number
  actuators_per_device: number
  interval_ms: number
  duration_seconds: number
}

export interface LoadTestPreflightResponse {
  allowed: boolean
  impact: 'low' | 'medium' | 'high'
  message: string
  forecast: {
    estimated_devices: number
    estimated_messages: number
    expected_load_per_second: number
  }
}

const FALLBACK_CAPABILITIES: LoadTestCapabilities = {
  max_bulk_count: 100,
  max_sensors_per_device: 10,
  max_actuators_per_device: 10,
  min_interval_ms: 100,
  max_interval_ms: 60000,
  min_duration_seconds: 10,
  max_duration_seconds: 3600,
}

// =============================================================================
// API Functions
// =============================================================================

export const loadTestApi = {
  /**
   * Bulk create mock ESPs for load testing
   */
  async bulkCreate(request: BulkCreateRequest): Promise<BulkCreateResponse> {
    const response = await api.post<BulkCreateResponse>(
      '/debug/load-test/bulk-create',
      request
    )
    return response.data
  },

  /**
   * Start sensor simulation
   */
  async startSimulation(request: SimulationRequest = {}): Promise<SimulationResponse> {
    const response = await api.post<SimulationResponse>(
      '/debug/load-test/simulate',
      request
    )
    return response.data
  },

  /**
   * Stop all simulations
   */
  async stopSimulation(): Promise<SimulationResponse> {
    const response = await api.post<SimulationResponse>('/debug/load-test/stop')
    return response.data
  },

  /**
   * Get load test metrics
   */
  async getMetrics(): Promise<MetricsResponse> {
    const response = await api.get<MetricsResponse>('/debug/load-test/metrics')
    return response.data
  },

  async getCapabilities(): Promise<LoadTestCapabilities> {
    try {
      const response = await api.get<Partial<LoadTestCapabilities>>('/debug/load-test/capabilities')
      return {
        ...FALLBACK_CAPABILITIES,
        ...response.data,
      }
    } catch {
      return FALLBACK_CAPABILITIES
    }
  },

  async preflight(request: LoadTestPreflightRequest): Promise<LoadTestPreflightResponse> {
    try {
      const response = await api.post<LoadTestPreflightResponse>('/debug/load-test/preflight', request)
      return response.data
    } catch {
      const estimatedDevices = request.bulk_count
      const estimatedMessages = Math.max(
        1,
        Math.floor((request.duration_seconds * 1000) / Math.max(1, request.interval_ms)),
      ) * Math.max(1, request.sensors_per_device)
      const expectedLoadPerSecond = Math.max(
        1,
        Math.round((estimatedMessages / Math.max(1, request.duration_seconds)) * 100) / 100,
      )
      const impact: LoadTestPreflightResponse['impact'] =
        expectedLoadPerSecond > 50 || estimatedDevices > 60 ? 'high'
          : expectedLoadPerSecond > 20 || estimatedDevices > 20 ? 'medium'
            : 'low'
      return {
        allowed: true,
        impact,
        message: 'Preflight lokal abgeschätzt (Server-Endpunkt nicht verfügbar).',
        forecast: {
          estimated_devices: estimatedDevices,
          estimated_messages: estimatedMessages,
          expected_load_per_second: expectedLoadPerSecond,
        },
      }
    }
  },
}

export default loadTestApi





















