/**
 * Composable for lazy-loading configured sensor threshold bounds.
 *
 * Reads `threshold_min` / `threshold_max` (scale) and the zone boundaries
 * (warn/alarm) from the server via `sensorsApi.getByConfigId(configId)` and
 * exposes them as reactive refs. `configuredMin`/`configuredMax` form the
 * middle tier of the E2 scale priority chain:
 *   props.yMin/yMax  >  configuredMin/Max  >  sensor-type fallback
 *
 * `configuredWarnLow/High`/`configuredAlarmLow/High` are a SEPARATE, zone-
 * boundary chain (AUT-1104 extension): `alert_config.custom_thresholds` (the
 * operator-maintained thresholds that actually drive real alerts, see
 * `alert_suppression_service.get_effective_thresholds()`) takes priority over
 * the same `sensor_config.thresholds` warning_min/max + threshold_min/max
 * used for the scale. Mirrors the effective-threshold logic already used by
 * `WidgetConfigPanel.vue`'s `fetchEffectiveThresholds()`, but derived from the
 * single `getByConfigId` response already fetched here instead of a second
 * `getAlertConfig` call — this composable is a hot path (every gauge widget),
 * `WidgetConfigPanel` is a one-off per config-panel open.
 *
 * Design decisions:
 * - Module-level cache (Map<configId, Promise<void>>) prevents duplicate
 *   API calls when multiple widgets for the same sensor mount simultaneously.
 * - `onUnmounted` cleanup resets the component-local refs to null so
 *   garbage collection is not blocked by stale reactive references.
 * - Never throws; network errors and missing configId both yield null.
 *
 * @see AUT-1099 — Gauge-Widget Neugestaltung (E2: single source of truth for scale)
 * @see AUT-1104 — custom_thresholds priority stage for zone boundaries
 */

import { ref, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { sensorsApi } from '@/api/sensors'

interface CachedThresholds {
  min: number | null
  max: number | null
  warnLow: number | null
  warnHigh: number | null
  alarmLow: number | null
  alarmHigh: number | null
}

// ─── Module-level cache ─────────────────────────────────────────────────────
// Shared across all component instances so only one fetch per configId
// is ever in flight at the same time.
const _cache = new Map<string, CachedThresholds>()
const _inflight = new Map<string, Promise<void>>()

// ─── Public API ─────────────────────────────────────────────────────────────

export interface UseSensorThresholdsReturn {
  configuredMin: Ref<number | null>
  configuredMax: Ref<number | null>
  /** Zone-boundary priority chain (AUT-1104): custom_thresholds > base warning_min/threshold_min > null. */
  configuredWarnLow: Ref<number | null>
  configuredWarnHigh: Ref<number | null>
  configuredAlarmLow: Ref<number | null>
  configuredAlarmHigh: Ref<number | null>
}

/**
 * @param configId - Reactive ref containing the sensor's `config_id` UUID,
 *   or `null` when no sensor is configured / not yet resolved.
 */
export function useSensorThresholds(
  configId: Ref<string | null>
): UseSensorThresholdsReturn {
  const configuredMin = ref<number | null>(null)
  const configuredMax = ref<number | null>(null)
  const configuredWarnLow = ref<number | null>(null)
  const configuredWarnHigh = ref<number | null>(null)
  const configuredAlarmLow = ref<number | null>(null)
  const configuredAlarmHigh = ref<number | null>(null)

  function _applyCached(cached: CachedThresholds): void {
    configuredMin.value = cached.min
    configuredMax.value = cached.max
    configuredWarnLow.value = cached.warnLow
    configuredWarnHigh.value = cached.warnHigh
    configuredAlarmLow.value = cached.alarmLow
    configuredAlarmHigh.value = cached.alarmHigh
  }

  async function _load(id: string): Promise<void> {
    // Return cached result immediately
    if (_cache.has(id)) {
      _applyCached(_cache.get(id)!)
      return
    }

    // Deduplicate inflight requests
    if (!_inflight.has(id)) {
      const promise = (async () => {
        try {
          const sensorConfig = await sensorsApi.getByConfigId(id)
          // AUT-1104: Exact pattern {0, 100, 0, 100} is the historic generic UI default
          // that was unconditionally saved before this fix — treat it as "not configured"
          // and fall through to the sensor-type fallback instead of using the contaminated values.
          const isLegacyDefault =
            sensorConfig.threshold_min === 0 &&
            sensorConfig.threshold_max === 100 &&
            sensorConfig.warning_min === 0 &&
            sensorConfig.warning_max === 100

          const custom = sensorConfig.custom_thresholds
          const hasCustom =
            !!custom &&
            (custom.warning_min != null ||
              custom.warning_max != null ||
              custom.critical_min != null ||
              custom.critical_max != null)

          _cache.set(id, {
            min: isLegacyDefault ? null : (sensorConfig.threshold_min ?? null),
            max: isLegacyDefault ? null : (sensorConfig.threshold_max ?? null),
            warnLow: hasCustom
              ? (custom!.warning_min ?? null)
              : isLegacyDefault
                ? null
                : (sensorConfig.warning_min ?? null),
            warnHigh: hasCustom
              ? (custom!.warning_max ?? null)
              : isLegacyDefault
                ? null
                : (sensorConfig.warning_max ?? null),
            alarmLow: hasCustom
              ? (custom!.critical_min ?? null)
              : isLegacyDefault
                ? null
                : (sensorConfig.threshold_min ?? null),
            alarmHigh: hasCustom
              ? (custom!.critical_max ?? null)
              : isLegacyDefault
                ? null
                : (sensorConfig.threshold_max ?? null),
          })
        } catch {
          // Network error or 404 — store null so we don't retry per session
          _cache.set(id, {
            min: null,
            max: null,
            warnLow: null,
            warnHigh: null,
            alarmLow: null,
            alarmHigh: null,
          })
        } finally {
          _inflight.delete(id)
        }
      })()
      _inflight.set(id, promise)
    }

    await _inflight.get(id)!
    _applyCached(_cache.get(id)!)
  }

  function _reset(): void {
    configuredMin.value = null
    configuredMax.value = null
    configuredWarnLow.value = null
    configuredWarnHigh.value = null
    configuredAlarmLow.value = null
    configuredAlarmHigh.value = null
  }

  // Watch configId and load thresholds whenever it changes
  const stopWatch = watch(
    configId,
    (id) => {
      if (!id) {
        _reset()
        return
      }
      _load(id)
    },
    { immediate: true }
  )

  onUnmounted(() => {
    stopWatch()
    _reset()
  })

  return {
    configuredMin,
    configuredMax,
    configuredWarnLow,
    configuredWarnHigh,
    configuredAlarmLow,
    configuredAlarmHigh,
  }
}
