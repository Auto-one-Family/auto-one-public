import api from './index'
import type {
  MockESP,
  MockESPCreate,
  MockSensorConfig,
  MockActuatorConfig,
  MockSystemState,
  CommandResponse,
  QualityLevel,
} from '@/types'

interface MockESPListResponse {
  success: boolean
  data: MockESP[]
  total: number
}

interface HeartbeatResponse {
  success: boolean
  esp_id: string
  timestamp: string
  message_published: boolean
  payload?: Record<string, unknown>
}

interface MqttMessageRecord {
  topic: string
  payload: Record<string, unknown>
  timestamp: string
  qos: number
}

interface MessagesResponse {
  success: boolean
  esp_id: string
  messages: MqttMessageRecord[]
  total: number
}

export const debugApi = {
  // ==========================================================================
  // Mock ESP CRUD
  // ==========================================================================

  /**
   * Create a new mock ESP32
   */
  async createMockEsp(config: MockESPCreate): Promise<MockESP> {
    const response = await api.post<MockESP>('/debug/mock-esp', config)
    return response.data
  },

  /**
   * List all mock ESPs
   */
  async listMockEsps(): Promise<MockESP[]> {
    const response = await api.get<MockESPListResponse>('/debug/mock-esp')
    return response.data.data
  },

  /**
   * Get a specific mock ESP
   */
  async getMockEsp(espId: string): Promise<MockESP> {
    const response = await api.get<MockESP>(`/debug/mock-esp/${espId}`)
    return response.data
  },

  /**
   * Delete a mock ESP
   */
  async deleteMockEsp(espId: string): Promise<void> {
    await api.delete(`/debug/mock-esp/${espId}`)
  },

  // ==========================================================================
  // Heartbeat & State
  // ==========================================================================

  /**
   * Trigger a heartbeat from a mock ESP
   */
  async triggerHeartbeat(espId: string): Promise<HeartbeatResponse> {
    const response = await api.post<HeartbeatResponse>(
      `/debug/mock-esp/${espId}/heartbeat`
    )
    return response.data
  },

  /**
   * Set system state of a mock ESP
   */
  async setState(
    espId: string,
    state: MockSystemState,
    reason?: string
  ): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/state`,
      { state, reason }
    )
    return response.data
  },

  /**
   * Configure auto-heartbeat
   */
  async setAutoHeartbeat(
    espId: string,
    enabled: boolean,
    intervalSeconds: number = 60
  ): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/auto-heartbeat`,
      null,
      { params: { enabled, interval_seconds: intervalSeconds } }
    )
    return response.data
  },

  // ==========================================================================
  // Sensor Operations
  // ==========================================================================

  /**
   * Add a sensor to a mock ESP
   */
  async addSensor(espId: string, config: MockSensorConfig): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/sensors`,
      config
    )
    return response.data
  },

  /**
   * Set sensor value
   */
  async setSensorValue(
    espId: string,
    gpio: number,
    rawValue: number,
    quality?: QualityLevel,
    publish: boolean = true
  ): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/sensors/${gpio}`,
      { raw_value: rawValue, quality, publish }
    )
    return response.data
  },

  /**
   * Remove a sensor from a mock ESP
   */
  async removeSensor(espId: string, gpio: number): Promise<CommandResponse> {
    const response = await api.delete<CommandResponse>(`/debug/mock-esp/${espId}/sensors/${gpio}`)
    return response.data
  },

  /**
   * Set multiple sensor values at once
   */
  async setBatchSensorValues(
    espId: string,
    values: Record<number, number>,
    publish: boolean = true
  ): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/sensors/batch`,
      { values, publish }
    )
    return response.data
  },

  // ==========================================================================
  // Actuator Operations
  // ==========================================================================

  /**
   * Add an actuator to a mock ESP
   */
  async addActuator(espId: string, config: MockActuatorConfig): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/actuators`,
      config
    )
    return response.data
  },

  /**
   * Set actuator state
   */
  async setActuatorState(
    espId: string,
    gpio: number,
    state: boolean,
    pwmValue?: number,
    publish: boolean = true
  ): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/actuators/${gpio}`,
      { state, pwm_value: pwmValue, publish }
    )
    return response.data
  },

  // ==========================================================================
  // Emergency Stop
  // ==========================================================================

  /**
   * Trigger emergency stop
   */
  async emergencyStop(espId: string, reason: string = 'manual'): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/emergency-stop`,
      null,
      { params: { reason } }
    )
    return response.data
  },

  /**
   * Clear emergency stop
   */
  async clearEmergency(espId: string): Promise<CommandResponse> {
    const response = await api.post<CommandResponse>(
      `/debug/mock-esp/${espId}/clear-emergency`
    )
    return response.data
  },

  // ==========================================================================
  // Message History
  // ==========================================================================

  /**
   * Get published MQTT messages from a mock ESP
   */
  async getMessages(espId: string, limit: number = 100): Promise<MqttMessageRecord[]> {
    const response = await api.get<MessagesResponse>(
      `/debug/mock-esp/${espId}/messages`,
      { params: { limit } }
    )
    return response.data.messages
  },

  /**
   * Clear message history
   */
  async clearMessages(espId: string): Promise<void> {
    await api.delete(`/debug/mock-esp/${espId}/messages`)
  },

  // ==========================================================================
  // Test Data Cleanup
  // ==========================================================================

  /**
   * Cleanup test data from database (sensor_data + actuator_history).
   *
   * Retention periods:
   * - TEST: 24 hours
   * - MOCK: 7 days
   * - SIMULATION: 30 days
   * - PRODUCTION: Never deleted
   *
   * @param dryRun - If true, preview what would be deleted without actually deleting
   * @param includeMock - Include MOCK data in cleanup
   * @param includeSimulation - Include SIMULATION data in cleanup
   *
   * @see El Servador/god_kaiser_server/src/api/v1/debug.py:1824 - Server endpoint
   * @see El Servador/god_kaiser_server/src/services/audit_retention_service.py:476 - Retention policies
   */
  async cleanupTestData(
    dryRun: boolean = true,
    includeMock: boolean = true,
    includeSimulation: boolean = true
  ): Promise<TestDataCleanupResponse> {
    const response = await api.delete<TestDataCleanupResponse>(
      '/debug/test-data/cleanup',
      {
        params: {
          dry_run: dryRun,
          include_mock: includeMock,
          include_simulation: includeSimulation,
        },
      }
    )
    return response.data
  },

  /**
   * Preview test data cleanup (dry run only)
   */
  async previewTestDataCleanup(
    includeMock: boolean = true,
    includeSimulation: boolean = true
  ): Promise<TestDataCleanupResponse> {
    return this.cleanupTestData(true, includeMock, includeSimulation)
  },

  // ==========================================================================
  // Maintenance Service (Paket D)
  // ==========================================================================

  /**
   * Get maintenance service status
   */
  async getMaintenanceStatus(): Promise<MaintenanceStatusResponse> {
    const response = await api.get<MaintenanceStatusResponse>('/debug/maintenance/status')
    return response.data
  },

  /**
   * Get maintenance configuration
   */
  async getMaintenanceConfig(): Promise<MaintenanceConfigResponse> {
    const response = await api.get<MaintenanceConfigResponse>('/debug/maintenance/config')
    return response.data
  },

  /**
   * Trigger a maintenance job manually
   *
   * Available jobs:
   * - cleanup_sensor_data
   * - cleanup_command_history
   * - cleanup_orphaned_mocks
   * - health_check_esps
   * - health_check_mqtt
   * - aggregate_stats
   */
  async triggerMaintenanceJob(jobName: string): Promise<MaintenanceTriggerResponse> {
    const response = await api.post<MaintenanceTriggerResponse>(
      `/debug/maintenance/trigger/${jobName}`
    )
    return response.data
  },
}

