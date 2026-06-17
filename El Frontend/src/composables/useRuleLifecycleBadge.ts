/**
 * useRuleLifecycleBadge Composable
 *
 * Single source of truth for mapping a RuleIntentLifecycle phase + enabled state
 * onto a human-readable label, a BaseBadge variant and a pulsing flag.
 *
 * Replaces duplicated statusInfo computed properties in RuleCard.vue and
 * RuleCardCompact.vue.
 *
 * @see src/components/rules/RuleCard.vue
 * @see src/components/logic/RuleCardCompact.vue
 * @see src/shared/design/primitives/BaseBadge.vue
 */

import { computed, type ComputedRef, type MaybeRefOrGetter, toValue } from 'vue'
import type { RuleIntentLifecycle } from '@/types/logic'

/** Badge variant values accepted by BaseBadge */
export type RuleLifecycleBadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'gray'

export interface RuleLifecycleBadge {
  /** Human-readable label for the current lifecycle phase */
  label: ComputedRef<string>
  /** BaseBadge variant corresponding to the lifecycle phase */
  variant: ComputedRef<RuleLifecycleBadgeVariant>
  /** Whether the badge should pulse (active pending phases) */
  isPulsing: ComputedRef<boolean>
}

/**
 * Maps a RuleIntentLifecycle phase onto display properties for BaseBadge.
 *
 * Priority order:
 * 1. Lifecycle terminal states (conflict, integration_issue, failed, success)
 * 2. Lifecycle pending states (accepted, pending_activation, pending_execution)
 * 3. Rule enabled/disabled fallback
 *
 * @param lifecycle - Reactive lifecycle object or getter, may be null/undefined
 * @param enabled   - Reactive boolean or getter indicating if the rule is active
 */
export function useRuleLifecycleBadge(
  lifecycle: MaybeRefOrGetter<RuleIntentLifecycle | null | undefined>,
  enabled: MaybeRefOrGetter<boolean>,
): RuleLifecycleBadge {
  const label = computed<string>(() => {
    const lc = toValue(lifecycle)
    if (lc?.state === 'terminal_conflict') return 'Konflikt'
    if (lc?.state === 'terminal_integration_issue') return 'Integration'
    if (lc?.state === 'terminal_failed') return 'Fehler'
    if (lc?.state === 'terminal_success') return 'Erfolg'
    if (lc?.state === 'accepted') return 'Angenommen'
    if (lc?.state === 'pending_activation') return 'Aktivierung...'
    if (lc?.state === 'pending_execution') return 'Ausfuehrung...'
    return toValue(enabled) ? 'Aktiv' : 'Deaktiviert'
  })

  const variant = computed<RuleLifecycleBadgeVariant>(() => {
    const lc = toValue(lifecycle)
    if (lc?.state === 'terminal_conflict') return 'warning'
    if (lc?.state === 'terminal_integration_issue') return 'danger'
    if (lc?.state === 'terminal_failed') return 'danger'
    if (lc?.state === 'terminal_success') return 'success'
    if (lc?.state === 'accepted') return 'warning'
    if (lc?.state === 'pending_activation') return 'warning'
    if (lc?.state === 'pending_execution') return 'warning'
    return toValue(enabled) ? 'success' : 'gray'
  })

  const isPulsing = computed<boolean>(() => {
    const lc = toValue(lifecycle)
    return (
      lc?.state === 'pending_activation' ||
      lc?.state === 'pending_execution' ||
      lc?.state === 'accepted'
    )
  })

  return { label, variant, isPulsing }
}
