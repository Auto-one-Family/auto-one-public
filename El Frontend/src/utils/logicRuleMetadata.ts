/**
 * AUT-1304 / AUT-1134 (B6): rule_metadata.paired_rule_id helpers for LogicView.
 * Keeps get/set semantics in one place (clearing removes the key, dose_config preserved).
 */

export function getPairedRuleIdFromMetadata(metadata: Record<string, unknown>): string {
  return (metadata.paired_rule_id as string | undefined) ?? ''
}

/** Returns a shallow copy; empty pairedRuleId removes paired_rule_id from metadata. */
export function applyPairedRuleIdToMetadata(
  metadata: Record<string, unknown>,
  pairedRuleId: string,
): Record<string, unknown> {
  const next = { ...metadata }
  if (pairedRuleId) {
    next.paired_rule_id = pairedRuleId
  } else {
    delete next.paired_rule_id
  }
  return next
}
