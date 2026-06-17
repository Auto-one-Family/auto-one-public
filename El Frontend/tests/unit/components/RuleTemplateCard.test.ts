/**
 * Tests for RuleTemplateCard component.
 * Verifies template display and use-template event emission.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleTemplateCard from '@/components/rules/RuleTemplateCard.vue'
import { RULE_TEMPLATE_CATEGORIES } from '@/config/rule-templates'
import type { RuleTemplate } from '@/config/rule-templates'
import { h } from 'vue'

const mockTemplate: RuleTemplate = {
  id: 'test-tmpl',
  name: 'Test Template',
  description: 'A test rule template',
  icon: { name: 'TestIcon', render: () => h('svg') },
  category: 'climate',
  rule: {
    name: 'Test Rule',
    description: 'Test',
    enabled: true,
    conditions: [{ type: 'sensor', esp_id: '', gpio: 0, sensor_type: 'DS18B20', operator: '>', value: 30 }],
    logic_operator: 'AND',
    actions: [{ type: 'actuator', esp_id: '', gpio: 0, command: 'ON' }],
    priority: 5,
  },
}

function mountCard(template = mockTemplate) {
  return mount(RuleTemplateCard, {
    props: { template },
    global: {
      stubs: {
        BaseCard: {
          template: '<div class="base-card"><slot /></div>',
          props: ['glass', 'hoverable'],
        },
      },
    },
  })
}

describe('RuleTemplateCard', () => {
  it('renders template name', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('Test Template')
  })

  it('renders template description', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).toContain('A test rule template')
  })

  it('renders category badge', () => {
    const wrapper = mountCard()
    const category = RULE_TEMPLATE_CATEGORIES['climate']
    expect(wrapper.text()).toContain(category.label)
  })

  it('renders "Verwenden" button', () => {
    const wrapper = mountCard()
    expect(wrapper.find('.rule-template-card__action').exists()).toBe(true)
    expect(wrapper.find('.rule-template-card__action').text()).toBe('Verwenden')
  })

  it('emits use-template on button click', async () => {
    const wrapper = mountCard()
    await wrapper.find('.rule-template-card__action').trigger('click')
    const emitted = wrapper.emitted('use-template')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toEqual(mockTemplate)
  })

  it('emits use-template on card click', async () => {
    const wrapper = mountCard()
    await wrapper.find('.rule-template-card').trigger('click')
    const emitted = wrapper.emitted('use-template')
    expect(emitted).toBeDefined()
  })
})
