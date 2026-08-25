/**
 * AUT-1389: EIN Adapter für deutsche Dezimal-Kommas vor Number()-Parse.
 *
 * "5,9" → 5.9. Kein Duplikat je Eingabefeld — alle pH/EC-Parse-Pfade
 * importieren diese Helfer.
 */

/** Normalize decimal separators: first ',' → '.' (German locale). */
export function normalizeLocaleNumberString(raw: string): string {
  return raw.trim().replace(',', '.')
}

/** Parse string|number with German comma support. NaN if empty/invalid. */
export function parseLocaleNumber(raw: string | number): number {
  if (typeof raw === 'number') return raw
  if (raw == null) return Number.NaN
  const normalized = normalizeLocaleNumberString(String(raw))
  if (normalized === '') return Number.NaN
  return Number(normalized)
}

/** Empty string → null; otherwise locale-aware Number (null if not finite). */
export function parseLocaleNumberOrNull(raw: string | number | null | undefined): number | null {
  if (raw === '' || raw == null) return null
  if (typeof raw === 'string') {
    const trimmed = raw.trim()
    // Tippen „5,“ noch unvollständig — kein NaN erzwingen.
    if (trimmed === '' || trimmed === '-' || /[.,]$/.test(trimmed)) return null
  }
  const n = parseLocaleNumber(raw)
  return Number.isFinite(n) ? n : null
}

/**
 * Live-Input: unvollständige Dezimalstrings (z. B. „5,“) als String durchreichen,
 * fertige Werte als number. Für kontrollierte Inputs mit Komma-Locale.
 */
export function coerceLocaleNumberInput(raw: string): number | string | null {
  if (raw === '') return null
  const trimmed = raw.trim()
  if (trimmed === '-' || /[.,]$/.test(trimmed)) return trimmed
  const n = parseLocaleNumber(trimmed)
  return Number.isFinite(n) ? n : trimmed
}
