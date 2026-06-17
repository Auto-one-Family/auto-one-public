import api from './index'
import type {
  SensorConfigCreate,
  SensorConfigResponse,
  SensorDataQuery,
  SensorDataResponse,
  SensorStatsResponse,
} from '@/types'

export const sensorsApi = {
  /**
   * Create or update sensor configuration
   */
  async createOrUpdate(
    espId: string,
    gpio: number,
    config: SensorConfigCreate
  ): Promise<SensorConfigResponse> {
    const response = await api.post<SensorConfigResponse>(
      `/sensors/${espId}/${gpio}`,
      {
        ...config,
        esp_id: espId,
        gpio,
      }
    )
    return response.data
  },

  /**
   * Delete sensor configuration by config_id (UUID).
   * Backend: DELETE /sensors/{esp_id}/{config_id}
   */
  async delete(espId: string, configId: string): Promise<SensorConfigResponse> {
    const response = await api.delete<SensorConfigResponse>(`/sensors/${espId}/${configId}`)
    return response.data
  },

  /**
   * Get sensor configuration by config_id (UUID) — always unambiguous.
   * Use this for multi-value sensors (e.g. 2x SHT31 on different I2C addresses).
   * Server: GET /sensors/config/{config_id}
   */
  async getByConfigId(configId: string): Promise<SensorConfigResponse> {
    const response = await api.get<SensorConfigResponse>(`/sensors/config/${configId}`)
    return response.data
  },

  /**
   * Get sensor configuration by ESP + GPIO.
   * @param sensorType - Optional; required for multi-value sensors (e.g. SHT31) that share a GPIO.
   */
  async get(
    espId: string,
    gpio: number,
    sensorType?: string
  ): Promise<SensorConfigResponse> {
    const response = await api.get<SensorConfigResponse>(
      `/sensors/${espId}/${gpio}`,
      sensorType != null ? { params: { sensor_type: sensorType } } : undefined
    )
    return response.data
  },

  /**
   * List sensor configurations
   */
  async list(params?: {
    esp_id?: string
    sensor_type?: string
    enabled?: boolean
    page?: number
    page_size?: number
  }): Promise<{ data: SensorConfigResponse[]; total: number }> {
    const response = await api.get<{
      data: SensorConfigResponse[]
      total: number
      page: number
      page_size: number
      total_pages: number
    }>('/sensors/', { params })
    return {
      data: response.data.data,
      total: response.data.total,
    }
  },

  // ===========================================================================
  // Sensor History API (Phase 3)
  // Server: GET /sensors/data (sensors.py:440-526)
  // ===========================================================================

  /**
   * Query historical sensor data with filters.
   *
   * @param query - Query parameters
   * @returns Sensor readings with metadata
   *
   * @example
   * // Get last 24h of temperature data for ESP
   * const data = await sensorsApi.queryData({
   *   esp_id: 'ESP_12AB34CD',
   *   sensor_type: 'temperature',
   *   limit: 500
   * })
   *
   * @example
   * // Get specific time range
   * const data = await sensorsApi.queryData({
   *   esp_id: 'ESP_12AB34CD',
   *   gpio: 34,
   *   start_time: '2025-01-01T00:00:00Z',
   *   end_time: '2025-01-01T23:59:59Z'
   * })
   */
  async queryData(query?: SensorDataQuery): Promise<SensorDataResponse> {
    const response = await api.get<SensorDataResponse>('/sensors/data', {
      params: query,
    })
    return response.data
  },

  /**
   * Get statistical summary for sensor data.
   *
   * Server: GET /sensors/{esp_id}/{gpio}/stats (sensors.py:644-717)
   *
   * @param espId - ESP device ID
   * @param gpio - GPIO pin number
   * @param params - Optional time range
   * @returns Statistics including min, max, avg, std_dev
   *
   * @example
   * // Get 24h stats (default)
   * const stats = await sensorsApi.getStats('ESP_12AB34CD', 34)
   * console.log(stats.stats.avg_value)
   *
   * @example
   * // Get stats for specific range
   * const stats = await sensorsApi.getStats('ESP_12AB34CD', 34, {
   *   start_time: '2025-01-01T00:00:00Z',
   *   end_time: '2025-01-07T23:59:59Z'
   * })
   */
  async getStats(
    espId: string,
    gpio: number,
    params?: {
      start_time?: string
      end_time?: string
      sensor_type?: string
    }
  ): Promise<SensorStatsResponse> {
    const response = await api.get<SensorStatsResponse>(
      `/sensors/${espId}/${gpio}/stats`,
      { params }
    )
    return response.data
  },

  /**
   * Query sensor data filtered by data source.
   *
   * Server: GET /sensors/data/by-source/{source} (sensors.py:534-612)
   *
   * @param source - Data source: production, mock, test, simulation
   * @param params - Optional filters
   * @returns Sensor readings from specified source
   */
  async queryDataBySource(
    source: 'production' | 'mock' | 'test' | 'simulation',
    params?: {
      esp_id?: string
      limit?: number
    }
  ): Promise<SensorDataResponse> {
    const response = await api.get<SensorDataResponse>(
      `/sensors/data/by-source/${source}`,
      { params }
    )
    return response.data
  },

  /**
   * Get sensor data count grouped by data source.
   *
   * Server: GET /sensors/data/stats/by-source (sensors.py:615-636)
   *
   * @returns Count per source type
   */
  async getCountBySource(): Promise<{
    success: boolean
    counts: Record<string, number>
    total: number
  }> {
    const response = await api.get<{
      success: boolean
      counts: Record<string, number>
      total: number
    }>('/sensors/data/stats/by-source')
    return response.data
  },

  // ===========================================================================
  // On-Demand Measurement (Phase 2D)
  // Server: POST /sensors/{esp_id}/{gpio}/measure (sensors.py:1649-1695)
  // ===========================================================================

  /**
   * Trigger a manual measurement for a sensor.
   *
   * Used for on-demand sensors or forcing immediate measurement.
   *
   * @param espId - ESP device ID (e.g., "ESP_12AB34CD")
   * @param gpio - Sensor GPIO pin
   * @returns Promise with measurement trigger response
   *
   * @example
   * // Trigger measurement
   * const result = await sensorsApi.triggerMeasurement('ESP_12AB34CD', 34)
   * console.log(result.request_id) // UUID for tracking
   */
  async triggerMeasurement(
    espId: string,
    gpio: number,
    options: TriggerMeasurementOptions = {},
  ): Promise<TriggerMeasurementResponse> {
    const response = await api.post<TriggerMeasurementResponse>(
      `/sensors/${espId}/${gpio}/measure`,
      Object.keys(options).length > 0 ? options : undefined,
    )
    return response.data
  },

  // =========================================================================
  // Alert Configuration (Phase 4A.7)
  // =========================================================================

  async getAlertConfig(sensorId: string): Promise<AlertConfigResponse> {
    const response = await api.get<AlertConfigResponse>(
      `/sensors/${sensorId}/alert-config`
    )
    return response.data
  },

  async updateAlertConfig(
    sensorId: string,
    config: AlertConfigUpdate
  ): Promise<AlertConfigResponse> {
    const response = await api.patch<AlertConfigResponse>(
      `/sensors/${sensorId}/alert-config`,
      config
    )
    return response.data
  },

  // =========================================================================
  // Runtime Statistics (Phase 4A.8)
  // =========================================================================

  async getRuntime(sensorId: string): Promise<RuntimeStatsResponse> {
    const response = await api.get<RuntimeStatsResponse>(
      `/sensors/${sensorId}/runtime`
    )
    return response.data
  },

  async updateRuntime(
    sensorId: string,
    stats: RuntimeStatsUpdate
  ): Promise<RuntimeStatsResponse> {
    const response = await api.patch<RuntimeStatsResponse>(
      `/sensors/${sensorId}/runtime`,
      stats
    )
    return response.data
  },
}

