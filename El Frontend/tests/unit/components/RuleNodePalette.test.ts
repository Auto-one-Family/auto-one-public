/**
 * AUT-1558: Palette offers canonical persist keys and cuts dead types.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleNodePalette from '@/components/rules/RuleNodePalette.vue'

describe('RuleNodePalette (AUT-1558)', () => {
  it('should keep pH/EC labels and persist ph/ec on drag', async () => {
    const wrapper = mount(RuleNodePalette)
    expect(wrapper.text()).toContain('pH-Wert')
    expect(wrapper.text()).toContain('EC-Wert')

    const items = wrapper.findAll('.palette__item')
    const phItem = items.find(item => item.find('.palette__item-label').text().includes('pH-Wert'))
    expect(phItem).toBeDefined()

    const dt = { setData: vi.fn(), effectAllowed: '' }
    await phItem!.trigger('dragstart', { dataTransfer: dt })
    const payload = JSON.parse(dt.setData.mock.calls[0][1] as string) as {
      defaults: { sensorType: string }
    }
    expect(payload.defaults.sensorType).toBe('ph')

    const ecItem = items.find(item => item.find('.palette__item-label').text().includes('EC-Wert'))
    const dtEc = { setData: vi.fn(), effectAllowed: '' }
    await ecItem!.trigger('dragstart', { dataTransfer: dtEc })
    const ecPayload = JSON.parse(dtEc.setData.mock.calls[0][1] as string) as {
      defaults: { sensorType: string }
    }
    expect(ecPayload.defaults.sensorType).toBe('ec')
  })

  it('should not offer light, level, or flow as palette triggers', () => {
    const wrapper = mount(RuleNodePalette)
    const labels = wrapper.findAll('.palette__item-label').map(n => n.text())
    expect(labels.some(l => l.includes('Licht'))).toBe(false)
    expect(labels.some(l => l.includes('Füllstand'))).toBe(false)
    expect(labels.some(l => /durchfluss|flow/i.test(l))).toBe(false)
  })
})
