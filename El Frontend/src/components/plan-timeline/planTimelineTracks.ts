/**
 * Pure helpers for Planungs-Zeitstrahl track scaffolding
 * (AUT-1234 T4 / AUT-1235 T5).
 *
 * Builds Zone/Subzone × Domain tracks. Editable tracks use one band per
 * plan_segment (1:1) so split/merge/resize operate on real IDs.
 * mergeAdjacentEqualSegments remains for overview/tests.
 * No Vue reactivity — unit-testable.
 */

import type { PlanDomain } from '@/types/logic'
import { PLAN_DOMAIN_CATALOG } from '@/types/logic'
import type { AppliedSetpointLog, PlanSegment } from '@/types/planSegment'
import {
  resolveBandVisualState,
  type PlanBandVisualState,
  type PastOverlayDelta,
} from '@/components/plan-timeline/planPastOverlay'

export interface PlanTimelineWindow {
  startMs: number
  endMs: number
  nowMs: number
}

export type PlanTimelineWindowPreset = '7d' | '14d' | '30d'

const DAY_MS = 24 * 60 * 60 * 1000

export const PLAN_TIMELINE_WINDOW_PRESETS: {
  key: PlanTimelineWindowPreset
  label: string
  days: number
}[] = [
  { key: '7d', label: '±7 Tage', days: 7 },
  { key: '14d', label: '±14 Tage', days: 14 },
  { key: '30d', label: '±30 Tage', days: 30 },
]

export function buildPlanTimelineWindow(
  preset: PlanTimelineWindowPreset,
  nowMs: number = Date.now(),
): PlanTimelineWindow {
  const days =
    PLAN_TIMELINE_WINDOW_PRESETS.find((p) => p.key === preset)?.days ?? 7
  const span = days * DAY_MS
  return {
    startMs: nowMs - span,
    endMs: nowMs + span,
    nowMs,
  }
}

/** Minimum visible span when no plan/plant anchors exist. */
const FULL_WINDOW_FALLBACK_PAD_MS = 7 * DAY_MS

/**
 * Full planning window from data anchors (segments + event timestamps).
 * Always includes `nowMs`. Open-ended segment ends resolve to now.
 * Empty data → ±7 days around now.
 */
export function buildFullPlanTimelineWindow(args: {
  nowMs?: number
  segmentFromTs?: readonly (string | null | undefined)[]
  segmentToTs?: readonly (string | null | undefined)[]
  eventTimestamps?: readonly (string | null | undefined)[]
  /** Optional planting / other ISO dates. */
  extraTimestamps?: readonly (string | null | undefined)[]
}): PlanTimelineWindow {
  const nowMs = args.nowMs ?? Date.now()
  const points: number[] = [nowMs]

  const pushIso = (raw: string | null | undefined): void => {
    if (!raw) return
    const ms = Date.parse(raw)
    if (!Number.isNaN(ms)) points.push(ms)
  }

  for (const ts of args.segmentFromTs ?? []) pushIso(ts)
  for (const ts of args.segmentToTs ?? []) {
    if (ts == null || ts === '') {
      points.push(nowMs)
    } else {
      pushIso(ts)
    }
  }
  for (const ts of args.eventTimestamps ?? []) pushIso(ts)
  for (const ts of args.extraTimestamps ?? []) pushIso(ts)

  let startMs = Math.min(...points)
  let endMs = Math.max(...points)

  if (endMs <= startMs) {
    startMs = nowMs - FULL_WINDOW_FALLBACK_PAD_MS
    endMs = nowMs + FULL_WINDOW_FALLBACK_PAD_MS
  }

  // Snap start to local midnight for cleaner axis ticks.
  const startDay = new Date(startMs)
  startDay.setHours(0, 0, 0, 0)
  startMs = startDay.getTime()

  // Ensure now sits inside; pad a little past the last anchor for readability.
  if (endMs < nowMs) endMs = nowMs
  if (endMs === nowMs) {
    endMs = nowMs + DAY_MS
  }

  // Degenerate / empty-only case already handled; keep a usable minimum span.
  if (endMs - startMs < FULL_WINDOW_FALLBACK_PAD_MS) {
    startMs = Math.min(startMs, nowMs - FULL_WINDOW_FALLBACK_PAD_MS / 2)
    endMs = Math.max(endMs, nowMs + FULL_WINDOW_FALLBACK_PAD_MS / 2)
  }

  return { startMs, endMs, nowMs }
}