// ===========================================================================
// Types for On-Demand Measurement (Phase 2D)
// ===========================================================================

export interface TriggerMeasurementOptions {
  sensor_type?: string
  sample_count?: number
  sample_delay_ms?: number
  timeout_ms?: number
}

export interface TriggerMeasurementResponse {
  success: boolean
  request_id: string
  esp_id: string
  gpio: number
  sensor_type: string
  message: string
}

// ===========================================================================
// OneWire Scan Types (Phase 6 - DS18B20 Support)
// ===========================================================================

/**
 * OneWire device found during bus scan.
 * 
 * Each device has a unique 64-bit ROM address (16 hex characters).
 * Device type is determined by family code (first byte).
 * 
 * OneWire Multi-Device Support:
 * - Multiple DS18B20 sensors can share the same GPIO pin (bus topology)
 * - Scan results are enriched with already_configured flag to distinguish
 *   new devices from those already in the database
 */
export interface OneWireDevice {
  /** ROM code: 16 hex characters, e.g., "28FF641E8D3C0C79" */
  rom_code: string
  /** Device type: ds18b20, ds18s20, ds1822, unknown */
  device_type: string
  /** GPIO pin the device was found on */
  pin: number
  // =========================================================================
  // OneWire Multi-Device Support (GPIO-Sharing)
  // =========================================================================
  /** True if this device is already configured in database */
  already_configured?: boolean
  /** Sensor name if already configured (for display in UI) */
  sensor_name?: string | null
}

