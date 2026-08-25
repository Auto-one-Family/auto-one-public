/**
 * AUT-1380 W2 — Anzeige-Spiegel der Plan→Totband-Ableitung.
 *
 * Kanonische Stelle (Server):
 * `plan_setpoint_resolver._apply_value_to_condition` —
 * between: symmetrisch; Hysterese: Aus = Soll, Totband nur auf der falschen Seite.
 * Kein DB-Writeback. Hier nur Display — kein zweiter Resolver.
 */

import { formatNumber } from '@/utils/formatters'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'
import {
  CATEGORY_DECIMALS,
  getSensorAggCategory,
  getSensorConfig,
} from '@/utils/sensorDefaults'

export type NodeBandKind = 'between' | 'hysteresis_cooling' | 'hysteresis_heating' | 'single'

export interface NodeBand {
  kind: NodeBandKind
  /** Unterkante (min / deactivate_below / activate_below) */
  low: number
  /** Oberkante (max / activate_above / deactivate_above) */
  high: number
  /** Statischer Referenz-/Mittelpunkt der Node-Konfiguration */
  nodeCenter: number
}

export interface EffectiveBand {
  low: number
  high: number
  setpoint: number
  source: 'plan_segment' | 'static_fallback'
  halfWidth: number
}

/**
 * between: symmetrisch um Soll (half-width = abs(high-low)/2).
 * Identisch Server `_apply_value_to_condition` für operator == "between".
 */
export function recenterBand(setpoint: number, low: number, high: number): {
  low: number
  high: number
  halfWidth: number
} {
  const halfWidth = Math.abs(high - low) / 2
  return {
    low: setpoint - halfWidth,
    high: setpoint + halfWidth,
    halfWidth,
  }
}

/**
 * Hysterese Plan-Spiegel (Server `_apply_value_to_condition`):
 * - cooling: Aus = Soll, Ein = Soll + gap (kein Totband unter Soll)
 * - heating: Aus = Soll, Ein = Soll - gap (kein Totband über Soll)
 */
export function recenterHysteresisBand(
  setpoint: number,
  low: number,
  high: number,
  kind: 'hysteresis_cooling' | 'hysteresis_heating',
): { low: number; high: number; halfWidth: number } {
  const gap = Math.abs(high - low)
  if (kind === 'hysteresis_cooling') {
    return { low: setpoint, high: setpoint + gap, halfWidth: gap }
  }
  return { low: setpoint - gap, high: setpoint, halfWidth: gap }
}

export function effectiveBandFromPlan(
  setpoint: number,
  band: NodeBand,
  source: 'plan_segment' | 'static_fallback' = 'plan_segment',
): EffectiveBand {
  if (band.kind === 'single') {
    return {
      low: setpoint,
      high: setpoint,
      setpoint,
      source,
      halfWidth: 0,
    }
  }
  const r =
    band.kind === 'hysteresis_cooling' || band.kind === 'hysteresis_heating'
      ? recenterHysteresisBand(setpoint, band.low, band.high, band.kind)
      : recenterBand(setpoint, band.low, band.high)
  return {
    low: r.low,
    high: r.high,
    setpoint,
    source,
    halfWidth: r.halfWidth,
  }
}

type CondDict = Record<string, unknown>

