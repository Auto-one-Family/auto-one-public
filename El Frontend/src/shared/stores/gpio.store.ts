/**
 * GPIO Store
 *
 * Manages GPIO pin status and OneWire bus scanning per ESP device.
 * Mirrors server-side gpio_service.py and onewire endpoints.
 *
 * Server-centric architecture:
 * Frontend → REST (GET /esp/{id}/gpio-status) → Server → this store
 * ESP32 → MQTT (heartbeat gpio_status[]) → Server → WS (esp_health) → esp.store → this store
 * Frontend → REST (POST /sensors/onewire/scan) → Server → MQTT → ESP → Server → REST response → this store
 *
 * Cross-store dependency: esp.store.ts calls updateGpioStatusFromHeartbeat
 * and fetchGpioStatus from this store.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import { espApi } from '@/api/esp'
import { oneWireApi, type OneWireDevice, type OneWireScanResponse } from '@/api/sensors'
import { useToast } from '@/composables/useToast'
import { createLogger } from '@/utils/logger'
import type {
  GpioStatusResponse, GpioUsageItem, GpioPinStatus,
  GpioOwner, HeartbeatGpioItem,
} from '@/types'

const logger = createLogger('GpioStore')

// =========================================================================
// OneWire Scan Types
// =========================================================================

export interface OneWireScanState {
  isScanning: boolean
  scanResults: OneWireDevice[]
  selectedRomCodes: string[]
  scanError: string | null
  lastScanTimestamp: number | null
  lastScanPin: number | null
}

export const useGpioStore = defineStore('gpio', () => {

  // =========================================================================
  // State
  // =========================================================================

  const gpioStatusMap = ref<Map<string, GpioStatusResponse>>(new Map())
  const gpioStatusLoading = ref<Map<string, boolean>>(new Map())
  const oneWireScanStates = ref<Record<string, OneWireScanState>>({})

  // =========================================================================
  // GPIO Status Getters
  // =========================================================================

  /** Get GPIO status for a specific ESP. */
  function getGpioStatusForEsp(espId: string): GpioStatusResponse | null {
    return gpioStatusMap.value.get(espId) ?? null
  }

  /** Get available GPIOs for a specific ESP. */
  function getAvailableGpios(espId: string): number[] {
    return gpioStatusMap.value.get(espId)?.available ?? []
  }

  /** Get reserved GPIOs for a specific ESP. */
  function getReservedGpios(espId: string): GpioUsageItem[] {
    return gpioStatusMap.value.get(espId)?.reserved ?? []
  }

  /** Check if a GPIO is available for a specific ESP. */
  function isGpioAvailableForEsp(espId: string, gpio: number): boolean {
    const status = gpioStatusMap.value.get(espId)
    if (!status) return false  // Unknown = not available (safe default)
    return status.available.includes(gpio)
  }

  /** Get human-readable name for system pins. */
  function getSystemPinName(gpio: number): string {
    const names: Record<number, string> = {
      0: 'Boot',
      1: 'UART TX',
      2: 'Boot',
      3: 'UART RX',
      6: 'Flash CLK',
      7: 'Flash D0',
      8: 'Flash D1',
      9: 'Flash D2',
      10: 'Flash D3',
      11: 'Flash CMD',
      21: 'I2C SDA',
      22: 'I2C SCL'
    }
    return names[gpio] ?? `System ${gpio}`
  }

  /**
   * Get enriched pin status list for UI.
   * Combines all GPIO info into displayable format.
   */
  function getAllPinStatuses(espId: string): GpioPinStatus[] {
    const status = gpioStatusMap.value.get(espId)
    if (!status) return []

    const allPins: GpioPinStatus[] = []

    // Available pins
    for (const gpio of status.available) {
      allPins.push({
        gpio,
        available: true,
        owner: null,
        component: null,
        name: null,
        statusClass: 'available',
        tooltip: `GPIO ${gpio} - Verfügbar`
      })
    }

    // Reserved pins
    for (const item of status.reserved) {
      allPins.push({
        gpio: item.gpio,
        available: false,
        owner: item.owner,
        component: item.component,
        name: item.name,
        statusClass: item.owner as 'sensor' | 'actuator' | 'system',
        tooltip: `GPIO ${item.gpio} - ${item.owner}: ${item.name || item.component}`
      })
    }

    // System pins
    for (const gpio of status.system) {
      allPins.push({
        gpio,
        available: false,
        owner: 'system',
        component: getSystemPinName(gpio),
        name: null,
        statusClass: 'system',
        tooltip: `GPIO ${gpio} - System (${getSystemPinName(gpio)})`
      })
    }

    return allPins.sort((a, b) => a.gpio - b.gpio)
  }

  // =========================================================================
  // GPIO Status Actions
  // =========================================================================

  /**
   * Fetch GPIO status for an ESP device.
   *
   * Called when:
   * - ESP detail view is opened
   * - Add sensor/actuator modal is opened
   * - After successful sensor/actuator creation
   */
  async function fetchGpioStatus(espId: string): Promise<GpioStatusResponse | null> {
    // Prevent duplicate fetches
    if (gpioStatusLoading.value.get(espId)) {
      return gpioStatusMap.value.get(espId) ?? null
    }

    gpioStatusLoading.value.set(espId, true)

    try {
      const status = await espApi.getGpioStatus(espId)
      gpioStatusMap.value.set(espId, status)
      return status
    } catch (err) {
      logger.error(`Failed to fetch GPIO status for ${espId}:`, err)
      return null
    } finally {
      gpioStatusLoading.value.set(espId, false)
    }
  }

  /** Clear GPIO status for an ESP (e.g., when device goes offline). */
  function clearGpioStatus(espId: string): void {
    gpioStatusMap.value.delete(espId)
  }

  /**
   * Update GPIO status from WebSocket esp_health event.
   *
   * Partial update: Only updates if gpio_status is present in event.
   * If no full status exists yet, triggers a full fetch.
   */
  function updateGpioStatusFromHeartbeat(
    espId: string,
    gpioStatus: HeartbeatGpioItem[]
  ): void {
    const current = gpioStatusMap.value.get(espId)
    if (!current) {
      // No full status yet, trigger full fetch
      fetchGpioStatus(espId)
      return
    }

    // Update reserved list from ESP-reported data
    const espReported: GpioUsageItem[] = gpioStatus
      .filter(item => !item.safe)  // Only non-safe-mode pins
      .map(item => ({
        gpio: item.gpio,
        owner: item.owner as GpioOwner,
        component: item.component,
        name: null,
        id: null,
        source: 'esp_reported' as const
      }))

    // Merge: Keep DB-sourced items, add/update ESP-reported
    const dbItems = current.reserved.filter(r => r.source === 'database' || r.source === 'static')
    const mergedReserved = [...dbItems]

    for (const espItem of espReported) {
      const existingIndex = mergedReserved.findIndex(r => r.gpio === espItem.gpio)
      if (existingIndex === -1) {
        mergedReserved.push(espItem)
      }
      // Don't overwrite DB/static items with ESP items (DB is more detailed)
    }

    // Update available list
    const reservedGpios = new Set(mergedReserved.map(r => r.gpio))
    const systemGpios = new Set(current.system)
    const available = Array.from({ length: 49 }, (_, i) => i)
      .filter(gpio => !reservedGpios.has(gpio) && !systemGpios.has(gpio))

    gpioStatusMap.value.set(espId, {
      ...current,
      available,
      reserved: mergedReserved,
      last_esp_report: new Date().toISOString()
    })
  }

  // =========================================================================
  // OneWire Scan State & Actions
  // =========================================================================

  /**
   * Get or initialize OneWire scan state for an ESP.
   */
  function getOneWireScanState(espId: string): OneWireScanState {
    if (!oneWireScanStates.value[espId]) {
      oneWireScanStates.value[espId] = {
        isScanning: false,
        scanResults: [],
        selectedRomCodes: [],
        scanError: null,
        lastScanTimestamp: null,
        lastScanPin: null
      }
    }
    return oneWireScanStates.value[espId]
  }

  /**
   * Scan OneWire bus for devices.
   *
   * Sends MQTT command to ESP, waits for scan result (10s timeout).
   */
  async function scanOneWireBus(espId: string, pin: number = 4): Promise<OneWireScanResponse> {
    const state = getOneWireScanState(espId)
    state.isScanning = true
    state.scanError = null
    state.scanResults = []
    state.selectedRomCodes = []

    const toast = useToast()

    try {
      const response = await oneWireApi.scanBus(espId, pin)

      state.scanResults = response.devices
      state.lastScanTimestamp = Date.now()
      state.lastScanPin = pin

      if (response.found_count === 0) {
        toast.warning(`Keine OneWire-Geräte auf GPIO ${pin} gefunden`, {
          duration: 6000
        })
      } else {
        toast.success(
          `${response.found_count} OneWire-Gerät(e) auf GPIO ${pin} gefunden`,
          { duration: 5000 }
        )
      }

      return response

    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string }; status?: number } }

      let errorMsg = 'Scan fehlgeschlagen'

      if (axiosError.response?.status === 404) {
        errorMsg = 'ESP-Gerät nicht gefunden'
      } else if (axiosError.response?.status === 503) {
        errorMsg = 'ESP-Gerät ist offline'
      } else if (axiosError.response?.status === 504) {
        errorMsg = `ESP antwortet nicht (Timeout). Ist OneWire-Bus auf GPIO ${pin} konfiguriert?`
      } else if (axiosError.response?.data?.detail) {
        errorMsg = axiosError.response.data.detail
      }

      state.scanError = errorMsg

      toast.error(`OneWire-Scan fehlgeschlagen: ${errorMsg}`, {
        duration: 8000
      })

      throw err
    } finally {
      state.isScanning = false
    }
  }

  /** Clear OneWire scan results and state. */
  function clearOneWireScan(espId: string): void {
    const state = getOneWireScanState(espId)
    state.scanResults = []
    state.selectedRomCodes = []
    state.scanError = null
  }

  /** Toggle ROM code selection for multi-select. */
  function toggleRomSelection(espId: string, romCode: string): void {
    const state = getOneWireScanState(espId)
    const index = state.selectedRomCodes.indexOf(romCode)

    if (index > -1) {
      state.selectedRomCodes.splice(index, 1)
    } else {
      state.selectedRomCodes.push(romCode)
    }
  }

  /** Select all discovered devices. */
  function selectAllOneWireDevices(espId: string): void {
    const state = getOneWireScanState(espId)
    state.selectedRomCodes = state.scanResults.map(d => d.rom_code)
  }

  /** Deselect all devices. */
  function deselectAllOneWireDevices(espId: string): void {
    const state = getOneWireScanState(espId)
    state.selectedRomCodes = []
  }

  /**
   * Select specific ROM codes (replaces current selection).
   * Used to select only NEW (non-configured) devices.
   */
  function selectSpecificRomCodes(espId: string, romCodes: string[]): void {
    const state = getOneWireScanState(espId)
    state.selectedRomCodes = [...romCodes]
  }

  /** Check if a ROM code is currently selected. */
  function isRomCodeSelected(espId: string, romCode: string): boolean {
    const state = getOneWireScanState(espId)
    return state.selectedRomCodes.includes(romCode)
  }

  return {
    // GPIO State (reactive)
    gpioStatusMap,
    gpioStatusLoading,

    // GPIO Getters
    getGpioStatusForEsp,
    getAvailableGpios,
    getReservedGpios,
    isGpioAvailableForEsp,
    getSystemPinName,
    getAllPinStatuses,

    // GPIO Actions
    fetchGpioStatus,
    clearGpioStatus,
    updateGpioStatusFromHeartbeat,

    // OneWire State (reactive)
    oneWireScanStates,

    // OneWire Getters & Actions
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
