/**
 * Ist/Soll/Delta display helpers for TankIstSollPanel (AUT-1225 Q4).
 *
 * Pure functions only — no store/API access — so they stay trivially
 * unit-testable. The single hard rule they encode: a missing/stale
 * value is NEVER rendered as "0" — always the em-dash "—".
 */

import type { TankMeasureTarget, TankTargetMeasure } from '@/types'
import { getSensorAggCategory } from '@/utils/sensorDefaults'

/**
 * Sensor-type keys the Ist lookup matches against (via AggCategory).
 * `temperature` is compact-tile only (AUT-1537) — not a TankTargetMeasure.
 */
export type IstSollMeasureKey = 'ec' | 'ph' | 'temperature'

/** Minimal sensor shape needed for the Ist lookup (subset of MockSensor). */
export interface IstSollSensorLike {
  sensor_type: string
  raw_value?: number | null
  processed_value?: number | null
}

/** Minimal device shape needed for the Ist lookup (subset of ESPDevice). */
export interface IstSollDeviceLike {
  device_id?: string
  esp_id?: string
  sensors?: IstSollSensorLike[]
}

/** Maps a server target measure key to the sensor_type it corresponds to. */
export function measureKeyFromTarget(measure: TankTargetMeasure): IstSollMeasureKey | null {
  if (measure === 'target_ec') return 'ec'
  if (measure === 'target_ph') return 'ph'
  return null
}

/**
 * Find the current Ist value for a measure across the tank's assigned
 * devices. Returns `null` when no assigned device carries a sensor of that
 * type, or the sensor has no value yet — callers must render "—", not "0".
 *
 * Prefers `processed_value` (Pi-enhanced) over `raw_value`, matching the
 * fallback used elsewhere in the dashboard (esp.ts sensor merge).
 */
export function findIstSensorValue(
  devices: IstSollDeviceLike[],
  assignedDeviceIds: string[],
  measureKey: IstSollMeasureKey,
): number | null {
  if (assignedDeviceIds.length === 0) return null
  const assignedIds = new Set(assignedDeviceIds)

  for (const device of devices) {
    const id = device.device_id || device.esp_id || ''
    if (!id || !assignedIds.has(id)) continue

    for (const sensor of device.sensors ?? []) {
      if (getSensorAggCategory(sensor.sensor_type) !== measureKey) continue
      const value = sensor.processed_value ?? sensor.raw_value
      if (value === null || value === undefined || Number.isNaN(value)) continue
      return value
    }
  }
  return null
}

/**
 * Format a numeric Ist/Soll value for display. `null`/`undefined`/`NaN`
 * ALWAYS render as the em-dash "—" — never "0" (AUT-1225 Q4 binding rule).
 */
export function formatIstSollValue(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/**
 * Compute Delta (Ist - Soll). Returns `null` unless BOTH operands are
 * finite numbers — a one-sided "0" delta would misrepresent a missing
 * reading as "on target".
 */
export function computeDelta(
  ist: number | null | undefined,
  soll: number | null | undefined,
): number | null {
  if (typeof ist !== 'number' || typeof soll !== 'number') return null
  if (Number.isNaN(ist) || Number.isNaN(soll)) return null
  return ist - soll
}

/** Format a Delta value with an explicit sign (e.g. "+0,30" / "-0,15" / "—"). */
export function formatDelta(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${formatIstSollValue(value, decimals)}`
}

/** German label for a resolved target measure. */
export function measureLabel(measure: TankTargetMeasure): string {
  return measure === 'target_ec' ? 'EC' : 'pH'
}

/** German label for how the Soll segment was resolved. */
export function resolvedViaLabel(resolvedVia: TankMeasureTarget['resolved_via']): string {
  if (resolvedVia === 'zone') return 'via Zone'
  if (resolvedVia === 'subzone') return 'via Subzone'
  return 'kein Plan-Segment'
}

/**
 * AUT-1327 / AUT-1339: single swap-point for tank detail navigation.
 * Canonical home = Nährlösungs-Tab Detail (`/nutrient-solution/:tankId`).
 */
export const TANK_DETAIL_ROUTE = '/nutrient-solution' as const

/**
 * Legacy query key still read by PlantsView for deep-links that used
 * `/plants?tank=` before the NL-Tab became the detail home.
 */
export const TANK_DETAIL_QUERY_KEY = 'tank' as const

/** Build href for the tank detail (Monitor compact → NL-Tab). */
export function tankDetailHref(tankId: string): string {
  return `${TANK_DETAIL_ROUTE}/${encodeURIComponent(tankId)}`
}