/** Left offset of "now" as percentage of the visible window (0–100). */
export function nowMarkerPercent(window: PlanTimelineWindow): number {
  const span = Math.max(window.endMs - window.startMs, 1)
  return ((window.nowMs - window.startMs) / span) * 100
}

export interface PlanTrackBand {
  id: string
  /** Single plan_segment.id (edit path). */
  segmentId: string
  measure: string
  value: number | null
  fromMs: number
  toMs: number
  /** Unclipped interval end (null = open-ended). */
  toTs: string | null
  fromTs: string
  leftPct: number
  widthPct: number
  label: string
  tooltip: string
  /** Vertical lane inside the track bar (0-based). Prevents measure overlap. */
  laneIndex: number
  /** Segment status (for past-overlay visual rules). */
  status?: string
  /** AUT-1236: solid / ghosted / withdrawn — never silently hidden. */
  visualState?: PlanBandVisualState
  /** AUT-1236: Ist vs historically applied Soll (from applied_setpoint_logs). */
  pastDelta?: PastOverlayDelta | null
}

export interface PlanTrackRowModel {
  id: string
  zoneId: string
  zoneName: string
  subzoneId: string | null
  subzoneName: string
  domain: PlanDomain | string
  domainLabel: string
  bands: PlanTrackBand[]
  /** Number of vertical lanes needed to render bands without stacking. */
  laneCount: number
  isEmpty: boolean
}

/**
 * Stable vertical order for measures within a domain track.
 * EC above pH, Temperatur above Feuchte — predictable operator scanning.
 */
export const PLAN_MEASURE_LANE_ORDER: readonly string[] = [
  'target_temperature',
  'target_humidity',
  'target_co2',
  'target_ec',
  'target_ph',
  'light_regime',
  'recipe_ref',
]

function measureLaneRank(measure: string): number {
  const idx = PLAN_MEASURE_LANE_ORDER.indexOf(measure)
  return idx === -1 ? 1000 : idx
}

/**
 * Assign vertical lane indices so overlapping bands (e.g. EC+pH, T+RH)
 * render in stacked lanes instead of painting on top of each other.
 * Same measure stays on contiguous lanes; within-measure overlaps pack greedily.
 */
export function assignBandLanes(bands: PlanTrackBand[]): {
  bands: PlanTrackBand[]
  laneCount: number
} {
  if (bands.length === 0) return { bands: [], laneCount: 1 }

  const measures = [...new Set(bands.map((b) => b.measure))].sort((a, b) => {
    const d = measureLaneRank(a) - measureLaneRank(b)
    return d !== 0 ? d : a.localeCompare(b)
  })

  const idToLane = new Map<string, number>()
  let nextLaneBase = 0

  for (const measure of measures) {
    const group = bands
      .filter((b) => b.measure === measure)
      .sort((a, b) => a.fromMs - b.fromMs || b.toMs - a.toMs)
    const localEnds: number[] = []
    for (const band of group) {
      let local = localEnds.findIndex((end) => end <= band.fromMs)
      if (local === -1) {
        local = localEnds.length
        localEnds.push(band.toMs)
      } else {
        localEnds[local] = band.toMs
      }
      idToLane.set(band.id, nextLaneBase + local)
    }
    nextLaneBase += Math.max(1, localEnds.length)
  }

  return {
    bands: bands.map((b) => ({
      ...b,
      laneIndex: idToLane.get(b.id) ?? 0,
    })),
    laneCount: Math.max(1, nextLaneBase),
  }
}

