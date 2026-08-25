/**
 * AUT-1306 / C5: Lesbarkeits-Helfer für Sequenz-Schritte (Node-Gesicht + Panel).
 * Kein Schema-Change — reine Anzeige über SequenceStepDraft.
 */

import type { SequenceStepDraft } from '@/types/logic'
import { resolveStepDoseMode } from '@/utils/sequenceDoseDisplay'

export type SequenceStepKind = 'actuator' | 'delay'

/** Laufenende Nr. 1…n für alle Schritte (Aktor und Pause). */
export function sequenceStepNumber(idx: number): string {
  return String(idx + 1)
}

/** Glasklare Typ-Bezeichnung — „Pause“ (nicht „Verzögerung“/„Mischzeit“). */
export function sequenceStepTypeLabel(stepType: SequenceStepKind): string {
  return stepType === 'delay' ? 'Pause' : 'Aktor'
}

/**
 * Primärtext neben Typ: Aktorname bzw. Pausenname.
 * Default Pause = „Pause“ (nicht „Mischzeit“).
 */
export function sequenceStepPrimaryLabel(
  step: SequenceStepDraft,
  resolveActuatorName: (espId?: string, gpio?: number, fallbackName?: string) => string,
): string {
  if (step.stepType === 'delay') {
    const name = step.name?.trim()
    return name || 'Pause'
  }
  return resolveActuatorName(step.espId, step.gpio, step.name)
}

/**
 * Detail rechts: Pausendauer bzw. Dosis (+ optionale Laufzeit) / Befehl.
 * AUT-1390: Modus-Tag folgt Meta-Flag `dose_mode` (nicht nur dose_ml-Heuristik).
 * Ohne Flag: Legacy AUT-1379 (dose_ml > 0 → ml-getrieben).
 */
export function sequenceStepDetailLabel(
  step: SequenceStepDraft,
  formatDuration: (seconds: number) => string,
): string {
  if (step.stepType === 'delay') {
    return formatDuration(step.seconds ?? 60)
  }
  const mode = resolveStepDoseMode(step.dose_mode, step.dose_ml)
  if (mode === 'target_optimal') {
    if (step.dose_ml != null && step.dose_ml > 0) {
      return `${step.dose_ml} ml (Zielwert-optimal)`
    }
    if (step.duration) {
      return `${formatDuration(step.duration)} (Zielwert-optimal)`
    }
    return 'Zielwert-optimal'
  }
  if (mode === 'ml' && step.dose_ml != null && step.dose_ml > 0) {
    return `${step.dose_ml} ml (ml-getrieben)`
  }
  if (step.duration) {
    return `${formatDuration(step.duration)} (laufzeit-getrieben)`
  }
  const cmd = (step.command ?? 'ON').toUpperCase()
  return cmd === 'OFF' ? 'AUS' : 'AN'
}

/** Kompakte Einzeile für Tests/Logs: „1 · Aktor · Pumpe A · 9 ml“. */
export function formatSequenceStepFaceLine(
  step: SequenceStepDraft,
  idx: number,
  resolveActuatorName: (espId?: string, gpio?: number, fallbackName?: string) => string,
  formatDuration: (seconds: number) => string,
): string {
  const nr = sequenceStepNumber(idx)
  const typ = sequenceStepTypeLabel(step.stepType)
  const primary = sequenceStepPrimaryLabel(step, resolveActuatorName)
  const detail = sequenceStepDetailLabel(step, formatDuration)
  return `${nr} · ${typ} · ${primary} · ${detail}`
}
