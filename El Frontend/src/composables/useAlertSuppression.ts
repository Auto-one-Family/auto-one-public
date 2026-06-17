/**
 * useAlertSuppression — AUT-255 Alert-Suppression-Kaskade
 *
 * Aggregates sensor-level and device-level alert-suppression state into a single
 * reactive view-model so that UI components can display the suppression cascade
 * (sensor own suppression vs. device-wide propagation).
 *
 * Server contract (read-only):
 * - SensorConfig.alert_config: { alerts_enabled?: boolean, suppression_until?: string|null, suppression_reason?: string|null }
 * - esp_device.alert_config:   { propagate_to_children?: boolean, suppression_until?: string|null, suppression_reason?: string|null }
 */
import { computed } from 'vue'
import type { Ref } from 'vue'
import { formatSuppressionReason } from '@/utils/formatters'

export type SuppressionSource = 'sensor' | 'device' | 'both' | 'none'

export interface SuppressionState {
  /** True when either sensor or device suppression is active */
  isActive: boolean
  /** Where the active suppression originates */
  source: SuppressionSource
  /** ISO timestamp of sensor-level suppression end (null if not set) */
  sensorSuppressedUntil: string | null
  /** ISO timestamp of device-level suppression end (null if not set) */
  deviceSuppressedUntil: string | null
  /** Sensor-level suppression reason (raw enum value) */
  sensorReason: string | null
  /** Device-level suppression reason (raw enum value) */
  deviceReason: string | null
  /** The later of the two end timestamps (effective reactivation time) */
  effectiveUntil: string | null
}

interface SensorAlertConfig {
  alerts_enabled?: boolean
  suppression_until?: string | null
  suppression_reason?: string | null
}

interface DeviceAlertConfig {
  propagate_to_children?: boolean
  suppression_until?: string | null
  suppression_reason?: string | null
}

export function useAlertSuppression(
  sensorAlertConfig: Ref<SensorAlertConfig | null | undefined>,
  deviceAlertConfig: Ref<DeviceAlertConfig | null | undefined>,
) {
  const suppression = computed((): SuppressionState => {
    const now = new Date()
    const sac = sensorAlertConfig.value
    const dac = deviceAlertConfig.value

    const sensorSuppressedUntil = sac?.suppression_until ?? null
    const deviceSuppressedUntil = dac?.suppression_until ?? null

    const sensorActive =
      sac?.alerts_enabled === false ||
      (sensorSuppressedUntil != null && new Date(sensorSuppressedUntil) > now)

    const deviceActive =
      dac?.propagate_to_children === true ||
      (deviceSuppressedUntil != null && new Date(deviceSuppressedUntil) > now)

    const isActive = sensorActive || deviceActive

    let source: SuppressionSource = 'none'
    if (sensorActive && deviceActive) source = 'both'
    else if (sensorActive) source = 'sensor'
    else if (deviceActive) source = 'device'

    let effectiveUntil: string | null = null
    if (sensorSuppressedUntil && deviceSuppressedUntil) {
      effectiveUntil =
        new Date(sensorSuppressedUntil) > new Date(deviceSuppressedUntil)
          ? sensorSuppressedUntil
          : deviceSuppressedUntil
    } else {
      effectiveUntil = sensorSuppressedUntil ?? deviceSuppressedUntil
    }

    return {
      isActive,
      source,
      sensorSuppressedUntil,
      deviceSuppressedUntil,
      sensorReason: sac?.suppression_reason ?? null,
      deviceReason: dac?.suppression_reason ?? null,
      effectiveUntil,
    }
  })

  return { suppression, formatSuppressionReason }
}
