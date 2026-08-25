/**
 * Pure split/merge helpers for plan_segment edit ops (AUT-1235 T5).
 *
 * All mutations are described as API payloads — callers persist via
 * planSegmentsApi / planSegments.store (no second draft store).
 */

import type { PlanSegment, PlanSegmentCreate, PlanSegmentUpdate } from '@/types/planSegment'

const TOUCH_TOLERANCE_MS = 1

export interface SplitPlan {
  /** PATCH existing segment: close at splitMs */
  leftUpdate: { id: string; payload: PlanSegmentUpdate }
  /** POST right half with new value */
  rightCreate: PlanSegmentCreate
}

export interface MergePlan {
  /** PATCH survivor to cover both intervals */
  survivorUpdate: { id: string; payload: PlanSegmentUpdate }
  /** DELETE absorbed segment */
  deleteId: string
}

function segmentEndMs(seg: PlanSegment, openEndMs: number): number {
  return seg.to_ts ? Date.parse(seg.to_ts) : openEndMs
}

/**
 * Build split payloads: left keeps original value, right gets `rightValue`.
 * Split point must lie strictly inside (from_ts, to_ts).
 */
export function buildSplitPlan(
  segment: PlanSegment,
  splitMs: number,
  rightValue: number,
): SplitPlan | null {
  const fromMs = Date.parse(segment.from_ts)
  const toMs = segment.to_ts ? Date.parse(segment.to_ts) : NaN
  if (Number.isNaN(fromMs) || Number.isNaN(toMs)) return null
  if (splitMs <= fromMs || splitMs >= toMs) return null

  const splitIso = new Date(splitMs).toISOString()
  return {
    leftUpdate: {
      id: segment.id,
      payload: { to_ts: splitIso },
    },
    rightCreate: {
      zone_id: segment.zone_id,
      domain: segment.domain,
      measure: segment.measure,
      value: rightValue,
      recipe_ref: segment.recipe_ref,
      from_ts: splitIso,
      to_ts: segment.to_ts,
      interp: segment.interp,
      phase_ref: segment.phase_ref,
      status: segment.status,
      tolerance: segment.tolerance,
    },
  }
}

/**
 * Find a directly adjacent segment with same measure + value (touching edges).
 * Prefers the neighbour to the right; falls back to left.
 */
export function findMergeCandidate(
  segment: PlanSegment,
  siblings: PlanSegment[],
  openEndMs: number = Date.now() + 365 * 24 * 60 * 60 * 1000,
): PlanSegment | null {
  const fromMs = Date.parse(segment.from_ts)
  const toMs = segmentEndMs(segment, openEndMs)
  if (Number.isNaN(fromMs) || Number.isNaN(toMs)) return null

  const sameContent = (other: PlanSegment): boolean =>
    other.id !== segment.id &&
    other.zone_id === segment.zone_id &&
    other.domain === segment.domain &&
    other.measure === segment.measure &&
    other.value === segment.value

  const right = siblings.find((other) => {
    if (!sameContent(other)) return false
    const otherFrom = Date.parse(other.from_ts)
    return Math.abs(otherFrom - toMs) <= TOUCH_TOLERANCE_MS
  })
  if (right) return right

  const left = siblings.find((other) => {
    if (!sameContent(other)) return false
    const otherTo = segmentEndMs(other, openEndMs)
    return Math.abs(otherTo - fromMs) <= TOUCH_TOLERANCE_MS
  })
  return left ?? null
}

/**
 * Merge `a` and `b` into the chronologically earlier survivor; delete the other.
 */
export function buildMergePlan(a: PlanSegment, b: PlanSegment): MergePlan | null {
  const aFrom = Date.parse(a.from_ts)
  const bFrom = Date.parse(b.from_ts)
  if (Number.isNaN(aFrom) || Number.isNaN(bFrom)) return null
  if (a.measure !== b.measure || a.value !== b.value) return null

  const earlier = aFrom <= bFrom ? a : b
  const later = aFrom <= bFrom ? b : a
  const laterTo = later.to_ts

  return {
    survivorUpdate: {
      id: earlier.id,
      payload: { to_ts: laterTo },
    },
    deleteId: later.id,
  }
}

/** Map pointer X in a track bar to a timestamp within the window. */
export function pointerToTimestamp(
  clientX: number,
  barRect: DOMRect,
  startMs: number,
  endMs: number,
): number {
  const span = Math.max(endMs - startMs, 1)
  const ratio = Math.min(1, Math.max(0, (clientX - barRect.left) / Math.max(barRect.width, 1)))
  return startMs + ratio * span
}
