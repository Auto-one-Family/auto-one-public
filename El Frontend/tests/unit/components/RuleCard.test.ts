/**
 * Tests for RuleCard component.
 * Verifies flow badges, status dot, events, and computed properties.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleCard from '@/components/rules/RuleCard.vue'
import type { LogicRule } from '@/types/logic'

// Mock date-fns to avoid locale issues in tests
vi.mock('date-fns', () => ({
  formatDistanceToNow: vi.fn(() => 'vor 5 Minuten'),
}))

vi.mock('date-fns/locale', () => ({
  de: {},
}))

const mockRule: LogicRule = {
  id: 'rule-1',
  name: 'Temperatur-Alarm',
  description: 'Test rule',
  enabled: true,
  conditions: [
    {
      type: 'sensor',
      esp_id: 'esp-1',
      gpio: 4,
      sensor_type: 'DS18B20',
      operator: '>',
      value: 30,
    },
  ],
  logic_operator: 'AND',
  actions: [
    {
      type: 'actuator',
      esp_id: 'esp-2',
      gpio: 5,
      command: 'ON',
    },
  ],
  priority: 5,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  last_triggered: '2026-02-11T10:00:00Z',
}

function mountCard(overrides: Partial<typeof mockRule> = {}, props: Record<string, unknown> = {}) {
  return mount(RuleCard, {
    props: {
      rule: { ...mockRule, ...overrides },
      isSelected: false,
      ...props,
    },
  })
}

describe('RuleCard', () => {
  it('renders rule name', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('Temperatur-Alarm')
  })

  it('shows sensor badge with type and condition', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('DS18B20')
    expect(wrapper.text()).toContain('> 30')
  })

  it('shows action badge with command', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('ON')
  })

  it('shows logic operator badge', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('AND')
  })

  it('shows flow arrows between badges', () => {
    const wrapper = mountCard()
    expect(wrapper.findAll('.rule-card__arrow').length).toBeGreaterThanOrEqual(2)
  })

  it('applies selected class when isSelected is true', () => {
    const wrapper = mountCard({}, { isSelected: true })
    expect(wrapper.find('.rule-card--selected').exists()).toBe(true)
  })

  it('applies disabled class when rule is disabled', () => {
    const wrapper = mountCard({ enabled: false })
    expect(wrapper.find('.rule-card--disabled').exists()).toBe(true)
  })

  it('applies active class when isActive is true', () => {
    const wrapper = mountCard({}, { isActive: true })
    expect(wrapper.find('.rule-card--active').exists()).toBe(true)
  })

  it('status dot has correct class for enabled rule', () => {
    const wrapper = mountCard({ enabled: true })
    expect(wrapper.find('.rule-card__status-dot--on').exists()).toBe(true)
  })

  it('status dot has correct class for disabled rule', () => {
    const wrapper = mountCard({ enabled: false })
    expect(wrapper.find('.rule-card__status-dot--off').exists()).toBe(true)
  })

  it('emits select with rule id on card click', async () => {
    const wrapper = mountCard()
    await wrapper.find('.rule-card').trigger('click')
    const emitted = wrapper.emitted('select')
    expect(emitted).toBeDefined()
    expect(emitted![0]).toEqual(['rule-1'])
  })

  it('emits toggle with rule id and new state on dot click', async () => {
    const wrapper = mountCard({ enabled: true })
    await wrapper.find('.rule-card__status-dot').trigger('click')
    const emitted = wrapper.emitted('toggle')
    expect(emitted).toBeDefined()
    expect(emitted![0]).toEqual(['rule-1', false])
  })

  it('emits delete with rule id on delete click', async () => {
    const wrapper = mountCard()
    await wrapper.find('.rule-card__delete').trigger('click')
    const emitted = wrapper.emitted('delete')
    expect(emitted).toBeDefined()
    expect(emitted![0]).toEqual(['rule-1'])
  })

  it('shows execution count when > 0', () => {
    const wrapper = mountCard({}, { executionCount: 5 })
    expect(wrapper.text()).toContain('5x/24h')
  })

  it('hides execution count when 0', () => {
    const wrapper = mountCard({}, { executionCount: 0 })
    expect(wrapper.text()).not.toContain('x/24h')
  })

  it('shows "Noch nie" when rule was never triggered', () => {
    const wrapper = mountCard({ last_triggered: undefined } as any)
    expect(wrapper.text()).toContain('Noch nie')
  })

  it('shows time badge with time_window condition', () => {
    const wrapper = mountCard({
      conditions: [{ type: 'time_window', start_hour: 22, end_hour: 6 }] as any,
      actions: [{ type: 'actuator', esp_id: '', gpio: 0, command: 'OFF' }] as any,
    })
    expect(wrapper.text()).toContain('Zeit')
  })

  it('shows notification badge for notification action', () => {
    const wrapper = mountCard({
      actions: [{ type: 'notification', channel: 'websocket', target: 'dashboard', message_template: 'test' }] as any,
    })
    expect(wrapper.text()).toContain('Benachrichtigung')
  })
})
