/**
 * Plant phase + lifecycle event labels (German).
 *
 * Single source of truth so the dropdowns in PlantCreateModal,
 * PlantPhaseChangeModal and PlantDetailPanel stay in sync.
 */

import type { PlantPhase } from '@/types'

export const PLANT_PHASE_LABELS: Record<PlantPhase, string> = {
  invitro_donor: 'In-Vitro – Donor',
  invitro_initiation: 'In-Vitro – Initiation',
  invitro_multiplication: 'In-Vitro – Multiplikation',
  invitro_rooting: 'In-Vitro – Bewurzelung',
  invitro_acclimatization: 'In-Vitro – Akklimatisierung',
  clone: 'Klon',
  'veg-frueh': 'Vegetativ (früh)',
  'veg-spaet': 'Vegetativ (spät)',
  'bluete-stretch': 'Blüte – Stretch',
  'bluete-bulk': 'Blüte – Bulk',
  'bluete-ende': 'Blüte – Ende',
  mutter: 'Mutterpflanze',
  steckling_wurzelung: 'Steckling – Bewurzelung',
  steckling_vor_versand: 'Steckling – vor Versand',
  harvested: 'Geerntet',
  archived: 'Archiviert',
}

export function getPlantPhaseLabel(phase: string): string {
  return PLANT_PHASE_LABELS[phase as PlantPhase] ?? phase
}

export const PLANT_EVENT_TYPE_LABELS: Record<string, string> = {
  phase_change: 'Phasenwechsel',
  note: 'Notiz',
  harvest: 'Ernte',
  watering: 'Bewässerung',
  treatment: 'Behandlung',
  measurement: 'Messung',
  created: 'Angelegt',
}

export function getPlantEventTypeLabel(eventType: string): string {
  return PLANT_EVENT_TYPE_LABELS[eventType] ?? eventType
}
