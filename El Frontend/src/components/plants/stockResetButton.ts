/**
 * AUT-1414 SR-3: Visibility + confirm copy for „Stock neu angesetzt".
 * Pure helpers — no API side effects (call site owns resetStockPrepared).
 */

import type { DoseRole } from '@/types'
import { formatDoseRoleLabel } from '@/utils/doseRoleDisplay'

const RESET_ROLES: ReadonlySet<string> = new Set(['part_a', 'part_b'])

export interface StockResetVisibilityInput {
  doseRole: DoseRole | string | null | undefined
  hasPump: boolean
  recipeId: string | null | undefined
}

/** Button only for Stock A/B with a resolved pump + recipe. */
export function canShowStockResetButton(input: StockResetVisibilityInput): boolean {
  const role = (input.doseRole ?? '').trim().toLowerCase()
  if (!RESET_ROLES.has(role)) return false
  if (!input.hasPump) return false
  const recipeId = (input.recipeId ?? '').trim()
  return recipeId.length > 0
}

export function buildStockResetConfirmMessage(input: {
  doseRole: DoseRole | string | null | undefined
  recipeLabel: string | null | undefined
}): { title: string; message: string } {
  const roleLabel = formatDoseRoleLabel(input.doseRole) ?? 'Stock'
  const recipe = (input.recipeLabel ?? '').trim() || 'dem gewählten Rezept'
  return {
    title: `${roleLabel} neu angesetzt?`,
    message:
      `Du hast ${roleLabel} frisch nach Rezept „${recipe}“ angesetzt und angeschlossen? ` +
      `Die gespeicherte Konzentration wird zurückgesetzt und beim nächsten Dosierlauf ` +
      `automatisch neu gemessen.`,
  }
}