export interface PlanZoneSection {
  zoneId: string
  zoneName: string
  tracks: PlanTrackRowModel[]
}

export interface SubzoneSlot {
  subzoneId: string | null
  subzoneName: string
}

export const PLAN_DOMAIN_LABELS: Record<string, string> = {
  nutrient_solution: 'Wasser',
  /** Klarname — never show raw domain=climate in the UI (AUT-1240). */
  climate: 'Luft',
}

/** Fixed operator rows for the consolidated zone timeline (no Mensch). */
export const PLAN_OPERATOR_ROW_KEYS = [
  'luft',
  'wasser',
  'boden',
  'licht',
  'pflanze',
] as const

export type PlanOperatorRowKey = (typeof PLAN_OPERATOR_ROW_KEYS)[number]

export const PLAN_OPERATOR_ROW_LABELS: Record<PlanOperatorRowKey, string> = {
  luft: 'Luft',
  wasser: 'Wasser',
  boden: 'Boden',
  licht: 'Licht',
  pflanze: 'Pflanze',
}

export interface PlanDateTick {
  ms: number
  leftPct: number
  label: string
  isToday: boolean
}

/**
 * Min center-to-center gap (%) so labels on one line do not visually overlap.
 * ~"28.07." / "heute" at text-xs ≈ 3–4% on typical track widths.
 */
const PLAN_AXIS_LABEL_GAP_PCT = 4.5

/**
 * Keep one label row collision-free: "heute" always wins, then greedily keep
 * other ticks that clear the gap to already-kept labels.
 */
export function resolvePlanDateTickLabelCollisions(
  ticks: readonly PlanDateTick[],
  gapPct: number = PLAN_AXIS_LABEL_GAP_PCT,
): PlanDateTick[] {
  const sorted = [...ticks].sort((a, b) => a.leftPct - b.leftPct)
  const heute = sorted.find((t) => t.isToday)
  const kept: PlanDateTick[] = []
  if (heute) kept.push(heute)

  for (const tick of sorted) {
    if (tick.isToday) continue
    const collides = kept.some(
      (k) => Math.abs(k.leftPct - tick.leftPct) < gapPct,
    )
    if (!collides) kept.push(tick)
  }

  return kept.sort((a, b) => a.leftPct - b.leftPct)
}

/**
 * Day ticks across the visible window. Step adapts to span length so full-range
 * views stay readable; always include a "heute" tick at now.
 * Labels stay on one line — overlapping date labels next to "heute" are dropped.
 */
export function buildPlanDateTicks(window: PlanTimelineWindow): PlanDateTick[] {
  const span = Math.max(window.endMs - window.startMs, 1)
  const dayMs = DAY_MS
  const startDay = new Date(window.startMs)
  startDay.setHours(0, 0, 0, 0)
  let cursor = startDay.getTime()
  if (cursor < window.startMs) cursor += dayMs

  const daySpan = span / dayMs
  let stepDays = 1
  if (daySpan >= 180) stepDays = 14
  else if (daySpan >= 90) stepDays = 7
  else if (daySpan >= 45) stepDays = 3
  else if (daySpan >= 28) stepDays = 2
  const ticks: PlanDateTick[] = []

  while (cursor <= window.endMs) {
    const leftPct = ((cursor - window.startMs) / span) * 100
    if (leftPct >= 0 && leftPct <= 100) {
      ticks.push({
        ms: cursor,
        leftPct,
        label: new Date(cursor).toLocaleDateString('de-DE', {
          day: '2-digit',
          month: '2-digit',
        }),
        isToday: false,
      })
    }
    cursor += stepDays * dayMs
  }

  const nowPct = ((window.nowMs - window.startMs) / span) * 100
  if (nowPct >= 0 && nowPct <= 100) {
    // Drop the calendar tick for "today" (midnight) — replace with "heute" at now.
    const todayStart = new Date(window.nowMs)
    todayStart.setHours(0, 0, 0, 0)
    const todayStartMs = todayStart.getTime()
    const withoutToday = ticks.filter((t) => {
      const tickDay = new Date(t.ms)
      tickDay.setHours(0, 0, 0, 0)
      return tickDay.getTime() !== todayStartMs
    })
    withoutToday.push({
      ms: window.nowMs,
      leftPct: nowPct,
      label: 'heute',
      isToday: true,
    })
    return resolvePlanDateTickLabelCollisions(withoutToday)
  }

  return resolvePlanDateTickLabelCollisions(ticks)
}

