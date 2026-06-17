<script setup lang="ts">
/**
 * RuleCardCompact
 *
 * Compact card for monitor rule overview:
 * - monitor: click navigates to /logic/:ruleId; quickActions shows Toggle + Edit actions.
 * - select: click emits 'select'; shows delete button, executionCount, isSelected state.
 */
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Clock, AlertCircle, ExternalLink, Pencil, Power, ShieldAlert, Trash2, Zap } from 'lucide-vue-next'
import { formatRelativeTime } from '@/utils/formatters'
import type { StatusLevel } from '@/utils/formatters'
import { useUiStore } from '@/shared/stores/ui.store'
import { useLogicStore } from '@/shared/stores/logic.store'
import { useToast } from '@/composables/useToast'
import { useRuleLifecycleBadge } from '@/composables/useRuleLifecycleBadge'
import { useRuleReadableText } from '@/composables/useRuleReadableText'
import BaseBadge from '@/shared/design/primitives/BaseBadge.vue'
import StatusBadge from '@/components/base/StatusBadge.vue'
import type { LogicRule, RuleIntentLifecycle, SensorCondition } from '@/types/logic'

interface Props {
  rule: LogicRule
  /** Whether this rule is currently executing (glow effect) */
  isActive?: boolean
  /** Zone names for L1 Monitor (answers "Where?"). L2 omits — zone is implicit. */
  zoneNames?: string[]
  lifecycle?: RuleIntentLifecycle | null
  quickActions?: boolean
  historyLimit?: number
  /**
   * 'monitor' (default): click navigates to /logic/:ruleId; quickActions optional.
   * 'select': click emits 'select'; shows delete button, executionCount, isSelected state.
   */
  mode?: 'monitor' | 'select'
  /** select-mode only: whether this rule is currently selected in the editor */
  isSelected?: boolean
  /** select-mode only: number of rule executions in the last 24h (warning threshold depends on rule.cooldown_seconds) */
  executionCount?: number
}

const props = withDefaults(defineProps<Props>(), {
  isActive: false,
  quickActions: false,
  historyLimit: 6,
  mode: 'monitor',
  isSelected: false,
  executionCount: 0,
})

const emit = defineEmits<{
  /** select-mode: emitted when the card is clicked */
  select: [ruleId: string]
  /** select-mode: emitted when the delete button is clicked */
  delete: [ruleId: string]
}>()

const router = useRouter()
const uiStore = useUiStore()
const logicStore = useLogicStore()
const toast = useToast()
const isToggling = ref(false)

const { label: lifecycleLabel, variant: lifecycleVariant, isPulsing: lifecycleIsPulsing } =
  useRuleLifecycleBadge(
    () => props.lifecycle ?? null,
    () => props.rule.enabled,
  )

const hasError = computed(
  () =>
    props.lifecycle?.state === 'terminal_failed' ||
    props.lifecycle?.state === 'terminal_integration_issue' ||
    props.rule.last_execution_success === false
)

const isDegraded = computed(() => Boolean(props.rule.degraded_since))

/** Dynamic threshold: no cooldown → warn above 200; short cooldown (1-60s) → above 500; long cooldown → above 100. */
const execWarnThreshold = computed(() => {
  const cd = props.rule.cooldown_seconds ?? 0
  if (cd === 0) return 200
  if (cd <= 60) return 500
  return 100
})

const EXEC_WARN_TOOLTIP =
  'Diese Regel wurde heute sehr oft ausgeführt. Das kann auf eine zu enge Schwelle hinweisen. ' +
  'Tipp: Aktivierungs- und Deaktivierungs-Schwelle um 2–5 Einheiten auseinanderziehen.'

/** AUT-250: Map rule state to canonical 4-level StatusLevel for StatusBadge. */
const ruleStatusLevel = computed<StatusLevel>(() => {
  if (hasError.value) return 'alarm'
  if (!props.rule.enabled) return 'offline'
  if (props.mode === 'select' && logicStore.isRuleTriggered(props.rule.id)) return 'warning'
  return 'ok'
})

/** Dynamic aria-label including status for screen readers (ARIA-live announces changes). */
const statusAriaLabel = computed(() => {
  const base = `Regel ${props.rule.name} öffnen`
  if (hasError.value) return `${base}. Status: Fehler.`
  if (props.isActive) return `${base}. Wird ausgeführt.`
  return `${base}. ${lifecycleLabel.value}.`
})

const ruleText = useRuleReadableText(() => props.rule)

// AUT-668: Inline threshold edit — only for monitor mode + single sensor condition + non-between operator
const thresholdInputRef = ref<HTMLInputElement | null>(null)
const isEditingThreshold = ref(false)
const editThresholdValue = ref(0)
const isSavingThreshold = ref(false)
const thresholdSaveError = ref(false)
let saveErrorTimer: ReturnType<typeof setTimeout> | null = null

