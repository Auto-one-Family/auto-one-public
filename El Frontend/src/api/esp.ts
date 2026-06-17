/**
 * Unified ESP API Client
 *
 * Supports both Mock ESPs (via /debug/mock-esp) and Real ESPs (via /v1/esp/devices).
 * Automatically routes API calls based on ESP ID detection.
 */

import api from './index'
import { debugApi } from './debug'
import { sensorsApi } from './sensors'
import { actuatorsApi } from './actuators'
import { createLogger } from '@/utils/logger'
import { getSensorUnit } from '@/utils/sensorDefaults'

const logger = createLogger('ESP-API')
import type {
  MockESP,
  MockESPCreate,
  MockSensor,
  OfflineInfo,
  GpioStatusResponse,
  PendingESPDevice,
  PendingDevicesListResponse,
  ESPApprovalRequest,
  ESPApprovalResponse,
  ESPRejectionRequest,
  SensorConfigResponse,
  ActuatorConfigResponse,
  MockActuator,
  QualityLevel
} from '@/types'

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * Unified ESP Device interface.
 *
 * ID Naming Convention (aligned with Server and ESP32 Firmware):
 * - `device_id`: Primary identifier (format: ESP_XXXXXXXX or ESP_MOCK_XXX)
 *   - Used by Server API and Database
 *   - Always present in all ESP types
 * - `esp_id`: Alias for device_id (backward compatibility with Mock ESPs)
 *   - Mock ESPs originally used esp_id as primary key
 *   - When present, should equal device_id
 * - `id`: Database UUID (optional, only from Server DB responses)
 *
 * Zone Naming Convention:
 * - `zone_id`: Technical zone identifier (lowercase, no spaces, e.g., "zelt_1")
 *   - Auto-generated from zone_name if not provided
 *   - Used in MQTT topics and API calls
 * - `zone_name`: Human-readable zone name (allows spaces, e.g., "Zelt 1")
 *   - Displayed in UI
 *   - Falls back to zone_id if not set
 *
 * @see El Servador/god_kaiser_server/src/schemas/esp.py - ESPDeviceResponse
 * @see El Trabajante/src/utils/topic_builder.cpp - MQTT topic format
 */
export interface ESPDevice {
  id?: string                         // Database UUID (from Server)
  device_id: string                   // Primary ID: ESP_XXXXXXXX or ESP_MOCK_XXX
  esp_id?: string                     // Alias for device_id (Mock ESP compatibility)
  name?: string | null                // Human-readable device name
  zone_id?: string | null             // Technical zone ID (lowercase, no spaces)
  zone_name?: string | null           // Human-readable zone name (UI display)
  master_zone_id?: string | null      // Parent zone for hierarchical zones
  kaiser_id?: string | null           // Kaiser ID for zone management
  subzone_id?: string | null          // Subzone assignment ID
  subzone_name?: string | null        // Human-readable subzone name
  is_zone_master?: boolean            // Whether this ESP is zone master
  ip_address?: string
  mac_address?: string
  firmware_version?: string
  hardware_type?: string              // ESP32_WROOM, XIAO_ESP32_C3, MOCK_ESP32
  capabilities?: Record<string, unknown>
  status?: string                     // pending_approval, approved, online, offline, rejected, error, unknown
  last_seen?: string | null           // ISO timestamp of last heartbeat
  metadata?: Record<string, unknown>
  sensor_count?: number
  actuator_count?: number
  // Mock ESP specific fields (from debug API in-memory store)
  system_state?: string               // MockSystemState (BOOT, OPERATIONAL, etc.)
  sensors?: MockSensor[]
  actuators?: MockActuator[]
  auto_heartbeat?: boolean            // Whether auto-heartbeat is enabled (Mock ESPs only)
  heartbeat_interval_seconds?: number // Heartbeat interval in seconds (Mock ESPs only)
  heap_free?: number                  // Free heap memory in bytes
  wifi_rssi?: number                  // WiFi signal strength in dBm
  uptime?: number                     // Uptime in seconds
  last_heartbeat?: string | null      // ISO timestamp
  connected?: boolean                 // MQTT connection status
  spool_pending_count?: number        // AUT-716: LittleFS spool entries pending replay
  spool_dropped_count?: number        // AUT-716: LittleFS spool entries dropped (fill threshold)
  /**
   * Offline-Informationen (nur wenn status = 'offline').
   * Enthält Grund, Zeitstempel und UI-Text.
   */
  offlineInfo?: OfflineInfo
  created_at?: string
  updated_at?: string
  /** Subzones assigned to this device (T14-Fix-F: hydrated at page load) */
  subzones?: SubzoneSummary[]
  /**
   * Letzter normalisierter esp_health-Laufzeit-Snapshot (P0-C).
   * Gesetzt im ESP-Store bei Heartbeat-WS; enthält Degradations-Flags + Roh-Telemetrie.
   */
  runtime_health_view?: import('@/domain/esp/espHealth').EspHealthViewModel
  /**
   * Letzter terminaler Config-Reject (AUT-134 PKG-04).
   * Gesetzt im ESP-Store bei `config_failed` (reason_code='config_oversize')
   * oder `intent_outcome` (flow='config', code='PAYLOAD_TOO_LARGE').
   * Read-only informational; kein Auto-Retry.
   * SEPARAT vom runtime_health_view-Pfad (Eingeschränkt-Badge).
   */
  config_last_reject?: import('@/types').ConfigLastReject | null
}

