/**
 * AUT-1375 A1.1: Salzrechner concentration display from pump SSOT.
 * No second formula — only pick which existing number to surface.
 */

/**
 * Prefer pump SSOT, then Assist A/B field, then legacy shared Assist concentration.
 * Returns null when nothing usable (UI shows "—").
 */
export function resolveDisplayConcentration(
  pump: number | null | undefined,
  assistAb: number | null | undefined,
  assistLegacy?: number | null | undefined,
): number | null {
  for (const v of [pump, assistAb, assistLegacy]) {
    if (v != null && Number.isFinite(v) && v > 0) return v
  }
  return null
}
