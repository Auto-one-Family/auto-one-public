<script setup lang="ts">
/**
 * RuleGroupQuickField
 *
 * AUT-1148 (S3): Bulk quick-field editor for the marked rules of a RuleGroupCard
 * (AUT-1147). Rendered by the caller inside RuleGroupCard's `quick-field` scoped
 * slot, e.g.:
 *
 *   <RuleGroupCard :rules="groupRules" @update:selectedIds="ids => selectedIds = ids">
 *     <template #quick-field="{ selectedIds }">
 *       <RuleGroupQuickField :rules="groupRules" :selected-ids="selectedIds" />
 *     </template>
 *   </RuleGroupCard>
 *
 * `rules` is the SAME array the caller already passed to RuleGroupCard — this
 * satisfies the AUT-1148 DoR ("S2 liefert Mehrfachauswahl-Events mit den
 * markierten Regel-IDs + deren aktuellen Werten"): RuleGroupCard's emitted event
 * carries only IDs, the current values come from this already-available prop.
 *
 * Schnittmengen-Logik: a field is shown ONLY if ALL currently selected rules
 * support it (An/Aus always; Zeiten only if every selected rule has a
 * time-window condition; Schwellwert/Zielwert only if every selected rule has
 * the SAME threshold mechanism — plain sensor-threshold OR hysteresis. A mixed
 * selection of both mechanisms hides the field entirely, matching the server
 * contract: bulk_quick_update_rules() applies one flat payload per rule via
 * LogicService._patch_quick_field_conditions(), which errors per-rule if the
 * requested quick-field doesn't match that rule's actual condition shape.
 *
 * "Gemischt"-Zustand: if the selected rules' current values for a shown field
 * differ, the field starts in a "gemischt" (mixed) state — no value is applied
 * until the user actively edits it (`*Touched` flags). Editing and saving are
 * two separate steps; only touched fields are sent, and there is EXACTLY ONE
 * save call regardless of how many fields were touched (Fix-Philosophie:
 * single save path via AUT-1145's bulk endpoint, no per-field network calls).
 *
 * @see AUT-1148
 * @see El Frontend/src/components/logic/RuleGroupCard.vue (quick-field slot host, AUT-1147)
 * @see El Frontend/src/shared/stores/logic.store.ts (bulkQuickUpdateRules action)
 */

import { ref, computed, watch } from 'vue'
import BaseToggle from '@/shared/design/primitives/BaseToggle.vue'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import { useLogicStore } from '@/shared/stores/logic.store'
import type { RuleBulkQuickUpdateResponse } from '@/api/logic'
import {
  hasTimeWindowCondition,
  hasSimpleThresholdCondition,
  hasHysteresisCondition,
  getSimpleThresholdValue,
  getHysteresisValues,
  getTimeWindowValues,
} from '@/types/logic'
import type { LogicRule } from '@/types/logic'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'

// ── Props / Emits ──────────────────────────────────────────────────────────────

interface Props {
  /** All rules of the group — same array the caller passed to RuleGroupCard. */
  rules: LogicRule[]
  /** Currently marked rule IDs, from RuleGroupCard's quick-field scoped slot. */
  selectedIds: string[]
}

const props = defineProps<Props>()

const emit = defineEmits<{
  /** Emitted after a successful bulk save, with the raw per-rule results. */
  applied: [response: RuleBulkQuickUpdateResponse]
}>()

const logicStore = useLogicStore()
const toast = useToast()

// ── Selection ────────────────────────────────────────────────────────────────

const selectedRules = computed<LogicRule[]>(() =>
  props.rules.filter((r) => props.selectedIds.includes(r.id))
)

// ── Schnittmengen-Logik: which fields apply to EVERY selected rule ──────────

const showTimeField = computed<boolean>(
  () => selectedRules.value.length > 0 && selectedRules.value.every(hasTimeWindowCondition)
)
const showSimpleThresholdField = computed<boolean>(
  () => selectedRules.value.length > 0 && selectedRules.value.every(hasSimpleThresholdCondition)
)
const showHysteresisField = computed<boolean>(
  () => selectedRules.value.length > 0 && selectedRules.value.every(hasHysteresisCondition)
)
/** Hysteresis takes precedence in the rare case a rule exposes both shapes. */
const thresholdMode = computed<'simple' | 'hysteresis'>(() =>
  showHysteresisField.value ? 'hysteresis' : 'simple'
)
const showThresholdField = computed<boolean>(
  () => showHysteresisField.value || showSimpleThresholdField.value
)