function asNumber(v: unknown): number | null {
  if (typeof v === 'number' && Number.isFinite(v)) return v
  if (typeof v === 'string' && v.trim() !== '') {
    const n = parseLocaleNumber(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/**
 * AUT-1389: Band aus Vue-Flow Sensor-Node-data (activateAbove/…) —
 * gleiche Kind-Semantik wie leafBand für Condition-Dicts.
 */
export function nodeBandFromFlowSensorData(data: Record<string, unknown>): NodeBand | null {
  const isHyst = data.isHysteresis === true || data.operator === 'hysteresis'
  if (isHyst) {
    const above = asNumber(data.activateAbove)
    const below = asNumber(data.deactivateBelow)
    if (above != null && below != null) {
      return {
        kind: 'hysteresis_cooling',
        low: below,
        high: above,
        nodeCenter: (above + below) / 2,
      }
    }
    const actBelow = asNumber(data.activateBelow)
    const deactAbove = asNumber(data.deactivateAbove)
    if (actBelow != null && deactAbove != null) {
      return {
        kind: 'hysteresis_heating',
        low: actBelow,
        high: deactAbove,
        nodeCenter: (actBelow + deactAbove) / 2,
      }
    }
    return null
  }
  if (data.operator === 'between') {
    const low = asNumber(data.min)
    const high = asNumber(data.max)
    if (low == null || high == null) return null
    return { kind: 'between', low, high, nodeCenter: (low + high) / 2 }
  }
  const value = asNumber(data.value)
  if (value != null) {
    return { kind: 'single', low: value, high: value, nodeCenter: value }
  }
  return null
}

function leafBand(cond: CondDict, sensorType: string): NodeBand | null {
  const st = String(cond.sensor_type ?? '').toLowerCase()
  if (st !== sensorType.toLowerCase()) return null
  const type = String(cond.type ?? '')

  if ((type === 'sensor' || type === 'sensor_threshold') && cond.operator === 'between') {
    const low = asNumber(cond.min)
    const high = asNumber(cond.max)
    if (low == null || high == null) return null
    return {
      kind: 'between',
      low,
      high,
      nodeCenter: (low + high) / 2,
    }
  }

  if (type === 'hysteresis') {
    const above = asNumber(cond.activate_above)
    const below = asNumber(cond.deactivate_below)
    if (above != null && below != null) {
      return {
        kind: 'hysteresis_cooling',
        low: below,
        high: above,
        nodeCenter: (above + below) / 2,
      }
    }
    const actBelow = asNumber(cond.activate_below)
    const deactAbove = asNumber(cond.deactivate_above)
    if (actBelow != null && deactAbove != null) {
      return {
        kind: 'hysteresis_heating',
        low: actBelow,
        high: deactAbove,
        nodeCenter: (actBelow + deactAbove) / 2,
      }
    }
  }

  if (type === 'sensor' || type === 'sensor_threshold') {
    const value = asNumber(cond.value)
    if (value != null) {
      return { kind: 'single', low: value, high: value, nodeCenter: value }
    }
  }
  return null
}

/** First matching leaf in list / compound — same walk spirit as server finder. */
export function extractNodeBand(
  conditions: unknown,
  sensorType: string,
): NodeBand | null {
  if (Array.isArray(conditions)) {
    for (const item of conditions) {
      const found = extractNodeBand(item, sensorType)
      if (found) return found
    }
    return null
  }
  if (conditions && typeof conditions === 'object') {
    const dict = conditions as CondDict
    if ('logic' in dict && 'conditions' in dict) {
      return extractNodeBand(dict.conditions, sensorType)
    }
    return leafBand(dict, sensorType)
  }
  return null
}

export function planMeasureToSensorType(measure: string | null | undefined): string | null {
  if (!measure) return null
  if (measure === 'target_ec') return 'ec'
  if (measure === 'target_ph') return 'ph'
  if (measure.startsWith('target_')) return measure.slice('target_'.length)
  return null
}

/**
 * Dezimalstellen für Totband-/Schwellen-Anzeige (pH → 2, EC → 0, …).
 * Verhindert Float-Artefakte wie 6.199999999999999 nach recenterBand.
 */
export function deadbandDisplayDecimals(sensorType?: string | null): number {
  if (!sensorType) return 2
  const cfg = getSensorConfig(sensorType)
  if (cfg && Number.isFinite(cfg.decimals)) return cfg.decimals
  const cat = getSensorAggCategory(sensorType)
  return CATEGORY_DECIMALS[cat] ?? 2
}

/** Operator-lesbare Kante: 6.1999… + ph → „6,20“. */
export function formatDeadbandEdge(
  value: number | null | undefined,
  sensorType?: string | null,
): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return formatNumber(value, deadbandDisplayDecimals(sensorType), '—', false)
}

export function formatEffectiveDeadbandLabel(input: {
  followsPlan: boolean
  planValue: number | null
  nodeBand: NodeBand | null
  origin: 'plan_segment' | 'static_fallback' | null
  /** Einheit für Operator-Text, z. B. µS/cm — ohne Code-Jargon. */
  unit?: string
  /** Sensortyp für Dezimalformat (ph/ec/…). */
  sensorType?: string | null
}): string | null {
  if (!input.followsPlan) return null
  const unitSuffix = input.unit ? ` ${input.unit}` : ''
  const st = input.sensorType
  if (input.planValue == null || !Number.isFinite(input.planValue)) {
    return 'Sollwert vom Tank-Plan wird noch geladen…'
  }
  if (!input.nodeBand) {
    return `Aktueller Sollwert: ${formatDeadbandEdge(input.planValue, st)}${unitSuffix}`
  }
  const source = input.origin === 'static_fallback' ? 'static_fallback' : 'plan_segment'
  const eff = effectiveBandFromPlan(input.planValue, input.nodeBand, source)
  // AUT-1389: eine menschenlesbare Wirksam-Zeile — kein Code-/Interna-Jargon.
  if (input.nodeBand.kind === 'single') {
    return `Aktueller Sollwert: ${formatDeadbandEdge(eff.setpoint, st)}${unitSuffix}`
  }
  return (
    `Aktuell: Soll ${formatDeadbandEdge(eff.setpoint, st)}${unitSuffix}` +
    `, Ein/Aus-Band ${formatDeadbandEdge(eff.low, st)}–${formatDeadbandEdge(eff.high, st)}${unitSuffix}`
  )
}