export type PlanDomainRowKind = 'segments' | 'empty' | 'measures'

export interface PlanDomainRowModel {
  key: PlanOperatorRowKey
  label: string
  kind: PlanDomainRowKind
  /** Present when kind === 'segments'. */
  track: PlanTrackRowModel | null
  emptyHint: string | null
}

/**
 * Fixed operator rows for a single zone (Luft/Wasser/Boden/Licht/Pflanze).
 * Segment rows use zone-wide climate / nutrient_solution tracks only.
 */
export function buildPlanDomainRows(args: {
  zoneId: string
  zoneName: string
  segments: PlanSegment[]
  window: PlanTimelineWindow
  appliedLogs?: AppliedSetpointLog[]
  pastDeltaByKey?: Map<string, PastOverlayDelta>
}): PlanDomainRowModel[] {
  const logs = args.appliedLogs ?? []
  const pastDeltaByKey = args.pastDeltaByKey ?? new Map()

  function zoneTrack(domain: PlanDomain | string): PlanTrackRowModel {
    const matching = args.segments.filter(
      (s) => s.zone_id === args.zoneId && s.domain === domain,
    )
    const bands = segmentsToBands(matching, args.window, logs, pastDeltaByKey)
    const laneCount =
      bands.length === 0
        ? 1
        : bands.reduce((max, b) => Math.max(max, b.laneIndex + 1), 1)
    return {
      id: `${args.zoneId}::zone::${domain}`,
      zoneId: args.zoneId,
      zoneName: args.zoneName,
      subzoneId: null,
      subzoneName: 'Zone-weit',
      domain,
      domainLabel: PLAN_DOMAIN_LABELS[domain] ?? domain,
      bands,
      laneCount,
      isEmpty: bands.length === 0,
    }
  }

  return [
    {
      key: 'luft',
      label: PLAN_OPERATOR_ROW_LABELS.luft,
      kind: 'segments',
      track: zoneTrack('climate'),
      emptyHint: null,
    },
    {
      key: 'wasser',
      label: PLAN_OPERATOR_ROW_LABELS.wasser,
      kind: 'segments',
      track: zoneTrack('nutrient_solution'),
      emptyHint: null,
    },
    {
      key: 'boden',
      label: PLAN_OPERATOR_ROW_LABELS.boden,
      kind: 'empty',
      track: null,
      emptyHint: 'kein Plan — keine Bodenspur',
    },
    {
      key: 'licht',
      label: PLAN_OPERATOR_ROW_LABELS.licht,
      kind: 'empty',
      track: null,
      emptyHint: 'Licht hier nicht planbar',
    },
    {
      key: 'pflanze',
      label: PLAN_OPERATOR_ROW_LABELS.pflanze,
      kind: 'measures',
      track: null,
      emptyHint: null,
    },
  ]
}

export const PLAN_MEASURE_LABELS: Record<string, string> = {
  target_ec: 'EC',
  target_ph: 'pH',
  target_temperature: 'Temperatur-Ziel',
  target_humidity: 'Feuchte-Ziel',
  target_co2: 'CO₂',
  light_regime: 'Licht',
  recipe_ref: 'Rezept',
}

function formatBandLabel(measure: string, value: number | null): string {
  const m = PLAN_MEASURE_LABELS[measure] ?? measure
  if (value === null || Number.isNaN(value)) return m
  return `${m} ${value}`
}