// ── Draft state (local edits, not yet saved) ────────────────────────────────

const activeDraft = ref(false)
const activeMixed = ref(false)
const activeTouched = ref(false)

const thresholdDraft = ref(0)
const hysteresisOnDraft = ref(0)
const hysteresisOffDraft = ref(0)
const thresholdMixed = ref(false)
const thresholdTouched = ref(false)

const startHourDraft = ref(0)
const startMinuteDraft = ref(0)
const endHourDraft = ref(23)
const endMinuteDraft = ref(0)
const daysOfWeekDraft = ref<number[]>([])
const timeMixed = ref(false)
const timeTouched = ref(false)

const isSaving = ref(false)

function allEqual<T>(values: T[]): boolean {
  return values.every((v) => v === values[0])
}

function daysOfWeekKey(days: number[]): string {
  return [...days].sort((a, b) => a - b).join(',')
}

/** (Re)compute drafts + mixed-flags from the current selection. Discards unsaved edits. */
function initDrafts(): void {
  activeTouched.value = false
  thresholdTouched.value = false
  timeTouched.value = false

  const selection = selectedRules.value
  if (selection.length === 0) return

  const activeValues = selection.map((r) => r.enabled)
  activeMixed.value = !allEqual(activeValues)
  activeDraft.value = activeValues[0]

  if (showHysteresisField.value) {
    const values = selection.map((r) => getHysteresisValues(r))
    thresholdMixed.value =
      !allEqual(values.map((v) => v.on)) || !allEqual(values.map((v) => v.off))
    hysteresisOnDraft.value = values[0].on ?? 0
    hysteresisOffDraft.value = values[0].off ?? 0
  } else if (showSimpleThresholdField.value) {
    const values = selection.map((r) => getSimpleThresholdValue(r))
    thresholdMixed.value = !allEqual(values)
    thresholdDraft.value = values[0] ?? 0
  }

  if (showTimeField.value) {
    const values = selection.map((r) => getTimeWindowValues(r))
    const keys = values.map(
      (v) => `${v?.startHour}:${v?.startMinute}-${v?.endHour}:${v?.endMinute}|${daysOfWeekKey(v?.daysOfWeek ?? [])}`
    )
    timeMixed.value = !allEqual(keys)
    startHourDraft.value = values[0]?.startHour ?? 0
    startMinuteDraft.value = values[0]?.startMinute ?? 0
    endHourDraft.value = values[0]?.endHour ?? 23
    endMinuteDraft.value = values[0]?.endMinute ?? 0
    daysOfWeekDraft.value = values[0]?.daysOfWeek ?? []
  }
}

watch(() => [props.selectedIds, props.rules] as const, initDrafts, { immediate: true })

// ── Weekday toggle (Mo–So, 0=Monday..6=Sunday — see types/logic.ts TimeCondition) ──
// Pattern: RuleConfigPanel.vue:152,1006-1018 (dayLabels + toggleDay/isDayActive).

const dayLabels = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

function isDayActive(day: number): boolean {
  return daysOfWeekDraft.value.includes(day)
}

function toggleDay(day: number): void {
  const idx = daysOfWeekDraft.value.indexOf(day)
  daysOfWeekDraft.value =
    idx >= 0
      ? daysOfWeekDraft.value.filter((d) => d !== day)
      : [...daysOfWeekDraft.value, day].sort((a, b) => a - b)
  timeTouched.value = true
}

// ── Field change handlers (mark touched, do NOT save) ───────────────────────

function onActiveChange(value: boolean): void {
  activeDraft.value = value
  activeTouched.value = true
}

function onThresholdChange(value: string | number): void {
  thresholdDraft.value = parseLocaleNumber(value)
  thresholdTouched.value = true
}

