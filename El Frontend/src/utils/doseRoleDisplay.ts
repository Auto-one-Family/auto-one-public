/**
 * AUT-1359: Einheitliche Anzeige für Dosierpumpen-Bezeichnung + Rezept-Rolle.
 *
 * Rolle kommt AUSSCHLIESSLICH aus gespeichertem `dose_role` — keine Ableitung
 * aus dem Gerätenamen, kein Hardcode/Default. Nicht gesetzt → keine Rolle.
 *
 * Bezeichnung: Gerätename → (falls leer) Gerätetyp → falls dose_role: " (Rolle)".
 */

import type { DoseRole } from '@/types'
import { ACTUATOR_TYPE_LABELS } from '@/utils/labels'

/** Kurze Rollen-Labels für Anzeige/Select (ohne Gerätenamen). */
export const DOSE_ROLE_DISPLAY_LABELS: Record<DoseRole, string> = {
  part_a: 'Stock A',
  part_b: 'Stock B',
  ph_down: 'pH-Minus',
  generic: 'Allgemein',
}

/** Select-Optionen Grundlagen-Tab (Wert = gespeichertes Feld, Label = Anzeige). */
export const DOSE_ROLE_SELECT_OPTIONS = [
  { value: '', label: '— nicht gesetzt —' },
  { value: 'part_a', label: DOSE_ROLE_DISPLAY_LABELS.part_a },
  { value: 'part_b', label: DOSE_ROLE_DISPLAY_LABELS.part_b },
  { value: 'ph_down', label: DOSE_ROLE_DISPLAY_LABELS.ph_down },
  { value: 'generic', label: DOSE_ROLE_DISPLAY_LABELS.generic },
] as const

/**
 * Rollen-Label nur aus gespeichertem `dose_role`.
 * unset / unbekannt → null (nichts erfinden).
 */
export function formatDoseRoleLabel(doseRole: string | null | undefined): string | null {
  if (doseRole == null || doseRole === '') return null
  if (doseRole in DOSE_ROLE_DISPLAY_LABELS) {
    return DOSE_ROLE_DISPLAY_LABELS[doseRole as DoseRole]
  }
  return null
}

export interface ActuatorDoseLabelInput {
  name?: string | null
  actuatorType?: string | null
  doseRole?: string | null
  /** Fallback wenn Typ unbekannt und Name leer (Default: „Gerät“). */
  typeFallback?: string
}

/**
 * Gerätename → (falls leer) Gerätetyp → falls dose_role gesetzt: „ (Rolle)“.
 *
 * Beispiele:
 * - name „Teil A“, role part_a → „Teil A (Stock A)“
 * - name „Teil B“, role unset → „Teil B“
 * - name leer, type pump, role part_b → „Pumpe (Stock B)“
 */
export function formatActuatorDoseLabel(input: ActuatorDoseLabelInput): string {
  const trimmedName = (input.name ?? '').trim()
  const typeKey = (input.actuatorType ?? '').toLowerCase().trim()
  const typeLabel =
    ACTUATOR_TYPE_LABELS[typeKey]
    ?? input.typeFallback
    ?? 'Gerät'
  const base = trimmedName || typeLabel
  const role = formatDoseRoleLabel(input.doseRole)
  if (!role) return base
  // Redundanz: kein „Stock A (Stock A)“ / kein doppeltes „… (Stock A)“
  if (base === role || base.endsWith(` (${role})`)) return base
  return `${base} (${role})`
}
