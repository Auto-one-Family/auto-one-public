import { computed, type Ref } from 'vue'
import type { ComputedRef } from 'vue'

/**
 * Parsed parts from a sensorId string (format: "espId:gpio:sensorType").
 *
 * Legacy support: two-part format "espId:gpio" is valid — sensorType will be null.
 */
export interface SensorIdParts {
  espId: string | null
  gpio: number | null
  sensorType: string | null
  /** true when espId and gpio are set (sensorType optional for legacy) */
  isValid: boolean
}

/**
 * Parses a sensorId string into its constituent parts.
 *
 * Supports both formats:
 * - "espId:gpio:sensorType" (3-part, current)
 * - "espId:gpio" (2-part, legacy — sensorType = null)
 *
 * @param sensorId - Ref or getter returning the sensorId string
 * @returns Reactive SensorIdParts
 */
export function useSensorId(
  sensorId: Ref<string> | (() => string)
): { [K in keyof SensorIdParts]: ComputedRef<SensorIdParts[K]> } {
  const raw = typeof sensorId === 'function' ? computed(sensorId) : sensorId

  const parsed = computed<SensorIdParts>(() => parseSensorId(raw.value))

  return {
    espId: computed(() => parsed.value.espId),
    gpio: computed(() => parsed.value.gpio),
    sensorType: computed(() => parsed.value.sensorType),
    isValid: computed(() => parsed.value.isValid),
  }
}

/**
 * Pure parsing function (non-reactive). Useful for one-off parsing outside components.
 */
export function parseSensorId(value: string | undefined | null): SensorIdParts {
  if (!value) {
    return { espId: null, gpio: null, sensorType: null, isValid: false }
  }

  const parts = value.split(':')
  if (parts.length < 2) {
    return { espId: null, gpio: null, sensorType: null, isValid: false }
  }

  const espId = parts[0] || null
  const gpioRaw = parseInt(parts[1], 10)
  const gpio = isNaN(gpioRaw) ? null : gpioRaw
  const sensorType = parts[2] || null

  const isValid = espId !== null && gpio !== null

  return { espId, gpio, sensorType, isValid }
}
