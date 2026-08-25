/**
 * German labels for tank / nutrient-ledger enums (AUT-1215).
 *
 * Values must stay in sync with server tuples in
 * nutrient_solution_batch.py / tank.py — do not invent extras.
 */

import type {
  NutrientBatchAcquisitionMethod,
  NutrientBatchEntryType,
  NutrientBatchQualifier,
  TankOperationMode,
} from '@/types'
import {
  NUTRIENT_BATCH_ACQUISITION_METHODS,
  NUTRIENT_BATCH_ENTRY_TYPES,
  NUTRIENT_BATCH_QUALIFIERS,
  TANK_OPERATION_MODES,
} from '@/types'

export const TANK_OPERATION_MODE_LABELS: Record<TankOperationMode, string> = {
  drain_to_waste: 'Drain-to-Waste',
  recirculating: 'Rezirkulation',
}

export const NUTRIENT_BATCH_ENTRY_TYPE_LABELS: Record<NutrientBatchEntryType, string> = {
  full_reset: 'Neuansatz',
  top_up_dose: 'Nachdosierung',
  fresh_water_refill: 'Nachfüllung',
  withdrawal: 'Entnahme',
  remeasurement_only: 'Nachmessung',
  system_incident: 'Anlagen-Vorfall',
}

export const NUTRIENT_BATCH_ACQUISITION_METHOD_LABELS: Record<
  NutrientBatchAcquisitionMethod,
  string
> = {
  measured_flow: 'Durchfluss gemessen',
  measured_level: 'Füllstand gemessen',
  computed_runtime_x_rate: 'Laufzeit × Rate berechnet',
  manual_entry: 'Manuell erfasst',
}

export const NUTRIENT_BATCH_QUALIFIER_LABELS: Record<NutrientBatchQualifier, string> = {
  precise: 'Präzise',
  approximate: 'Ungefähr',
  estimated: 'Geschätzt',
}

/** Entry types that typically carry a recipe + components (Zugang). */
export const INFLOW_ENTRY_TYPES: readonly NutrientBatchEntryType[] = [
  'full_reset',
  'top_up_dose',
  'fresh_water_refill',
] as const

export function showsComponents(entryType: NutrientBatchEntryType): boolean {
  return entryType === 'full_reset' || entryType === 'top_up_dose'
}

export function showsRecipeLabel(entryType: NutrientBatchEntryType): boolean {
  return (
    entryType === 'full_reset' ||
    entryType === 'top_up_dose' ||
    entryType === 'system_incident'
  )
}

export function showsMeasurements(entryType: NutrientBatchEntryType): boolean {
  return (
    entryType === 'full_reset' ||
    entryType === 'top_up_dose' ||
    entryType === 'remeasurement_only' ||
    entryType === 'system_incident'
  )
}

// Re-export server value lists for template v-for
export {
  NUTRIENT_BATCH_ACQUISITION_METHODS,
  NUTRIENT_BATCH_ENTRY_TYPES,
  NUTRIENT_BATCH_QUALIFIERS,
  TANK_OPERATION_MODES,
}
