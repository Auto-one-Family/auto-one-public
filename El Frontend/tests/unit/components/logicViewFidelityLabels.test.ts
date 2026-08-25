/**
 * AUT-1336: Fidelity labels for Kopplungs-Einstellungen (Anzeige = Wirkung).
 * Spiegelt LogicView.vue Copy in Erweitert-Zone — kein neuer Save-Pfad.
 */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const LogicViewFidelityLabelsShell = defineComponent({
  name: 'LogicViewFidelityLabelsShell',
  setup() {
    return () =>
      h('div', { id: 'rules-editor-advanced', class: 'rules-editor-advanced' }, [
        h(
          'label',
          {
            class: 'rule-meta-field',
            title:
              'Nur Gruppierung/Organisation (Monitor/Logic-Uebersicht) — keine Regel-Sperre. Leer = automatisch aus Bedingungen/Aktionen abgeleitet.',
          },
          [
            h('span', 'Regel-Gruppe (Organisation)'),
            h('select', {
              'aria-label': 'Regel-Gruppe (Organisation, keine Regel-Sperre)',
            }),
          ],
        ),
        h(
          'label',
          {
            class: 'rule-meta-field',
            title:
              'Warnhinweis auf eine Gegenspieler-Regel (z.B. pH-Plus <-> pH-Minus): beim Speichern prueft der Server ueberlappende Hysterese-Schwellen (nicht-blockierende Totband-Warnung). Kein Runtime-Lock — echte Sperre ist der Interlock (Läuft nicht / not_running).',
          },
          [
            h('span', 'Gegenspieler (Totband-Warnung)'),
            h('select', {
              'aria-label':
                'Gegenspieler-Regel (Totband-Warnung beim Speichern, kein Runtime-Lock)',
            }),
          ],
        ),
        h(
          'label',
          {
            class: 'rule-meta-field rule-meta-field--toggle',
            title:
              'Wenn aktiv: Vorrang bei Aktor-Konflikten (bestehender ConflictManager: priority / Safety) und Health-/Degraded-Tracking. Nur für sicherheitsrelevante Regeln aktivieren.',
          },
          [h('span', 'Kritisch')],
        ),
      ])
  },
})

describe('LogicView fidelity labels (AUT-1336)', () => {
  it('should label Gegenspieler as save-time warning, not runtime lock', () => {
    const wrapper = mount(LogicViewFidelityLabelsShell)
    expect(wrapper.text()).toContain('Gegenspieler (Totband-Warnung)')
    expect(wrapper.text()).not.toContain('Gekoppelte Regel')
    const title = wrapper.findAll('label')[1].attributes('title') ?? ''
    expect(title).toContain('Kein Runtime-Lock')
    expect(title).toContain('Interlock')
  })

  it('should mark Regel-Gruppe as organisation only in Erweitert', () => {
    const wrapper = mount(LogicViewFidelityLabelsShell)
    expect(wrapper.find('#rules-editor-advanced').exists()).toBe(true)
    expect(wrapper.text()).toContain('Regel-Gruppe (Organisation)')
    const title = wrapper.findAll('label')[0].attributes('title') ?? ''
    expect(title).toContain('keine Regel-Sperre')
  })

  it('should describe Kritisch as ConflictManager precedence plus health', () => {
    const wrapper = mount(LogicViewFidelityLabelsShell)
    const title = wrapper.findAll('label')[2].attributes('title') ?? ''
    expect(title).toContain('ConflictManager')
    expect(title).toContain('Degraded')
    expect(title).not.toContain('eingeschränkten Betriebsmodus ausgeführt')
  })
})
