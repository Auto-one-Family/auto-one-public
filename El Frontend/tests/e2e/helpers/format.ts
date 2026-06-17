/**
 * Format helpers for E2E assertions
 *
 * Mirrors app formatNumber (src/utils/formatters.ts) to ensure tests
 * assert on the exact display format the user sees (de-DE).
 *
 * Use for: getByText(), toBeVisible() assertions on sensor values.
 */

/**
 * Format a number for assertion – matches app display (de-DE).
 * Matches formatNumber in src/utils/formatters.ts.
 *
 * @example formatForAssertion(23.5, 1) → "23,5"
 * @example formatForAssertion(25.5, 2) → "25,50"
 */
export function formatForAssertion(value: number, decimals = 1): string {
  if (value === null || value === undefined || isNaN(value)) {
    return '-'
  }
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/**
 * Regex that matches displayed value (locale-aware).
 * Use when value might appear with unit or in larger text.
 *
 * @example toDisplayRegex(23.5, 1) → /23[,.]5/ (matches "23,5" or "23.5")
 */
export function toDisplayRegex(value: number, decimals = 1): RegExp {
  const formatted = formatForAssertion(value, decimals)
  // Escape for regex; support both comma and point (defensive)
  const escaped = formatted.replace(/,/g, '[,.]')
  return new RegExp(escaped)
}
