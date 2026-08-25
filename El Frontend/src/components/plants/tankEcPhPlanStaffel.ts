/**
 * Pure helpers for tank-scoped EC/pH plan staffeln (AUT-1340 P6).
 *
 * Pairs zone-wide nutrient_solution segments (target_ec + target_ph) that share
 * the same [from_ts, to_ts) window into one human-readable staffel row.
 * Writes still go through planSegmentsApi / usePlanSegmentsStore — no second path.
 */

import type { PlanSegment } from '@/types/planSegment'

export const TANK_PLAN_DOMAIN = 'nutrient_solution' as const
export const TANK_PLAN_MEASURE_EC = 'target_ec' as const
export const TANK_PLAN_MEASURE_PH = 'target_ph' as const

/** AUT-1239 climate domain — same interval pairing as EC/pH (AUT-1536). */
export const CLIMATE_PLAN_DOMAIN = 'climate' as const
export const CLIMATE_PLAN_MEASURE_TEMP = 'target_temperature' as const
export const CLIMATE_PLAN_MEASURE_RH = 'target_humidity' as const

export interface EcPhStaffel {
  /** Stable key: from_ts|to_ts (to_ts empty string when open-ended). */
  key: string
  fromTs: string
  toTs: string | null
  ec: PlanSegment | null
  ph: PlanSegment | null
}

export interface ClimateStaffel {
  key: string
  fromTs: string
  toTs: string | null
  temperature: PlanSegment | null
  humidity: PlanSegment | null
}

/** Half-open cover check matching server PlanSegment.contains / resolve_at. */
export function segmentCoversAt(segment: PlanSegment, atMs: number): boolean {
  const fromMs = Date.parse(segment.from_ts)
  if (Number.isNaN(fromMs) || atMs < fromMs) return false
  if (segment.to_ts == null) return true
  const toMs = Date.parse(segment.to_ts)
  if (Number.isNaN(toMs)) return false
  return atMs < toMs
}

function staffelKey(fromTs: string, toTs: string | null): string {
  return `${fromTs}|${toTs ?? ''}`
}

interface PairStaffelRow {
  key: string
  fromTs: string
  toTs: string | null
  first: PlanSegment | null
  second: PlanSegment | null
}

/**
 * Pair two measures that share the same [from_ts, to_ts) window.
 * Used by EC/pH (nutrient_solution) and T/RH (climate) — one grouping loop.
 */
function buildPairStaffeln(
  segments: readonly PlanSegment[],
  zoneId: string,
  domain: string,
  firstMeasure: string,
  secondMeasure: string,
): PairStaffelRow[] {
  const relevant = segments.filter(
    (s) =>
      s.zone_id === zoneId &&
      s.domain === domain &&
      (s.measure === firstMeasure || s.measure === secondMeasure),
  )

  const byWindow = new Map<string, PairStaffelRow>()
  for (const seg of relevant) {
    const key = staffelKey(seg.from_ts, seg.to_ts)
    let row = byWindow.get(key)
    if (!row) {
      row = {
        key,
        fromTs: seg.from_ts,
        toTs: seg.to_ts,
        first: null,
        second: null,
      }
      byWindow.set(key, row)
    }
    if (seg.measure === firstMeasure) row.first = seg
    else row.second = seg
  }

  return Array.from(byWindow.values()).sort(
    (a, b) => Date.parse(a.fromTs) - Date.parse(b.fromTs),
  )
}

function findActivePairStaffel<T extends { fromTs: string; toTs: string | null }>(
  staffeln: readonly T[],
  probeOf: (row: T) => PlanSegment | null,
  atMs: number,
): T | null {
  let best: T | null = null
  let bestFrom = -Infinity
  for (const row of staffeln) {
    const probe = probeOf(row)
    if (!probe || !segmentCoversAt(probe, atMs)) continue
    const fromMs = Date.parse(row.fromTs)
    if (Number.isNaN(fromMs)) continue
    if (fromMs >= bestFrom) {
      best = row
      bestFrom = fromMs
    }
  }
  return best
}

/**
 * Filter + group nutrient_solution EC/pH segments for one zone into staffeln.
 * Sorted by from_ts ascending (staffelung order).
 */
export function buildEcPhStaffeln(
  segments: readonly PlanSegment[],
  zoneId: string,
): EcPhStaffel[] {
  return buildPairStaffeln(
    segments,
    zoneId,
    TANK_PLAN_DOMAIN,
    TANK_PLAN_MEASURE_EC,
    TANK_PLAN_MEASURE_PH,
  ).map((row) => ({
    key: row.key,
    fromTs: row.fromTs,
    toTs: row.toTs,
    ec: row.first,
    ph: row.second,
  }))
}

/** Staffel covering @now (latest from_ts wins if overlap — same as server). */
export function findActiveEcPhStaffel(
  staffeln: readonly EcPhStaffel[],
  atMs: number = Date.now(),
): EcPhStaffel | null {
  return findActivePairStaffel(staffeln, (row) => row.ec ?? row.ph, atMs)
}

/** Pair climate T+RH segments that share a window (AUT-1536, same loop as EC/pH). */
export function buildClimateStaffeln(
  segments: readonly PlanSegment[],
  zoneId: string,
): ClimateStaffel[] {
  return buildPairStaffeln(
    segments,
    zoneId,
    CLIMATE_PLAN_DOMAIN,
    CLIMATE_PLAN_MEASURE_TEMP,
    CLIMATE_PLAN_MEASURE_RH,
  ).map((row) => ({
    key: row.key,
    fromTs: row.fromTs,
    toTs: row.toTs,
    temperature: row.first,
    humidity: row.second,
  }))
}

export function findActiveClimateStaffel(
  staffeln: readonly ClimateStaffel[],
  atMs: number = Date.now(),
): ClimateStaffel | null {
  return findActivePairStaffel(
    staffeln,
    (row) => row.temperature ?? row.humidity,
    atMs,
  )
}

/** Local calendar date → ISO at local midnight (for date inputs). */
export function dateInputToIsoStart(dateLocal: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateLocal)) return null
  const d = new Date(`${dateLocal}T00:00:00`)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}

/** ISO → local YYYY-MM-DD for date inputs. */
export function isoToDateInput(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export function formatStaffelRange(fromTs: string, toTs: string | null): string {
  const fromLabel = isoToDateInput(fromTs) || fromTs
  if (!toTs) return `ab ${fromLabel}`
  const toLabel = isoToDateInput(toTs) || toTs
  return `${fromLabel} – ${toLabel}`
}

export function formatMeasureValue(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return '—'
  return String(Number(value))
}
