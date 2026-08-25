/**
 * AUT-1376 A2.1/A2.2 — reine Anzeige-Helfer für Plan-Abo-Herkunft im Logic-Editor.
 * Kein Resolver-/Trigger-Touch — formatiert applied_setpoint_log (+ optional plan@now).
 */

import type { AppliedSetpointLog } from '@/types/planSegment'

export interface LivePlanHint {
  value: number
  segmentId: string | null
  measure: string
}

function shortId(id: string | null | undefined): string | null {
  if (!id) return null
  return id.length > 8 ? `${id.slice(0, 8)}…` : id
}

/**
 * Herkunftszeile aus Plan-Abo-Status + letztem applied_setpoint_log.
 * Trennt klar: Abo AN ≠ Segment speist gerade.
 */
export function formatPlanOriginLabel(input: {
  followsPlan: boolean
  hasZoneDomainMeasure: boolean
  isLoading: boolean
  log: AppliedSetpointLog | null
}): string {
  if (!input.followsPlan) {
    return 'Statischer Fallback — diese Regel nutzt ihren festen Regel-Wert.'
  }
  if (!input.hasZoneDomainMeasure) {
    return 'Plan-Abo AN — Zone/Domain/Measure vervollständigen, um den Plan-Wert zu nutzen.'
  }
  if (input.isLoading) {
    return 'Lade letzten angewandten Wert…'
  }
  const log = input.log
  if (!log) {
    return 'Plan-Abo AN — noch kein Anwendungs-Protokoll; nach dem nächsten Regel-Tick sichtbar, welcher Wert wirklich wirkte.'
  }
  const valueLabel = Number.isFinite(log.applied_value) ? String(log.applied_value) : '—'
  if (log.origin === 'plan_segment') {
    const seg = shortId(log.segment_id)
    const segPart = seg ? ` Segment ${seg}` : ''
    return `Wirkend (letzter Tick): ${valueLabel} aus Plan-Segment${segPart} — speist Trigger/Soll. Plan-Abo AN.`
  }
  if (log.origin === 'static_fallback') {
    return (
      `Wirkend (letzter Tick): ${valueLabel} — eigener Fallback ` +
      `(kein covering Plan-Segment für Zone×Domain×Measure). Plan-Abo AN — nicht „Plan aus“.`
    )
  }
  return `Wirkend (letzter Tick): ${valueLabel} — Herkunft: ${log.origin}. Plan-Abo AN.`
}

/** Read-only Zusatzzeile: plan_segment@now (z. B. über Tank-Targets), kein Trigger. */
export function formatLivePlanHint(hint: LivePlanHint | null): string | null {
  if (!hint || !Number.isFinite(hint.value)) return null
  const seg = shortId(hint.segmentId)
  const segPart = seg ? ` (Segment ${seg})` : ''
  return `Plan@now (${hint.measure}): ${hint.value}${segPart} — speist den Trigger, sobald ein covering Segment greift.`
}
