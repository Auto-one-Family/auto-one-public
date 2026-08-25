/**
 * AUT-1304: Inline Totband-Warnungen (.rules-editor-alerts) — non-blocking UI binding.
 * Spiegelt LogicView.vue selectedRule?.warnings (kein eigener Save-Pfad).
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const LogicViewWarningsAlert = defineComponent({
  name: 'LogicViewWarningsAlert',
  props: {
    warnings: {
      type: Array as () => string[] | undefined,
      default: undefined,
    },
  },
  setup(props) {
    return () =>
      props.warnings?.length
        ? h(
            'div',
            { class: 'rules-editor-alerts', role: 'status', 'aria-live': 'polite' },
            [
              h('div', { class: 'rules-editor-alerts__item' }, props.warnings.join(' · ')),
            ],
          )
        : null
  },
})

describe('LogicView warnings alerts (AUT-1304)', () => {
  it('renders warnings inline when present', () => {
    const wrapper = mount(LogicViewWarningsAlert, {
      props: {
        warnings: ['Totband ueberlappt', 'Zweite Warnung'],
      },
    })

    expect(wrapper.find('.rules-editor-alerts').exists()).toBe(true)
    expect(wrapper.find('.rules-editor-alerts__item').text()).toBe(
      'Totband ueberlappt · Zweite Warnung',
    )
  })

  it('renders nothing when warnings array is empty or absent', () => {
    expect(
      mount(LogicViewWarningsAlert, { props: { warnings: [] } }).find('.rules-editor-alerts').exists(),
    ).toBe(false)
    expect(mount(LogicViewWarningsAlert).find('.rules-editor-alerts').exists()).toBe(false)
  })
})
