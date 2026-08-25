/**
 * AUT-1334 (C7): gestufte Offenlegung — Erweitert-Zone außerhalb Toolbar-Basiszeile.
 * Spiegelt LogicView.vue showRuleAdvancedMeta / .rules-editor-advanced (kein neuer Save-Pfad).
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'

const LogicViewAdvancedMetaShell = defineComponent({
  name: 'LogicViewAdvancedMetaShell',
  setup() {
    const showRuleAdvancedMeta = ref(false)
    return () =>
      h('div', { class: 'rules-view' }, [
        h('div', { class: 'rules-toolbar' }, [
          h(
            'button',
            {
              type: 'button',
              class: 'rules-advanced-toggle',
              'aria-expanded': showRuleAdvancedMeta.value,
              'aria-controls': 'rules-editor-advanced',
              onClick: () => {
                showRuleAdvancedMeta.value = !showRuleAdvancedMeta.value
              },
            },
            'Erweitert',
          ),
        ]),
        showRuleAdvancedMeta.value
          ? h(
              'div',
              { id: 'rules-editor-advanced', class: 'rules-editor-advanced' },
              [
                h('div', { class: 'rule-metadata-inputs' }, 'Meta'),
                h('div', { class: 'rule-plan-row' }, 'Plan'),
              ],
            )
          : null,
      ])
  },
})

describe('LogicView advanced meta disclosure (AUT-1334)', () => {
  it('should keep advanced zone collapsed by default', () => {
    const wrapper = mount(LogicViewAdvancedMetaShell)
    expect(wrapper.find('.rules-editor-advanced').exists()).toBe(false)
    expect(wrapper.find('.rules-advanced-toggle').attributes('aria-expanded')).toBe('false')
  })

  it('should show metadata and plan row outside toolbar when Erweitert is open', async () => {
    const wrapper = mount(LogicViewAdvancedMetaShell)
    await wrapper.find('.rules-advanced-toggle').trigger('click')
    expect(wrapper.find('.rules-editor-advanced').exists()).toBe(true)
    expect(wrapper.find('.rules-toolbar .rule-metadata-inputs').exists()).toBe(false)
    expect(wrapper.find('.rules-editor-advanced .rule-metadata-inputs').exists()).toBe(true)
    expect(wrapper.find('.rules-editor-advanced .rule-plan-row').exists()).toBe(true)
    expect(wrapper.find('.rules-advanced-toggle').attributes('aria-expanded')).toBe('true')
  })
})