function bandFromSegment(
  seg: PlanSegment,
  window: PlanTimelineWindow,
  logs: AppliedSetpointLog[] = [],
  pastDeltaByKey: Map<string, PastOverlayDelta> = new Map(),
): PlanTrackBand | null {
  const fromMs = Date.parse(seg.from_ts)
  const toMs = seg.to_ts ? Date.parse(seg.to_ts) : window.endMs
  if (Number.isNaN(fromMs) || Number.isNaN(toMs) || toMs <= fromMs) return null

  const span = Math.max(window.endMs - window.startMs, 1)
  const clippedFrom = Math.max(fromMs, window.startMs)
  const clippedTo = Math.min(toMs, window.endMs)
  if (clippedTo <= clippedFrom) return null

  const leftPct = ((clippedFrom - window.startMs) / span) * 100
  const widthPct = ((clippedTo - clippedFrom) / span) * 100
  const label = formatBandLabel(seg.measure, seg.value)
  const visualState = resolveBandVisualState(seg, logs, window.nowMs)
  const deltaKey = `${seg.zone_id}::${seg.domain}::${seg.measure}`
  const pastDelta = pastDeltaByKey.get(deltaKey) ?? null
  const deltaHint =
    pastDelta && pastDelta.fromAppliedLog
      ? `\nIst ${pastDelta.istDisplay} / Soll(hist) ${pastDelta.sollDisplay} / Δ ${pastDelta.deltaDisplay}`
      : ''
  return {
    id: seg.id,
    segmentId: seg.id,
    measure: seg.measure,
    value: seg.value,
    fromMs: clippedFrom,
    toMs: clippedTo,
    fromTs: seg.from_ts,
    toTs: seg.to_ts,
    leftPct,
    widthPct,
    label,
    laneIndex: 0,
    tooltip: `${label}\n${new Date(clippedFrom).toLocaleString('de-DE')} – ${new Date(clippedTo).toLocaleString('de-DE')}${deltaHint}`,
    status: seg.status,
    visualState,
    pastDelta,
  }
}

/**
 * One visual band per plan_segment (edit path, AUT-1235).
 * Lane indices are assigned so concurrent measures do not stack visually.
 */
export function segmentsToBands(
  segments: PlanSegment[],
  window: PlanTimelineWindow,
  logs: AppliedSetpointLog[] = [],
  pastDeltaByKey: Map<string, PastOverlayDelta> = new Map(),
): PlanTrackBand[] {
  const raw = [...segments]
    .sort((a, b) => Date.parse(a.from_ts) - Date.parse(b.from_ts))
    .map((seg) => bandFromSegment(seg, window, logs, pastDeltaByKey))
    .filter((b): b is PlanTrackBand => b !== null)
  return assignBandLanes(raw).bands
}

/**
 * Merge adjacent segments with the same measure + value into one visual band.
 * Overview helper — editable tracks use {@link segmentsToBands} instead.
 */
