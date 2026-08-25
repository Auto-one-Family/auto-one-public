/**
 * Cohort grouping for the consolidated Planungs-Zeitstrahl.
 *
 * - Plants with the same batch_label form one seed group.
 * - Plants without batch_label are singleton seed groups.
 * - Seed groups with identical phase signatures are merged.
 * Phase signature = occurred phase_changed + nutrient_phase_changed
 * (timestamp|type|new_phase).
 */

import { getPlantPhaseLabel } from '@/components/plants/plantLabels'
import type { PlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import type { Plant, PlantLifecycleEvent } from '@/types'

const PHASE_EVENT_TYPES = new Set(['phase_changed', 'nutrient_phase_changed'])

export interface PlanCohortPlantRef {
  plantId: string
  label: string
  batchLabel: string | null
}

export interface PlanPhaseBand {
  id: string
  label: string
  startMs: number
  endMs: number
  leftPct: number
  widthPct: number
  tooltip: string
}

export interface PlanCohortPhaseTrack {
  id: string
  label: string
  plantIds: string[]
  bands: PlanPhaseBand[]
  isEmpty: boolean
}

export interface PlanCohort {
  id: string
  label: string
  plantIds: string[]
  plants: PlanCohortPlantRef[]
  /** Stable signature used for merge. */
  signature: string
}

function plantDisplayLabel(plant: Plant): string {
  return (
    plant.batch_label ||
    plant.batch ||
    plant.genotype_label ||
    plant.genotype ||
    plant.qr_code ||
    plant.plant_id
  )
}

function seedKey(plant: Plant): string {
  const batch = (plant.batch_label || plant.batch || '').trim()
  if (batch) return `batch:${batch}`
  return `plant:${plant.plant_id}`
}

function seedLabel(plants: Plant[]): string {
  const first = plants[0]
  if (!first) return '—'
  const batch = (first.batch_label || first.batch || '').trim()
  if (batch) {
    return plants.length > 1 ? `${batch} (${plants.length})` : batch
  }
  return plantDisplayLabel(first)
}

/**
 * Content-only phase signature (no plant id) so equal sequences merge.
 * Uses the first plant in the seed that has occurred phase events.
 */
export function buildPhaseSignature(
  plantIds: readonly string[],
  eventsByPlantId: Map<string, PlantLifecycleEvent[]>,
): string {
  for (const plantId of [...plantIds].sort()) {
    const phaseEvents = (eventsByPlantId.get(plantId) ?? [])
      .filter(
        (e) =>
          e.event_status === 'occurred' && PHASE_EVENT_TYPES.has(e.event_type),
      )
      .slice()
      .sort(
        (a, b) =>
          Date.parse(a.event_timestamp) - Date.parse(b.event_timestamp) ||
          a.event_type.localeCompare(b.event_type),
      )
    if (phaseEvents.length === 0) continue
    return phaseEvents
      .map((e) => {
        const ts = Date.parse(e.event_timestamp)
        return `${ts}|${e.event_type}|${e.new_phase ?? ''}`
      })
      .filter((p) => !p.startsWith('NaN|'))
      .join(';;')
  }
  return ''
}

/**
 * Group zone plants into cohorts (batch / singleton), then merge equal signatures.
 */
export function buildPlanCohorts(
  plants: readonly Plant[],
  eventsByPlantId: Map<string, PlantLifecycleEvent[]>,
): PlanCohort[] {
  const seedMap = new Map<string, Plant[]>()
  for (const plant of plants) {
    const key = seedKey(plant)
    const list = seedMap.get(key)
    if (list) list.push(plant)
    else seedMap.set(key, [plant])
  }

  const seeds = [...seedMap.entries()].map(([key, group]) => {
    const plantIds = group.map((p) => p.plant_id)
    return {
      seedId: key,
      plants: group,
      plantIds,
      label: seedLabel(group),
      signature: buildPhaseSignature(plantIds, eventsByPlantId),
    }
  })

  const bySig = new Map<string, typeof seeds>()
  for (const seed of seeds) {
    const list = bySig.get(seed.signature)
    if (list) list.push(seed)
    else bySig.set(seed.signature, [seed])
  }

  const cohorts: PlanCohort[] = []
  for (const [signature, group] of bySig.entries()) {
    const allPlants = group.flatMap((s) => s.plants)
    const plantIds = allPlants.map((p) => p.plant_id)
    const label =
      group.length === 1
        ? group[0].label
        : group.map((s) => s.label).join(' · ')
    cohorts.push({
      id: `cohort:${group.map((s) => s.seedId).sort().join('+')}`,
      label,
      plantIds,
      plants: allPlants.map((p) => ({
        plantId: p.plant_id,
        label: plantDisplayLabel(p),
        batchLabel: p.batch_label || p.batch || null,
      })),
      signature,
    })
  }

  return cohorts.sort((a, b) => a.label.localeCompare(b.label, 'de'))
}

/**
 * Light/growth phase bands for a cohort, clipped to the timeline window.
 * Uses phase_changed (occurred) from the first plant that has events
 * (same signature ⇒ equivalent sequences).
 */
export function buildCohortPhaseBands(
  cohort: PlanCohort,
  eventsByPlantId: Map<string, PlantLifecycleEvent[]>,
  window: PlanTimelineWindow,
): PlanPhaseBand[] {
  let lightEvents: PlantLifecycleEvent[] = []
  for (const plantId of cohort.plantIds) {
    const events = (eventsByPlantId.get(plantId) ?? []).filter(
      (e) =>
        e.event_status === 'occurred' && e.event_type === 'phase_changed',
    )
    if (events.length > 0) {
      lightEvents = events
      break
    }
  }
  if (lightEvents.length === 0) return []

  const sorted = [...lightEvents].sort(
    (a, b) => Date.parse(a.event_timestamp) - Date.parse(b.event_timestamp),
  )
  const span = Math.max(window.endMs - window.startMs, 1)
  const bands: PlanPhaseBand[] = []

  for (let i = 0; i < sorted.length; i++) {
    const evt = sorted[i]
    const startMs = Date.parse(evt.event_timestamp)
    const endMs =
      i < sorted.length - 1
        ? Date.parse(sorted[i + 1].event_timestamp)
        : window.nowMs
    if (Number.isNaN(startMs) || Number.isNaN(endMs) || endMs <= startMs) {
      continue
    }
    const clippedFrom = Math.max(startMs, window.startMs)
    const clippedTo = Math.min(endMs, window.endMs)
    if (clippedTo <= clippedFrom) continue

    const phaseValue = evt.new_phase ?? ''
    const label = phaseValue ? getPlantPhaseLabel(phaseValue) : '—'
    const leftPct = ((clippedFrom - window.startMs) / span) * 100
    const widthPct = ((clippedTo - clippedFrom) / span) * 100
    bands.push({
      id: `${cohort.id}::${evt.event_id}`,
      label,
      startMs: clippedFrom,
      endMs: clippedTo,
      leftPct,
      widthPct,
      tooltip: `${cohort.label}: ${label}`,
    })
  }
  return bands
}

/**
 * One phase track per cohort (empty track when no phase events in window).
 */
export function buildCohortPhaseTracks(
  cohorts: readonly PlanCohort[],
  eventsByPlantId: Map<string, PlantLifecycleEvent[]>,
  window: PlanTimelineWindow,
): PlanCohortPhaseTrack[] {
  return cohorts.map((cohort) => {
    const bands = buildCohortPhaseBands(cohort, eventsByPlantId, window)
    return {
      id: cohort.id,
      label: cohort.label,
      plantIds: [...cohort.plantIds],
      bands,
      isEmpty: bands.length === 0,
    }
  })
}
