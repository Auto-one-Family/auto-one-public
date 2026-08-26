/**
 * Ist/Soll/Delta display helpers for TankIstSollPanel (AUT-1225 Q4).
 *
 * Pure functions only — no store/API access — so they stay trivially
 * unit-testable. Missing/stale/untrusted samples are never treated as a
 * live Ist of 0. Display may show lastKnownValue with a stale hint;
 * Delta and assist receive null.
 */

import type { TankMeasureTarget, TankTargetMeasure } from '@/types'
import { DATA_STALE_THRESHOLD_S } from '@/utils/formatters'
import { getSensorAggCategory } from '@/utils/sensorDefaults'

/**
 * Sensor-type keys the Ist lookup matches against (via AggCategory).
 * `temperature` is compact-tile only (AUT-1537) — not a TankTargetMeasure.
 */
export type IstSollMeasureKey = 'ec' | 'ph' | 'temperature'

/** Qualities that must never be treated as a live tank Ist (processor/firmware error). */
export const UNTRUSTED_IST_QUALITIES = new Set(['error', 'critical', 'warming_up'])

/**
 * EC below this (µS/cm) is physically possible but typical for a dry / air
 * probe — display warning only, not a control-loop change.
 */
export const DRY_EC_HINT_US_CM = 100

/** How trustworthy the current Ist sample is for display vs. assist/delta. */
export type IstTrust = 'live' | 'stale' | 'untrusted' | 'missing'

export interface IstSensorReading {
  /** Usable for Delta / assist only when `trust === 'live'`. */
  value: number | null
  lastKnownValue: number | null
  lastRead: string | null
  quality: string | null
  trust: IstTrust
}

/** Minimal sensor shape needed for the Ist lookup (subset of MockSensor). */
export interface IstSollSensorLike {
  sensor_type: string
  raw_value?: number | null
  processed_value?: number | null
  quality?: string | null
  last_read?: string | null
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

function finiteSensorNumber(sensor: IstSollSensorLike): number | null {
  const value = sensor.processed_value ?? sensor.raw_value
  if (value === null || value === undefined || Number.isNaN(value)) return null
  return value
}

function isStaleLastRead(lastRead: string | null | undefined, nowMs: number): boolean {
  if (!lastRead) return false
  const ts = new Date(lastRead).getTime()
  if (!Number.isFinite(ts)) return false
  return nowMs - ts > DATA_STALE_THRESHOLD_S * 1000
}

/**
 * Resolve Ist for a tank measure with trust — stale / error / warming-up
 * readings stay visible as `lastKnownValue` but `value` is null so Delta
 * and assist never treat them as live tank EC/pH.
 */
export function resolveIstSensorReading(
  devices: IstSollDeviceLike[],
  assignedDeviceIds: string[],
  measureKey: IstSollMeasureKey,
  nowMs: number = Date.now(),
): IstSensorReading {
  const empty: IstSensorReading = {
    value: null,
    lastKnownValue: null,
    lastRead: null,
    quality: null,
    trust: 'missing',
  }
  if (assignedDeviceIds.length === 0) return empty
  const assignedIds = new Set(assignedDeviceIds)

  for (const device of devices) {
    const id = device.device_id || device.esp_id || ''
    if (!id || !assignedIds.has(id)) continue

    for (const sensor of device.sensors ?? []) {
      if (getSensorAggCategory(sensor.sensor_type) !== measureKey) continue
      const lastKnownValue = finiteSensorNumber(sensor)
      const quality = sensor.quality ?? null
      const lastRead = sensor.last_read ?? null
      if (lastKnownValue === null) {
        return { ...empty, lastRead, quality, trust: 'missing' }
      }
      if (quality && UNTRUSTED_IST_QUALITIES.has(quality)) {
        return {
          value: null,
          lastKnownValue,
          lastRead,
          quality,
          trust: 'untrusted',
        }
      }
      if (isStaleLastRead(lastRead, nowMs)) {
        return {
          value: null,
          lastKnownValue,
          lastRead,
          quality,
          trust: 'stale',
        }
      }
      return {
        value: lastKnownValue,
        lastKnownValue,
        lastRead,
        quality,
        trust: 'live',
      }
    }
  }
  return empty
}

/**
 * Find the current Ist value for a measure across the tank's assigned
 * devices. Returns `null` when no assigned device carries a sensor of that
 * type, the sensor has no value yet, or the sample is stale/untrusted —
 * callers must render "—", not "0".
 *
 * Prefers `processed_value` (Pi-enhanced) over `raw_value`, matching the
 * fallback used elsewhere in the dashboard (esp.ts sensor merge).
 */
export function findIstSensorValue(
  devices: IstSollDeviceLike[],
  assignedDeviceIds: string[],
  measureKey: IstSollMeasureKey,
): number | null {
  return resolveIstSensorReading(devices, assignedDeviceIds, measureKey).value
}

/** Live EC that is implausibly low for nutrient solution — probe likely in air. */
export function isLikelyDryEcReading(
  measureKey: IstSollMeasureKey,
  reading: IstSensorReading,
): boolean {
  if (measureKey !== 'ec') return false
  const sample = reading.lastKnownValue
  if (sample === null || !Number.isFinite(sample)) return false
  return sample < DRY_EC_HINT_US_CM
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
 * Legacy query key. `/plants?tank=` bookmarks redirect to the NL-Tab detail.
 */
export const TANK_DETAIL_QUERY_KEY = 'tank' as const

/** Build href for the tank detail (Monitor compact → NL-Tab). */
export function tankDetailHref(tankId: string): string {
  return `${TANK_DETAIL_ROUTE}/${encodeURIComponent(tankId)}`
}
