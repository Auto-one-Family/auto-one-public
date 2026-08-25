/**
 * AUT-1413 SR-4: Shared pump concentration status copy for Kalibrier-Tab + Salzrechner.
 * Display/traceability only — no concentration calculation.
 */

export type StockConcentrationKind = 'pending_remeasure' | 'measured'

export interface StockConcentrationStatusInput {
  concentration: number | null | undefined
  /** Display label from stock_mix_recipes (already resolved). */
  recipeLabel?: string | null
  /** ISO timestamp from actuator_configs.stock_prepared_at */
  stockPreparedAt?: string | null
}

export interface StockConcentrationStatus {
  kind: StockConcentrationKind
  /** Full sentence for Kalibrierungs-Tab */
  label: string
  /** Short mirror text for Salzrechner */
  shortLabel: string
}

function formatPreparedDate(iso: string | null | undefined): string | null {
  if (!iso) return null
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return null
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  return `${day}.${month}.`
}

/**
 * Derive operator-facing status from pump concentration + optional stock identity.
 * Never invents recipe/date when identity fields are empty.
 */
export function formatStockConcentrationStatus(
  input: StockConcentrationStatusInput,
): StockConcentrationStatus {
  const conc = input.concentration
  const hasConc = conc != null && Number.isFinite(conc) && conc > 0
  const recipe = (input.recipeLabel ?? '').trim() || null
  const date = formatPreparedDate(input.stockPreparedAt)

  if (!hasConc) {
    if (recipe && date) {
      return {
        kind: 'pending_remeasure',
        label: `Konzentration: wird bei nächster Dosierung neu gemessen (angesetzt: ${recipe}, ${date})`,
        shortLabel: `wird neu gemessen · ${recipe} · ${date}`,
      }
    }
    if (recipe) {
      return {
        kind: 'pending_remeasure',
        label: `Konzentration: wird bei nächster Dosierung neu gemessen (angesetzt: ${recipe})`,
        shortLabel: `wird neu gemessen · ${recipe}`,
      }
    }
    return {
      kind: 'pending_remeasure',
      label: 'Konzentration: wird bei nächster Dosierung neu gemessen',
      shortLabel: 'wird neu gemessen',
    }
  }

  const parts = ['gemessen']
  if (recipe) parts.push(recipe)
  if (date) parts.push(date)
  const joined = parts.join(' · ')
  return {
    kind: 'measured',
    label: joined,
    shortLabel: joined,
  }
}