const canInlineEdit = computed(() => {
  if (props.mode !== 'monitor') return false
  if (props.rule.conditions.length !== 1) return false
  const c = props.rule.conditions[0]
  if (c.type !== 'sensor' && c.type !== 'sensor_threshold') return false
  return (c as SensorCondition).operator !== 'between'
})

const thresholdCurrentValue = computed(() =>
  canInlineEdit.value ? (props.rule.conditions[0] as SensorCondition).value : null
)

async function startThresholdEdit(): Promise<void> {
  const c = props.rule.conditions[0] as SensorCondition
  editThresholdValue.value = c.value
  isEditingThreshold.value = true
  await nextTick()
  thresholdInputRef.value?.focus()
  thresholdInputRef.value?.select()
}

function cancelThresholdEdit(): void {
  isEditingThreshold.value = false
  thresholdSaveError.value = false
  if (saveErrorTimer) {
    clearTimeout(saveErrorTimer)
    saveErrorTimer = null
  }
}

async function saveThreshold(): Promise<void> {
  if (!isEditingThreshold.value || isSavingThreshold.value) return
  const c = props.rule.conditions[0] as SensorCondition
  const newValue = editThresholdValue.value
  if (isNaN(newValue) || newValue === c.value) {
    cancelThresholdEdit()
    return
  }
  isSavingThreshold.value = true
  thresholdSaveError.value = false
  try {
    const updatedConditions = props.rule.conditions.map((cond, i) =>
      i === 0 ? { ...cond, value: newValue } : cond
    )
    await logicStore.updateRule(props.rule.id, { conditions: updatedConditions })
    isEditingThreshold.value = false
  } catch {
    thresholdSaveError.value = true
    if (saveErrorTimer) clearTimeout(saveErrorTimer)
    saveErrorTimer = setTimeout(() => {
      thresholdSaveError.value = false
      isEditingThreshold.value = false
      saveErrorTimer = null
    }, 3000)
  } finally {
    isSavingThreshold.value = false
  }
}

const lastTriggeredText = computed(() =>
  formatRelativeTime(props.rule.last_triggered)
)

/** Zone badge text: "Zone1, Zone2" or "Zone1 +2" when >2 zones. Fallback "—" when no zones (5s rule: "Wo?" always answerable). */
const zoneBadgeText = computed(() => {
  if (!props.zoneNames || props.zoneNames.length === 0) return '—'
  if (props.zoneNames.length <= 2) return props.zoneNames.join(', ')
  return `${props.zoneNames[0]} +${props.zoneNames.length - 1}`
})

function navigateToRule() {
  router.push({ name: 'logic-rule', params: { ruleId: props.rule.id } })
}

function handleMainClick(): void {
  if (props.mode === 'select') {
    emit('select', props.rule.id)
    return
  }
  navigateToRule()
}

async function toggleRuleSafely(): Promise<void> {
  if (isToggling.value) return

  const enabling = !props.rule.enabled
  const confirmed = await uiStore.confirm({
    title: enabling ? 'Regel aktivieren?' : 'Regel deaktivieren?',
    message: enabling
      ? `Regel "${props.rule.name}" wird sofort wieder scharf geschaltet. Fortfahren?`
      : `Regel "${props.rule.name}" wird deaktiviert und löst nicht mehr aus. Fortfahren?`,
    variant: enabling ? 'warning' : 'info',
    confirmText: enabling ? 'Sicher aktivieren' : 'Deaktivieren',
    cancelText: 'Abbrechen',
  })

  if (!confirmed) return

  isToggling.value = true
  try {
    const enabled = await logicStore.toggleRule(props.rule.id)
    toast.success(enabled ? 'Regel aktiviert' : 'Regel deaktiviert')
  } catch {
    toast.error(logicStore.error ?? 'Regel konnte nicht umgeschaltet werden')
  } finally {
    isToggling.value = false
  }
}
</script>

