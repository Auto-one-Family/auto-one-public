/**
 * Past-overlay helpers for Planungs-Zeitstrahl (AUT-1236 T6).
 *
 * Historical Soll comes ONLY from applied_setpoint_logs (T3 protocol),
 * never from projecting today's plan_segments backwards.
 * Delta formatting reuses tankIstSollFormat (AUT-908 / AUT-1225 pattern).
 */

import {
  computeDelta,
  formatDelta,
  formatIstSollValue,
  measureKeyFromTarget,
} from '@/components/plants/tankIstSollFormat'
import type { TankTargetMeasure } from '@/types'
import type { AppliedSetpointLog, PlanSegment } from '@/types/planSegment'

/** Minimal window shape — avoids circular import with planTimelineTracks. */
export interface PastOverlayWindow {
  startMs: number
  endMs: number
  nowMs: number
}

/** Visual state for a plan-segment band in the past overlay. */
export type PlanBandVisualState = 'solid' | 'ghosted' | 'withdrawn'

export interface PastOverlayDelta {
  /** Historically applied Soll (from applied_setpoint_logs). */
  historicalSoll: number | null
  /** Mean Ist telemetry for the past window slice. */
  istAvg: number | null
  delta: number | null
  sollDisplay: string
  istDisplay: string
  deltaDisplay: string
  /** True when Soll came from applied_setpoint_logs (not current plan). */
  fromAppliedLog: boolean
}

/**
 * Ghosted = planned segment entirely in the past with no applied_setpoint_log
 * evidence (segment_id match or overlapping effective_at). Never hide it.
 */
export function resolveBandVisualState(
  segment: PlanSegment,
  logs: AppliedSetpointLog[],
  nowMs: number,
): PlanBandVisualState {
  if (segment.status === 'withdrawn') return 'withdrawn'

  const fromMs = Date.parse(segment.from_ts)
  const toMs = segment.to_ts ? Date.parse(segment.to_ts) : Number.POSITIVE_INFINITY
  if (Number.isNaN(fromMs)) return 'solid'

  const entirelyPast = toMs < nowMs
  if (!entirelyPast) return 'solid'

  if (segment.status === 'planned' && !hasAppliedEvidence(segment, logs, fromMs, toMs)) {
    return 'ghosted'
  }
  return 'solid'
}

function hasAppliedEvidence(
  segment: PlanSegment,
  logs: AppliedSetpointLog[],
  fromMs: number,
  toMs: number,
): boolean {
  for (const log of logs) {
    if (log.segment_id && log.segment_id === segment.id) return true
    if (log.zone_id !== segment.zone_id) continue
    if (log.domain !== segment.domain) continue
    if (log.measure !== segment.measure) continue
    const at = Date.parse(log.effective_at)
    if (Number.isNaN(at)) continue
    if (at >= fromMs && at < toMs) return true
  }
  return false
}

/**
 * Pick the historically applied Soll for a past interval from the log —
 * NOT from the current plan_segment.value (which may have been edited later).
 * Uses the last log row in [fromMs, toMs) for that zone×domain×measure.
 */
export function historicalSollFromLogs(
  logs: AppliedSetpointLog[],
  zoneId: string,
  domain: string,
  measure: string,
  fromMs: number,
  toMs: number,
): number | null {
  let last: AppliedSetpointLog | null = null
  for (const log of logs) {
    if (log.zone_id !== zoneId) continue
    if (log.domain !== domain) continue
    if (log.measure !== measure) continue
    const at = Date.parse(log.effective_at)
    if (Number.isNaN(at) || at < fromMs || at >= toMs) continue
    if (!last || at >= Date.parse(last.effective_at)) last = log
  }
  return last ? last.applied_value : null
}

/** Average of finite readings (Ist telemetrie). */
export function averageIst(values: Array<number | null | undefined>): number | null {
  const nums = values.filter(
    (v): v is number => typeof v === 'number' && Number.isFinite(v),
  )
  if (nums.length === 0) return null
  return nums.reduce((a, b) => a + b, 0) / nums.length
}

/**
 * Build Ist/Soll/Delta summary for a past track slice.
 * Delta helpers from tankIstSollFormat (AUT-908 pattern).
 */
export function buildPastOverlayDelta(args: {
  logs: AppliedSetpointLog[]
  zoneId: string
  domain: string
  measure: string
  fromMs: number
  toMs: number
  istReadings: Array<number | null | undefined>
}): PastOverlayDelta {
  const historicalSoll = historicalSollFromLogs(
    args.logs,
    args.zoneId,
    args.domain,
    args.measure,
    args.fromMs,
    args.toMs,
  )
  const istAvg = averageIst(args.istReadings)
  const delta = computeDelta(istAvg, historicalSoll)
  return {
    historicalSoll,
    istAvg,
    delta,
    sollDisplay: formatIstSollValue(historicalSoll),
    istDisplay: formatIstSollValue(istAvg),
    deltaDisplay: formatDelta(delta),
    fromAppliedLog: historicalSoll !== null,
  }
}

/** Map plan measure → sensor_type key used by sensorsApi.queryData. */
export function sensorTypeForPlanMeasure(measure: string): string | null {
  const key = measureKeyFromTarget(measure as TankTargetMeasure)
  return key
}

/** Clip overlay window to past only (start → min(now, end)). */
export function pastWindowSlice(window: PastOverlayWindow): {
  fromMs: number
  toMs: number
} | null {
  const toMs = Math.min(window.nowMs, window.endMs)
  if (toMs <= window.startMs) return null
  return { fromMs: window.startMs, toMs }
}

/**
 * Plant-measure marker visual: planned + timestamp in past → ghosted;
 * reverted → withdrawn (strikethrough). Never hide.
 */
export function resolveMeasureMarkerVisualState(
  eventStatus: string,
  eventTimestampMs: number,
  nowMs: number,
): PlanBandVisualState {
  if (eventStatus === 'reverted') return 'withdrawn'
  if (eventStatus === 'planned' && eventTimestampMs < nowMs) return 'ghosted'
  return 'solid'
}
