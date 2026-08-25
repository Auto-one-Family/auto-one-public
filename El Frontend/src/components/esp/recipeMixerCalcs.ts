/**
 * AUT-1356 U4-b — pure FE arithmetic for Rechner 1 (Dreisatz) and
 * concentration-from-ΔEC (Wizard). No salt→EC conversion (empiric = truth).
 */

/** Grams to weigh for a stock vessel: g = g/L × V_ml / 1000. */
export function gramsFromRecipe(gPerL: number, vesselMl: number): number | null {
  if (!Number.isFinite(gPerL) || !Number.isFinite(vesselMl)) return null
  if (gPerL < 0 || vesselMl <= 0) return null
  return (gPerL * vesselMl) / 1000
}

/**
 * AUT-1362: Internal dilute scale (fallback/base). Never show factors in UI.
 * e.g. 200/250 → 0.8 (milder stock → fewer g/L).
 */
export function diluteScaleFactor(
  concentrationFactor: number | null | undefined,
  fallbackFactor: number | null | undefined,
): number | null {
  if (
    concentrationFactor == null ||
    fallbackFactor == null ||
    !Number.isFinite(concentrationFactor) ||
    !Number.isFinite(fallbackFactor)
  ) {
    return null
  }
  if (concentrationFactor <= 0 || fallbackFactor <= 0) return null
  return fallbackFactor / concentrationFactor
}

/** Effective g/L after optional dilute (internal scale only). */
export function effectiveGPerL(gPerL: number, diluteScale: number | null): number | null {
  if (!Number.isFinite(gPerL) || gPerL < 0) return null
  if (diluteScale == null) return gPerL
  if (!Number.isFinite(diluteScale) || diluteScale <= 0) return null
  return gPerL * diluteScale
}

/**
 * Dose ml per L tank after dilute: more dilute stock → more ml.
 * baseDose × (concentrationFactor / fallbackFactor) = baseDose / diluteScale.
 */
export function effectiveDoseMlPerL(
  baseDoseMlPerL: number | null | undefined,
  diluteScale: number | null,
): number | null {
  if (baseDoseMlPerL == null || !Number.isFinite(baseDoseMlPerL) || baseDoseMlPerL < 0) {
    return null
  }
  if (diluteScale == null) return baseDoseMlPerL
  if (!Number.isFinite(diluteScale) || diluteScale <= 0) return null
  return baseDoseMlPerL / diluteScale
}

/** Role Klartext fallbacks when metadata.handling_hint missing (AUT-1362). */
export const DEFAULT_HANDLING_HINTS: Record<string, string> = {
  part_a: 'In Wasser auflösen, umrühren.',
  part_b:
    'Warmes Wasser (~25–30 °C), langsam unter Rühren einlaufen lassen, leicht sauer halten — dann löst sich alles klar.',
  ph_down: 'Säure vorsichtig zugeben; nicht mit Stock A/B mischen.',
  generic: 'Nach Rezeptauflösung umrühren.',
}

export function resolveHandlingHint(
  doseRole: string | null | undefined,
  metadata: Record<string, unknown> | null | undefined,
): string {
  const fromMeta = metadata?.handling_hint
  if (typeof fromMeta === 'string' && fromMeta.trim().length > 0) {
    return fromMeta.trim()
  }
  if (doseRole && DEFAULT_HANDLING_HINTS[doseRole]) {
    return DEFAULT_HANDLING_HINTS[doseRole]
  }
  return DEFAULT_HANDLING_HINTS.generic
}

/**
 * Empiric concentration (µS/cm rise per ml Stock per L tank):
 * concentration = (EC₁ − EC₀) × V_l / dose_ml
 */
export function concentrationFromDeltaEc(
  ec0UsCm: number,
  ec1UsCm: number,
  volumeL: number,
  doseMl: number,
): number | null {
  if (
    !Number.isFinite(ec0UsCm) ||
    !Number.isFinite(ec1UsCm) ||
    !Number.isFinite(volumeL) ||
    !Number.isFinite(doseMl)
  ) {
    return null
  }
  if (volumeL <= 0 || doseMl <= 0) return null
  return ((ec1UsCm - ec0UsCm) * volumeL) / doseMl
}

/** Duration (s) for a known dose: ceil(ml / flow_rate_ml_s), min 1. */
export function doseDurationSeconds(doseMl: number, flowRateMlS: number): number | null {
  if (!Number.isFinite(doseMl) || !Number.isFinite(flowRateMlS)) return null
  if (doseMl <= 0 || flowRateMlS <= 0) return null
  return Math.max(1, Math.ceil(doseMl / flowRateMlS))
}

/** Pair-scale factor k = measured / seedRef (seedRef defaults to rough ~100). */
export function pairScaleFactor(measuredConc: number, seedRef: number | null | undefined): number | null {
  if (!Number.isFinite(measuredConc) || measuredConc <= 0) return null
  const ref = seedRef != null && Number.isFinite(seedRef) && seedRef > 0 ? seedRef : 100
  return measuredConc / ref
}

/**
 * AUT-1403: Klartext A/B-Ausfällungs-Hinweis (nicht blockierend).
 * Kein Ca-Flag im Modell — Erkennung über Seed-Komponentennamen (Calcinit / MgSO₄ / Kristalon / MKP).
 */
export const STOCK_MIX_AB_SPLIT_WARNING =
  'Stock A ist für den Calcium-Träger (Calcinit) reserviert. MgSO4, Kristalon und MKP ' +
  'gehören in Stock B — gemeinsam mit Calcinit angesetzt fällt Calciumphosphat/-sulfat aus ' +
  '(Trübung), was der EC-Wert nicht anzeigt.'

/** Normalize component label for substring checks (MgSO₄ → mgso4). */
export function normalizeStockComponentName(name: string): string {
  return name
    .normalize('NFKD')
    .replace(/\p{M}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]/g, '')
}

function isCalciumCarrierName(normalized: string): boolean {
  return normalized.includes('calcinit')
}

function isSulfateOrPhosphateCarrierName(normalized: string): boolean {
  return (
    normalized.includes('mgso') ||
    normalized.includes('kristalon') ||
    normalized.includes('mkp')
  )
}

/**
 * Soft A/B-split hint for stock_mix recipe edit (AUT-1403).
 * Returns warning text when Ca-Träger is outside part_a, or Sulfat/Phosphat lands in part_a.
 * Never blocks save — display-only.
 */
export function resolveAbSplitWarning(
  doseRole: string | null | undefined,
  componentNames: readonly string[],
): string | null {
  if (!doseRole || componentNames.length === 0) return null
  const normalized = componentNames.map(normalizeStockComponentName)
  const hasCalcium = normalized.some(isCalciumCarrierName)
  const hasSulfatePhosphate = normalized.some(isSulfateOrPhosphateCarrierName)
  if (doseRole !== 'part_a' && hasCalcium) return STOCK_MIX_AB_SPLIT_WARNING
  if (doseRole === 'part_a' && hasSulfatePhosphate) return STOCK_MIX_AB_SPLIT_WARNING
  return null
}