/**
 * Response from OneWire bus scan.
 * 
 * Server: POST /api/v1/sensors/esp/{esp_id}/onewire/scan
 * 
 * OneWire Multi-Device Support:
 * - Devices are enriched with already_configured flag
 * - new_count indicates how many devices are NOT yet in database
 * - Frontend can use this to show which devices are new vs already configured
 */
export interface OneWireScanResponse {
  success: boolean
  message: string
  devices: OneWireDevice[]
  /** Total number of devices found on bus */
  found_count: number
  // =========================================================================
  // OneWire Multi-Device Support (GPIO-Sharing)
  // =========================================================================
  /** Number of NEW devices (not yet configured in database) */
  new_count?: number
  pin: number
  esp_id: string
  scan_duration_ms?: number
}

// ===========================================================================
// OneWire Scan API Functions (Phase 6)
// ===========================================================================

export const oneWireApi = {
  /**
   * Scan OneWire bus for connected devices.
   * 
   * Server sends MQTT command to ESP, ESP scans bus, returns found devices.
   * Timeout: 10 seconds on server side.
   * 
   * Server: POST /api/v1/sensors/esp/{esp_id}/onewire/scan?pin=4
   * 
   * @param espId - ESP device ID (e.g., "ESP_12AB34CD")
   * @param pin - GPIO pin for OneWire bus (default: 4)
   * @returns Scan response with found devices
   * 
   * @example
   * const result = await oneWireApi.scanBus('ESP_12AB34CD', 4)
   * console.log(`Found ${result.found_count} devices`)
   * result.devices.forEach(d => console.log(d.rom_code))
   */
  async scanBus(espId: string, pin: number = 4): Promise<OneWireScanResponse> {
    const response = await api.post<OneWireScanResponse>(
      `/sensors/esp/${espId}/onewire/scan`,
      null,
      { params: { pin } }
    )
    return response.data
  },

  /**
   * Get all configured OneWire sensors for an ESP.
   * 
   * Server: GET /api/v1/sensors/esp/{esp_id}/onewire
   * 
   * @param espId - ESP device ID
   * @param pin - Optional filter by GPIO pin
   * @returns Array of sensor configurations
   */
  async listSensors(
    espId: string,
    pin?: number
  ): Promise<{ sensors: import('@/types').SensorConfigResponse[]; total: number }> {
    const response = await api.get<{
      sensors: import('@/types').SensorConfigResponse[]
      total: number
    }>(`/sensors/esp/${espId}/onewire`, { params: pin !== undefined ? { pin } : {} })
    return response.data
  },

}

// Phase 4A.7 Types
export interface AlertConfigUpdate {
  alerts_enabled?: boolean
  suppression_reason?: string
  suppression_note?: string
  suppression_until?: string | null
  custom_thresholds?: {
    warning_min?: number | null
    warning_max?: number | null
    critical_min?: number | null
    critical_max?: number | null
  }
  severity_override?: string | null
}

export interface AlertConfigResponse {
  success: boolean
  sensor_id?: string
  actuator_id?: string
  esp_id?: string
  alert_config: Record<string, unknown>
  global_thresholds?: Record<string, unknown> | null
}

export interface RuntimeStatsUpdate {
  uptime_hours?: number
  last_restart?: string
  expected_lifetime_hours?: number
  last_maintenance?: string
  maintenance_interval_hours?: number
  maintenance_log?: Array<{
    date: string
    action: string
    notes?: string
    performed_by?: string
  }>
}

export interface RuntimeStatsResponse {
  success: boolean
  sensor_id?: string
  actuator_id?: string
  runtime_stats: Record<string, unknown>
  computed_uptime_hours?: number | null
  maintenance_overdue?: boolean
}












