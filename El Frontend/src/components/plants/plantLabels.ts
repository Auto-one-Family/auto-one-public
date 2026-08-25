/**
 * Plant phase + lifecycle event labels (German).
 *
 * Single source of truth so the dropdowns in PlantCreateModal,
 * PlantPhaseChangeModal and PlantDetailPanel stay in sync.
 */

import type { PlantEventStatus, PlantPhase, PlantTankIncidentEvent } from '@/types'

export const PLANT_PHASE_LABELS: Record<PlantPhase, string> = {
  invitro_donor: 'In-Vitro – Donor',
  invitro_initiation: 'In-Vitro – Initiation',
  invitro_multiplication: 'In-Vitro – Multiplikation',
  invitro_rooting: 'In-Vitro – Bewurzelung',
  invitro_acclimatization: 'In-Vitro – Akklimatisierung',
  clone: 'Klon',
  'veg-frueh': 'Vegetativ (früh)',
  'veg-spaet': 'Vegetativ (spät)',
  'uebergang-vorbluete': 'Übergang/Vorblüte',
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
  // Canonical server event types (AUT-1183)
  phase_changed: 'Phasenwechsel (Licht)',
  nutrient_phase_changed: 'Phasenwechsel (Nährstoff)',
  // Plant measures (AUT-1235 — LIFECYCLE_EVENT_TYPES)
  topping: 'Schnitt (Topping)',
  defoliation: 'Entlauben',
  transplanted: 'Umtopfen',
  training: 'Training',
  // Legacy / other event types
  phase_change: 'Phasenwechsel',
  note: 'Notiz',
  note_added: 'Notiz',
  harvest: 'Ernte',
  watering: 'Bewässerung',
  treatment: 'Behandlung',
  measurement: 'Messung',
  created: 'Angelegt',
}

export function getPlantEventTypeLabel(eventType: string): string {
  return PLANT_EVENT_TYPE_LABELS[eventType] ?? eventType
}

/**
 * AUT-1207: labels for the event truth status. 'occurred' has no label —
 * it is the silent default and gets no badge in the timeline.
 */
export const PLANT_EVENT_STATUS_LABELS: Record<Exclude<PlantEventStatus, 'occurred'>, string> = {
  planned: 'Geplant',
  reverted: 'Zurückgenommen',
  test_data: 'Testdaten',
}

export function getPlantEventStatusLabel(status: PlantEventStatus): string | null {
  if (status === 'occurred') return null
  return PLANT_EVENT_STATUS_LABELS[status]
}

/**
 * AUT-1211: badge label marking a tank-wide system incident in the plant's
 * event timeline — deliberately distinct from a real per-plant lifecycle
 * event (see PlantTankIncidentEvent).
 */
export const TANK_INCIDENT_LABEL = 'Anlagen-Ereignis'

/** One-line summary for a tank incident timeline entry. */
export function formatTankIncidentSummary(incident: PlantTankIncidentEvent): string {
  const parts = [incident.recipe_label ?? 'Nährlösungs-Tank neu angesetzt']
  parts.push(`${incident.volume_l} L`)
  if (incident.ph_measured_after != null) parts.push(`pH ${incident.ph_measured_after}`)
  if (incident.ec_measured_after != null) parts.push(`EC ${incident.ec_measured_after}`)
  return parts.join(' · ')
}