function onHysteresisOnChange(value: string | number): void {
  hysteresisOnDraft.value = parseLocaleNumber(value)
  thresholdTouched.value = true
}

function onHysteresisOffChange(value: string | number): void {
  hysteresisOffDraft.value = parseLocaleNumber(value)
  thresholdTouched.value = true
}

function onTimeFieldChange(field: 'startHour' | 'startMinute' | 'endHour' | 'endMinute', value: string | number): void {
  const numeric = Number(value)
  if (field === 'startHour') startHourDraft.value = numeric
  else if (field === 'startMinute') startMinuteDraft.value = numeric
  else if (field === 'endHour') endHourDraft.value = numeric
  else endMinuteDraft.value = numeric
  timeTouched.value = true
}

// ── Save (EXACTLY ONE network call via logicStore.bulkQuickUpdateRules) ─────

const hasUnsavedChanges = computed<boolean>(
  () => activeTouched.value || thresholdTouched.value || timeTouched.value
)

async function handleApply(): Promise<void> {
  if (props.selectedIds.length === 0 || isSaving.value || !hasUnsavedChanges.value) return

  isSaving.value = true
  try {
    const response = await logicStore.bulkQuickUpdateRules({
      ids: [...props.selectedIds],
      ...(activeTouched.value ? { active: activeDraft.value } : {}),
      ...(thresholdTouched.value
        ? thresholdMode.value === 'hysteresis'
          ? { hysteresis_on_value: hysteresisOnDraft.value, hysteresis_off_value: hysteresisOffDraft.value }
          : { threshold_value: thresholdDraft.value }
        : {}),
      ...(timeTouched.value
        ? {
            start_hour: startHourDraft.value,
            start_minute: startMinuteDraft.value,
            end_hour: endHourDraft.value,
            end_minute: endMinuteDraft.value,
            days_of_week: [...daysOfWeekDraft.value],
          }
        : {}),
    })

    // Fields just saved are now uniform across the selection — clear their
    // mixed/touched state without a full recompute (props.rules may not yet
    // reflect condition-value changes; that sync is a page-wiring concern, S4).
    // Only clear when EVERY marked rule succeeded — a partial failure (e.g. a
    // rule deleted meanwhile, see server-side test_bulk_rule_not_found_reports_per_rule_error)
    // means at least one rule kept its old value, so the field must stay
    // touched/mixed until the user retries instead of silently claiming a
    // uniform state that was never actually reached.
    const failedCount = response.results.filter((r) => !r.success).length
    if (failedCount === 0) {
      if (activeTouched.value) {
        activeMixed.value = false
        activeTouched.value = false
      }
      if (thresholdTouched.value) {
        thresholdMixed.value = false
        thresholdTouched.value = false
      }
      if (timeTouched.value) {
        timeMixed.value = false
        timeTouched.value = false
      }
    } else {
      toast.error(`Bulk-Update: ${failedCount} von ${response.results.length} Regeln fehlgeschlagen.`)
    }

    emit('applied', response)
  } catch {
    toast.error('Bulk-Update fehlgeschlagen — bitte erneut versuchen.')
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="rule-group-quick-field">
    <p v-if="selectedIds.length === 0" class="rule-group-quick-field__empty">
      Regeln markieren, um sie gemeinsam zu bearbeiten.
    </p>

    <template v-else>
      <!-- An/Aus — always shown, applies to every rule -->
      <div class="rule-group-quick-field__field">
        <div class="rule-group-quick-field__field-row">
          <BaseToggle
            :model-value="activeDraft"
            label="An/Aus"
            @update:model-value="onActiveChange"
          />
          <span v-if="activeMixed && !activeTouched" class="rule-group-quick-field__mixed-hint">
            gemischt
          </span>
        </div>
      </div>

      <!-- Schwellwert/Zielwert — only if ALL selected rules share the same threshold mechanism -->
      <div v-if="showThresholdField" class="rule-group-quick-field__field">
        <template v-if="thresholdMode === 'hysteresis'">
          <div class="rule-group-quick-field__field-row">
            <BaseInput
              :model-value="hysteresisOnDraft"
              type="text"
              inputmode="decimal"
              parse-locale-decimal
              label="Ein-Wert"
              @update:model-value="onHysteresisOnChange"
            />
            <BaseInput
              :model-value="hysteresisOffDraft"
              type="text"
              inputmode="decimal"
              parse-locale-decimal
              label="Aus-Wert"
              @update:model-value="onHysteresisOffChange"
            />
            <span v-if="thresholdMixed && !thresholdTouched" class="rule-group-quick-field__mixed-hint">
              gemischt
            </span>
          </div>
        </template>
        <template v-else>
          <div class="rule-group-quick-field__field-row">
            <BaseInput
              :model-value="thresholdDraft"
              type="text"
              inputmode="decimal"
              parse-locale-decimal
              label="Schwellwert"
              @update:model-value="onThresholdChange"
            />
            <span v-if="thresholdMixed && !thresholdTouched" class="rule-group-quick-field__mixed-hint">
              gemischt
            </span>
          </div>
        </template>
      </div>

      <!-- Zeiten — only if ALL selected rules have a time-window condition -->
      <div v-if="showTimeField" class="rule-group-quick-field__field">
        <div class="rule-group-quick-field__field-row rule-group-quick-field__field-row--times">
          <BaseInput
            :model-value="startHourDraft"
            type="number"
            :min="0"
            :max="23"
            label="Von (Stunde)"
            @update:model-value="(v) => onTimeFieldChange('startHour', v)"
          />
          <BaseInput
            :model-value="startMinuteDraft"
            type="number"
            :min="0"
            :max="59"
            label="Von (Minute)"
            @update:model-value="(v) => onTimeFieldChange('startMinute', v)"
          />
          <BaseInput
            :model-value="endHourDraft"
            type="number"
            :min="0"
            :max="24"
            label="Bis (Stunde)"
            @update:model-value="(v) => onTimeFieldChange('endHour', v)"
          />
          <BaseInput
            :model-value="endMinuteDraft"
            type="number"
            :min="0"
            :max="59"
            label="Bis (Minute)"
            @update:model-value="(v) => onTimeFieldChange('endMinute', v)"
          />
          <span v-if="timeMixed && !timeTouched" class="rule-group-quick-field__mixed-hint">
            gemischt
          </span>
        </div>
        <div class="rule-group-quick-field__days">
          <button
            v-for="(label, idx) in dayLabels"
            :key="idx"
            type="button"
            class="rule-group-quick-field__day"
            :class="{ 'rule-group-quick-field__day--active': isDayActive(idx) }"
            :aria-pressed="isDayActive(idx)"
            :aria-label="label"
            @click="toggleDay(idx)"
          >
            {{ label }}
          </button>
        </div>
      </div>

      <BaseButton
        :disabled="!hasUnsavedChanges"
        :loading="isSaving"
        size="sm"
        @click="handleApply"
      >
        Übernehmen auf {{ selectedIds.length }}&thinsp;{{ selectedIds.length === 1 ? 'Regel' : 'Regeln' }}
      </BaseButton>
    </template>
  </div>
</template>

<style scoped>
.rule-group-quick-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-width: 0;
}

.rule-group-quick-field__empty {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin: 0;
}

.rule-group-quick-field__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  min-width: 0;
}

.rule-group-quick-field__field-row {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
  flex-wrap: wrap;
  min-width: 0;
}

.rule-group-quick-field__field-row--times {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: end;
}

.rule-group-quick-field__field-row > :deep(.w-full) {
  min-width: 0;
  flex: 1 1 8rem;
}

.rule-group-quick-field__mixed-hint {
  font-size: var(--text-xxs);
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border-radius: var(--radius-sm);
  padding: 2px 6px;
  white-space: nowrap;
  align-self: center;
}

.rule-group-quick-field__days {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.rule-group-quick-field__day {
  min-width: 44px;
  min-height: 44px;
  padding: 0 var(--space-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast), border-color var(--transition-fast);
}

.rule-group-quick-field__day:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 2px;
}

.rule-group-quick-field__day--active {
  background: color-mix(in srgb, var(--color-info) 20%, transparent);
  border-color: var(--color-info);
  color: var(--color-text-primary);
}
</style>
