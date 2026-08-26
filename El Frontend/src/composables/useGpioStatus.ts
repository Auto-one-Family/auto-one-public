/**
 * Composable for GPIO status management
 *
 * Provides reactive GPIO status for a specific ESP device.
 * Handles loading, error states, and automatic updates.
 *
 * @example
 * ```vue
 * <script setup>
 * const { gpioStatus, availableGpios, isLoading, refresh } = useGpioStatus('ESP_12AB34CD')
 * </script>
 * ```
 *
 * @author KI-Agent (Claude)
 * @since Phase 3 (GPIO-Status Frontend Integration)
 */

import { computed, watch, onMounted, type Ref, isRef } from 'vue'
import { useEspStore } from '@/stores/esp'
import type {
  GpioStatusResponse,
  GpioPinStatus,
  GpioUsageItem,
  GpioValidationResult
} from '@/types/gpio'

export function useGpioStatus(espId: string | Ref<string>) {
  const espStore = useEspStore()

  // Reactive espId (support both string and ref)
  const resolvedEspId = computed(() =>
    isRef(espId) ? espId.value : espId
  )

  // ════════════════════════════════════════════════════════════════
  // REACTIVE STATE
  // ════════════════════════════════════════════════════════════════

  const gpioStatus = computed<GpioStatusResponse | null>(() =>
    espStore.getGpioStatusForEsp(resolvedEspId.value)
  )

  const isLoading = computed<boolean>(() =>
    espStore.gpioStatusLoading.get(resolvedEspId.value) ?? false
  )

  const availableGpios = computed<number[]>(() =>
    espStore.getAvailableGpios(resolvedEspId.value)
  )

  const reservedGpios = computed<GpioUsageItem[]>(() =>
    espStore.getReservedGpios(resolvedEspId.value)
  )

  const allPinStatuses = computed<GpioPinStatus[]>(() =>
    espStore.getAllPinStatuses(resolvedEspId.value)
  )

  const lastUpdate = computed<string | null>(() =>
    gpioStatus.value?.last_esp_report ?? null
  )

  // ════════════════════════════════════════════════════════════════
  // VALIDATION HELPERS
  // ════════════════════════════════════════════════════════════════

  /**
   * Check if a specific GPIO is available.
   */
  function isGpioAvailable(gpio: number): boolean {
    return espStore.isGpioAvailableForEsp(resolvedEspId.value, gpio)
  }

  /**
   * Check if a GPIO is used as a OneWire bus.
   * 
   * OneWire Multi-Device Support: Returns true if the GPIO is already
   * configured as a OneWire bus, meaning additional DS18B20 sensors
   * can be added to this GPIO without conflict.
   */
  function isOneWireBus(gpio: number): boolean {
    const status = gpioStatus.value
    if (!status?.onewire_buses) return false
    return status.onewire_buses.some(bus => bus.gpio === gpio)
  }

  /**
   * Get OneWire bus info for a GPIO.
   */
  function getOneWireBusInfo(gpio: number) {
    const status = gpioStatus.value
    if (!status?.onewire_buses) return null
    return status.onewire_buses.find(bus => bus.gpio === gpio) ?? null
  }

  /**
   * Validate GPIO selection with detailed message.
   */
  function validateGpio(gpio: number): GpioValidationResult {
    const status = gpioStatus.value

    if (!status) {
      return { valid: false, message: 'GPIO-Status nicht verfügbar' }
    }

    // System pin?
    if (status.system.includes(gpio)) {
      return {
        valid: false,
        message: `GPIO ${gpio} ist ein System-Pin und nicht verfügbar`
      }
    }

    // Reserved?
    const reserved = status.reserved.find(r => r.gpio === gpio)
    if (reserved) {
      const ownerLabel = reserved.owner === 'sensor' ? 'Sensor' :
                         reserved.owner === 'actuator' ? 'Aktor' : 'System'
      return {
        valid: false,
        message: `GPIO ${gpio} ist bereits belegt von ${ownerLabel}: ${reserved.name || reserved.component}`
      }
    }

    // Available
    if (status.available.includes(gpio)) {
      return { valid: true, message: null }
    }

    // Unknown state
    return { valid: false, message: `GPIO ${gpio} Status unbekannt` }
  }

  /**
   * Validate GPIO selection for a specific sensor type.
   * 
   * OneWire Multi-Device Support: DS18B20 (OneWire) sensors can share
   * a GPIO pin with other DS18B20 sensors, unlike Analog/Digital sensors.
   * 
   * @param gpio - GPIO pin number
   * @param sensorType - Sensor type (e.g., 'ds18b20', 'ph', 'sht31_temp')
   * @returns Validation result with detailed message
   */
  function validateGpioForSensor(gpio: number, sensorType?: string): GpioValidationResult {
    const status = gpioStatus.value

    if (!status) {
      return { valid: false, message: 'GPIO-Status nicht verfügbar' }
    }

    // System pin? - Never allowed
    if (status.system.includes(gpio)) {
      return {
        valid: false,
        message: `GPIO ${gpio} ist ein System-Pin und nicht verfügbar`
      }
    }

    // Check if this is a OneWire sensor (DS18B20)
    const isOneWireSensor = sensorType?.toLowerCase().includes('ds18b20')

    // OneWire Special Case: DS18B20 can share GPIO with other DS18B20
    if (isOneWireSensor && isOneWireBus(gpio)) {
      const busInfo = getOneWireBusInfo(gpio)
      const deviceCount = busInfo?.devices.length ?? 0
      return {
        valid: true,
        message: `GPIO ${gpio} ist ein OneWire-Bus mit ${deviceCount} Sensor(en). Weitere DS18B20 können hinzugefügt werden.`
      }
    }

    // Check reserved GPIOs
    const reserved = status.reserved.find(r => r.gpio === gpio)
    if (reserved) {
      // If it's a OneWire sensor trying to use a non-OneWire occupied GPIO
      if (isOneWireSensor) {
        return {
          valid: false,
          message: `GPIO ${gpio} ist bereits von einem anderen Sensor-Typ belegt: ${reserved.name || reserved.component}`
        }
      }
      
      const ownerLabel = reserved.owner === 'sensor' ? 'Sensor' :
                         reserved.owner === 'actuator' ? 'Aktor' : 'System'
      return {
        valid: false,
        message: `GPIO ${gpio} ist bereits belegt von ${ownerLabel}: ${reserved.name || reserved.component}`
      }
    }

    // Check if there's a OneWire bus on this GPIO (for non-OneWire sensors)
    if (!isOneWireSensor && isOneWireBus(gpio)) {
      return {
        valid: false,
        message: `GPIO ${gpio} ist ein OneWire-Bus. Nur DS18B20-Sensoren können diesen Pin nutzen.`
      }
    }

    // Available
    if (status.available.includes(gpio)) {
      return { valid: true, message: null }
    }

    // Unknown state
    return { valid: false, message: `GPIO ${gpio} Status unbekannt` }
  }

  /**
   * Get status info for a specific GPIO.
   */
  function getGpioInfo(gpio: number): GpioPinStatus | null {
    return allPinStatuses.value.find(p => p.gpio === gpio) ?? null
  }

  // ════════════════════════════════════════════════════════════════
  // ACTIONS
  // ════════════════════════════════════════════════════════════════

  /**
   * Refresh GPIO status from server.
   */
  async function refresh(): Promise<void> {
    await espStore.fetchGpioStatus(resolvedEspId.value)
  }

  // ════════════════════════════════════════════════════════════════
  // LIFECYCLE
  // ════════════════════════════════════════════════════════════════

  // Auto-fetch on mount if not already loaded
  onMounted(() => {
    if (!gpioStatus.value && !isLoading.value && resolvedEspId.value) {
      refresh()
    }
  })

  // Re-fetch when espId changes
  watch(resolvedEspId, (newId, oldId) => {
    if (newId && newId !== oldId) {
      refresh()
    }
  })

  // ════════════════════════════════════════════════════════════════
  // RETURN
  // ════════════════════════════════════════════════════════════════

  return {
    // State
    gpioStatus,
    isLoading,
    availableGpios,
    reservedGpios,
    allPinStatuses,
    lastUpdate,

    // Validation
    isGpioAvailable,
    validateGpio,
    validateGpioForSensor,
    getGpioInfo,

    // OneWire Multi-Device Support
    isOneWireBus,
    getOneWireBusInfo,

    // Actions
    refresh
  }
}