<template>
  <article
    class="rule-card-compact"
    :class="{
      'rule-card-compact--active': isActive,
      'rule-card-compact--error': hasError,
      'rule-card-compact--selected': mode === 'select' && isSelected,
      'rule-card-compact--disabled': mode === 'select' && !rule.enabled,
    }"
  >
    <button
      type="button"
      class="rule-card-compact__summary"
      :aria-label="statusAriaLabel"
      aria-live="polite"
      @click="handleMainClick"
    >
      <div class="rule-card-compact__header">
        <StatusBadge
          :level="ruleStatusLevel"
          :label-override="lifecycleLabel"
          compact
        />
        <span v-if="rule.is_critical" class="rule-card-compact__critical-badge" title="Kritische Regel">
          <ShieldAlert class="rule-card-compact__critical-icon" />
          KRIT
        </span>
        <span class="rule-card-compact__name">{{ rule.name }}</span>
        <span v-if="isDegraded" class="rule-card-compact__degraded-pill" :title="rule.degraded_reason || 'Degradiert'">
          Degradiert
        </span>
        <BaseBadge
          class="rule-card-compact__lifecycle-badge"
          :variant="lifecycleVariant"
          size="xs"
          :pulse="lifecycleIsPulsing"
        >
          {{ lifecycleLabel }}
        </BaseBadge>
        <AlertCircle
          v-if="hasError"
          class="rule-card-compact__error-icon"
          :title="'Letzte Ausführung fehlgeschlagen'"
        />
        <button
          v-if="mode === 'select'"
          class="rule-card-compact__delete"
          title="Regel löschen"
          aria-label="Regel löschen"
          @click.stop="emit('delete', rule.id)"
        >
          <Trash2 class="rule-card-compact__delete-icon" />
        </button>
      </div>
      <div class="rule-card-compact__footer">
        <span v-if="zoneNames !== undefined" class="rule-card-compact__zone-badge">
          {{ zoneBadgeText }}
        </span>
        <span v-if="ruleText" class="rule-card-compact__badge">
          {{ ruleText }}
        </span>
        <button
          v-if="canInlineEdit && !isEditingThreshold"
          type="button"
          class="rule-card-compact__edit-threshold-btn"
          :title="`Schwellwert ${thresholdCurrentValue} direkt anpassen`"
          aria-label="Schwellwert inline anpassen"
          @click.stop="startThresholdEdit"
        >
          <Pencil class="rule-card-compact__edit-threshold-icon" />
        </button>
        <span class="rule-card-compact__time">
          <Clock class="rule-card-compact__time-icon" />
          {{ lastTriggeredText }}
        </span>
      </div>
    </button>

    <div
      v-if="mode === 'select' && executionCount > execWarnThreshold"
      class="rule-card-compact__exec-secondary"
    >
      <button
        type="button"
        class="rule-card-compact__exec-warn-btn"
        :title="EXEC_WARN_TOOLTIP"
        :aria-label="`Regel-Einstellungen öffnen — ${executionCount}x in den letzten 24h ausgelöst`"
        @click="navigateToRule"
      >
        <Zap class="rule-card-compact__time-icon" />
        {{ executionCount }}x/24h — Einstellungen öffnen
        <ExternalLink class="rule-card-compact__time-icon" />
      </button>
    </div>

    <div v-if="isEditingThreshold" class="rule-card-compact__threshold-edit-row">
      <input
        ref="thresholdInputRef"
        v-model.number="editThresholdValue"
        type="number"
        step="any"
        class="rule-card-compact__threshold-input"
        :disabled="isSavingThreshold"
        @keydown.enter.prevent="saveThreshold"
        @keydown.escape="cancelThresholdEdit"
        @blur="saveThreshold"
      />
      <span v-if="thresholdSaveError" class="rule-card-compact__threshold-error">Speichern fehlgeschlagen</span>
      <button
        v-else
        type="button"
        class="rule-card-compact__threshold-cancel"
        :disabled="isSavingThreshold"
        @mousedown.prevent
        @click="cancelThresholdEdit"
      >✕</button>
    </div>

    <div v-if="mode === 'monitor' && quickActions" class="rule-card-compact__quick-panel">
      <div class="rule-card-compact__quick-actions">
        <button
          type="button"
          class="rule-card-compact__action-btn rule-card-compact__action-btn--toggle"
          :disabled="isToggling"
          @click="toggleRuleSafely"
        >
          <Power class="rule-card-compact__action-icon" />
          {{ rule.enabled ? 'Sicher deaktivieren' : 'Sicher aktivieren' }}
        </button>
        <button type="button" class="rule-card-compact__action-btn" @click="navigateToRule">
          <ExternalLink class="rule-card-compact__action-icon" />
          Vollständig bearbeiten
        </button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.rule-card-compact {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  transition: all var(--transition-fast);
  width: 100%;
}

.rule-card-compact__summary {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
  width: 100%;
}

.rule-card-compact:hover {
  border-color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
}

