/**
 * Health API Client
 *
 * Fetches fleet-wide health data from GET /v1/health/esp
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface RecentError {
  timestamp: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  category: string
  message: string
}

export interface FleetHealthDevice {
  device_id: string
  name: string | null
  status: 'online' | 'offline' | 'error' | 'unknown'
  last_seen: string | null
  uptime_seconds: number | null
  heap_free: number | null
  wifi_rssi: number | null
  sensor_count: number
  actuator_count: number
  recent_errors?: RecentError[]
}

export interface FleetHealthResponse {
  success: boolean
  total_devices: number
  online_count: number
  offline_count: number
  error_count: number
  unknown_count: number
  total_sensors: number
  total_actuators: number
  avg_heap_free: number | null
  avg_wifi_rssi: number | null
  devices: FleetHealthDevice[]
}

// =============================================================================
// API Functions
// =============================================================================

export async function getFleetHealth(): Promise<FleetHealthResponse> {
  const response = await api.get<FleetHealthResponse>('/health/esp')
  return response.data
}
