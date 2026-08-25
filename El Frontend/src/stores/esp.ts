/**
 * Unified ESP Store
 * 
 * Manages both Mock and Real ESP devices in a unified way.
 * Automatically routes API calls based on ESP type detection.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { espApi, type ESPDevice, type ESPDeviceUpdate, type ESPDeviceCreate } from '@/api/esp'
import { debugApi } from '@/api/debug'
import { sensorsApi } from '@/api/sensors'
import { actuatorsApi } from '@/api/actuators'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import { useWebSocket } from '@/composables/useWebSocket'
import { getESPStatus } from '@/composables/useESPStatus'
import { websocketService, type WebSocketMessage } from '@/services/websocket'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import type {
  MockSystemState, MockSensorConfig, MockActuatorConfig, QualityLevel,
  MockESPCreate, OfflineInfo, OfflineReason,
  StatusSource, SensorConfigCreate, ActuatorConfigCreate, MockSensor, MockActuator,
  HeartbeatGpioItem,
  PendingESPDevice, ESPApprovalRequest, ESPApprovalResponse,
  DeviceDiscoveredPayload, DeviceApprovedPayload, DeviceRejectedPayload
} from '@/types'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useDeviceContextStore } from '@/shared/stores/deviceContext.store'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { useSensorStore } from '@/shared/stores/sensor.store'
import { useGpioStore } from '@/shared/stores/gpio.store'
import { useNotificationStore } from '@/shared/stores/notification.store'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { useIntentSignalsStore } from '@/shared/stores/intentSignals.store'
import { ESP_STORE_WS_SUBSCRIPTION_TYPES } from '@/stores/esp-websocket-subscription'
import { normalizeEspHealthPayload } from '@/domain/esp/espHealth'
import { useConfigStore } from '@/shared/stores/config.store'
import {
  inferInterfaceType,
  getDefaultI2CAddress
} from '@/utils/sensorDefaults'
import {
  extractConfigRejectFromConfigFailed,
  extractConfigRejectFromIntentOutcome,
  type ConfigRejectSnapshot,
} from '@/utils/contractEventMapper'
import type { ConfigLastReject } from '@/types'
import { normalizeSubzoneId } from '@/utils/subzoneHelpers'
import { isPwmActuator } from '@/utils/actuatorDefaults'
import {
  isDeviceFlapping,
  countRecentDisconnects,
  pruneOldTimestamps,
} from '@/composables/monitorConnectivity'

/**
 * Extract error message from Axios error response.
 */
function extractErrorMessage(err: unknown, fallback: string): string {
  return formatUiApiError(toUiApiError(err, fallback))
}

// ============================================================
// LIVE-STATE MERGE HELPERS
// fetchDevice / fetchAll replace the device with a DB snapshot.
// WS events update in-memory state in real-time and are more
// authoritative for live fields (last_seen, status, connected).
// These helpers prevent a stale DB snapshot from downgrading an
// actively-online device to "offline".
// ============================================================

/**
 * Returns the more recent of two ISO timestamp strings.
 * Falls back to the non-null one when parsing fails.
 */
function pickFresherIso(
  incoming: string | null | undefined,
  existing: string | null | undefined,
): string | null | undefined {
  if (!existing) return incoming ?? null
  if (!incoming) return existing
  const a = Date.parse(incoming)
  const b = Date.parse(existing)
  if (!Number.isFinite(a)) return existing
  if (!Number.isFinite(b)) return incoming
  return a >= b ? incoming : existing
}

// Must match HEARTBEAT_OFFLINE_MS in useESPStatus.ts (3.5 min).
const LIVE_STATUS_MAX_AGE_MS = 210_000

/**
 * If the in-memory device was recently seen as online/stale (WS-authoritative),
 * don't let a DB snapshot downgrade it to offline.
 * Returns the existing status when it is still fresh; otherwise returns the API status.
 */
function keepFreshOnlineStatus(
  apiStatus: string | undefined,
  existingStatus: string | undefined,
  fresherLastSeen: string | null | undefined,
): string | undefined {
  if (
    (existingStatus === 'online' || existingStatus === 'stale') &&
    fresherLastSeen
  ) {
    const age = Date.now() - Date.parse(fresherLastSeen)
    if (Number.isFinite(age) && age < LIVE_STATUS_MAX_AGE_MS) {
      return existingStatus
    }
  }
  return apiStatus
}

function normalizeSensorTypeForMerge(sensorType: string | undefined | null): string {
  return (sensorType ?? '').trim().toLowerCase()
}

function sensorLiveTimestampMs(sensor: MockSensor): number | null {
  const candidates = [sensor.last_event_at, sensor.last_read, sensor.last_reading_at]
  let best: number | null = null
  for (const ts of candidates) {
    if (!ts) continue
    const ms = Date.parse(ts)
    if (!Number.isFinite(ms)) continue
    if (best === null || ms > best) best = ms
  }
  return best
}

function sensorsMatchForLiveMerge(existing: MockSensor, incoming: MockSensor): boolean {
  if (existing.config_id && incoming.config_id) {
    return existing.config_id === incoming.config_id
  }
  if (existing.gpio !== incoming.gpio) return false
  if (normalizeSensorTypeForMerge(existing.sensor_type) !== normalizeSensorTypeForMerge(incoming.sensor_type)) {
    return false
  }
  if (existing.i2c_address != null && incoming.i2c_address != null) {
    return existing.i2c_address === incoming.i2c_address
  }
  if (existing.onewire_address && incoming.onewire_address) {
    return existing.onewire_address === incoming.onewire_address
  }
  return true
}

/**
 * Preserve in-memory WS sensor readings when a DB snapshot from fetchAll/fetchDevice
 * is older than the live store (AUT-580: visibility/login resync must not freeze UI).
 */
function mergeLiveSensorLists(
  incoming: MockSensor[],
  existing: MockSensor[] | undefined,
): MockSensor[] {
  if (!existing?.length) return incoming
  return incoming.map((incomingSensor) => {
    const liveSensor = existing.find((candidate) => sensorsMatchForLiveMerge(candidate, incomingSensor))
    if (!liveSensor) return incomingSensor

    const incomingMs = sensorLiveTimestampMs(incomingSensor)
    const liveMs = sensorLiveTimestampMs(liveSensor)
    if (liveMs === null || (incomingMs !== null && incomingMs >= liveMs)) {
      return incomingSensor
    }

    return {
      ...incomingSensor,
      raw_value: liveSensor.raw_value ?? incomingSensor.raw_value,
      processed_value: liveSensor.processed_value ?? incomingSensor.processed_value,
      quality: liveSensor.quality ?? incomingSensor.quality,
      unit: liveSensor.unit ?? incomingSensor.unit,
      last_read: pickFresherIso(incomingSensor.last_read, liveSensor.last_read) ?? incomingSensor.last_read,
      last_event_at: pickFresherIso(incomingSensor.last_event_at, liveSensor.last_event_at) ?? incomingSensor.last_event_at,
      last_reading_at: pickFresherIso(incomingSensor.last_reading_at, liveSensor.last_reading_at) ?? incomingSensor.last_reading_at,
      // AUT-1010 F4: is_multi_value + multi_values must stay an atomic pair from one
      // source — never flag from the REST snapshot with values from the live state.
      ...(liveSensor.is_multi_value && liveSensor.multi_values
        ? { is_multi_value: true, multi_values: liveSensor.multi_values }
        : { is_multi_value: incomingSensor.is_multi_value, multi_values: incomingSensor.multi_values }),
      is_stale: liveSensor.is_stale ?? incomingSensor.is_stale,
      metadata: liveSensor.metadata ?? incomingSensor.metadata,
    }
  })
}

function actuatorLiveTimestampMs(actuator: MockActuator): number | null {
  if (!actuator.last_command_at) return null
  const ms = Date.parse(actuator.last_command_at)
  return Number.isFinite(ms) ? ms : null
}

function mergeLiveActuatorLists(
  incoming: MockActuator[],
  existing: MockActuator[] | undefined,
  espId: string,
  actStore: ReturnType<typeof useActuatorStore>,
): MockActuator[] {
  return incoming.map((incomingActuator) => {
    if (existing && actStore.isActuatorCommandPending(espId, incomingActuator.gpio)) {
      const liveActuator = existing.find((candidate) => candidate.gpio === incomingActuator.gpio)
      return liveActuator
        ? {
            ...incomingActuator,
            state: liveActuator.state,
            pwm_value: liveActuator.pwm_value,
            last_command_at:
              pickFresherIso(incomingActuator.last_command_at, liveActuator.last_command_at)
              ?? liveActuator.last_command_at
              ?? incomingActuator.last_command_at,
          }
        : incomingActuator
    }

    const liveActuator = existing?.find((candidate) => candidate.gpio === incomingActuator.gpio)
    if (!liveActuator) return incomingActuator

    const incomingMs = actuatorLiveTimestampMs(incomingActuator)
    const liveMs = actuatorLiveTimestampMs(liveActuator)
    if (liveMs === null || (incomingMs !== null && incomingMs >= liveMs)) {
      return incomingActuator
    }

    return {
      ...incomingActuator,
      state: liveActuator.state,
      pwm_value: liveActuator.pwm_value,
      emergency_stopped: liveActuator.emergency_stopped,
      last_command_at: pickFresherIso(incomingActuator.last_command_at, liveActuator.last_command_at) ?? incomingActuator.last_command_at,
    }
  })
}

// ============================================
// OFFLINE REASON HELPERS
// ============================================

/**
 * Generiert menschenlesbaren Text für Offline-Grund.
 *
 * @param source - Quelle der Offline-Erkennung
 * @param reason - Detaillierter Grund (optional)
 * @returns Menschenlesbarer deutscher Text
 */
function getOfflineDisplayText(source: StatusSource, reason?: string): string {
  switch (source) {
    case 'lwt':
      return 'Verbindung verloren'
    case 'heartbeat_timeout':
      return 'Keine Antwort'
    case 'api':
      return reason === 'shutdown' ? 'Heruntergefahren' : 'Offline'
    default:
      return 'Offline'
  }
}

/**
 * Mappt source zu OfflineReason.
 */
function getOfflineReason(source: StatusSource, reason?: string): OfflineReason {
  if (source === 'lwt') return 'lwt'
  if (source === 'heartbeat_timeout' || reason === 'heartbeat_timeout') return 'heartbeat_timeout'
  if (reason === 'shutdown') return 'shutdown'
  return 'unknown'
}

type ReconnectPhase = 'adopting' | 'adopted' | 'delta_enforced' | 'converged'

function parseStatusSource(source: unknown): StatusSource | undefined {
  if (source === 'lwt' || source === 'heartbeat' || source === 'heartbeat_timeout' || source === 'api') {
    return source
  }
  return undefined
}

function parseReconnectPhase(phase: unknown): ReconnectPhase | undefined {
  if (phase === 'adopting' || phase === 'adopted' || phase === 'delta_enforced' || phase === 'converged') {
    return phase
  }
  return undefined
}

