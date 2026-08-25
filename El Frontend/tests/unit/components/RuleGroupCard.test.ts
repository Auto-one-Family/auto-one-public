/**
 * Tests for RuleGroupCard component.
 *
 * Verifies header rendering (label, icon accent, count), always-visible rule
 * list, empty state, multi-select interaction, and edit affordance.
 *
 * Note: lucide-vue-next icons are globally mocked in tests/setup.ts
 * (Proxy returning { name, render: () => null }), so no manual icon stubs needed.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleGroupCard from '@/components/logic/RuleGroupCard.vue'
import type { LogicRule, RuleGroup } from '@/types/logic'

vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    isRuleTriggered: (ruleId: string) => ruleId === 'triggered-rule',
  }),
}))

function makeRule(overrides: Partial<LogicRule> & { id: string }): LogicRule {
  return {
    id:             overrides.id,
    name:           overrides.name           ?? 'Test-Regel',
    description:    overrides.description,
    enabled:        overrides.enabled        ?? true,
    conditions:     overrides.conditions     ?? [
      { type: 'sensor', esp_id: 'esp-1', gpio: 4, sensor_type: 'DS18B20', operator: '>' as const, value: 28 },
    ],
    logic_operator: overrides.logic_operator ?? 'AND',
    actions:        overrides.actions        ?? [
      { type: 'actuator' as const, esp_id: 'esp-1', gpio: 5, command: 'ON' as const },
    ],
    priority:       overrides.priority       ?? 5,
    created_at:     overrides.created_at     ?? '2026-01-01T00:00:00Z',
    updated_at:     overrides.updated_at     ?? '2026-01-01T00:00:00Z',
    rule_group:     overrides.rule_group,
  }
}

const ruleKlima1 = makeRule({ id: 'k1', name: 'Lueftung AN' })
const ruleKlima2 = makeRule({ id: 'k2', name: 'Lueftung AB', enabled: false })
const ruleZeitplan1 = makeRule({
  id: 'z1',
  name: 'Nacht-Modus',
  conditions: [{ type: 'time_window', start_hour: 22, end_hour: 6 }],
})
const ruleAlarm1 = makeRule({
  id: 'a1',
  name: 'pH-Alarm',
  conditions: [
    {
      type: 'sensor',
      esp_id: 'esp-2',
      gpio: 3,
      sensor_type: 'ph',
      operator: '<',
      value: 5.5,
    },
  ],
  actions: [
    {
      type: 'notification',
      channel: 'websocket',
      target: 'dashboard',
      message_template: 'pH zu niedrig',
    },
  ],
})

const globalStubs = {
  BaseCard: {
    template: '<div class="base-card"><slot /></div>',
    props: ['glass', 'hoverable'],
  },
  StatusBadge: {
    template: '<span class="status-badge-stub" :data-level="level" />',
    props: ['level', 'compact'],
  },
}

function mountCard(
  groupName: RuleGroup,
  rules: LogicRule[],
  targetLabels?: Map<string, string>,
) {
  return mount(RuleGroupCard, {
    props: { groupName, rules, targetLabels },
    global: { stubs: globalStubs },
  })
}

describe('RuleGroupCard', () => {
  it('should render label and rule count for temperatur group without duplicate badge', () => {
    const wrapper = mountCard('temperatur', [ruleKlima1, ruleKlima2])

    expect(wrapper.find('.rule-group-card__name').text()).toBe('Temperatur')
    expect(wrapper.find('.base-badge').exists()).toBe(false)
    expect(wrapper.find('.rule-group-card__count-chip').text()).toContain('2')
    expect(wrapper.find('.rule-group-card__count-chip').text()).toContain('Regeln')
    expect(wrapper.find('.rule-group-card').attributes('style')).toContain('--rule-group-accent')
  })

  it('should render correct label and rule count for zeitplan group', () => {
    const wrapper = mountCard('zeitplan', [ruleZeitplan1])

    expect(wrapper.find('.rule-group-card__name').text()).toBe('Zeitplan')
    expect(wrapper.find('.rule-group-card__count-chip').text()).toContain('1')
    expect(wrapper.find('.rule-group-card__count-chip').text()).toContain('Regel')
  })

  it('should render correct label and rule count for ph group', () => {
    const secondAlarmRule = makeRule({ id: 'a2', name: 'EC-Alarm' })
    const thirdAlarmRule = makeRule({ id: 'a3', name: 'Temp-Alarm' })
    const wrapper = mountCard('ph', [ruleAlarm1, secondAlarmRule, thirdAlarmRule])

    expect(wrapper.find('.rule-group-card__name').text()).toBe('pH')
    expect(wrapper.find('.rule-group-card__count-chip').text()).toContain('3')
    expect(wrapper.find('.rule-group-card__count-chip').text()).toContain('Regeln')
  })

  it('should render cleanly with 0 rules: count=0 and empty state visible', () => {
    const wrapper = mountCard('sonstiges', [])

    expect(wrapper.find('.rule-group-card__count-chip').text()).toContain('0')
    expect(wrapper.find('.rule-group-card__empty').exists()).toBe(true)
    expect(wrapper.find('.rule-group-card__rule-list').exists()).toBe(false)
    expect(wrapper.find('.rule-group-card__select-all').exists()).toBe(false)
    expect(wrapper.find('.rule-group-card').exists()).toBe(true)
  })

  it('should emit update:selectedIds with 3 IDs after clicking 3 checkboxes', async () => {
    const rules = [
      makeRule({ id: 'rule-1' }),
      makeRule({ id: 'rule-2' }),
      makeRule({ id: 'rule-3' }),
      makeRule({ id: 'rule-4' }),
    ]
    const wrapper = mountCard('temperatur', rules)

    const checkboxes = wrapper.findAll('.rule-group-card__checkbox')
    expect(checkboxes).toHaveLength(4)

    await checkboxes[0].trigger('change')
    await checkboxes[1].trigger('change')
    await checkboxes[2].trigger('change')

    const emitted = wrapper.emitted('update:selectedIds')
    expect(emitted).toBeDefined()

    const lastEmission = emitted![emitted!.length - 1][0] as string[]
    expect(lastEmission).toHaveLength(3)
    expect(lastEmission).toContain('rule-1')
    expect(lastEmission).toContain('rule-2')
    expect(lastEmission).toContain('rule-3')
    expect(lastEmission).not.toContain('rule-4')
  })

  it('should map rule status to ok/offline/warning', () => {
    const activeRule = makeRule({ id: 'active-rule', enabled: true })
    const inactiveRule = makeRule({ id: 'inactive-rule', enabled: false })
    const triggeredRule = makeRule({ id: 'triggered-rule', enabled: true })
    const wrapper = mountCard('temperatur', [activeRule, inactiveRule, triggeredRule])

    const badges = wrapper.findAll('.status-badge-stub')
    expect(badges).toHaveLength(3)
    expect(badges[0].attributes('data-level')).toBe('ok')
    expect(badges[1].attributes('data-level')).toBe('offline')
    expect(badges[2].attributes('data-level')).toBe('warning')
  })

  it('should display rule name and readable summary in rule rows', () => {
    const wrapper = mountCard('temperatur', [ruleKlima1])

    expect(wrapper.find('.rule-group-card__rule-name').text()).toBe('Lueftung AN')
    const rowTexts = wrapper.findAll('.rule-group-card__rule-text')
    expect(rowTexts).toHaveLength(1)
    expect(rowTexts[0].text()).toContain('Wenn')
  })

  it('should show target label chip when targetLabels map is provided', () => {
    const labels = new Map([['k1', 'Zone Klima-A']])
    const wrapper = mountCard('temperatur', [ruleKlima1], labels)

    const chip = wrapper.find('.rule-group-card__target-chip')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toBe('Zone Klima-A')
  })

  it('should have no expand/collapse button (rule list always visible)', () => {
    const wrapper = mountCard('temperatur', [ruleKlima1])

    expect(wrapper.find('[aria-expanded]').exists()).toBe(false)
    expect(wrapper.find('.rule-group-card__rule-list').exists()).toBe(true)
  })

  it('should select-all select all rules and deselect on second click', async () => {
    const rules = [makeRule({ id: 'r1' }), makeRule({ id: 'r2' })]
    const wrapper = mountCard('temperatur', rules)

    const selectAll = wrapper.find('.rule-group-card__select-all')
    expect(selectAll.exists()).toBe(true)

    await selectAll.trigger('click')
    const emittedAfterSelect = wrapper.emitted('update:selectedIds')!
    expect((emittedAfterSelect[0][0] as string[])).toHaveLength(2)

    await selectAll.trigger('click')
    const emittedAfterDeselect = wrapper.emitted('update:selectedIds')!
    expect((emittedAfterDeselect[1][0] as string[])).toHaveLength(0)
  })

  it('should show the mark-to-edit hint once and hide the quick-field slot until a rule is selected', async () => {
    const wrapper = mount(RuleGroupCard, {
      props: { groupName: 'temperatur', rules: [ruleKlima1] },
      slots: {
        'quick-field': '<div class="quick-field-slot-probe">Schnellfeld</div>',
      },
      global: { stubs: globalStubs },
    })

    const hints = wrapper.findAll('.rule-group-card__selection-hint')
    expect(hints).toHaveLength(1)
    expect(hints[0].text()).toContain('markieren')
    expect(wrapper.find('.quick-field-slot-probe').exists()).toBe(false)
    expect(wrapper.find('.rule-group-card__quick-field').exists()).toBe(false)

    await wrapper.find('.rule-group-card__checkbox').trigger('change')

    expect(wrapper.find('.quick-field-slot-probe').exists()).toBe(true)
    expect(wrapper.find('.rule-group-card__quick-field').exists()).toBe(true)
    expect(wrapper.find('.rule-group-card__selection-hint').text()).toContain('ausgewählt')
  })

  it('should emit edit-rule without toggling checkbox', async () => {
    const rules = [makeRule({ id: 'r1' }), makeRule({ id: 'r2' })]
    const wrapper = mountCard('temperatur', rules)

    const editButtons = wrapper.findAll('.rule-group-card__edit-btn')
    expect(editButtons).toHaveLength(2)

    await editButtons[1].trigger('click')

    expect(wrapper.emitted('edit-rule')).toEqual([['r2']])
    expect(wrapper.emitted('update:selectedIds')).toBeUndefined()
  })
})