export function mergeAdjacentEqualSegments(
  segments: PlanSegment[],
  window: PlanTimelineWindow,
): PlanTrackBand[] {
  if (segments.length === 0) return []

  const sorted = [...segments].sort(
    (a, b) => Date.parse(a.from_ts) - Date.parse(b.from_ts),
  )

  type Raw = {
    id: string
    segmentId: string
    measure: string
    value: number | null
    fromMs: number
    toMs: number
    fromTs: string
    toTs: string | null
  }

  const merged: Raw[] = []
  for (const seg of sorted) {
    const fromMs = Date.parse(seg.from_ts)
    const toMs = seg.to_ts ? Date.parse(seg.to_ts) : window.endMs
    if (Number.isNaN(fromMs) || Number.isNaN(toMs) || toMs <= fromMs) continue

    const last = merged[merged.length - 1]
    const sameContent =
      last &&
      last.measure === seg.measure &&
      last.value === seg.value &&
      fromMs <= last.toMs + 1

    if (sameContent && last) {
      last.toMs = Math.max(last.toMs, toMs)
      last.id = `${last.id}+${seg.id}`
      last.toTs = seg.to_ts
    } else {
      merged.push({
        id: seg.id,
        segmentId: seg.id,
        measure: seg.measure,
        value: seg.value,
        fromMs,
        toMs,
        fromTs: seg.from_ts,
        toTs: seg.to_ts,
      })
    }
  }

  const span = Math.max(window.endMs - window.startMs, 1)
  const rawBands = merged
    .map((raw): PlanTrackBand | null => {
      const clippedFrom = Math.max(raw.fromMs, window.startMs)
      const clippedTo = Math.min(raw.toMs, window.endMs)
      if (clippedTo <= clippedFrom) return null
      const leftPct = ((clippedFrom - window.startMs) / span) * 100
      const widthPct = ((clippedTo - clippedFrom) / span) * 100
      const label = formatBandLabel(raw.measure, raw.value)
      return {
        id: raw.id,
        segmentId: raw.segmentId,
        measure: raw.measure,
        value: raw.value,
        fromMs: clippedFrom,
        toMs: clippedTo,
        fromTs: raw.fromTs,
        toTs: raw.toTs,
        leftPct,
        widthPct,
        label,
        laneIndex: 0,
        tooltip: `${label}\n${new Date(clippedFrom).toLocaleString('de-DE')} – ${new Date(clippedTo).toLocaleString('de-DE')}`,
      }
    })
    .filter((b): b is PlanTrackBand => b !== null)
  return assignBandLanes(rawBands).bands
}

/**
 * Build track scaffold: one row per Zone × Subzone-slot × Domain.
 * Zone-wide slot (subzoneId=null) is always present per zone.
 */
export function buildPlanZoneSections(args: {
  zones: { zoneId: string; zoneName: string }[]
  subzonesByZone: Record<string, SubzoneSlot[]>
  segments: PlanSegment[]
  domains: readonly (PlanDomain | string)[]
  window: PlanTimelineWindow
  /** AUT-1236: applied_setpoint_logs for historical Soll + ghosted evidence. */
  appliedLogs?: AppliedSetpointLog[]
  /** AUT-1236: per-track Ist/Soll/Delta keyed zone::domain::measure. */
  pastDeltaByKey?: Map<string, PastOverlayDelta>
}): PlanZoneSection[] {
  const domains =
    args.domains.length > 0 ? args.domains : [...PLAN_DOMAIN_CATALOG]
  const logs = args.appliedLogs ?? []
  const pastDeltaByKey = args.pastDeltaByKey ?? new Map()

  return args.zones.map((zone) => {
    const named = args.subzonesByZone[zone.zoneId] ?? []
    const slots: SubzoneSlot[] = [
      { subzoneId: null, subzoneName: 'Zone-weit' },
      ...named,
    ]

    const tracks: PlanTrackRowModel[] = []
    for (const slot of slots) {
      for (const domain of domains) {
        const matching = args.segments.filter((s) => {
          if (s.zone_id !== zone.zoneId) return false
          if (s.domain !== domain) return false
          // Zone-wide segments have no subzone assignment in the list payload;
          // subzone-scoped rendering is refined when assignment data is exposed.
          // Until then: show all zone segments on the zone-wide track only.
          return slot.subzoneId === null
        })
        // 1:1 bands for edit (split/merge/resize need real segment ids)
        const bands = segmentsToBands(matching, args.window, logs, pastDeltaByKey)
        const laneCount =
          bands.length === 0
            ? 1
            : bands.reduce((max, b) => Math.max(max, b.laneIndex + 1), 1)
        tracks.push({
          id: `${zone.zoneId}::${slot.subzoneId ?? 'zone'}::${domain}`,
          zoneId: zone.zoneId,
          zoneName: zone.zoneName,
          subzoneId: slot.subzoneId,
          subzoneName: slot.subzoneName,
          domain,
          domainLabel: PLAN_DOMAIN_LABELS[domain] ?? domain,
          bands,
          laneCount,
          isEmpty: bands.length === 0,
        })
      }
    }

    return {
      zoneId: zone.zoneId,
      zoneName: zone.zoneName,
      tracks,
    }
  })
}
