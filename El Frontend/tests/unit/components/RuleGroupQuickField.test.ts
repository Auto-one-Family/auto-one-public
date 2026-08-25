/**
 * Tests for RuleGroupQuickField component (AUT-1148, S3).
 *
 * Verifies the Schnittmengen-Logik (which fields are shown for a given
 * selection), the "gemischt" state (shown Ist-Werte differ), and that saving
 * touched fields triggers EXACTLY ONE call to logicStore.bulkQuickUpdateRules
 * regardless of how many fields were touched (AUT-1148 Fix-Philosophie: single
 * save path, no per-field network calls).
 *
 * Test conventions: mount() + expect() assertions, global.stubs for shared
 * design primitives. No .toMatchSnapshot() — consistent with RuleGroupCard.test.ts.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleGroupQuickField from '@/components/logic/RuleGroupQuickField.vue'
import type { LogicRule } from '@/types/logic'

const bulkQuickUpdateRules = vi.fn().mockResolvedValue({ success: true, results: [] })

vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    bulkQuickUpdateRules,
  }),
}))

const toastError = vi.fn()
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    error: toastError,
    success: vi.fn(),
    warning: vi.fn(),
  }),
}))

// ── Shared mock rules ─────────────────────────────────────────────────────────

function makeRule(overrides: Partial<LogicRule> & { id: string }): LogicRule {
  return {
    id: overrides.id,
    name: overrides.name ?? 'Test-Regel',
    description: overrides.description,
    enabled: overrides.enabled ?? true,
    conditions: overrides.conditions ?? [],
    logic_operator: overrides.logic_operator ?? 'AND',
    actions: overrides.actions ?? [
      { type: 'actuator' as const, esp_id: 'esp-1', gpio: 5, command: 'ON' as const },
    ],
    priority: overrides.priority ?? 5,
    created_at: overrides.created_at ?? '2026-01-01T00:00:00Z',
    updated_at: overrides.updated_at ?? '2026-01-01T00:00:00Z',
    rule_group: overrides.rule_group,
  }
}

const hysteresisRule1 = makeRule({
  id: 'h1',
  enabled: true,
  conditions: [{ type: 'hysteresis', esp_id: 'esp-1', gpio: 4, activate_above: 28, deactivate_below: 25 }],
})
const hysteresisRule2 = makeRule({
  id: 'h2',
  enabled: true,
  conditions: [{ type: 'hysteresis', esp_id: 'esp-1', gpio: 4, activate_above: 28, deactivate_below: 25 }],
})

const timeRule = makeRule({
  id: 't1',
  enabled: true,
  conditions: [{ type: 'time_window', start_hour: 22, start_minute: 0, end_hour: 6, end_minute: 0, days_of_week: [0, 1, 2, 3, 4] }],
})

const timeRuleA = makeRule({
  id: 'ta',
  enabled: true,
  conditions: [{ type: 'time_window', start_hour: 22, start_minute: 0, end_hour: 6, end_minute: 0, days_of_week: [0, 1, 2, 3, 4] }],
})
const timeRuleB = makeRule({
  id: 'tb',
  enabled: true,
  conditions: [{ type: 'time_window', start_hour: 8, start_minute: 30, end_hour: 18, end_minute: 0, days_of_week: [0, 1, 2, 3, 4] }],
})

const thresholdRuleA = makeRule({
  id: 's1',
  enabled: true,
  conditions: [{ type: 'sensor', esp_id: 'esp-2', gpio: 3, sensor_type: 'ph', operator: '<', value: 5.5 }],
})
const thresholdRuleB = makeRule({
  id: 's2',
  enabled: false,
  conditions: [{ type: 'sensor', esp_id: 'esp-2', gpio: 7, sensor_type: 'ec', operator: '>', value: 1800 }],
})

// ── Global stubs ──────────────────────────────────────────────────────────────

const globalStubs = {
  BaseToggle: {
    template:
      '<input type="checkbox" class="base-toggle-stub" :checked="modelValue" @change="$emit(\'update:modelValue\', ($event.target as HTMLInputElement).checked)" />',
    props: ['modelValue', 'label'],
    emits: ['update:modelValue'],
  },
  BaseInput: {
    template:
      '<input class="base-input-stub" :data-label="label" :value="modelValue" @input="$emit(\'update:modelValue\', ($event.target as HTMLInputElement).value)" />',
    props: ['modelValue', 'type', 'label', 'min', 'max'],
    emits: ['update:modelValue'],
  },
  BaseButton: {
    template: '<button class="base-button-stub" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['disabled', 'loading', 'size'],
    emits: ['click'],
  },
}

function mountField(rules: LogicRule[], selectedIds: string[]) {
  return mount(RuleGroupQuickField, {
    props: { rules, selectedIds },
    global: { stubs: globalStubs },
  })
}

// =============================================================================
// Tests
// =============================================================================

describe('RuleGroupQuickField', () => {
  // ── Test 1: empty selection ───────────────────────────────────────────────
  it('shows empty hint and no fields when nothing is selected', () => {
    const wrapper = mountField([hysteresisRule1, hysteresisRule2], [])

    expect(wrapper.find('.rule-group-quick-field__empty').exists()).toBe(true)
    expect(wrapper.find('.base-toggle-stub').exists()).toBe(false)
    expect(wrapper.find('.base-button-stub').exists()).toBe(false)
  })

  // ── Test 2: same type (hysteresis) → threshold field visible, correct mode ──
  it('shows the hysteresis on/off fields when all selected rules share hysteresis conditions', () => {
    const wrapper = mountField([hysteresisRule1, hysteresisRule2], ['h1', 'h2'])

    const inputs = wrapper.findAll('.base-input-stub')
    // Exactly Ein-Wert + Aus-Wert — no Zeiten inputs (neither rule has a time-window condition)
    expect(inputs).toHaveLength(2)
    expect(inputs.map((i) => i.attributes('data-label')).sort()).toEqual(['Aus-Wert', 'Ein-Wert'])
    // Not mixed — both rules have identical hysteresis values
    expect(wrapper.find('.rule-group-quick-field__mixed-hint').exists()).toBe(false)
  })

  // ── Test 3: mixed type (zeitplan + schwellwert) → only An/Aus visible ──────
  it('shows only An/Aus when selection mixes a time-window rule and a threshold rule', () => {
    const wrapper = mountField([timeRule, thresholdRuleA], ['t1', 's1'])

    // An/Aus always present
    expect(wrapper.find('.base-toggle-stub').exists()).toBe(true)
    // Neither Zeiten nor Schwellwert apply to BOTH rules → no other field renders at all
    expect(wrapper.findAll('.base-input-stub')).toHaveLength(0)
  })

  // ── Test 4: mixed Ist-Werte (same type, different values) → "gemischt" ────
  it('shows a "gemischt" hint when selected rules of the same type have different values', () => {
    const wrapper = mountField([thresholdRuleA, thresholdRuleB], ['s1', 's2'])

    // enabled differs (true vs false) AND threshold value differs (5.5 vs 1800) → exactly 2 hints
    const mixedHints = wrapper.findAll('.rule-group-quick-field__mixed-hint')
    expect(mixedHints).toHaveLength(2)
  })

  // ── Test 5: exactly one network call regardless of how many fields touched ─
  it('calls bulkQuickUpdateRules exactly once when multiple fields are touched and saved', async () => {
    bulkQuickUpdateRules.mockClear()
    const wrapper = mountField([hysteresisRule1, hysteresisRule2], ['h1', 'h2'])

    // Touch An/Aus
    await wrapper.find('.base-toggle-stub').setValue(false)
    // Touch both hysteresis inputs
    const inputs = wrapper.findAll('.base-input-stub')
    const onInput = inputs.find((i) => i.attributes('data-label') === 'Ein-Wert')!
    const offInput = inputs.find((i) => i.attributes('data-label') === 'Aus-Wert')!
    await onInput.setValue('30')
    await offInput.setValue('26')

    // Save
    await wrapper.find('.base-button-stub').trigger('click')

    expect(bulkQuickUpdateRules).toHaveBeenCalledTimes(1)
    expect(bulkQuickUpdateRules).toHaveBeenCalledWith({
      ids: ['h1', 'h2'],
      active: false,
      hysteresis_on_value: 30,
      hysteresis_off_value: 26,
    })
  })

  // ── Bonus: save button disabled until a field is touched ─────────────────
  it('disables the save button until a field is touched', () => {
    const wrapper = mountField([hysteresisRule1, hysteresisRule2], ['h1', 'h2'])
    expect(wrapper.find('.base-button-stub').attributes('disabled')).toBeDefined()
  })

  // ── Test 6: mixed Ist-Werte for the Zeiten field specifically ─────────────
  // (AUT-1148 Given/When/Then #1: two time-window rules, different windows.)
  it('shows a "gemischt" hint in the Zeiten field when selected time-window rules have different windows', () => {
    const wrapper = mountField([timeRuleA, timeRuleB], ['ta', 'tb'])

    // Both rules share the time-window mechanism → Zeiten visible, no Schwellwert
    expect(wrapper.findAll('.base-input-stub').length).toBeGreaterThan(0)
    // enabled is identical (true/true) on both — the ONLY mixed field is Zeiten
    // (22:00–06:00 vs 08:30–18:00)
    expect(wrapper.findAll('.rule-group-quick-field__mixed-hint')).toHaveLength(1)
  })

  // ── Test 7: partial bulk failure must not be treated as a clean save ─────
  it('keeps the touched state and shows an error toast when the bulk response reports a partial failure', async () => {
    bulkQuickUpdateRules.mockClear()
    toastError.mockClear()
    bulkQuickUpdateRules.mockResolvedValueOnce({
      success: true,
      results: [
        { rule_id: 'h1', success: true },
        { rule_id: 'h2', success: false, error: 'Rule not found' },
      ],
    })
    const wrapper = mountField([hysteresisRule1, hysteresisRule2], ['h1', 'h2'])

    await wrapper.find('.base-toggle-stub').setValue(false)
    await wrapper.find('.base-button-stub').trigger('click')

    expect(toastError).toHaveBeenCalledWith('Bulk-Update: 1 von 2 Regeln fehlgeschlagen.')
    // Touched state must survive the partial failure so the user can retry —
    // NOT silently cleared as if every marked rule had been saved uniformly.
    expect(wrapper.find('.base-button-stub').attributes('disabled')).toBeUndefined()
  })
})