/** Summary of a subzone assigned to an ESP device (from GET /esp/devices) */
export interface SubzoneSummary {
  subzone_id: string
  subzone_name: string
  assigned_gpios: number[]
  sensor_count: number
  actuator_count: number
  is_active?: boolean
}

export interface ESPDeviceListResponse {
  success: boolean
  data: ESPDevice[]
  pagination?: {
    page: number
    page_size: number
    total: number
    total_pages: number
  }
}

export interface ESPDeviceUpdate {
  /** Explicit `null` clears the device name in the DB (omit field = no change). */
  name?: string | null
  zone_id?: string | null
  zone_name?: string | null
  is_zone_master?: boolean
  capabilities?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface ESPDeviceCreate {
  device_id: string
  name?: string
  zone_id?: string
  zone_name?: string
  is_zone_master?: boolean
  ip_address: string
  mac_address: string
  firmware_version?: string
  hardware_type?: string
  capabilities?: Record<string, unknown>
}

export interface ESPHealthResponse {
  success: boolean
  device_id: string
  status: string
  metrics?: {
    uptime: number
    heap_free: number
    wifi_rssi: number
    sensor_count: number
    actuator_count: number
    timestamp: number
  }
  last_seen?: string
  uptime_formatted?: string
}

export interface ESPCommandResponse {
  success: boolean
  device_id: string
  command: string
  command_sent?: boolean
  result?: Record<string, unknown>
  error?: string
}

export interface ESPConfigResponse {
  success: boolean
  device_id: string
  config_sent: boolean
  config_acknowledged?: boolean
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Check if an ESP ID is a Mock ESP
 */
function isMockEsp(espId: string): boolean {
  return (
    espId.startsWith('ESP_MOCK_') ||
    espId.startsWith('MOCK_')
  )
}

/**
 * Normalize ESP ID (handle both device_id and esp_id)
 */
function normalizeEspId(device: ESPDevice | string): string {
  if (typeof device === 'string') {
    return device
  }
  return device.device_id || device.esp_id || ''
}

// =============================================================================
// Sensor Config → MockSensor Mapping
// =============================================================================

/**
 * Map SensorConfigResponse (from /sensors API) to MockSensor format
 * used by ESPOrbitalLayout and SensorSatellite components.
 *
 * This bridges the gap between DB sensor configs and the in-memory
 * Mock ESP sensor format that the UI components expect.
 */
function mapSensorConfigToMockSensor(config: SensorConfigResponse): MockSensor {
  const metadata = config.metadata ?? null
  const metadataLatestValue =
    metadata && typeof metadata['latest_value'] === 'number'
      ? metadata['latest_value']
      : null
  const metadataLatestQuality =
    metadata && typeof metadata['latest_quality'] === 'string'
      ? metadata['latest_quality']
      : null
  const metadataLatestTimestamp =
    metadata && typeof metadata['latest_timestamp'] === 'string'
      ? metadata['latest_timestamp']
      : null

  // Keep "no measurement yet" as null so UI can show "Keine Daten" instead of a fake 0.
  const latestValue = config.latest_value ?? metadataLatestValue ?? null
  const latestQuality = (config.latest_quality ?? metadataLatestQuality ?? 'good') as QualityLevel
  const latestTimestamp = config.latest_timestamp ?? metadataLatestTimestamp ?? null

  return {
    config_id: config.id,
    gpio: config.gpio,
    sensor_type: config.sensor_type,
    name: config.name || null,
    raw_value: latestValue,
    unit: getSensorUnit(config.sensor_type),
    quality: latestQuality,
    raw_mode: true,
    last_read: latestTimestamp,
    operating_mode: config.processing_mode as MockSensor['operating_mode'],
    config_status: config.config_status as MockSensor['config_status'],
    config_error: config.config_error || null,
    config_error_detail: config.config_error_detail || null,
    i2c_address: config.i2c_address ?? null,
    subzone_id: config.subzone_id ?? null,
    device_scope: config.device_scope ?? null,
    assigned_zones: config.assigned_zones ?? null,
  }
}

/**
 * Fetch sensor configs for real (DB) devices and attach as sensors[].
 *
 * Without this enrichment, DB devices only have sensor_count (integer)
 * but no sensors[] array, causing SensorSatellite cards to not render.
 */
async function enrichDbDevicesWithSensors(devices: ESPDevice[]): Promise<void> {
  // Collect device IDs with sensors
  const devicesWithSensors = devices.filter(d => (d.sensor_count ?? 0) > 0)

  if (devicesWithSensors.length === 0) return

  try {
    // Fetch all sensor configs in one call (server max page_size is 100)
    const { data: allSensors } = await sensorsApi.list({ page_size: 100 })

    // Group sensors by ESP device ID
    const sensorsByEsp = new Map<string, MockSensor[]>()
    for (const sensorConfig of allSensors) {
      const espId = sensorConfig.esp_device_id || sensorConfig.esp_id
      if (!espId) continue

      if (!sensorsByEsp.has(espId)) {
        sensorsByEsp.set(espId, [])
      }
      sensorsByEsp.get(espId)!.push(mapSensorConfigToMockSensor(sensorConfig))
    }

    // Attach sensors to devices
    for (const device of devicesWithSensors) {
      const deviceId = device.device_id || device.esp_id || ''
      const sensors = sensorsByEsp.get(deviceId)
      if (sensors && sensors.length > 0) {
        device.sensors = sensors
        device.sensor_count = sensors.length
        logger.debug(`Enriched ${deviceId} with ${sensors.length} sensors`)
      }
    }

    logger.info(`Enriched ${devicesWithSensors.length} DB devices with sensor data`)
  } catch (err) {
    logger.error('Failed to enrich DB devices with sensors - sensor cards may be empty until live data arrives', err)
  }
}

/**
 * Map ActuatorConfigResponse to MockActuator shape expected by components.
 */
function mapActuatorConfigToMockActuator(config: ActuatorConfigResponse): MockActuator {
  return {
    gpio: config.gpio,
    actuator_type: config.actuator_type,
    name: config.name || null,
    state: config.is_active ?? false,
    pwm_value: config.current_value ?? 0,
    emergency_stopped: false,
    last_command_at: config.last_command_at || null,
    subzone_id: config.subzone_id ?? null,
    config_status: config.config_status as MockActuator['config_status'],
    config_error: config.config_error || null,
    config_error_detail: config.config_error_detail || null,
    device_scope: config.device_scope ?? null,
    assigned_zones: config.assigned_zones ?? null,
  }
}

/**
 * Fetch actuator configs for real (DB) devices and attach as actuators[].
 *
 * Without this enrichment, DB devices only have actuator_count (integer)
 * but no actuators[] array, causing Rule Builder to show "no actuators" fallback.
 */
async function enrichDbDevicesWithActuators(devices: ESPDevice[]): Promise<void> {
  const devicesWithActuators = devices.filter(d => (d.actuator_count ?? 0) > 0)

  if (devicesWithActuators.length === 0) return

  try {
    const { data: allActuators } = await actuatorsApi.list({ page_size: 100 })

    const actuatorsByEsp = new Map<string, MockActuator[]>()
    for (const actuatorConfig of allActuators) {
      const espId = actuatorConfig.esp_device_id || actuatorConfig.esp_id
      if (!espId) continue

      if (!actuatorsByEsp.has(espId)) {
        actuatorsByEsp.set(espId, [])
      }
      actuatorsByEsp.get(espId)!.push(mapActuatorConfigToMockActuator(actuatorConfig))
    }

    for (const device of devicesWithActuators) {
      const deviceId = device.device_id || device.esp_id || ''
      const actuators = actuatorsByEsp.get(deviceId)
      if (actuators && actuators.length > 0) {
        device.actuators = actuators
        device.actuator_count = actuators.length
        logger.debug(`Enriched ${deviceId} with ${actuators.length} actuators`)
      }
    }

    logger.info(`Enriched ${devicesWithActuators.length} DB devices with actuator data`)
  } catch (err) {
    logger.error('Failed to enrich DB devices with actuators - rule builder may show manual input fallback', err)
  }
}

// =============================================================================
// Unified ESP API
// =============================================================================

export const espApi = {
  /**
   * List all ESP devices (Mock + Real)
   *
   * IMPORTANT: Mock ESPs exist in both in-memory store AND database.
   * This function deduplicates by preferring the in-memory mock data
   * (which has richer state like sensors, actuators, system_state).
   */
  async listDevices(params?: {
    zone_id?: string
    status?: string
    hardware_type?: string
    page?: number
    page_size?: number
  }): Promise<ESPDevice[]> {
    // Fetch both Mock and Real ESPs in parallel
    // Mock ESP fetch is non-critical (graceful fallback to empty)
    // DB device fetch failure is propagated to caller for proper error handling
    let dbFetchError: Error | null = null
    const [mockEsps, dbDevices] = await Promise.all([
      debugApi.listMockEsps().catch((err) => {
        logger.warn('Failed to fetch mock ESPs (non-critical)', err)
        return [] as MockESP[]
      }),
      api
        .get<ESPDeviceListResponse>('/esp/devices', { params })
        .catch((err) => {
          logger.error('Failed to fetch DB devices - dashboard may show incomplete data', err)
          dbFetchError = err instanceof Error ? err : new Error(String(err))
          return { data: { success: false, data: [] } }
        })
        .then((res) => (res.data?.data || []) as ESPDevice[]),
    ])

    // If DB fetch failed and no mock ESPs available, propagate the error
    if (dbFetchError && mockEsps.length === 0) {
      throw dbFetchError
    }

    logger.info(`listDevices: ${mockEsps.length} mocks, ${dbDevices.length} DB devices`)

    // DEBUG: Log raw mock ESP data from server to verify name field
    if (mockEsps.length > 0) {
      logger.debug('Raw Mock ESP data from debug API', {
        mocks: mockEsps.map(m => ({ esp_id: m.esp_id, name: m.name, zone_id: m.zone_id }))
      })
    }

    // Create Set of mock ESP IDs for fast lookup
    const mockEspIds = new Set(mockEsps.map((m) => m.esp_id))

    // Build subzone lookup from DB devices (T14-Fix-F: Mock ESPs need DB subzones)
    const dbSubzonesByDeviceId = new Map<string, SubzoneSummary[]>()
    for (const dbDev of dbDevices) {
      const devId = dbDev.device_id || dbDev.esp_id || ''
      if (devId && dbDev.subzones?.length) {
        dbSubzonesByDeviceId.set(devId, dbDev.subzones)
      }
    }

    // Normalize Mock ESPs to unified format (rich data from in-memory store)
    const normalizedMockEsps: ESPDevice[] = mockEsps.map((mock) => ({
      id: mock.esp_id,
      device_id: mock.esp_id,
      esp_id: mock.esp_id,
      name: mock.name || null,  // Now properly passed from server
      zone_id: mock.zone_id || null,
      zone_name: mock.zone_name || null,
      master_zone_id: mock.master_zone_id || null,
      is_zone_master: false,
      hardware_type: mock.hardware_type || 'MOCK_ESP32',
      status: mock.connected ? 'online' : 'offline',
      system_state: mock.system_state,
      sensors: mock.sensors,
      actuators: mock.actuators,
      auto_heartbeat: mock.auto_heartbeat,
      heap_free: mock.heap_free,
      wifi_rssi: mock.wifi_rssi,
      uptime: mock.uptime,
      last_heartbeat: mock.last_heartbeat,
      last_seen: mock.last_heartbeat,
      connected: mock.connected,
      sensor_count: mock.sensors?.length || 0,
      actuator_count: mock.actuators?.length || 0,
      created_at: mock.created_at,
      subzones: dbSubzonesByDeviceId.get(mock.esp_id) || [],
    }))

    // Filter DB devices: exclude those that exist in mock store (prevent duplicates)
    // But mark mock IDs that only exist in DB as "orphaned"
    const filteredDbDevices = dbDevices
      .filter((device) => {
        const deviceId = device.device_id || device.esp_id || ''
        // If it's in the mock store, skip it (we already have richer data)
        if (mockEspIds.has(deviceId)) {
          logger.debug(`Filtering out DB device ${deviceId} (exists in mock store)`)
          return false
        }
        return true
      })
      .map((device) => {
        const deviceId = device.device_id || device.esp_id || ''
        // Mark mock-pattern IDs that aren't in mock store as orphaned
        if (isMockEsp(deviceId)) {
          logger.debug(`Marking ${deviceId} as orphaned mock (not in mock store)`)
          return {
            ...device,
            metadata: { ...device.metadata, orphaned_mock: true },
          }
        }
        return device
      })

    // Enrich DB devices with sensor configs (so SensorSatellite cards render)
    // Mock ESPs already have sensors[] from debug store; DB devices only have sensor_count
    await enrichDbDevicesWithSensors(filteredDbDevices)
    // Enrich DB devices with actuator configs (so Rule Builder actuator dropdown works)
    await enrichDbDevicesWithActuators(filteredDbDevices)

    const result = [...normalizedMockEsps, ...filteredDbDevices]
    logger.debug(`Returning ${result.length} devices (${normalizedMockEsps.length} mocks + ${filteredDbDevices.length} filtered DB)`)

    // Combine: Mock ESPs first (active), then real/orphaned
    return result
  },

  /**
   * Get a specific ESP device (Mock or Real)
   *
   * Handles orphaned mock devices by falling back to database if debug API returns 404
   */
  async getDevice(espId: string): Promise<ESPDevice> {
    const normalizedId = normalizeEspId(espId)

    if (isMockEsp(normalizedId)) {
      try {
        const mockEsp = await debugApi.getMockEsp(normalizedId)

        const result: ESPDevice = {
          id: mockEsp.esp_id,
          device_id: mockEsp.esp_id,
          esp_id: mockEsp.esp_id,
          name: mockEsp.name || null,  // Now properly passed from server
          zone_id: mockEsp.zone_id || null,
          zone_name: mockEsp.zone_name || null, // Map zone_name from Mock ESP
          master_zone_id: mockEsp.master_zone_id || null,
          is_zone_master: false,
          hardware_type: mockEsp.hardware_type || 'MOCK_ESP32',
          status: mockEsp.connected ? 'online' : 'offline',
          system_state: mockEsp.system_state,
          sensors: mockEsp.sensors,
          actuators: mockEsp.actuators,
          auto_heartbeat: mockEsp.auto_heartbeat,
          heap_free: mockEsp.heap_free,
          wifi_rssi: mockEsp.wifi_rssi,
          uptime: mockEsp.uptime,
          last_heartbeat: mockEsp.last_heartbeat,
          last_seen: mockEsp.last_heartbeat,
          connected: mockEsp.connected,
          sensor_count: mockEsp.sensors?.length || 0,
          actuator_count: mockEsp.actuators?.length || 0,
          created_at: mockEsp.created_at,
        }
        return result
      } catch (err: unknown) {
        const axiosError = err as { response?: { status?: number } }

        // If 404: device might exist in DB only (orphaned mock)
        if (axiosError.response?.status === 404) {
          logger.warn(`Mock ESP ${normalizedId} not in debug store, trying database...`)
          const response = await api.get<ESPDevice>(`/esp/devices/${normalizedId}`)
          // Mark as orphaned mock for UI indication
          return {
            ...response.data,
            metadata: { ...response.data.metadata, orphaned_mock: true },
          }
        }
        throw err
      }
    } else {
      const response = await api.get<ESPDevice>(`/esp/devices/${normalizedId}`)
      const device = response.data

      // Enrich real device with sensor configs (same as in listDevices)
      if ((device.sensor_count ?? 0) > 0 && !device.sensors?.length) {
        await enrichDbDevicesWithSensors([device])
      }
      // Enrich real device with actuator configs (same as in listDevices)
      if ((device.actuator_count ?? 0) > 0 && !device.actuators?.length) {
        await enrichDbDevicesWithActuators([device])
      }

      return device
    }
  },

  /**
   * Create a new ESP device (Mock or Real)
   */
  async createDevice(config: ESPDeviceCreate | MockESPCreate): Promise<ESPDevice> {
    // Check if it's a Mock ESP create request
    const mockConfig = config as MockESPCreate
    if (mockConfig.esp_id && isMockEsp(mockConfig.esp_id)) {
      const mockEsp = await debugApi.createMockEsp(mockConfig)
      return {
        id: mockEsp.esp_id,
        device_id: mockEsp.esp_id,
        esp_id: mockEsp.esp_id,
        name: mockEsp.name || null,  // Now properly passed from server
        zone_id: mockEsp.zone_id || null,
        zone_name: mockEsp.zone_name || null, // Map zone_name from Mock ESP
        master_zone_id: mockEsp.master_zone_id || null,
        is_zone_master: false,
        hardware_type: mockEsp.hardware_type || 'MOCK_ESP32',
        status: mockEsp.connected ? 'online' : 'offline',
        system_state: mockEsp.system_state,
        sensors: mockEsp.sensors,
        actuators: mockEsp.actuators,
        auto_heartbeat: mockEsp.auto_heartbeat,
        heap_free: mockEsp.heap_free,
        wifi_rssi: mockEsp.wifi_rssi,
        uptime: mockEsp.uptime,
        last_heartbeat: mockEsp.last_heartbeat,
        last_seen: mockEsp.last_heartbeat,
        connected: mockEsp.connected,
        sensor_count: mockEsp.sensors?.length || 0,
        actuator_count: mockEsp.actuators?.length || 0,
        created_at: mockEsp.created_at,
      }
    } else {
      const realConfig = config as ESPDeviceCreate
      const response = await api.post<ESPDevice>('/esp/devices', realConfig)
      return response.data
    }
  },

  /**
   * Update an ESP device (Mock or Real)
   *
   * Mock ESPs are registered in the database (see debug.py:create_mock_esp)
   * and can be updated via the normal ESP API.
   */
  async updateDevice(
    espId: string,
    update: ESPDeviceUpdate
  ): Promise<ESPDevice> {
    const normalizedId = normalizeEspId(espId)

    // Both Mock and Real ESPs are in the database and can be updated via the normal API
    // Mock ESPs are registered in DB when created (debug.py lines 104-146)
    try {
      logger.debug(`Sending PATCH to /esp/devices/${normalizedId}`, update)
      const response = await api.patch<ESPDevice>(
        `/esp/devices/${normalizedId}`,
        update
      )
      logger.debug('Server response', {
        status: response.status,
        name: response.data.name,
        device_id: response.data.device_id,
        fullData: response.data,
      })
      return response.data
    } catch (err: unknown) {
      const axiosError = err as { response?: { status?: number } }

      // If 404 and it's a Mock ESP, it might only exist in the debug store
      // This can happen if the server was restarted (DB cleared) but UI still has cached data
      if (axiosError.response?.status === 404 && isMockEsp(normalizedId)) {
        logger.warn(
          `Mock ESP ${normalizedId} not found in database. ` +
          `It may need to be recreated. Fetching current state from debug store...`
        )

        // Try to get current state from debug store
        try {
          const current = await debugApi.getMockEsp(normalizedId)
          return {
            id: current.esp_id,
            device_id: current.esp_id,
            esp_id: current.esp_id,
            name: current.name || null,  // Now properly passed from server
            zone_id: current.zone_id || null,
            zone_name: current.zone_name || null,
            master_zone_id: current.master_zone_id || null,
            is_zone_master: false,
            hardware_type: current.hardware_type || 'MOCK_ESP32',
            status: current.connected ? 'online' : 'offline',
            system_state: current.system_state,
            sensors: current.sensors,
            actuators: current.actuators,
            auto_heartbeat: current.auto_heartbeat,
            heap_free: current.heap_free,
            wifi_rssi: current.wifi_rssi,
            uptime: current.uptime,
            last_heartbeat: current.last_heartbeat,
            last_seen: current.last_heartbeat,
            connected: current.connected,
            sensor_count: current.sensors?.length || 0,
            actuator_count: current.actuators?.length || 0,
            created_at: current.created_at,
            metadata: { db_sync_required: true, message: 'Mock ESP exists in debug store but not in database' },
          }
        } catch {
          // Not in debug store either - device truly doesn't exist
          throw err
        }
      }
      throw err
    }
  },

  /**
   * Delete an ESP device (Mock or Real)
   *
   * Handles orphaned mock devices that exist in DB but not in debug store:
   * - First tries debug API for mock devices
   * - Falls back to database deletion if debug API returns 404
   */
  async deleteDevice(espId: string): Promise<void> {
    const normalizedId = normalizeEspId(espId)

    if (isMockEsp(normalizedId)) {
      try {
        // Try debug API first (in-memory mock store)
        await debugApi.deleteMockEsp(normalizedId)
      } catch (err: unknown) {
        const axiosError = err as { response?: { status?: number } }

        // If 404: device exists in DB but not in mock store (orphaned)
        // Try to delete from database directly
        if (axiosError.response?.status === 404) {
          logger.warn(`Mock ESP ${normalizedId} not found in debug store, trying database deletion...`)
          try {
            await api.delete(`/esp/devices/${normalizedId}`)
            logger.info(`Successfully deleted orphaned mock ESP ${normalizedId} from database`)
            return
          } catch (dbErr: unknown) {
            const dbAxiosError = dbErr as { response?: { status?: number } }
            // If also 404 in DB, device is already gone - consider success
            if (dbAxiosError.response?.status === 404) {
              logger.info(`Mock ESP ${normalizedId} already deleted from database`)
              return
            }
            throw new Error(`Konnte verwaisten Mock ESP nicht löschen: ${normalizedId}. Das Gerät existiert möglicherweise nur noch im UI-Cache.`)
          }
        }
        throw err
      }
    } else {
      // Real ESP - delete from database
      await api.delete(`/esp/devices/${normalizedId}`)
    }
  },

  /**
   * Get ESP health metrics
   */
  async getHealth(espId: string): Promise<ESPHealthResponse> {
    const normalizedId = normalizeEspId(espId)

    if (isMockEsp(normalizedId)) {
      const mockEsp = await debugApi.getMockEsp(normalizedId)
      return {
        success: true,
        device_id: mockEsp.esp_id,
        status: mockEsp.connected ? 'online' : 'offline',
        metrics: {
          uptime: mockEsp.uptime,
          heap_free: mockEsp.heap_free,
          wifi_rssi: mockEsp.wifi_rssi,
          sensor_count: mockEsp.sensors?.length || 0,
          actuator_count: mockEsp.actuators?.length || 0,
          timestamp: Math.floor(Date.now() / 1000),
        },
        last_seen: mockEsp.last_heartbeat ?? undefined,
      }
    } else {
      const response = await api.get<ESPHealthResponse>(
        `/esp/devices/${normalizedId}/health`
      )
      return response.data
    }
  },

  /**
   * Restart an ESP device
   *
   * Note: Mock ESPs don't support restart commands. The response will indicate
   * that no command was sent.
   */
  async restartDevice(
    espId: string,
    delaySeconds?: number,
    reason?: string
  ): Promise<ESPCommandResponse> {
    const normalizedId = normalizeEspId(espId)

    if (isMockEsp(normalizedId)) {
      // Mock ESPs don't have restart endpoint - be honest about it
      logger.info(`Restart command not available for Mock ESP ${normalizedId}`)
      return {
        success: false, // Changed to false - command wasn't actually executed
        device_id: normalizedId,
        command: 'restart',
        command_sent: false,
        error: 'Mock ESPs unterstützen keine Restart-Befehle. Dies ist ein simuliertes Gerät.',
      }
    } else {
      const response = await api.post<ESPCommandResponse>(
        `/esp/devices/${normalizedId}/restart`,
        { delay_seconds: delaySeconds || 0, reason }
      )
      return response.data
    }
  },

  /**
   * Factory reset an ESP device
   *
   * Note: Mock ESPs don't support factory reset. The response will indicate
   * that no command was sent.
   */
  async resetDevice(
    espId: string,
    preserveWifi: boolean = false
  ): Promise<ESPCommandResponse> {
    const normalizedId = normalizeEspId(espId)

    if (isMockEsp(normalizedId)) {
      // Mock ESPs don't have reset endpoint - be honest about it
      logger.info(`Factory reset command not available for Mock ESP ${normalizedId}`)
      return {
        success: false, // Changed to false - command wasn't actually executed
        device_id: normalizedId,
        command: 'reset',
        command_sent: false,
        error: 'Mock ESPs unterstützen keine Reset-Befehle. Zum Zurücksetzen bitte löschen und neu erstellen.',
      }
    } else {
      const response = await api.post<ESPCommandResponse>(
        `/esp/devices/${normalizedId}/reset`,
        { confirm: true, preserve_wifi: preserveWifi }
      )
      return response.data
    }
  },

  // ===========================================================================
  // ESP32 Config-Push Architektur
  // ===========================================================================
  //
  // Config-Push zu ESP32-Geräten erfolgt AUTOMATISCH durch das Backend nach
  // Sensor/Actuator CRUD-Operationen. Das Frontend muss keinen separaten
  // Config-Push triggern.
  //
  // Ablauf:
  //   1. Frontend ruft sensorsApi.create() oder actuatorsApi.create() auf
  //   2. Backend speichert in DB und triggert automatisch Config-Push
  //   3. ESP32 erhält Config via MQTT
  //
  // Für manuelle Konfiguration einzelner Sensoren/Aktoren die entsprechenden
  // CRUD-Methoden in sensorsApi und actuatorsApi verwenden.
  // ===========================================================================

  /**
   * Get GPIO status for an ESP device.
   *
   * Returns available, reserved, and system GPIOs for the device.
   * Used by GPIO picker components and validation.
   *
   * Note: Works for both Mock and Real ESPs - server provides GPIO status for all devices.
   *
   * @param espId - ESP device ID (e.g., "ESP_12AB34CD")
   * @returns GPIO status with available/reserved/system pins
   * @throws ApiError on network or server error
   */
  async getGpioStatus(espId: string): Promise<GpioStatusResponse> {
    const normalizedId = normalizeEspId(espId)
    const response = await api.get<GpioStatusResponse>(
      `/esp/devices/${normalizedId}/gpio-status`
    )
    return response.data
  },

  /**
   * Check if ESP is Mock
   */
  isMockEsp(espId: string): boolean {
    return isMockEsp(espId)
  },

  // ===========================================================================
  // Discovery/Approval API (Phase: Device Discovery)
  // ===========================================================================

  /**
   * Get list of pending (unapproved) devices.
   * 
   * @returns Array of pending devices awaiting approval
   */
  async getPendingDevices(): Promise<PendingESPDevice[]> {
    const response = await api.get<PendingDevicesListResponse>('/esp/devices/pending')
    return response.data.devices || []
  },

  /**
   * Approve a pending device.
   * 
   * @param deviceId - Device ID to approve (e.g., "ESP_D0B19C")
   * @param data - Optional approval data (name, zone assignment)
   * @returns Approval response with device status
   */
  async approveDevice(
    deviceId: string,
    data?: ESPApprovalRequest
  ): Promise<ESPApprovalResponse> {
    const response = await api.post<ESPApprovalResponse>(
      `/esp/devices/${deviceId}/approve`,
      data || {}
    )
    return response.data
  },

  /**
   * Reject a pending device.
   * 
   * Device will enter cooldown (5 minutes) before it can be rediscovered.
   * 
   * @param deviceId - Device ID to reject
   * @param reason - Reason for rejection (required)
   * @returns Rejection response with cooldown info
   */
  async rejectDevice(
    deviceId: string,
    reason: string
  ): Promise<ESPApprovalResponse> {
    const data: ESPRejectionRequest = { reason }
    const response = await api.post<ESPApprovalResponse>(
      `/esp/devices/${deviceId}/reject`,
      data
    )
    return response.data
  },

  // =========================================================================
  // Device-Level Alert Configuration (Phase 4A.7)
  // =========================================================================

  async getAlertConfig(espId: string): Promise<import('./sensors').AlertConfigResponse> {
    const response = await api.get<import('./sensors').AlertConfigResponse>(
      `/esp/devices/${espId}/alert-config`
    )
    return response.data
  },

  async updateAlertConfig(
    espId: string,
    config: DeviceAlertConfigUpdate
  ): Promise<import('./sensors').AlertConfigResponse> {
    const response = await api.patch<import('./sensors').AlertConfigResponse>(
      `/esp/devices/${espId}/alert-config`,
      config
    )
    return response.data
  },
}

export interface DeviceAlertConfigUpdate {
  alerts_enabled?: boolean
  suppression_reason?: string
  suppression_note?: string
  suppression_until?: string | null
  propagate_to_children?: boolean
}



