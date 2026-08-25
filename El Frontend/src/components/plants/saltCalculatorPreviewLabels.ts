/**
 * AUT-1368 / AUT-1404 Klartext: Anzeige-Helfer für den Salzrechner.
 *
 * Dosismengen kommen nur vom Server-Assist — hier wird nichts neu gerechnet.
 * Labels sind für Operatoren, keine internen Feldnamen (GPIO, dose_role, SSOT).
 */

import type { SaltCalculatorSuggestionKind } from '@/types'

/** Richtungs-Label aus Assist suggestion_kind (Anzeige = Wirkung). */
export function suggestionKindLabel(
  kind: SaltCalculatorSuggestionKind | string | null | undefined,
): string {
  if (kind === 'dose_up') return 'Aufdosieren'
  if (kind === 'dilute') return 'Verdünnen'
  if (kind === 'within_tolerance') return 'Im Zielband'
  if (kind === 'unavailable') return 'Kein Vorschlag'
  return 'Vorschlag'
}

/** Volumen-Anteil aus Assist-ml (nicht EC-Beitrag). */
export function formatAssistVolumeRatioLabel(
  doseAMl: number,
  doseBMl: number,
): string {
  if (!(doseAMl > 0) || !(doseBMl > 0)) {
    return 'Anteil nach Volumen'
  }
  const ratio = doseAMl / doseBMl
  if (Math.abs(ratio - 1) < 0.05) {
    return 'gleicher Anteil'
  }
  return `Anteil A:B ≈ ${ratio.toFixed(1)}:1`
}

/** Herkunft des Tankvolumens — Klartext. */
export function volumeAltSourceLabel(source: string): string {
  if (source === 'manual_override') return 'von Hand eingegeben'
  if (source === 'v_real_anchor_flow') return 'gemessen'
  if (source === 'v_real_minus_measured_zugabe') return 'gemessen (vor Frischwasser)'
  if (source === 'ledger_prior_volume') return 'aus letzter Buchung'
  if (source === 'ledger_reconstructed') return 'aus Buchungsverlauf'
  return 'unbekannt'
}

/** Herkunft Frischwasser-EC — Klartext. */
export function ecWasserSourceLabel(source: string | null | undefined): string {
  if (source === 'request_override') return 'für diese Rechnung überschrieben'
  if (source === 'tank_config') return 'am Tank hinterlegt'
  if (source === 'none') return 'nicht hinterlegt'
  return 'nicht hinterlegt'
}

export interface SaltAssistHintInput {
  volume_alt_l: number
  volume_alt_source: string
  volume_zugabe_l: number
  ec_wasser_us_cm: number | null | undefined
  ec_wasser_source: string | null | undefined
  ec_after_dilution_us_cm: number
}

/**
 * Kurze Operator-Hinweise aus strukturierten Assist-Feldern.
 * Roh-Notes (GPIO, dose_role, V_real, …) werden nicht durchgereicht.
 */
export function buildSaltAssistOperatorHints(input: SaltAssistHintInput): string[] {
  const hints: string[] = []
  const volLabel = volumeAltSourceLabel(input.volume_alt_source)
  hints.push(
    `Tankvolumen ${formatVolumeDe(input.volume_alt_l)} L (${volLabel}).`,
  )
  if (input.volume_zugabe_l > 0) {
    const ecW =
      input.ec_wasser_us_cm != null && Number.isFinite(input.ec_wasser_us_cm)
        ? `${formatEcDe(input.ec_wasser_us_cm)} µS/cm (${ecWasserSourceLabel(input.ec_wasser_source)})`
        : ecWasserSourceLabel(input.ec_wasser_source)
    hints.push(
      `${formatVolumeDe(input.volume_zugabe_l)} L Frischwasser eingerechnet` +
        ` (EC Frischwasser: ${ecW})` +
        ` — EC danach ${formatEcDe(input.ec_after_dilution_us_cm)} µS/cm.`,
    )
  }
  return hints
}

function formatVolumeDe(liters: number): string {
  return liters.toLocaleString('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })
}

function formatEcDe(ec: number): string {
  return ec.toLocaleString('de-DE', {
    maximumFractionDigits: 0,
  })
}