export const useEspStore = defineStore('esp', () => {
  // Logger
  const logger = createLogger('ESPStore')

  // State
  const devices = ref<ESPDevice[]>([])
  /** Bumped on every live WS patch / snapshot replace so UI can depend on store freshness. */
  const devicesLiveTick = ref(0)
  const selectedDeviceId = ref<string | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // GPIO Status State → delegated to gpio.store.ts
  // Expose via computed for backward compatibility
  const gpioStore = useGpioStore()
  const gpioStatusMap = computed(() => gpioStore.gpioStatusMap)
  const gpioStatusLoading = computed(() => gpioStore.gpioStatusLoading)

  // =========================================================================
  // Pending Devices State (Discovery/Approval Phase)
  // =========================================================================
  const pendingDevices = ref<PendingESPDevice[]>([])
  const isPendingLoading = ref(false)

  // Track locally-initiated approvals to avoid duplicate fetchAll from WS echo
  const _recentlyApprovedByClient = ref<string | null>(null)
  const _recentlyApprovedAt = ref<number>(0)

  // WebSocket integration
  // Note: Server broadcasts these types from MQTT handlers:
  // - esp_health (heartbeat_handler.py)
  // - sensor_data (sensor_handler.py)
  // - actuator_status (actuator_handler.py)
  // - actuator_alert (actuator_alert_handler.py)
  // - config_response (config_handler.py)
  // - sensor_health (maintenance/jobs/sensor_health.py) - Phase 2E
  // - device_discovered, device_approved, device_rejected (Discovery/Approval Phase)
  const ws = useWebSocket({
    autoConnect: true,
    autoReconnect: true,
    filters: {
      // P0-A: must match every ws.on type in initWebSocket (see esp-websocket-subscription.ts)
      types: ESP_STORE_WS_SUBSCRIPTION_TYPES,
    },
  })

  // Store unsubscribe functions for cleanup
  const wsUnsubscribers: (() => void)[] = []
  let subzoneRefreshTimer: ReturnType<typeof setTimeout> | null = null

  // =========================================================================
  // Device Flapping Detection (PKG-20)
  // =========================================================================
  const _disconnectLog = new Map<string, number[]>()
  const _flappingTick = ref(0)
  let _flappingPruneTimer: ReturnType<typeof setInterval> | null = null

  function recordDisconnect(espId: string): void {
    let timestamps = _disconnectLog.get(espId)
    if (!timestamps) {
      timestamps = []
      _disconnectLog.set(espId, timestamps)
    }
    timestamps.push(Date.now())
    pruneOldTimestamps(timestamps)
    _flappingTick.value++
  }

  const flappingDeviceIds = computed<string[]>(() => {
    void _flappingTick.value
    const result: string[] = []
    const now = Date.now()
    for (const [espId, timestamps] of _disconnectLog) {
      if (isDeviceFlapping(timestamps, now)) {
        result.push(espId)
      }
    }
    return result
  })

  const flappingDeviceCount = computed(() => flappingDeviceIds.value.length)

  const hasFlappingDevices = computed(() => flappingDeviceCount.value > 0)

  function getDisconnectCount(espId: string): number {
    void _flappingTick.value
    const timestamps = _disconnectLog.get(espId)
    if (!timestamps) return 0
    return countRecentDisconnects(timestamps)
  }

  function getFlappingDevicesInZone(zoneId: string): string[] {
    return flappingDeviceIds.value.filter(espId => {
      const device = devices.value.find(d => getDeviceId(d) === espId)
      return device?.zone_id === zoneId
    })
  }

  // Getters
  const selectedDevice = computed(() =>
    devices.value.find(device => 
      (device.device_id || device.esp_id) === selectedDeviceId.value
    ) || null
  )

  const deviceCount = computed(() => devices.value.length)

  const onlineDevices = computed(() =>
    devices.value.filter(device => {
      const s = getESPStatus(device)
      return s === 'online' || s === 'stale'
    })
  )

  const offlineDevices = computed(() =>
    devices.value.filter(device => {
      const s = getESPStatus(device)
      return s !== 'online' && s !== 'stale'
    })
  )

  const mockDevices = computed(() =>
    devices.value.filter(device => 
      espApi.isMockEsp(device.device_id || device.esp_id || '')
    )
  )

  const realDevices = computed(() =>
    devices.value.filter(device => 
      !espApi.isMockEsp(device.device_id || device.esp_id || '')
    )
  )

  const devicesByZone = computed(() => (zoneId: string) =>
    devices.value.filter(device => device.zone_id === zoneId)
  )

  const unassignedDevices = computed(() =>
    devices.value.filter(device => !device.zone_id)
  )

  const masterZoneDevices = computed(() =>
    devices.value.filter(device => device.is_zone_master === true)
  )

  // Pending devices count for ActionBar badge
  const pendingCount = computed(() => pendingDevices.value.length)

/**
 * Check if device is Mock ESP
 */
function isMock(deviceId: string): boolean {
  return espApi.isMockEsp(deviceId)
}

/**
 * Find device by esp_id with UUID fallback (DEFENSIVE PROGRAMMING).
 *
 * CRITICAL: Server SHOULD always send device_id (e.g., "ESP_00000001").
 * However, if UUID slips through (e.g., "8f67d252-8aaa-4a87-9577-fb18e7ad7979"),
 * we try to match by internal id as a fallback.
 *
 * This prevents frontend breakage if server-side bug occurs.
 *
 * @param espId - Either device_id (expected) or UUID (fallback)
 * @returns Device index and device, or null if not found
 */
function findDeviceByEspIdDefensive(espId: string): { index: number; device: ESPDevice } | null {
  // Primary lookup: by device_id (expected)
  let index = devices.value.findIndex(d => getDeviceId(d) === espId)

  if (index !== -1) {
    return { index, device: devices.value[index] }
  }

  // Fallback: Check if espId looks like UUID (contains dashes and 36 chars)
  if (espId.includes('-') && espId.length === 36) {
    logger.warn(`Received UUID "${espId}" instead of device_id. ` +
      `Server should send device_id! Trying fallback lookup...`
    )

    // Try matching by internal id field (UUID from database)
    index = devices.value.findIndex(d => d.id === espId)

    if (index !== -1) {
      logger.info(`Fallback lookup successful: ${espId} → ${getDeviceId(devices.value[index])}`)
      return { index, device: devices.value[index] }
    }
  }

  return null
}

  /**
   * Get normalized device ID
   */
  function getDeviceId(device: ESPDevice): string {
    return device.device_id || device.esp_id || ''
  }

  function bumpDevicesLiveTick(): void {
    devicesLiveTick.value += 1
  }

  function replaceDevices(snapshot: ESPDevice[]): void {
    devices.value = snapshot
    bumpDevicesLiveTick()
  }

  function applyDevicePatch(
    espId: string,
    patchFn: (device: ESPDevice) => ESPDevice,
  ): boolean {
    const result = findDeviceByEspIdDefensive(espId)
    if (!result) return false
    const nextDevice = patchFn(result.device)
    devices.value[result.index] = nextDevice
    bumpDevicesLiveTick()
    return true
  }

  /**
   * Re-arm WS handlers + subscription after logout/login (Pinia store survives navigation).
   */
  async function ensureRealtimeHandlers(): Promise<void> {
    if (wsUnsubscribers.length === 0) {
      initWebSocket()
    }
    try {
      await ws.connect()
    } catch (err) {
      logger.error('Failed to ensure realtime WebSocket handlers', err)
    }
  }

  // =========================================================================
  // GPIO Status - delegated to gpio.store.ts
  // =========================================================================

  const getGpioStatusForEsp = gpioStore.getGpioStatusForEsp
  const getAvailableGpios = gpioStore.getAvailableGpios
  const getReservedGpios = gpioStore.getReservedGpios
  const isGpioAvailableForEsp = gpioStore.isGpioAvailableForEsp
  const getSystemPinName = gpioStore.getSystemPinName
  const getAllPinStatuses = gpioStore.getAllPinStatuses
  const fetchGpioStatus = gpioStore.fetchGpioStatus
  const clearGpioStatus = gpioStore.clearGpioStatus
  const updateGpioStatusFromHeartbeat = gpioStore.updateGpioStatusFromHeartbeat

  // =========================================================================
  // OneWire Scan - delegated to gpio.store.ts
  // =========================================================================

  const oneWireScanStates = computed(() => gpioStore.oneWireScanStates)
  const getOneWireScanState = gpioStore.getOneWireScanState
  const scanOneWireBus = gpioStore.scanOneWireBus
  const clearOneWireScan = gpioStore.clearOneWireScan
  const toggleRomSelection = gpioStore.toggleRomSelection
  const selectAllOneWireDevices = gpioStore.selectAllOneWireDevices
  const deselectAllOneWireDevices = gpioStore.deselectAllOneWireDevices
  const selectSpecificRomCodes = gpioStore.selectSpecificRomCodes
  const isRomCodeSelected = gpioStore.isRomCodeSelected

  // Actions
  async function fetchAll(params?: {
    zone_id?: string
    status?: string
    hardware_type?: string
    page?: number
    page_size?: number
  }): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      const fetchedDevices = await espApi.listDevices(params)

      logger.debug('fetchAll: Fetched devices:')
      fetchedDevices.forEach((d) => {
        logger.debug(`  - ${d.device_id || d.esp_id}: name="${d.name ?? '(unnamed)'}"`)
      })

      // Deduplicate by device ID (safety net for API-level deduplication failures)
      const seen = new Set<string>()
      const dedupedDevices: ESPDevice[] = []
      const actStore = useActuatorStore()

      for (const device of fetchedDevices) {
        const id = getDeviceId(device)
        if (id && !seen.has(id)) {
          seen.add(id)
          const existing = devices.value.find((candidate) => getDeviceId(candidate) === id)
          // Keep live WS payload data if the snapshot omits arrays temporarily.
          // Preserve optimistic actuator.state for any pending command intents so that
          // a WS reconnect + fetchAll does not overwrite an in-flight ON/OFF toggle.
          const incomingSensors = Array.isArray(device.sensors)
            ? device.sensors
            : (existing?.sensors ?? [])
          const incomingActuators = Array.isArray(device.actuators)
            ? device.actuators
            : (existing?.actuators ?? [])
          const mergedSensors = mergeLiveSensorLists(
            incomingSensors as MockSensor[],
            existing?.sensors as MockSensor[] | undefined,
          )
          const mergedActuators = mergeLiveActuatorLists(
            incomingActuators as MockActuator[],
            existing?.actuators as MockActuator[] | undefined,
            id,
            actStore,
          )
          // Preserve live WS-updated fields when they are fresher than the DB snapshot.
          const fresherLastSeen = existing
            ? pickFresherIso(device.last_seen, existing.last_seen)
            : device.last_seen
          const fresherLastHb = existing
            ? pickFresherIso(device.last_heartbeat, existing.last_heartbeat)
            : device.last_heartbeat
          const mergedDevice: ESPDevice = {
            ...device,
            sensors: mergedSensors,
            actuators: mergedActuators,
            last_seen: fresherLastSeen,
            last_heartbeat: fresherLastHb,
            status: existing
              ? keepFreshOnlineStatus(device.status, existing.status, fresherLastSeen)
              : device.status,
            connected: existing
              ? keepFreshOnlineStatus(device.status, existing.status, fresherLastSeen) === 'online'
                ? true
                : device.connected
              : device.connected,
          }
          dedupedDevices.push(mergedDevice)
        } else if (id) {
          logger.warn(`Duplicate device filtered: ${id}`)
        }
      }

      logger.info('Loaded devices', { count: dedupedDevices.length })
      replaceDevices(dedupedDevices)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to fetch ESP devices')
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function fetchDevice(deviceId: string): Promise<ESPDevice> {
    isLoading.value = true
    error.value = null

    try {
      const device = await espApi.getDevice(deviceId)

      // Update device in list if exists, otherwise add.
      // Preserve live WS-updated timestamps/status: a DB snapshot fetched
      // right after saving config can be slightly behind the real-time WS state.
      const index = devices.value.findIndex(d =>
        getDeviceId(d) === getDeviceId(device)
      )
      if (index !== -1) {
        const existing = devices.value[index]
        const deviceId = getDeviceId(device)
        const actStore = useActuatorStore()
        const fresherLastSeen = pickFresherIso(device.last_seen, existing.last_seen)
        const fresherLastHb = pickFresherIso(device.last_heartbeat, existing.last_heartbeat)
        const incomingSensors = Array.isArray(device.sensors)
          ? (device.sensors as MockSensor[])
          : ((existing.sensors ?? []) as MockSensor[])
        const incomingActuators = Array.isArray(device.actuators)
          ? (device.actuators as MockActuator[])
          : ((existing.actuators ?? []) as MockActuator[])
        applyDevicePatch(deviceId, () => ({
          ...device,
          sensors: mergeLiveSensorLists(incomingSensors, existing.sensors as MockSensor[] | undefined),
          actuators: mergeLiveActuatorLists(
            incomingActuators,
            existing.actuators as MockActuator[] | undefined,
            deviceId,
            actStore,
          ),
          last_seen: fresherLastSeen,
          last_heartbeat: fresherLastHb,
          status: keepFreshOnlineStatus(device.status, existing.status, fresherLastSeen),
          connected: keepFreshOnlineStatus(device.status, existing.status, fresherLastSeen) === 'online'
            ? true
            : device.connected,
        }))
        const patched = devices.value.find((entry) => getDeviceId(entry) === deviceId)
        return patched ?? device
      }

      replaceDevices([...devices.value, device])
      return device
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, `Failed to fetch device ${deviceId}`)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  // ===========================================================================
  // Pending Devices Actions (Discovery/Approval Phase)
  // ===========================================================================

  /**
   * Fetch all pending (unapproved) devices.
   * Called on initial load and after approval/rejection.
   */
  async function fetchPendingDevices(): Promise<void> {
    isPendingLoading.value = true
    error.value = null

    try {
      const devices = await espApi.getPendingDevices()
      pendingDevices.value = devices
      logger.debug(`Fetched ${devices.length} pending devices`)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to fetch pending devices')
      logger.error(`Failed to fetch pending devices:`, err)
    } finally {
      isPendingLoading.value = false
    }
  }

  /**
   * Approve a pending device.
   * 
   * @param deviceId - Device ID to approve
   * @param data - Optional approval data (name, zone)
   * @returns Approval response
   */
  async function approveDevice(
    deviceId: string,
    data?: ESPApprovalRequest
  ): Promise<ESPApprovalResponse> {
    error.value = null
    const toast = useToast()

    try {
      const response = await espApi.approveDevice(deviceId, data)
      
      // Remove from pending list
      pendingDevices.value = pendingDevices.value.filter(d => d.device_id !== deviceId)
      
      // Track this approval so the WS echo handler skips its fetchAll
      _recentlyApprovedByClient.value = deviceId
      _recentlyApprovedAt.value = Date.now()
      
      // Toast notification
      toast.success(`Gerät ${deviceId} wurde genehmigt`, { duration: 4000 })
      
      // Refresh device list to show the newly approved device
      fetchAll()
      
      return response
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, `Failed to approve device ${deviceId}`)
      toast.error(`Fehler beim Genehmigen: ${error.value}`, { duration: 6000 })
      throw err
    }
  }

  /**
   * Reject a pending device.
   * 
   * @param deviceId - Device ID to reject
   * @param reason - Reason for rejection
   * @returns Rejection response
   */
  async function rejectDevice(
    deviceId: string,
    reason: string
  ): Promise<ESPApprovalResponse> {
    error.value = null
    const toast = useToast()

    try {
      const response = await espApi.rejectDevice(deviceId, reason)
      
      // Remove from pending list
      pendingDevices.value = pendingDevices.value.filter(d => d.device_id !== deviceId)
      
      // Toast notification
      toast.info(`Gerät ${deviceId} wurde abgelehnt`, { duration: 4000 })
      
      return response
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, `Failed to reject device ${deviceId}`)
      toast.error(`Fehler beim Ablehnen: ${error.value}`, { duration: 6000 })
      throw err
    }
  }

  async function createDevice(config: ESPDeviceCreate | MockESPCreate): Promise<ESPDevice> {
    isLoading.value = true
    error.value = null

    try {
      const device = await espApi.createDevice(config)
      const deviceId = getDeviceId(device)

      // Check if device already exists (prevent duplicates)
      const existingIndex = devices.value.findIndex(d => getDeviceId(d) === deviceId)
      if (existingIndex !== -1) {
        // Replace existing with new data
        devices.value[existingIndex] = device
        logger.debug(`Device ${deviceId} already exists, updated`)
      } else {
        devices.value.push(device)
      }

      return device
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to create ESP device')
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function updateDevice(deviceId: string, update: ESPDeviceUpdate): Promise<ESPDevice> {
    isLoading.value = true
    error.value = null

    logger.info('updateDevice called:', { deviceId, update })

    try {
      // First, persist the update to the database
      await espApi.updateDevice(deviceId, update)

      // PATCH returns DB metadata only (sensor_count, no sensors[]/actuators[]).
      // Re-fetch merges debug+DB for mocks and enriches sensor/actuator configs for real ESPs.
      const device = await espApi.getDevice(deviceId)
      logger.info('Device re-fetched after update:', {
        deviceId: getDeviceId(device),
        name: device.name,
        sensorCount: device.sensors?.length ?? device.sensor_count,
      })

      // Update device in list (preserve live arrays if enrichment failed transiently)
      const index = devices.value.findIndex(d =>
        getDeviceId(d) === getDeviceId(device)
      )
      if (index !== -1) {
        const existing = devices.value[index]
        devices.value[index] = {
          ...device,
          sensors: Array.isArray(device.sensors) && device.sensors.length > 0
            ? device.sensors
            : (existing.sensors ?? []),
          actuators: Array.isArray(device.actuators) && device.actuators.length > 0
            ? device.actuators
            : (existing.actuators ?? []),
        }
        logger.info('Device updated in list:', devices.value[index].name)
      }

      return device
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, `Failed to update device ${deviceId}`)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Update device zone fields directly in store (optimistic update).
   * Called immediately after successful API response for instant UI feedback.
   * WebSocket event will also update, but this ensures immediate reactivity.
   */
  function updateDeviceZone(
    deviceId: string,
    zoneData: { zone_id?: string; zone_name?: string; master_zone_id?: string }
  ): void {
    const index = devices.value.findIndex(d => getDeviceId(d) === deviceId)
    if (index === -1) {
      logger.warn(`updateDeviceZone: device not found: ${deviceId}`)
      return
    }

    const device = devices.value[index]
    // Replace entire object to trigger Vue reactivity
    devices.value[index] = {
      ...device,
      zone_id: zoneData.zone_id ?? device.zone_id,
      zone_name: zoneData.zone_name ?? device.zone_name,
      master_zone_id: zoneData.master_zone_id ?? device.master_zone_id,
    }
    logger.info(`Zone updated (optimistic): ${deviceId} → ${zoneData.zone_id}`)
  }

  async function deleteDevice(deviceId: string): Promise<void> {
    error.value = null

    try {
      await espApi.deleteDevice(deviceId)
    } catch (err: unknown) {
      const axiosError = err as { response?: { status?: number } }

      // If 404, device is already gone - still remove from local list
      if (axiosError.response?.status === 404) {
        logger.warn(`Device ${deviceId} not found on server, removing from local list`)
      } else {
        error.value = extractErrorMessage(err, `Fehler beim Löschen von ${deviceId}`)
        throw err
      }
    } finally {
      // Always remove from local list (handles orphaned devices)
      devices.value = devices.value.filter(d => getDeviceId(d) !== deviceId)

      if (selectedDeviceId.value === deviceId) {
        selectedDeviceId.value = null
      }
    }
  }

  async function getHealth(deviceId: string) {
    error.value = null

    try {
      return await espApi.getHealth(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, `Failed to get health for ${deviceId}`)
      throw err
    }
  }

  async function restartDevice(deviceId: string, delaySeconds?: number, reason?: string) {
    error.value = null

    try {
      return await espApi.restartDevice(deviceId, delaySeconds, reason)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, `Failed to restart device ${deviceId}`)
      throw err
    }
  }

  async function resetDevice(deviceId: string, preserveWifi: boolean = false) {
    error.value = null

    try {
      return await espApi.resetDevice(deviceId, preserveWifi)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, `Failed to reset device ${deviceId}`)
      throw err
    }
  }

  // Mock ESP specific actions (for backward compatibility)
  async function triggerHeartbeat(deviceId: string): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Heartbeat trigger is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.triggerHeartbeat(deviceId)
      // Refresh device data
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      const axiosError = err as { response?: { status?: number } }

      // Special handling for orphaned mock devices
      if (axiosError.response?.status === 404) {
        error.value = `Mock ESP "${deviceId}" ist verwaist (nur in DB, nicht im Debug-Store). Bitte löschen und neu erstellen.`
      } else {
        error.value = extractErrorMessage(err, 'Failed to trigger heartbeat')
      }
      throw err
    }
  }

  async function setState(deviceId: string, state: MockSystemState, reason?: string): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Set state is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.setState(deviceId, state, reason)
      // Refresh device data
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      const axiosError = err as { response?: { status?: number } }

      // Special handling for orphaned mock devices
      if (axiosError.response?.status === 404) {
        error.value = `Mock ESP "${deviceId}" ist verwaist (nur in DB, nicht im Debug-Store). Bitte löschen und neu erstellen.`
      } else {
        error.value = extractErrorMessage(err, 'Failed to set state')
      }
      throw err
    }
  }

  async function setAutoHeartbeat(deviceId: string, enabled: boolean, interval: number = 60): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Auto-heartbeat is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.setAutoHeartbeat(deviceId, enabled, interval)
      // Refresh device data to get updated auto_heartbeat state
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to configure auto-heartbeat')
      throw err
    }
  }

  /**
   * Fügt einen Sensor zu einem ESP hinzu.
   *
   * Routing-Logik (Phase 2B):
   * - Mock-ESP (isMock=true)  → debugApi.addSensor()  → /debug/mock-esp/{id}/sensors
   * - Real-ESP (isMock=false) → sensorsApi.createOrUpdate() → /sensors/{espId}/{gpio}
   *
   * @param deviceId - ESP Device ID
   * @param config - Sensor-Konfiguration (Mock-Format, wird für Real-ESPs gemappt)
   */
  async function addSensor(
    deviceId: string,
    config: MockSensorConfig & { operating_mode?: string; timeout_seconds?: number }
  ): Promise<void> {
    error.value = null

    try {
      if (isMock(deviceId)) {
        // =========================================================================
        // MOCK-ESP: Debug-API verwenden (bestehende Logik)
        // =========================================================================
        await debugApi.addSensor(deviceId, config)

      } else {
        // =========================================================================
        // REAL-ESP: Sensor-API verwenden (NEU in Phase 2B)
        // =========================================================================
        // Infer interface type from sensor_type
        const interfaceType = inferInterfaceType(config.sensor_type)
        const defaultI2CAddress = getDefaultI2CAddress(config.sensor_type)

        const realConfig: SensorConfigCreate = {
          esp_id: deviceId,
          gpio: config.gpio,
          sensor_type: config.sensor_type,
          name: config.name || null,
          enabled: true,
          // Subzone: top-level für Backend SubzoneService; normalize "__none__" → null (Defense-in-Depth)
          subzone_id: normalizeSubzoneId(config.subzone_id),
          // =========================================================================
          // MULTI-VALUE SENSOR SUPPORT (I2C/OneWire)
          // =========================================================================
          interface_type: config.interface_type || interfaceType,
          // I2C: Use address from config (user selection), fallback to registry default
          // ADS1115: pass its I2C address even though interface_type is ANALOG
          i2c_address: interfaceType === 'I2C'
            ? (config.i2c_address ?? defaultI2CAddress)
            : (config.adc_source === 'ads1115' ? (config.i2c_address ?? null) : null),
          // OneWire: Use provided ROM address (from scan) or null (server auto-generates)
          onewire_address: config.onewire_address || null,
          // =========================================================================
          // ADS1115 External ADC Support
          // =========================================================================
          adc_source: config.adc_source ?? null,
          adc_channel: config.adc_channel ?? null,
          pga_gain: config.pga_gain ?? null,
          // =========================================================================
          // Operating Mode Felder (Phase 2B)
          // =========================================================================
          operating_mode: (config.operating_mode as SensorConfigCreate['operating_mode']) || 'continuous',
          timeout_seconds: config.timeout_seconds ?? 180,
          timeout_warning_enabled: (config.timeout_seconds ?? 180) > 0,
          // Weitere Felder mit Defaults
          calibration: null,
          threshold_min: null,
          threshold_max: null,
          metadata: {
            created_via: 'dashboard_drag_drop'
          }
        }

        await sensorsApi.createOrUpdate(deviceId, config.gpio, realConfig)
      }

      // UI aktualisieren
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to add sensor')
      throw err
    }
  }

  /**
   * Aktualisiert die Konfiguration eines bestehenden Sensors (Phase 2F).
   *
   * Verwendet für Operating Mode Overrides und Sensor-Einstellungen.
   * Routing-Logik:
   * - Mock-ESP (isMock=true)  → debugApi.updateSensor() (falls verfügbar) oder Re-Add
   * - Real-ESP (isMock=false) → sensorsApi.createOrUpdate()
   *
   * @param deviceId - ESP Device ID
   * @param gpio - GPIO Pin des Sensors
   * @param config - Zu aktualisierende Felder (partial update)
   */
  async function updateSensorConfig(
    deviceId: string,
    gpio: number,
    config: Partial<{
      name: string | null
      operating_mode: string | null
      timeout_seconds: number | null
      timeout_warning_enabled: boolean | null
      enabled: boolean
      schedule_config: { type: string; expression: string } | null
      measurement_freshness_hours: number | null
      calibration_interval_days: number | null
    }>
  ): Promise<void> {
    error.value = null

    // Find existing sensor to get current values
    const device = devices.value.find(d => getDeviceId(d) === deviceId)
    if (!device) {
      throw new Error(`Device not found: ${deviceId}`)
    }

    const sensors = device.sensors as MockSensor[] | undefined
    const existingSensor = sensors?.find(s => s.gpio === gpio)
    if (!existingSensor) {
      throw new Error(`Sensor not found: GPIO ${gpio}`)
    }

    try {
      if (isMock(deviceId)) {
        // =========================================================================
        // MOCK-ESP: Debug-API verwenden oder Sensor neu erstellen
        // =========================================================================
        // Mock ESPs können Sensoren über addSensor mit überschriebenen Werten aktualisieren
        const mockConfig: MockSensorConfig & {
          operating_mode?: string
          timeout_seconds?: number
          measurement_freshness_hours?: number | null
          calibration_interval_days?: number | null
        } = {
          gpio: gpio,
          sensor_type: existingSensor.sensor_type,
          name: config.name !== undefined ? config.name || '' : existingSensor.name || '',
          raw_value: existingSensor.raw_value ?? 0,
          unit: existingSensor.unit || '',
          quality: existingSensor.quality || 'good',
          raw_mode: true,
          interface_type: existingSensor.interface_type ?? undefined,
          i2c_address: existingSensor.i2c_address ?? null,
          operating_mode: config.operating_mode !== undefined ? config.operating_mode || undefined : existingSensor.operating_mode,
          timeout_seconds: config.timeout_seconds !== undefined ? config.timeout_seconds ?? undefined : existingSensor.timeout_seconds,
          measurement_freshness_hours: config.measurement_freshness_hours !== undefined ? config.measurement_freshness_hours : existingSensor.measurement_freshness_hours,
          calibration_interval_days: config.calibration_interval_days !== undefined ? config.calibration_interval_days : existingSensor.calibration_interval_days,
        }

        // Remove sensor first, then re-add with updated config
        await debugApi.removeSensor(deviceId, gpio)
        await debugApi.addSensor(deviceId, mockConfig)

      } else {
        // =========================================================================
        // REAL-ESP: Sensor-API mit Partial Update
        // =========================================================================
        // Infer interface type from existing sensor_type
        const interfaceType = inferInterfaceType(existingSensor.sensor_type)
        const defaultI2CAddress = getDefaultI2CAddress(existingSensor.sensor_type)

        const realConfig: SensorConfigCreate = {
          esp_id: deviceId,
          gpio: gpio,
          sensor_type: existingSensor.sensor_type,
          name: config.name !== undefined ? config.name : existingSensor.name,
          enabled: config.enabled !== undefined ? config.enabled : true,
          // =========================================================================
          // MULTI-VALUE SENSOR SUPPORT (I2C/OneWire)
          // =========================================================================
          interface_type: interfaceType,
          // I2C: Preserve existing address, fallback to registry default
          i2c_address: interfaceType === 'I2C' ? (existingSensor.i2c_address ?? defaultI2CAddress) : null,
          onewire_address: null, // Server preserves existing address on update
          // =========================================================================
          // Operating Mode Felder (Phase 2F)
          // =========================================================================
          operating_mode: config.operating_mode !== undefined
            ? (config.operating_mode as SensorConfigCreate['operating_mode'] ?? undefined)
            : (existingSensor.operating_mode as SensorConfigCreate['operating_mode'] ?? undefined),
          timeout_seconds: config.timeout_seconds !== undefined
            ? (config.timeout_seconds ?? undefined)
            : (existingSensor.timeout_seconds ?? undefined),
          timeout_warning_enabled: config.timeout_warning_enabled !== undefined
            ? (config.timeout_warning_enabled ?? undefined)
            : ((existingSensor.timeout_seconds ?? 180) > 0 ? true : undefined),
          // Schedule configuration (Phase 2F)
          schedule_config: config.schedule_config !== undefined
            ? (config.schedule_config ?? undefined)
            : (existingSensor.schedule_config as { type: string; expression: string } ?? undefined),
          // Sensor-Lifecycle: Freshness & Calibration (AUT-39)
          measurement_freshness_hours: config.measurement_freshness_hours !== undefined
            ? (config.measurement_freshness_hours ?? undefined)
            : (existingSensor.measurement_freshness_hours ?? undefined),
          calibration_interval_days: config.calibration_interval_days !== undefined
            ? (config.calibration_interval_days ?? undefined)
            : (existingSensor.calibration_interval_days ?? undefined),
          // Preserve existing metadata
          calibration: undefined,
          threshold_min: undefined,
          threshold_max: undefined,
          metadata: {
            updated_via: 'edit_modal_phase_2f'
          }
        }

        await sensorsApi.createOrUpdate(deviceId, gpio, realConfig)
      }

      // UI aktualisieren
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to update sensor config')
      throw err
    }
  }

  async function setSensorValue(
    deviceId: string,
    gpio: number,
    rawValue: number,
    quality?: QualityLevel,
    publish: boolean = true
  ): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Set sensor value is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.setSensorValue(deviceId, gpio, rawValue, quality, publish)
      // Refresh device data
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to set sensor value')
      throw err
    }
  }

  async function removeSensor(deviceId: string, gpio: number): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Remove sensor is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.removeSensor(deviceId, gpio)
      // Refresh device data
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to remove sensor')
      throw err
    }
  }

  async function addActuator(deviceId: string, config: MockActuatorConfig): Promise<void> {
    error.value = null
    const mock = isMock(deviceId)
    logger.info('[DnD] addActuator called', { deviceId, actuatorType: config.actuator_type, gpio: config.gpio, isMock: mock })

    try {
      if (mock) {
        // =========================================================================
        // MOCK-ESP: Debug-API verwenden (bestehende Logik)
        // =========================================================================
        await debugApi.addActuator(deviceId, config)
      } else {
        // =========================================================================
        // REAL-ESP: Actuator-API verwenden (analog zu addSensor Phase 2B)
        // =========================================================================
        const realConfig: ActuatorConfigCreate = {
          esp_id: deviceId,
          gpio: config.gpio,
          actuator_type: config.actuator_type,
          name: config.name || null,
          enabled: true,
          subzone_id: normalizeSubzoneId(config.subzone_id),
          max_runtime_seconds: config.max_runtime_seconds ?? null,
          cooldown_seconds: config.cooldown_seconds ?? null,
          pwm_frequency: isPwmActuator(config.actuator_type) ? 1000 : null,
          metadata: {
            created_via: 'dashboard_drag_drop',
            ...(config.aux_gpio != null && config.aux_gpio !== 255 ? { aux_gpio: config.aux_gpio } : {}),
            inverted_logic: !!config.inverted_logic,
          }
        }
        await actuatorsApi.createOrUpdate(deviceId, config.gpio, realConfig)
      }

      // UI aktualisieren
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to add actuator')
      throw err
    }
  }

  async function setActuatorState(
    deviceId: string,
    gpio: number,
    state: boolean,
    pwmValue?: number
  ): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Set actuator state is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.setActuatorState(deviceId, gpio, state, pwmValue)
      // Refresh device data
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to set actuator state')
      throw err
    }
  }

  async function emergencyStop(deviceId: string, reason: string = 'manual'): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Emergency stop is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.emergencyStop(deviceId, reason)
      // Refresh device data
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to trigger emergency stop')
      throw err
    }
  }

  async function clearEmergency(deviceId: string): Promise<void> {
    if (!isMock(deviceId)) {
      throw new Error('Clear emergency is only available for Mock ESPs')
    }

    error.value = null

    try {
      await debugApi.clearEmergency(deviceId)
      // Refresh device data
      await fetchDevice(deviceId)
    } catch (err: unknown) {
      error.value = extractErrorMessage(err, 'Failed to clear emergency')
      throw err
    }
  }

  function selectDevice(deviceId: string | null): void {
    selectedDeviceId.value = deviceId
  }

  function clearError(): void {
    error.value = null
  }

  function updateDeviceInList(device: ESPDevice): void {
    const index = devices.value.findIndex(d => 
      getDeviceId(d) === getDeviceId(device)
    )
    if (index !== -1) {
      applyDevicePatch(getDeviceId(device), () => device)
    }
  }

  // =============================================================================
  // WebSocket Event Handlers
  // =============================================================================

  /**
   * Handle esp_health WebSocket event
   *
   * Receives updates from:
   * 1. Heartbeat handler (MQTT) - sends timestamp (Unix seconds)
   * 2. MOCK-FIX in esp.py PATCH - sends last_seen (ISO string)
   * 3. LWT handler - sends source='lwt' when ESP disconnects unexpectedly
   *
   * BUG X FIX: If device is unknown but status is "online", refresh device list
   * to show newly connected ESPs immediately in the UI.
   */
  function handleEspHealth(message: any): void {
    const data = message.data
    const espId = data.esp_id || data.device_id

    // DEBUG: Log when WebSocket event arrives
    logger.debug('handleEspHealth received:', {
      esp_id: espId,
      status: data.status,
      timestamp: data.timestamp,
      source: data.source,
      reason: data.reason,
      receivedAt: Date.now()
    })

    if (!espId) return

    const device = devices.value.find(d => getDeviceId(d) === espId)

    // BUG X FIX: Unknown device came online - refresh device list for real-time updates
    if (!device && data.status === 'online') {
      logger.info(`New device online: ${espId}, refreshing device list...`)
      fetchAll().catch(err => {
        logger.error(`Failed to refresh devices after new online device:`, err)
      })
      return
    }

    if (device) {
      // IMPORTANT: Replace entire device object for Vue reactivity
      // Direct mutation doesn't reliably trigger computed/watch updates
      const deviceIndex = devices.value.findIndex(d => getDeviceId(d) === espId)
      if (deviceIndex === -1) return
      const incomingStatus = typeof data.status === 'string' ? data.status : undefined
      const effectiveStatus = incomingStatus ?? device.status

      // Calculate new last_seen from either source:
      // - timestamp: Unix ms from heartbeat handler (MQTT) - 13 digits
      // - timestamp: Unix seconds from old handlers - 10 digits
      // - last_seen: ISO string from API/handlers
      // Fallback: when status is online but no usable timestamp is present
      // (e.g. ESP time not synced yet), use local receive time.
      let newLastSeen: string | undefined = device.last_seen ?? undefined
      const parseTimestampToIso = (rawTs: unknown): string | undefined => {
        if (typeof rawTs !== 'number' && typeof rawTs !== 'string') return undefined
        const parsed = typeof rawTs === 'number' ? rawTs : Number(rawTs)
        if (!Number.isFinite(parsed) || parsed <= 0) return undefined
        const tsMs = parsed > 10000000000 ? parsed : parsed * 1000
        return new Date(tsMs).toISOString()
      }
      const parseIsoToMs = (iso: unknown): number | undefined => {
        if (typeof iso !== 'string' || iso.trim().length === 0) return undefined
        const ms = Date.parse(iso)
        return Number.isFinite(ms) ? ms : undefined
      }
      const timestampIso = parseTimestampToIso(data.timestamp)
        ?? parseTimestampToIso(data.metrics_delta_ts)
      const incomingLastSeen =
        timestampIso
        ?? (typeof data.last_seen === 'string' ? data.last_seen : undefined)
      const currentLastSeenMs = parseIsoToMs(device.last_seen)
      const incomingLastSeenMs = parseIsoToMs(incomingLastSeen)

      if (incomingLastSeen && incomingLastSeenMs !== undefined) {
        // Guard against out-of-order or stale heartbeat events.
        if (currentLastSeenMs === undefined || incomingLastSeenMs >= currentLastSeenMs) {
          newLastSeen = incomingLastSeen
        } else {
          logger.debug(`Ignoring stale esp_health timestamp for ${espId}`, {
            current: device.last_seen,
            incoming: incomingLastSeen
          })
        }
      } else if (effectiveStatus === 'online') {
        // No usable timestamp in payload, but device is online now.
        // Use receive-time to avoid temporary "verzoegert" badge.
        newLastSeen = new Date().toISOString()
      }

      // Calculate offline info if device went offline
      let offlineInfo: OfflineInfo | undefined = undefined
      if (incomingStatus === 'offline') {
        recordDisconnect(espId)

        const source = parseStatusSource(data.source) ?? 'heartbeat_timeout'
        const reason = getOfflineReason(source, data.reason)
        const displayText = getOfflineDisplayText(source, data.reason)

        // AUT-592: Guard against stale LWT payload timestamps. The LWT timestamp is
        // set at MQTT connect() time and can be hours old by the time the broker
        // delivers it. If it predates the device's current last_seen, use last_seen
        // (or local receive-time) as the canonical "offline since" timestamp.
        const offlineTs = (() => {
          if (!data.timestamp) return Math.floor(Date.now() / 1000)
          const tsMs = (data.timestamp as number) * 1000
          if (currentLastSeenMs !== undefined && tsMs < currentLastSeenMs - 5000) {
            return Math.floor(currentLastSeenMs / 1000)
          }
          return data.timestamp as number
        })()
        offlineInfo = {
          reason,
          source,
          timestamp: offlineTs,
          displayText
        }

        // Toast notification for LWT (unexpected disconnect)
        if (source === 'lwt') {
          const toast = useToast()
          toast.warning(
            `${device.name || device.device_id}: Verbindung unerwartet verloren`,
            { duration: 5000 }
          )
        }
      }

      // Reset actuator states to idle when device goes offline with reset count
      let updatedActuators = device.actuators
      if (data.status === 'offline' && data.actuator_states_reset && data.actuator_states_reset > 0) {
        const resetEpochMs = Date.now()
        const actStore = useActuatorStore()
        const knownGpios = ((device.actuators as Array<{ gpio?: number }> | undefined) ?? [])
          .map((actuator) => actuator.gpio)
          .filter((gpio): gpio is number => typeof gpio === 'number')
        actStore.markActuatorResetEpoch(espId, resetEpochMs, undefined, knownGpios)

        updatedActuators = (device.actuators as any[])?.map((actuator: any) => {
          if (actuator.state !== 'idle' && actuator.state !== 'emergency_stop'
              && actuator.state !== false) {
            return { ...actuator, state: false, current_value: 0 }
          }
          return actuator
        }) ?? []
      }

      const dataRec = data as Record<string, unknown>
      const metrics = (dataRec.metrics as Record<string, unknown> | undefined) || undefined
      const pickNumeric = (...candidates: unknown[]): number | undefined => {
        for (const candidate of candidates) {
          if (typeof candidate === 'number' && Number.isFinite(candidate)) return candidate
          if (typeof candidate === 'string' && candidate.trim().length > 0) {
            const parsed = Number(candidate)
            if (Number.isFinite(parsed)) return parsed
          }
        }
        return undefined
      }
      const resolvedHeap = pickNumeric(
        dataRec.heap_free,
        dataRec.heap,
        dataRec.free_heap,
        metrics?.heap_free,
        metrics?.heap,
        metrics?.free_heap,
      )
      const resolvedWifiRssi = pickNumeric(
        dataRec.wifi_rssi,
        dataRec.rssi,
        metrics?.wifi_rssi,
        metrics?.rssi,
      )
      const runtimeHealthView = normalizeEspHealthPayload(dataRec)
      const nextConnected =
        effectiveStatus === 'online'
          ? true
          : effectiveStatus === 'offline'
            ? false
            : (typeof data.connected === 'boolean' ? data.connected : device.connected)

      // Replace device with updated copy (triggers Vue reactivity)
      devices.value[deviceIndex] = {
        ...device,
        uptime: data.uptime ?? device.uptime,
        heap_free: resolvedHeap ?? device.heap_free,
        wifi_rssi: resolvedWifiRssi ?? device.wifi_rssi,
        sensor_count: data.sensor_count ?? device.sensor_count,
        actuator_count: data.actuator_count ?? device.actuator_count,
        last_seen: newLastSeen,
        last_heartbeat: newLastSeen,
        status: effectiveStatus,
        connected: nextConnected,
        name: data.name ?? device.name,
        actuators: updatedActuators,
        // Keep offlineInfo sticky unless we received an explicit online transition.
        offlineInfo: effectiveStatus === 'offline'
          ? (incomingStatus === 'offline' ? offlineInfo : device.offlineInfo)
          : (effectiveStatus === 'online' ? undefined : device.offlineInfo),
        runtime_health_view: runtimeHealthView,
        spool_pending_count: data.spool_pending_count ?? device.spool_pending_count,
        spool_dropped_count: data.spool_dropped_count ?? device.spool_dropped_count,
      }

      logger.debug(`esp_health update for ${espId}:`, {
        last_seen: newLastSeen,
        status: effectiveStatus,
        name: data.name ?? device.name,
        offlineInfo:
          effectiveStatus === 'offline'
            ? (incomingStatus === 'offline' ? offlineInfo : device.offlineInfo)
            : (effectiveStatus === 'online' ? 'cleared' : device.offlineInfo),
      })

      // Phase 3: Update GPIO status from heartbeat if present
      if (data.gpio_status && Array.isArray(data.gpio_status)) {
        updateGpioStatusFromHeartbeat(espId, data.gpio_status as HeartbeatGpioItem[])
      }
    }
  }

  /**
   * Handle esp_reconnect_phase WebSocket event.
   * Allows UI to react immediately during reconnect adoption before full esp_health update.
   */
  function handleEspReconnectPhase(message: { data: Record<string, unknown> }): void {
    const data = message.data as { esp_id?: string; phase?: string; timestamp?: number }
    if (!data.esp_id) return

    const phase = parseReconnectPhase(data.phase)
    if (!phase) return

    const changed = applyDevicePatch(data.esp_id, (device) => {
      const metadata = { ...(device.metadata ?? {}) }

      if (phase === 'converged') {
        delete metadata.reconnect_phase
        delete metadata.reconnect_phase_ts
      } else {
        metadata.reconnect_phase = phase
        metadata.reconnect_phase_ts = data.timestamp ?? Math.floor(Date.now() / 1000)
      }

      return {
        ...device,
        // Reconnect flow started on server side; keep local connectivity responsive.
        connected: true,
        metadata,
      }
    })

    if (changed) {
      logger.debug(`esp_reconnect_phase for ${data.esp_id}: ${phase}`)
    }
  }

  /**
   * Actuator alert handler - delegates to actuator.store.ts
   * Server: actuator_alert_handler.py → WS: actuator_alert
   */
  function handleActuatorAlert(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleActuatorAlert(
      message,
      applyDevicePatch,
      () => devices.value.map((device) => getDeviceId(device)),
    )
  }

  /**
   * Sensor data handler - delegates to sensor.store.ts
   * Server: sensor_handler.py → WS: sensor_data
   */
  function handleSensorData(message: { data: Record<string, unknown> }): void {
    const sensorStore = useSensorStore()
    sensorStore.handleSensorData(
      message as unknown as Parameters<typeof sensorStore.handleSensorData>[0],
      applyDevicePatch,
    )
  }

  /**
   * Actuator status handler - delegates to actuator.store.ts
   * Server: actuator_handler.py → WS: actuator_status
   */
  function handleActuatorStatus(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleActuatorStatus(
      message as unknown as Parameters<typeof actStore.handleActuatorStatus>[0],
      applyDevicePatch,
      devices.value,
      getDeviceId,
    )
  }

  /**
   * Config response handler - delegates to config.store.ts
   * Server: config_ack_handler.py → WS: config_response
   */
  function handleConfigResponse(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleConfigResponse(message)
    const cfgStore = useConfigStore()
    cfgStore.handleConfigResponse(message, devices.value, getDeviceId, fetchGpioStatus)
  }

  /**
   * Config response guard-replay handler (PKG-04b, INC-2026-04-20).
   * Server: config_handler.py Terminal Authority Guard (was_stale path) → WS: config_response_guard_replay
   * Delegates to actuator.store (intent finalization) + config.store (operator toast).
   */
  function handleConfigResponseGuardReplay(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleConfigResponseGuardReplay(message)
    const cfgStore = useConfigStore()
    cfgStore.handleConfigResponse(message, devices.value, getDeviceId, fetchGpioStatus)
  }

  /**
   * Handle zone_assignment WebSocket event
   * Updates device zone fields when ESP confirms zone assignment
   *
   * WP4: DEFENSIVE implementation - only overwrite fields that are DEFINED in the event
   *
   * Server payload (from zone_ack_handler.py):
   * {
   *   esp_id: string,
   *   status: "zone_assigned" | "error",
   *   zone_id: string,
   *   zone_name?: string,       // ← server-dev WP4: NOW SENT
   *   kaiser_id?: string,       // ← server-dev WP4: NOW SENT
   *   master_zone_id?: string,
   *   timestamp: number,
   *   message?: string
   * }
   */
  /**
   * Zone assignment handler - delegates to zone.store.ts
   * Server: zone_ack_handler.py → WS: zone_assignment
   */
  function handleZoneAssignment(message: any): void {
    const zoneStore = useZoneStore()
    zoneStore.handleZoneAssignment(
      message,
      applyDevicePatch,
      (espId: string) => findDeviceByEspIdDefensive(espId)?.device ?? null,
    )
  }

  /**
   * Subzone assignment handler - delegates to zone.store.ts
   * Server: subzone_ack_handler.py → WS: subzone_assignment
   */
  function handleSubzoneAssignment(message: any): void {
    const zoneStore = useZoneStore()
    const needsRefresh = zoneStore.handleSubzoneAssignment(
      message,
      applyDevicePatch,
      (espId: string) => findDeviceByEspIdDefensive(espId)?.device ?? null,
    )
    // Refresh only as fallback when delta patching is insufficient.
    // Debounced to avoid REST+WS double refresh storms.
    if (needsRefresh) {
      if (subzoneRefreshTimer) {
        clearTimeout(subzoneRefreshTimer)
      }
      subzoneRefreshTimer = setTimeout(() => {
        fetchAll().catch((e: unknown) => {
          logger.warn('Failed to refresh devices after subzone change', e)
        })
        subzoneRefreshTimer = null
      }, 250)
    }
  }

  /**
   * Device scope changed handler - delegates to zone.store.ts (T13-R2)
   * Server: sensors.py/actuators.py → WS: device_scope_changed
   */
  function handleDeviceScopeChanged(message: any): void {
    const zoneStore = useZoneStore()
    const patched = zoneStore.handleDeviceScopeChanged(
      message,
      applyDevicePatch,
      (espId: string) => findDeviceByEspIdDefensive(espId)?.device ?? null,
    )
    // Fallback only when patching is not possible
    if (!patched) {
      fetchAll().catch((e: unknown) => {
        logger.warn('Failed to refresh devices after scope change', e)
      })
    }
  }

  /**
   * Device context changed handler - delegates to zone.store.ts (T13-R2)
   * Server: device_context.py → WS: device_context_changed
   */
  function handleDeviceContextChanged(message: any): void {
    const zoneStore = useZoneStore()
    const patched = zoneStore.handleDeviceContextChanged(
      message,
      applyDevicePatch,
      (espId: string) => findDeviceByEspIdDefensive(espId)?.device ?? null,
    )
    // Update granular context store immediately (6.7)
    const deviceContextStore = useDeviceContextStore()
    if (message?.data) {
      deviceContextStore.handleContextChanged(message.data)
    }
    // Fallback only when patching is not possible
    if (!patched) {
      fetchAll().catch((e: unknown) => {
        logger.warn('Failed to refresh devices after context change', e)
      })
    }
  }

  // ===========================================================================
  // Discovery/Approval WebSocket Handlers
  // ===========================================================================

  /**
   * Handle device_discovered WebSocket event.
   * Adds new device to pending list and shows toast notification.
   */
  function handleDeviceDiscovered(message: any): void {
    const data = message.data as DeviceDiscoveredPayload
    const toast = useToast()

    if (!data.device_id) {
      logger.warn('device_discovered missing device_id')
      return
    }

    logger.info(`New device discovered: ${data.device_id}`)

    // Add to pending list if not already present
    const exists = pendingDevices.value.some(d => d.device_id === data.device_id)
    if (!exists) {
      const newPending: PendingESPDevice = {
        device_id: data.device_id,
        discovered_at: data.discovered_at || new Date().toISOString(),
        last_seen: data.last_seen ?? data.discovered_at ?? new Date().toISOString(),
        ip_address: data.ip_address,
        heap_free: data.heap_free,
        wifi_rssi: data.wifi_rssi,
        sensor_count: data.sensor_count ?? 0,
        actuator_count: data.actuator_count ?? 0,
        heartbeat_count: 1,
        hardware_type: data.hardware_type,
      }
      pendingDevices.value.push(newPending)
    }

    // Toast notification
    toast.info(`Neues Gerät entdeckt: ${data.device_id}`, { duration: 4000 })
  }

  /**
   * Handle device_approved WebSocket event.
   * Removes device from pending list.
   */
  function handleDeviceApproved(message: any): void {
    const data = message.data as DeviceApprovedPayload
    const toast = useToast()

    if (!data.device_id) {
      logger.warn('device_approved missing device_id')
      return
    }

    logger.info(`Device approved: ${data.device_id} by ${data.approved_by}`)

    // Remove from pending list
    pendingDevices.value = pendingDevices.value.filter(d => d.device_id !== data.device_id)

    // Check if this approval was initiated by this client (avoids duplicate fetchAll)
    const isOwnApproval =
      _recentlyApprovedByClient.value === data.device_id &&
      (Date.now() - _recentlyApprovedAt.value) < 5000

    if (isOwnApproval) {
      // Own client already triggered fetchAll in approveDevice() - skip duplicate
      _recentlyApprovedByClient.value = null
      logger.debug(`Skipping fetchAll for own approval of ${data.device_id}`)
    } else {
      // Another client approved - show toast and refresh
      toast.success(`Gerät ${data.device_id} wurde genehmigt`, { duration: 4000 })
      fetchAll()
    }
  }

  /**
   * Handle device_rejected WebSocket event.
   * Removes device from pending list.
   */
  function handleDeviceRejected(message: any): void {
    const data = message.data as DeviceRejectedPayload
    const toast = useToast()

    if (!data.device_id) {
      logger.warn('device_rejected missing device_id')
      return
    }

    logger.info(`Device rejected: ${data.device_id} - ${data.rejection_reason}`)

    // Remove from pending list
    pendingDevices.value = pendingDevices.value.filter(d => d.device_id !== data.device_id)

    // Toast notification
    toast.warning(`Gerät ${data.device_id} wurde abgelehnt`, { duration: 4000 })
  }

  /**
   * Sensor health handler - delegates to sensor.store.ts
   * Server: maintenance/jobs/sensor_health.py → WS: sensor_health
   */
  function handleSensorHealth(message: { data: Record<string, unknown> }): void {
    const sensorStore = useSensorStore()
    sensorStore.handleSensorHealth(
      message as unknown as Parameters<typeof sensorStore.handleSensorHealth>[0],
      applyDevicePatch,
    )
  }

  /**
   * Sensor config deleted handler — removes ghost sensor from device.sensors array.
   * Server: sensors.py DELETE → WS: sensor_config_deleted
   * Payload: { config_id, esp_id, gpio, sensor_type }
   */
  function handleSensorConfigDeleted(message: { data: Record<string, unknown> }): void {
    const data = message.data as {
      config_id?: string
      esp_id?: string
      gpio?: number
      sensor_type?: string
    }
    if (!data.esp_id) return

    const changed = applyDevicePatch(data.esp_id, (device) => {
      const currentSensors = (device.sensors ?? []) as MockSensor[]
      if (!currentSensors.length) return device

      const nextSensors = currentSensors.filter((sensor) => {
        if (data.config_id) {
          return String(sensor.config_id ?? '') !== data.config_id
        }
        if (data.gpio !== undefined && data.sensor_type) {
          return !(sensor.gpio === data.gpio && sensor.sensor_type === data.sensor_type)
        }
        return true
      })

      if (nextSensors.length === currentSensors.length) return device
      return {
        ...device,
        sensors: nextSensors,
        sensor_count: nextSensors.length,
      }
    })

    if (!changed) return

    // Keep GPIO availability in sync after config removal so pickers in
    // Hardware L2 immediately reflect newly freed pins.
    fetchGpioStatus(data.esp_id).catch((err: unknown) => {
      logger.warn(`Failed to refresh GPIO status after sensor delete (${data.esp_id})`, err)
    })

    const toast = useToast()
    const sensorLabel = data.sensor_type ? ` (${data.sensor_type})` : ''
    toast.info(`Sensor entfernt${sensorLabel}`, {
      duration: 3000,
      dedupeKey: `sensor-delete:${data.esp_id}:${data.config_id ?? `${data.gpio}:${data.sensor_type ?? 'unknown'}`}`,
    })
  }

  /**
   * Actuator config deleted handler — removes actuator from device.actuators array.
   * Server: actuators.py DELETE → WS: actuator_config_deleted
   * Payload: { esp_id, gpio, actuator_type }
   */
  function handleActuatorConfigDeleted(message: { data: Record<string, unknown> }): void {
    const data = message.data as { esp_id?: string; gpio?: number; actuator_type?: string }
    if (!data.esp_id || data.gpio === undefined) return

    const changed = applyDevicePatch(data.esp_id, (device) => {
      const currentActuators = device.actuators ?? []
      if (!currentActuators.length) return device

      const nextActuators = currentActuators.filter((actuator) => actuator.gpio !== data.gpio)
      if (nextActuators.length === currentActuators.length) return device

      return {
        ...device,
        actuators: nextActuators,
        actuator_count: nextActuators.length,
      }
    })

    if (!changed) return

    // Keep GPIO availability in sync after config removal so pickers in
    // Hardware L2 immediately reflect newly freed pins.
    fetchGpioStatus(data.esp_id).catch((err: unknown) => {
      logger.warn(`Failed to refresh GPIO status after actuator delete (${data.esp_id})`, err)
    })

    const toast = useToast()
    toast.info(`Aktor entfernt (GPIO ${data.gpio})`, {
      duration: 3000,
      dedupeKey: `actuator-delete:${data.esp_id}:${data.gpio}`,
    })
  }

  // =============================================================================
  // WebSocket Handlers: Actuator Feedback & Notifications (Phase UI/UX 1)
  // =============================================================================

  /**
   * Actuator response handler - delegates to actuator.store.ts
   * Server: actuator_handler.py → WS: actuator_response
   */
  function handleActuatorResponse(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleActuatorResponse(message, devices.value, getDeviceId, applyDevicePatch)
  }

  /**
   * Notification handler - delegates to notification.store.ts
   * Server: logic engine, system → WS: notification
   */
  function handleNotification(message: { data: Record<string, unknown> }): void {
    useNotificationStore().handleNotification(message)
  }

  /**
   * Error event handler - delegates to notification.store.ts
   * Server: error tracker → WS: error_event
   */
  function handleErrorEvent(message: { data: Record<string, unknown> }): void {
    useNotificationStore().handleErrorEvent(message, devices.value, getDeviceId)
    if (message.data.error_type === 'atc_degraded') {
      useSensorStore().handleAtcDegraded(message.data)
    }
  }

  /**
   * System event handler - delegates to notification.store.ts
   * Server: system events → WS: system_event
   */
  function handleSystemEvent(message: { data: Record<string, unknown> }): void {
    useNotificationStore().handleSystemEvent(message)
  }

  // =============================================================================
  // Phase 4A: Notification Inbox Handlers - delegates to notification-inbox.store.ts
  // =============================================================================

  function handleNotificationNew(message: { data: Record<string, unknown> }): void {
    useNotificationInboxStore().handleWSNotificationNew(message.data)
    useAlertCenterStore().scheduleStatsRefresh()
  }

  function handleNotificationUpdated(message: { data: Record<string, unknown> }): void {
    useNotificationInboxStore().handleWSNotificationUpdated(message.data)
    useAlertCenterStore().scheduleStatsRefresh()
  }

  function handleNotificationUnreadCount(message: { data: Record<string, unknown> }): void {
    useNotificationInboxStore().handleWSUnreadCount(message.data)
    useAlertCenterStore().scheduleStatsRefresh()
  }

  // =============================================================================
  // Phase 2: Actuator Command Lifecycle Handlers - delegates to actuator.store.ts
  // =============================================================================

  function handleActuatorCommand(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleActuatorCommand(message, devices.value, getDeviceId, applyDevicePatch)
  }

  function handleActuatorCommandFailed(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleActuatorCommandFailed(message, devices.value, getDeviceId, applyDevicePatch)
  }

  // =============================================================================
  // Phase 2: Config Publish Lifecycle Handlers
  // =============================================================================

  /**
   * Config published handler - delegates to config.store.ts
   * Server: config_publisher → WS: config_published
   */
  function handleConfigPublished(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleConfigPublished(message)
    useConfigStore().handleConfigPublished(message, devices.value, getDeviceId)
  }

  /**
   * Config failed handler - delegates to config.store.ts
   * Server: config_publisher → WS: config_failed
   *
   * AUT-134 PKG-04: Bei reason_code='config_oversize' wird zusätzlich
   * `config_last_reject` auf dem Device gesetzt (terminale UI-Sichtbarkeit).
   * Pending-State (z.B. `metadata.config_push_pending`) wird gelöscht,
   * damit kein Spinner-Deadlock entsteht.
   */
  function handleConfigFailed(message: { data: Record<string, unknown> }): void {
    const actStore = useActuatorStore()
    actStore.handleConfigFailed(message)
    useConfigStore().handleConfigFailed(message, devices.value, getDeviceId)

    const reject = extractConfigRejectFromConfigFailed(message.data)
    if (reject) {
      applyConfigRejectToDevice(reject)
    }
  }

  /**
   * Apply a terminal config-reject snapshot to the device entity (AUT-134 PKG-04).
   * - Setzt `config_last_reject` für Operator-UI-Sichtbarkeit
   * - Löscht `metadata.config_push_pending` (kein Spinner-Deadlock bei Oversize)
   * - Read-only informational; kein Auto-Retry-Trigger
   */
  function applyConfigRejectToDevice(reject: ConfigRejectSnapshot): void {
    const lastReject: ConfigLastReject = {
      reason_code: reject.reasonCode,
      payload_size_bytes: reject.payloadSizeBytes,
      budget_bytes: reject.budgetBytes,
      correlation_id: reject.correlationId,
      timestamp: reject.timestamp,
      source: reject.source,
    }
    const changed = applyDevicePatch(reject.espId, (device) => {
      const metadata = { ...(device.metadata ?? {}) }
      // Defensive: clear any pending-config flag so spinners don't hang.
      if ('config_push_pending' in metadata) {
        delete metadata.config_push_pending
      }
      return {
        ...device,
        metadata,
        config_last_reject: lastReject,
      }
    })
    if (changed) {
      logger.warn(
        `Config-Reject (${reject.source}) für ${reject.espId}: ${reject.reasonCode}` +
          (reject.payloadSizeBytes !== null && reject.budgetBytes !== null
            ? ` (${reject.payloadSizeBytes}/${reject.budgetBytes} bytes)`
            : ''),
      )
    }
  }

  // =============================================================================
  // Phase 2: Device Rediscovery Handler
  // =============================================================================

  /**
   * Handle device_rediscovered WebSocket event.
   * Two cases:
   * 1) Approved device that went offline came back → update devices list
   * 2) Rejected device sends heartbeat again (cooldown expired) → now pending again, refresh pending list
   */
  function handleDeviceRediscovered(message: { data: Record<string, unknown> }): void {
    const data = message.data
    const espId = (data.esp_id as string) || (data.device_id as string)
    if (!espId) return

    const toast = useToast()

    // Case 1: Device in approved list (was offline, came back)
    const deviceIndex = devices.value.findIndex(d => getDeviceId(d) === espId)
    if (deviceIndex !== -1) {
      const device = devices.value[deviceIndex]
      devices.value[deviceIndex] = {
        ...device,
        status: 'online',
        connected: true,
        last_seen: new Date().toISOString(),
        offlineInfo: undefined,
        ip_address: (data.ip_address as string) ?? device.ip_address,
      }
      const deviceName = device.name || espId
      toast.info(`${deviceName} ist wieder online`)
      return
    }

    // Case 2: Rejected device rediscovered → now pending_approval again
    fetchPendingDevices().catch(err => {
      logger.error(`Failed to refresh pending after device_rediscovered:`, err)
    })
    toast.info(`${espId} ist wieder zur Genehmigung verfügbar`)
  }

  // =============================================================================
  // Logic execution (cross-ESP automation) — live actuator state in Monitor L2
  // =============================================================================

  function handleLogicExecution(message: { data: Record<string, unknown> }): void {
    const data = message.data
    if (!data.success) return

    const action = data.action as { esp_id?: string; gpio?: number; command?: string } | undefined
    if (!action?.esp_id || action.gpio === undefined || !action.command) return

    const espId = String(action.esp_id)
    const gpio = Number(action.gpio)
    const command = String(action.command).trim().toUpperCase()

    applyDevicePatch(espId, (device) => {
      if (!device?.actuators) return device
      const actuators = (device.actuators as unknown as Array<Record<string, unknown>>).map(a => ({ ...a }))
      const actuator = actuators.find(a => a.gpio === gpio)
      if (!actuator) return device

      if (command === 'ON') {
        actuator.state = true
      } else if (command === 'OFF') {
        actuator.state = false
        actuator.pwm_value = 0
      } else if (command === 'PWM') {
        actuator.state = true
      } else if (command === 'TOGGLE') {
        actuator.state = !(actuator.state === true)
      }

      return { ...device, actuators: actuators as unknown as ESPDevice['actuators'] }
    })
  }

  // =============================================================================
  // Sequence Handlers - delegates to actuator.store.ts
  // =============================================================================

  function handleSequenceStarted(message: { data: Record<string, unknown> }): void {
    useActuatorStore().handleSequenceStarted(message)
  }

  function handleSequenceStep(message: { data: Record<string, unknown> }): void {
    useActuatorStore().handleSequenceStep(message)
  }

  function handleSequenceCompleted(message: { data: Record<string, unknown> }): void {
    useActuatorStore().handleSequenceCompleted(message)
  }

  function handleSequenceError(message: { data: Record<string, unknown> }): void {
    useActuatorStore().handleSequenceError(message)
  }

  function handleSequenceCancelled(message: { data: Record<string, unknown> }): void {
    useActuatorStore().handleSequenceCancelled(message)
  }

  // =============================================================================
  // Intent outcome (canonical MQTT contract, April 2026)
  // =============================================================================

  function handleIntentOutcome(message: { data: Record<string, unknown> }): void {
    useIntentSignalsStore().ingestOutcome(message.data)
    const correlationId = typeof message.data.correlation_id === 'string'
      ? message.data.correlation_id.trim()
      : ''
    const isFinal = message.data.is_final === true
    if (correlationId && isFinal) {
      websocketService.sendClientStageObservation(correlationId, 't7_ui_applied', {
        source: 'intent_outcome',
        flow: message.data.flow,
        outcome: message.data.outcome,
      })
    }

    // AUT-134 PKG-04: ESP32 (PKG-02) sendet Reject-Outcome via Server an Frontend.
    // Map flow='config' + code='PAYLOAD_TOO_LARGE' (terminal) → ConfigLastReject.
    const reject = extractConfigRejectFromIntentOutcome(message.data)
    if (reject) {
      applyConfigRejectToDevice(reject)
    }

    // Reliable fallback: finalize pending actuator intents via intent_outcome (QoS 1).
    // actuator_response is QoS 0 and can be lost under MQTT network stress.
    const flow = typeof message.data.flow === 'string' ? message.data.flow : ''
    const outcome = typeof message.data.outcome === 'string' ? message.data.outcome : ''
    if (flow === 'command' && ['applied', 'failed', 'rejected', 'expired'].includes(outcome)) {
      useActuatorStore().handleActuatorCommandIntentOutcome(
        message.data,
        devices.value,
        getDeviceId,
        applyDevicePatch,
      )
    }
  }

  function handleIntentOutcomeLifecycle(message: WebSocketMessage): void {
    const data = message.data as Record<string, unknown>
    const msgCorr = typeof message.correlation_id === 'string' ? message.correlation_id : undefined
    useIntentSignalsStore().ingestLifecycle(data, msgCorr)
  }

  // =============================================================================
  // Actuator Commands (Real ESP + Mock)
  // =============================================================================

  /**
   * Send actuator command to real or mock ESP.
   * For real ESPs: calls REST API → MQTT → ESP.
   * For mock ESPs: calls debug API.
   * Toast feedback comes via WebSocket events.
   */
  async function sendActuatorCommand(
    deviceId: string,
    gpio: number,
    command: 'ON' | 'OFF' | 'PWM' | 'TOGGLE',
    value?: number,
    // AUT-995 Feld 6 (AO-5): optional auto-off timer in seconds (e.g. "Jetzt dosieren"). Real ESP only.
    duration?: number
  ): Promise<void> {
    const toast = useToast()
    const actStore = useActuatorStore()

    if (isMock(deviceId)) {
      // Mock path: use debug API
      try {
        if (command === 'PWM') {
          const normalized = value ?? 0
          await debugApi.setActuatorState(
            deviceId,
            gpio,
            normalized > 0,
            Math.round(normalized * 255),
          )
        } else {
          const state = command === 'ON' || command === 'TOGGLE'
          const pwmForMock = command === 'ON' ? 255 : command === 'OFF' ? 0 : undefined
          await debugApi.setActuatorState(deviceId, gpio, state, pwmForMock)
        }
        await fetchDevice(deviceId)
        toast.success(`[Simulation] Befehl ausgeführt: ${command} an ${deviceId} GPIO ${gpio}`, {
          dedupeKey: `sim-actuator-command:${deviceId}:${gpio}:${command}:${value ?? 'na'}`,
        })
      } catch (err: unknown) {
        const msg = extractErrorMessage(err, '[Simulation] Mock-Befehl konnte nicht gesendet werden')
        toast.error(msg, { persistent: true })
        throw err
      }
      return
    }

    const device = devices.value.find(d => getDeviceId(d) === deviceId)
    if (device) {
      const status = getESPStatus(device)
      if (status === 'offline' || status === 'error') {
        const msg =
          status === 'offline'
            ? `Befehl nicht gesendet: ${deviceId} ist offline.`
            : `Befehl nicht gesendet: ${deviceId} ist im Fehlerzustand.`
        toast.error(msg, { persistent: true })
        throw new Error(msg)
      }
    }

    // Real ESP: use actuator command API
    try {
      const response = await actuatorsApi.sendCommand(deviceId, gpio, {
        command,
        value: value ?? (command === 'ON' ? 1.0 : 0.0),
        // Only include duration when explicitly requested, so normal toggles keep their previous payload.
        ...(duration != null ? { duration } : {}),
      })
      const responseData = response as unknown as Record<string, unknown>
      const correlationId = typeof responseData.correlation_id === 'string' ? responseData.correlation_id : undefined
      const requestId = typeof responseData.request_id === 'string' ? responseData.request_id : undefined
      actStore.registerCommandIntent(deviceId, gpio, command, correlationId, requestId)
      // Optimistic update: reflect command immediately before WS actuator_command arrives.
      if (command === 'ON' || command === 'OFF' || command === 'PWM') {
        const commandAt = new Date().toISOString()
        applyDevicePatch(deviceId, (device) => ({
          ...device,
          actuators: (device.actuators ?? []).map((a) => {
            if (a.gpio !== gpio) return a
            if (command === 'ON') {
              return { ...a, state: true, pwm_value: 1, last_command_at: commandAt }
            }
            if (command === 'OFF') {
              return { ...a, state: false, pwm_value: 0, last_command_at: commandAt }
            }
            const normalized = value ?? 0
            return { ...a, state: normalized > 0, pwm_value: normalized, last_command_at: commandAt }
          }),
        }))
      }
    } catch (err: unknown) {
      const uiError = toUiApiError(err, 'Befehl konnte nicht gesendet werden')
      const msg =
        uiError.status === 409
          ? `Befehl nicht ausgeführt: Gerät ist offline oder aktuell blockiert.\n${formatUiApiError(uiError)}`
          : formatUiApiError(uiError)
      toast.error(msg, { persistent: true })
      throw err
    }
  }

  /**
   * Emergency stop all actuators (real API, not mock-only).
   */
  async function emergencyStopAll(reason: string = 'Manueller Notfall-Stopp über UI'): Promise<void> {
    const toast = useToast()
    try {
      const result = await actuatorsApi.emergencyStop({ reason })
      toast.show({
        message: `NOTFALL-STOPP: ${result.actuators_stopped} Aktoren auf ${result.devices_stopped} Geräten gestoppt`,
        type: 'warning',
        persistent: true,
      })
      await fetchAll()
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, 'Notfall-Stopp fehlgeschlagen')
      toast.error(msg, { persistent: true })
      throw err
    }
  }

  /**
   * Clear emergency stop for all actuators (real API).
   * Releases emergency state so actuators can be controlled again.
   */
  async function clearEmergencyAll(): Promise<void> {
    const toast = useToast()
    try {
      const result = await actuatorsApi.clearEmergency()
      toast.success(`Not-Aus aufgehoben: ${result.devices_cleared} Geräte`)
      await fetchAll()
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, 'Not-Aus aufheben fehlgeschlagen')
      toast.error(msg, { persistent: true })
      throw err
    }
  }

  // =============================================================================
  // WebSocket Registration
  // =============================================================================
  // NOTE: Pinia stores don't have lifecycle hooks like Vue components.
  // We register handlers immediately and provide explicit cleanup methods.

  /**
   * Initialize WebSocket subscriptions.
   * Called automatically on store creation.
   * Safe to call multiple times (guards against duplicate registration).
   */
  function initWebSocket(): void {
    if (wsUnsubscribers.length > 0) {
      logger.debug('WebSocket handlers already registered, skipping')
      return
    }

    // Each ws.on() returns an unsubscribe function - store for cleanup
    wsUnsubscribers.push(
      ws.on('esp_health', handleEspHealth),
      ws.on('sensor_data', handleSensorData),
      ws.on('actuator_status', handleActuatorStatus),
      ws.on('actuator_alert', handleActuatorAlert),
      ws.on('config_response', handleConfigResponse),
      ws.on('config_response_guard_replay', handleConfigResponseGuardReplay),
      ws.on('zone_assignment', handleZoneAssignment),
      ws.on('subzone_assignment', handleSubzoneAssignment),  // WP4
      ws.on('sensor_health', handleSensorHealth),  // Phase 2E
      ws.on('sensor_config_deleted', handleSensorConfigDeleted),  // T08-Fix D
      ws.on('actuator_config_deleted', handleActuatorConfigDeleted),  // Fix-Q: reactive actuator delete
      // T13-R2: Device Scope & Context
      ws.on('device_scope_changed', handleDeviceScopeChanged),
      ws.on('device_context_changed', handleDeviceContextChanged),
      ws.on('esp_reconnect_phase', handleEspReconnectPhase),
      // Discovery/Approval Phase
      ws.on('device_discovered', handleDeviceDiscovered),
      ws.on('device_approved', handleDeviceApproved),
      ws.on('device_rejected', handleDeviceRejected),
      // Phase UI/UX 1: Feedback & Notifications
      ws.on('actuator_response', handleActuatorResponse),
      ws.on('notification', handleNotification),
      ws.on('error_event', handleErrorEvent),
      ws.on('system_event', handleSystemEvent),
      // Phase 4A: Notification Inbox
      ws.on('notification_new', handleNotificationNew),
      ws.on('notification_updated', handleNotificationUpdated),
      ws.on('notification_unread_count', handleNotificationUnreadCount),
      // Phase UI/UX 2: Full Event Coverage
      ws.on('actuator_command', handleActuatorCommand),
      ws.on('actuator_command_failed', handleActuatorCommandFailed),
      ws.on('config_published', handleConfigPublished),
      ws.on('config_failed', handleConfigFailed),
      ws.on('device_rediscovered', handleDeviceRediscovered),
      ws.on('sequence_started', handleSequenceStarted),
      ws.on('sequence_step', handleSequenceStep),
      ws.on('sequence_completed', handleSequenceCompleted),
      ws.on('sequence_error', handleSequenceError),
      ws.on('sequence_cancelled', handleSequenceCancelled),
      ws.on('intent_outcome', handleIntentOutcome),
      ws.on('intent_outcome_lifecycle', handleIntentOutcomeLifecycle),
      ws.on('logic_execution', handleLogicExecution),
    )

    // PKG-20: periodic prune of stale disconnect timestamps (every 60 s)
    if (!_flappingPruneTimer) {
      _flappingPruneTimer = setInterval(() => {
        const now = Date.now()
        for (const [espId, timestamps] of _disconnectLog) {
          pruneOldTimestamps(timestamps, now)
          if (timestamps.length === 0) _disconnectLog.delete(espId)
        }
        _flappingTick.value++
      }, 60_000)
    }

    // BUG U FIX: Register callback to refresh ESP data when WebSocket connects/reconnects
    // This ensures the UI shows the current state from the server after connection is established
    wsUnsubscribers.push(
      websocketService.onConnect(() => {
        logger.info('WebSocket connected, refreshing ESP data...')
        const actStore = useActuatorStore()
        fetchAll()
          .catch(err => {
            logger.error(`Failed to refresh ESP data after WebSocket connect:`, err)
          })
          .finally(() => {
            actStore.reconcilePendingIntentsFromServer({
              espIds: devices.value.map((device) => getDeviceId(device)).filter(Boolean),
            }).catch(err => {
              logger.warn('Failed to reconcile pending intents after WebSocket connect', err)
            })
          })
        const zs = useZoneStore()
        zs.fetchZoneEntities().catch(err => {
          logger.error(`Failed to refresh zone entities after WebSocket connect:`, err)
        })
      })
    )

    logger.debug('WebSocket handlers registered')
  }

  /**
   * Cleanup WebSocket subscriptions.
   * Call when app is being destroyed or user logs out.
   */
  function cleanupWebSocket(): void {
    useIntentSignalsStore().clearAll()
    if (subzoneRefreshTimer) {
      clearTimeout(subzoneRefreshTimer)
      subzoneRefreshTimer = null
    }
    if (_flappingPruneTimer) {
      clearInterval(_flappingPruneTimer)
      _flappingPruneTimer = null
    }
    _disconnectLog.clear()
    wsUnsubscribers.forEach(unsub => unsub())
    wsUnsubscribers.length = 0
    ws.disconnect()
    logger.debug('WebSocket handlers unregistered')
  }

  // Auto-initialize WebSocket handlers on store creation
  initWebSocket()

  return {
    // State
    devices,
    devicesLiveTick,
    selectedDeviceId,
    isLoading,
    error,
    
    // Pending Devices State (Discovery/Approval)
    pendingDevices,
    isPendingLoading,
    pendingCount,

    // Getters
    selectedDevice,
    deviceCount,
    onlineDevices,
    offlineDevices,
    mockDevices,
    realDevices,
    devicesByZone,
    unassignedDevices,
    masterZoneDevices,
    isMock,
    getDeviceId,

    // Actions
    fetchAll,
    fetchDevice,
    ensureRealtimeHandlers,
    createDevice,
    updateDevice,
    updateDeviceZone,
    deleteDevice,
    getHealth,
    restartDevice,
    resetDevice,
    
    // Pending Device Actions (Discovery/Approval)
    fetchPendingDevices,
    approveDevice,
    rejectDevice,
    
    // Actuator Commands (Real + Mock)
    sendActuatorCommand,
    emergencyStopAll,
    clearEmergencyAll,

    // Mock ESP specific actions
    triggerHeartbeat,
    setState,
    setAutoHeartbeat,
    addSensor,
    updateSensorConfig,  // Phase 2F: Edit Sensor Config
    setSensorValue,
    removeSensor,
    addActuator,
    setActuatorState,
    emergencyStop,
    clearEmergency,
    
    // Utility
    selectDevice,
    clearError,
    updateDeviceInList,
    replaceDevices,
    applyDevicePatch,

    // Flapping Detection (PKG-20)
    flappingDeviceIds,
    flappingDeviceCount,
    hasFlappingDevices,
    getDisconnectCount,
    getFlappingDevicesInZone,

    // WebSocket management
    initWebSocket,
    cleanupWebSocket,

    // GPIO Status (Phase 3)
    gpioStatusMap,
    gpioStatusLoading,
    getGpioStatusForEsp,
    getAvailableGpios,
    getReservedGpios,
    isGpioAvailableForEsp,
    getAllPinStatuses,
    getSystemPinName,
    fetchGpioStatus,
    clearGpioStatus,
    updateGpioStatusFromHeartbeat,

    // OneWire Scan (Phase 6 - DS18B20 Support)
    oneWireScanStates,
    getOneWireScanState,
    scanOneWireBus,
    clearOneWireScan,
    toggleRomSelection,
    selectAllOneWireDevices,
    deselectAllOneWireDevices,
    selectSpecificRomCodes,
    isRomCodeSelected,
  }
})