.rule-card-compact__summary:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.rule-card-compact__quick-panel {
  border-top: 1px dashed var(--glass-border);
  padding: var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.rule-card-compact__quick-actions {
  display: grid;
  gap: var(--space-2);
}

.rule-card-compact__action-btn {
  min-height: 44px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: var(--text-xs);
  cursor: pointer;
}

.rule-card-compact__action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rule-card-compact__action-btn--toggle {
  border-color: color-mix(in srgb, var(--color-warning) 35%, var(--glass-border));
}

.rule-card-compact__action-icon {
  width: 12px;
  height: 12px;
}

.rule-card-compact--active {
  animation: rule-compact-flash 1.5s ease-out;
}

@keyframes rule-compact-flash {
  0% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4);
    border-color: var(--color-success);
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
    border-color: var(--glass-border);
  }
}

.rule-card-compact--error {
  border-color: rgba(248, 113, 113, 0.4);
  border-left: 3px solid var(--color-error);
}

.rule-card-compact--error:hover {
  border-color: rgba(248, 113, 113, 0.6);
  border-left-color: var(--color-error);
}

.rule-card-compact__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.rule-card-compact__name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Lifecycle status badge — rendered by BaseBadge, needs flex alignment */
.rule-card-compact__lifecycle-badge {
  flex-shrink: 0;
}

.rule-card-compact__error-icon {
  width: 12px;
  height: 12px;
  color: var(--color-error);
  flex-shrink: 0;
}

.rule-card-compact__footer {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.rule-card-compact__zone-badge {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
  padding: 2px 8px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-card-compact__badge {
  font-size: var(--text-xxs);
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rule-card-compact__time {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.rule-card-compact__time-icon {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
}

.rule-card-compact__critical-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: var(--text-xxs);
  font-weight: 700;
  letter-spacing: 0.04em;
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.12);
  border: 1px solid rgba(251, 191, 36, 0.25);
  border-radius: var(--radius-sm);
  padding: 1px 5px;
  flex-shrink: 0;
}

.rule-card-compact__critical-icon {
  width: 10px;
  height: 10px;
}

.rule-card-compact__degraded-pill {
  font-size: var(--text-xxs);
  font-weight: 700;
  letter-spacing: 0.03em;
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.12);
  border: 1px solid rgba(248, 113, 113, 0.3);
  border-radius: var(--radius-full);
  padding: 1px 7px;
  flex-shrink: 0;
  animation: degraded-compact-pulse 3s ease-in-out infinite;
}

@keyframes degraded-compact-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* select-mode additions */
.rule-card-compact--selected {
  border-color: var(--color-accent);
  background: rgba(59, 130, 246, 0.05);
}

.rule-card-compact--disabled {
  opacity: 0.6;
}

.rule-card-compact__delete {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  opacity: 0;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.rule-card-compact:hover .rule-card-compact__delete {
  opacity: 1;
}

.rule-card-compact__delete:hover {
  background: rgba(239, 68, 68, 0.1);
}

.rule-card-compact__delete-icon {
  width: 12px;
  height: 12px;
  color: var(--color-error);
}

.rule-card-compact__exec-secondary {
  border-top: 1px solid var(--glass-border);
  padding: var(--space-2) var(--space-3);
}

.rule-card-compact__exec-warn-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 44px;
  padding: 0 var(--space-1);
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  color: var(--color-warning);
  background: transparent;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.rule-card-compact__exec-warn-btn:hover {
  color: var(--color-text-primary);
}

@media (hover: none) {
  .rule-card-compact__exec-warn-btn {
    text-decoration: underline;
  }
}

/* AUT-668: Inline threshold edit */
.rule-card-compact__edit-threshold-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  opacity: 0;
  transition: opacity var(--transition-fast);
  flex-shrink: 0;
  color: var(--color-text-muted);
}

.rule-card-compact:hover .rule-card-compact__edit-threshold-btn {
  opacity: 1;
}

.rule-card-compact__edit-threshold-btn:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
}

.rule-card-compact__edit-threshold-icon {
  width: 10px;
  height: 10px;
}

.rule-card-compact__threshold-edit-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-top: 1px solid var(--glass-border);
}

.rule-card-compact__threshold-input {
  width: 6em;
  height: 28px;
  padding: 2px 6px;
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--color-iridescent-2);
  border-radius: var(--radius-sm);
  outline: none;
  appearance: textfield;
}

.rule-card-compact__threshold-input:focus {
  border-color: var(--color-iridescent-2);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--color-iridescent-2) 25%, transparent);
}

.rule-card-compact__threshold-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.rule-card-compact__threshold-error {
  font-size: var(--text-xxs);
  color: var(--color-error);
  flex: 1;
}

.rule-card-compact__threshold-cancel {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  font-size: var(--text-xs);
  flex-shrink: 0;
  margin-left: auto;
}

.rule-card-compact__threshold-cancel:hover {
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
}

.rule-card-compact__threshold-cancel:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
