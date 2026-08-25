<script setup lang="ts">
/**
 * Typed create/edit form for a plan_segment (AUT-1235 T5 / AUT-1240).
 * Numeric measures use min/max/step — no free-text numbers.
 * No agronomic defaults: value slot stays empty until the operator enters one.
 */

import { computed, ref, watch } from 'vue'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import BaseInput from '@/shared/design/primitives/BaseInput.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import BaseButton from '@/shared/design/primitives/BaseButton.vue'
import {
  PLAN_MEASURES_BY_DOMAIN,
  type PlanDomain,
  type PlanMeasure,
} from '@/types/logic'
import {
  clampPlanMeasureValue,
  getPlanMeasureInputSpec,
  PLAN_MEASURE_INPUT_SPECS,
} from '@/components/plan-timeline/planMeasureInput'
import { PLAN_MEASURE_LABELS } from '@/components/plan-timeline/planTimelineTracks'
import { parseLocaleNumber } from '@/utils/parseLocaleNumber'

export interface PlanSegmentEditorDraft {
  zoneId: string
  domain: string
  measure: string
  /** null = empty slot (create); never invent a crop target. */
  value: number | null
  fromTs: string
  toTs: string
  /** When set, modal PATCHes value/bounds of an existing segment. */
  segmentId?: string
}

interface Props {
  open: boolean
  draft: PlanSegmentEditorDraft | null
  saving?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  saving: false,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  save: [draft: PlanSegmentEditorDraft]
}>()

const measure = ref<string>('target_ec')
/** Empty string = no value yet (BaseInput does not accept null). */
const value = ref<string | number>('')
const fromLocal = ref('')
const toLocal = ref('')
const formError = ref<string | null>(null)

const measureOptions = computed(() => {
  const domain = (props.draft?.domain ?? 'nutrient_solution') as PlanDomain
  const allowed =
    PLAN_MEASURES_BY_DOMAIN[domain] ?? PLAN_MEASURES_BY_DOMAIN.nutrient_solution
  return allowed.map((m) => ({
    value: m,
    label: PLAN_MEASURE_LABELS[m] ?? m,
  }))
})

const inputSpec = computed(() => getPlanMeasureInputSpec(measure.value))

const title = computed(() =>
  props.draft?.segmentId ? 'Segment bearbeiten' : 'Segment anlegen',
)

function toDatetimeLocal(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromDatetimeLocal(local: string): string {
  return new Date(local).toISOString()
}

watch(
  () => props.draft,
  (d) => {
    formError.value = null
    if (!d) return
    const domain = d.domain as PlanDomain
    const allowed =
      PLAN_MEASURES_BY_DOMAIN[domain] ?? PLAN_MEASURES_BY_DOMAIN.nutrient_solution
    measure.value =
      d.measure in PLAN_MEASURE_INPUT_SPECS &&
      (allowed as readonly string[]).includes(d.measure)
        ? d.measure
        : allowed[0]
    value.value =
      d.value == null || Number.isNaN(Number(d.value)) ? '' : Number(d.value)
    fromLocal.value = toDatetimeLocal(d.fromTs)
    toLocal.value = toDatetimeLocal(d.toTs)
  },
  { immediate: true },
)

watch(measure, () => {
  // Keep typed number if present; do not inject a default target.
  if (value.value === '' || value.value == null) return
  const n = parseLocaleNumber(value.value)
  if (!Number.isFinite(n)) return
  value.value = clampPlanMeasureValue(measure.value, n)
})

function close(): void {
  emit('update:open', false)
}

function submit(): void {
  formError.value = null
  if (!props.draft || !fromLocal.value || !toLocal.value) {
    formError.value = 'Bitte Zeitraum und Wert ausfüllen.'
    return
  }
  const parsedValue = parseLocaleNumber(value.value as string | number)
  if (value.value === '' || value.value == null || Number.isNaN(parsedValue)) {
    formError.value = 'Bitte einen Sollwert eingeben (kein Vorgabe-Wert).'
    return
  }
  const fromTs = fromDatetimeLocal(fromLocal.value)
  const toTs = fromDatetimeLocal(toLocal.value)
  if (Number.isNaN(Date.parse(fromTs)) || Number.isNaN(Date.parse(toTs))) {
    formError.value = 'Ungültiger Zeitpunkt.'
    return
  }
  if (Date.parse(toTs) <= Date.parse(fromTs)) {
    formError.value = 'Ende muss nach dem Beginn liegen.'
    return
  }
  emit('save', {
    ...props.draft,
    measure: measure.value as PlanMeasure,
    value: clampPlanMeasureValue(measure.value, parsedValue),
    fromTs,
    toTs,
  })
}
</script>

<template>
  <BaseModal
    :open="open"
    :title="title"
    max-width="max-w-md"
    @update:open="emit('update:open', $event)"
  >
    <form v-if="draft" class="seg-editor" @submit.prevent="submit">
      <BaseSelect
        v-model="measure"
        :options="measureOptions"
        label="Messgröße"
        :disabled="Boolean(draft.segmentId)"
        aria-label="Messgröße"
      />

      <BaseInput
        v-if="inputSpec"
        v-model="value"
        type="text"
        inputmode="decimal"
        parse-locale-decimal
        :label="inputSpec.unit ? `${inputSpec.label} (${inputSpec.unit})` : inputSpec.label"
        :min="inputSpec.min"
        :max="inputSpec.max"
        :step="inputSpec.step"
        :placeholder="'Wert eingeben'"
        required
        aria-label="Sollwert"
      />

      <label class="seg-editor__label">
        Von
        <input
          v-model="fromLocal"
          type="datetime-local"
          class="seg-editor__dt"
          required
          aria-label="Segmentbeginn"
        />
      </label>

      <label class="seg-editor__label">
        Bis
        <input
          v-model="toLocal"
          type="datetime-local"
          class="seg-editor__dt"
          required
          aria-label="Segmentende"
        />
      </label>

      <p v-if="formError" class="seg-editor__error" role="alert">{{ formError }}</p>

      <div class="seg-editor__actions">
        <BaseButton type="button" variant="ghost" @click="close">Abbrechen</BaseButton>
        <BaseButton type="submit" variant="primary" :loading="saving" :disabled="saving">
          Speichern
        </BaseButton>
      </div>
    </form>
  </BaseModal>
</template>

<style scoped>
.seg-editor {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.seg-editor__label {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.seg-editor__dt {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.seg-editor__error {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-danger);
}

.seg-editor__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
</style>