// =============================================================================
// Types
// =============================================================================

/**
 * Response from test data cleanup operation.
 *
 * @see El Servador/god_kaiser_server/src/api/v1/debug.py:1814 - TestDataCleanupResponse
 */
export interface TestDataCleanupResponse {
  success: boolean
  dry_run: boolean
  sensor_data: {
    deleted_count: number
    deleted_by_source: Record<string, number>
    duration_ms: number
    errors: string[]
  }
  actuator_data: {
    deleted_count: number
    deleted_by_source: Record<string, number>
    duration_ms: number
    errors: string[]
  }
  total_deleted: number
  message: string
}

/**
 * Maintenance job information
 *
 * @see El Servador/god_kaiser_server/src/api/v1/debug.py - MaintenanceStatusResponse
 */
export interface MaintenanceJob {
  job_id: string
  next_run: string | null
  last_run: string | null
  last_result: string
  // Job-specific results
  dry_run?: boolean
  records_found?: number
  records_deleted?: number
  batches_processed?: number
  cutoff_date?: string
  duration_seconds?: number
  status?: string
  orphaned_found?: number
  deleted?: number
  warned?: number
  esps_checked?: number
  timeouts_detected?: number
  offline_devices?: string[]
  connected?: boolean
  stats_updated?: boolean
}

/**
 * Maintenance service status response
 */
export interface MaintenanceStatusResponse {
  service_running: boolean
  jobs: MaintenanceJob[]
  stats_cache: {
    last_updated: string | null
    total_esps: number
    online_esps: number
    offline_esps: number
    total_sensors: number
    total_actuators: number
    sensors_by_type?: Record<string, number>
    actuators_by_type?: Record<string, number>
  }
}

/**
 * Maintenance configuration response
 */
export interface MaintenanceConfigResponse {
  // Sensor Data Cleanup
  sensor_data_retention_enabled: boolean
  sensor_data_retention_days: number
  sensor_data_cleanup_dry_run: boolean
  sensor_data_cleanup_batch_size: number
  sensor_data_cleanup_max_batches: number

  // Command History Cleanup
  command_history_retention_enabled: boolean
  command_history_retention_days: number
  command_history_cleanup_dry_run: boolean
  command_history_cleanup_batch_size: number
  command_history_cleanup_max_batches: number

  // Audit Log Cleanup
  audit_log_retention_enabled: boolean
  audit_log_retention_days: number
  audit_log_cleanup_dry_run: boolean
  audit_log_cleanup_batch_size: number
  audit_log_cleanup_max_batches: number

  // Orphaned Mocks
  orphaned_mock_cleanup_enabled: boolean
  orphaned_mock_auto_delete: boolean
  orphaned_mock_age_hours: number

  // Health Checks
  heartbeat_timeout_seconds: number
  mqtt_health_check_interval_seconds: number
  esp_health_check_interval_seconds: number

  // Stats Aggregation
  stats_aggregation_enabled: boolean
  stats_aggregation_interval_minutes: number

  // Safety Features
  cleanup_require_confirmation: boolean
  cleanup_alert_threshold_percent: number
  cleanup_max_records_per_run: number
}

/**
 * Maintenance trigger response
 */
export interface MaintenanceTriggerResponse {
  job_id: string
  triggered: boolean
  message: string
}
