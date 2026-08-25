/**
 * Ledger EC unit adapter (AUT-1350 / AUT-1358) — FE mirror of
 * `El Servador/.../services/ledger_ec_units.py`.
 *
 * Ledger API/DB fields (`ec_*_ms_cm`, batch `ec_measured_after`) store **mS/cm**.
 * Operational FE (Plan / Ist-Soll / Batch-Modal input) uses **µS/cm** SSOT.
 *
 * ALL ×1000 / ÷1000 at this boundary MUST go through these helpers.
 */

/** Exact factor: 1 mS/cm = 1000 µS/cm (same as server US_PER_MS). */
export const US_PER_MS = 1000

/** Read boundary: Ledger mS/cm → operational µS/cm. */
export function ledgerMsCmToUsCm(msCm: number): number {
  return Number(msCm) * US_PER_MS
}

/**
 * Write boundary: operational µS/cm → Ledger mS/cm.
 * Mirrors server `us_cm_to_ledger_ms_cm` / `TankService.to_ledger_ec_ms_cm`.
 */
export function usCmToLedgerMsCm(usCm: number): number {
  return Number(usCm) / US_PER_MS
}

/** Nullable write helper before POST …/batches. */
export function optionalUsCmToLedgerMsCm(usCm: number | null | undefined): number | null {
  if (usCm == null) return null
  return usCmToLedgerMsCm(usCm)
}
