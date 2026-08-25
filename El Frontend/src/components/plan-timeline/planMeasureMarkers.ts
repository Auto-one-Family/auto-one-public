/**
 * Plant-measure markers from the lifecycle event log.
 *
 * Planned / reverted stay as point markers. Executed measures with a
 * linked sensor window render as a range on the matching phase section.
 */

import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import {
  resolveMeasureMarkerVisualState,
  type PlanBandVisualState,
} from '@/components/plan-timeline/planPastOverlay'
import type { PlantEventStatus, PlantLifecycleEvent } from '@/types'

export interface PlanMeasureCreatePayload {
  plantId: string
  eventType: PlanPlantMeasureEventType
  note: string | null
  eventStatus: Extract<PlantEventStatus, 'occurred' | 'planned'>
  windowStart: string | null
  windowEnd: string | null
}

/** Canonical server event types for operator plant measures (Schnitt/Entlauben/Umtopfen). */
export const PLAN_PLANT_MEASURE_EVENT_TYPES = [
  'topping',
  'defoliation',
  'transplanted',
  'training',
] as const

export type PlanPlantMeasureEventType = (typeof PLAN_PLANT_MEASURE_EVENT_TYPES)[number]

export const PLAN_PLANT_MEASURE_OPTIONS: {
  value: PlanPlantMeasureEventType
  label: string
}[] = [
  { value: 'topping', label: 'Schnitt (Topping)' },
  { value: 'defoliation', label: 'Entlauben' },
  { value: 'transplanted', label: 'Umtopfen' },
  { value: 'training', label: 'Training' },
]

export interface PlanMeasureMarker {
  eventId: string
  plantId: string
  eventType: string
  label: string
  timestampMs: number
  leftPct: number
  widthPct: number
  notes: string | null
  eventStatus: string
  visualState: PlanBandVisualState
  phase: string | null
  zoneId: string | null
  subzoneId: string | null
  windowStartMs: number | null
  windowEndMs: number | null
}

const MEASURE_TYPE_SET = new Set<string>(PLAN_PLANT_MEASURE_EVENT_TYPES)

export function isPlanPlantMeasureEventType(eventType: string): boolean {
  return MEASURE_TYPE_SET.has(eventType)
}

function clampPct(value: number): number {
  return Math.min(100, Math.max(0, value))
}

/**
 * Filter lifecycle events to plant measures visible in the window.
 * Includes occurred + planned + reverted (never silently hide withdrawn).
 */
export function buildPlannedMeasureMarkers(
  events: PlantLifecycleEvent[],
  window: PlanTimelineWindow,
  labelForType: (eventType: string) => string,
): PlanMeasureMarker[] {
  const span = Math.max(window.endMs - window.startMs, 1)
  const out: PlanMeasureMarker[] = []

  for (const event of events) {
    if (event.event_status === 'test_data') continue
    if (!isPlanPlantMeasureEventType(event.event_type)) continue
    const ts = Date.parse(event.event_timestamp)
    if (Number.isNaN(ts)) continue

    const windowStart = event.linked_sensor_window_start
      ? Date.parse(event.linked_sensor_window_start)
      : NaN
    const windowEnd = event.linked_sensor_window_end
      ? Date.parse(event.linked_sensor_window_end)
      : NaN
    const hasRange =
      event.event_status === 'occurred' &&
      Number.isFinite(windowStart) &&
      Number.isFinite(windowEnd) &&
      windowEnd > windowStart

    const rangeStart = hasRange ? windowStart : ts
    const rangeEnd = hasRange ? windowEnd : ts
    if (rangeEnd < window.startMs || rangeStart > window.endMs) continue

    const leftMs = Math.max(rangeStart, window.startMs)
    const rightMs = hasRange ? Math.min(rangeEnd, window.endMs) : leftMs

    out.push({
      eventId: event.event_id,
      plantId: event.plant_id,
      eventType: event.event_type,
      label: labelForType(event.event_type),
      timestampMs: ts,
      leftPct: clampPct(((leftMs - window.startMs) / span) * 100),
      widthPct: hasRange ? clampPct(((rightMs - leftMs) / span) * 100) : 0,
      notes: event.notes ?? null,
      eventStatus: event.event_status,
      visualState: resolveMeasureMarkerVisualState(
        event.event_status,
        ts,
        window.nowMs,
      ),
      phase: event.new_phase ?? null,
      zoneId: event.zone_id ?? null,
      subzoneId: event.subzone_id ?? null,
      windowStartMs: hasRange ? windowStart : null,
      windowEndMs: hasRange ? windowEnd : null,
    })
  }

  return out.sort((a, b) => a.timestampMs - b.timestampMs)
}
