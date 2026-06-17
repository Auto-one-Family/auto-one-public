/**
 * Subzone Helper Utilities
 *
 * Defense-in-depth: Normalize "Keine Subzone" semantics before API calls.
 * Backend uses utils/subzone_helpers.normalize_subzone_id (Auftrag 1);
 * Frontend normalizes for consistency.
 */

/**
 * Normalizes subzone_id for API requests.
 * "Keine Subzone" = always null. Never send "__none__" or "" to backend.
 *
 * @param val - Raw subzone_id from form/store
 * @returns null for "no subzone", trimmed string otherwise
 */
export function normalizeSubzoneId(val: string | null | undefined): string | null {
  if (val == null || val === '') return null
  const trimmed = String(val).trim()
  if (trimmed === '' || trimmed === '__none__') return null
  return trimmed
}

const GERMAN_TRANSLITERATIONS: Record<string, string> = {
  'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
  'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
}

/**
 * Generate a URL/ID-safe slug from a German name.
 * Transliterates German umlauts BEFORE lowercasing (ä→ae, ö→oe, ü→ue, ß→ss),
 * then replaces non-alphanumeric characters with underscores.
 *
 * @example slugifyGerman("Nährlösung") → "naehrloesung"
 * @example slugifyGerman("Gewächshaus Alpha") → "gewaechshaus_alpha"
 */
export function slugifyGerman(name: string): string {
  let result = name
  for (const [char, replacement] of Object.entries(GERMAN_TRANSLITERATIONS)) {
    result = result.replace(new RegExp(char, 'g'), replacement)
  }
  return result
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '')
}
