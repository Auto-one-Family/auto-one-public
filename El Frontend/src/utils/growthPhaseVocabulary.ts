/**
 * Shared growth-phase vocabulary.
 *
 * Space = zone / subzone (WHERE). Time = plant-phase section (WHEN).
 * Canonical keys are PLANT_PHASES. Legacy zone-context strings map here.
 */

import { getPlantPhaseLabel, PLANT_PHASE_LABELS } from '@/components/plants/plantLabels'
import { PLANT_PHASES, type PlantPhase } from '@/types'

const CANONICAL = new Set<string>(PLANT_PHASES)

const LEGACY_ZONE_PHASE_TO_CANONICAL: Record<string, PlantPhase> = {
  seedling: 'clone',
  clone: 'clone',
  vegetative: 'veg-frueh',
  veg: 'veg-frueh',
  pre_flower: 'uebergang-vorbluete',
  'pre-flower': 'uebergang-vorbluete',
  flower: 'bluete-stretch',
  flower_early: 'bluete-stretch',
  flower_late: 'bluete-bulk',
  flower_week_1: 'bluete-stretch',
  flower_week_2: 'bluete-stretch',
  flower_week_3: 'bluete-stretch',
  flower_week_4: 'bluete-stretch',
  flower_week_5: 'bluete-bulk',
  flower_week_6: 'bluete-bulk',
  flower_week_7: 'bluete-bulk',
  flower_week_8: 'bluete-bulk',
  flower_week_9: 'bluete-ende',
  flower_week_10: 'bluete-ende',
  flush: 'bluete-ende',
  harvest: 'harvested',
  harvested: 'harvested',
  drying: 'harvested',
  curing: 'harvested',
}

export function normalizeGrowthPhase(raw: string | null | undefined): PlantPhase | null {
  if (raw == null) return null
  const key = raw.trim().toLowerCase().replace(/ /g, '_')
  if (!key) return null
  if (CANONICAL.has(key)) return key as PlantPhase
  if (key in LEGACY_ZONE_PHASE_TO_CANONICAL) {
    return LEGACY_ZONE_PHASE_TO_CANONICAL[key]
  }
  if (key.startsWith('flower_week_')) {
    const week = Number.parseInt(key.slice('flower_week_'.length), 10)
    if (!Number.isFinite(week)) return 'bluete-stretch'
    if (week <= 4) return 'bluete-stretch'
    if (week <= 8) return 'bluete-bulk'
    return 'bluete-ende'
  }
  return null
}

export function growthPhaseSelectOptions(): { value: PlantPhase; label: string }[] {
  return PLANT_PHASES.map((value) => ({
    value,
    label: PLANT_PHASE_LABELS[value],
  }))
}

export function displayGrowthPhase(raw: string | null | undefined): string {
  const canonical = normalizeGrowthPhase(raw)
  if (canonical) return getPlantPhaseLabel(canonical)
  return raw?.trim() || '—'
}
