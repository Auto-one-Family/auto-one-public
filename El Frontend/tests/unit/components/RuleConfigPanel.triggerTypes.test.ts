/**
 * AUT-1558: Offline-trigger / fallback sensor-type picker cuts light/flow/level
 * and persists ph/ec.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import RuleConfigPanel from '@/components/rules/RuleConfigPanel.vue'
import type { Node } from '@vue-flow/core'

vi.mock('@/api/actuators', () => ({
  actuatorsApi: { get: vi.fn(async () => null) },
}))
vi.mock('@/api/sensors', () => ({
  sensorsApi: { get: vi.fn(async () => null) },
}))
vi.mock('@/api/plugins', () => ({
  pluginsApi: { list: vi.fn(async () => []) },
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}))
vi.mock('@/composables/useSensorOptions', () => ({
  useSensorOptions: () => ({ groupedSensorOptions: { value: [] } }),
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

const DEVICE_ID = 'ESP_TRIGGER'

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [
      {
        id: 'dev-1',
        device_id: DEVICE_ID,
        esp_id: DEVICE_ID,
        name: 'Test-ESP',
        sensors: [],
        actuators: [],
      },
    ],
    getDeviceId: (d: { device_id?: string; esp_id?: string; id?: string }) =>
      d.device_id || d.esp_id || d.id || '',
  }),
}))

vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    get rules() {
      return ref([]).value
    },
  }),
}))

function sensorNode(): Node {
  return {
    id: 's1',
    type: 'sensor',
    position: { x: 0, y: 0 },
    data: {
      espId: DEVICE_ID,
      gpio: 4,
      sensorType: 'ds18b20',
      operator: '>',
      value: 25,
    },
  }
}

describe('RuleConfigPanel trigger type picker (AUT-1558)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should not offer light or flow and should persist ph/ec', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: { node: sensorNode() },
    })
    await flushPromises()

    const typeSelect = wrapper.findAll('select.config-select').find(sel =>
      sel.findAll('option').some(o => (o.element as HTMLOptionElement).value === 'ph'),
    )
    expect(typeSelect).toBeDefined()
    const values = typeSelect!.findAll('option').map(o => (o.element as HTMLOptionElement).value)
    expect(values).toContain('ph')
    expect(values).toContain('ec')
    expect(values).toContain('liquid_level')
    expect(values).not.toContain('pH')
    expect(values).not.toContain('EC')
    expect(values).not.toContain('light')
    expect(values).not.toContain('flow')
    expect(values).not.toContain('level')
  })

  it('should select ph/ec for legacy stored pH/EC tokens', async () => {
    const phNode = sensorNode()
    phNode.data.sensorType = 'pH'
    phNode.data.conditionCategory = 'ph'
    const phWrapper = mount(RuleConfigPanel, {
      props: { node: phNode },
    })
    await flushPromises()

    const phSelect = phWrapper.findAll('select.config-select').find(sel =>
      sel.findAll('option').some(o => (o.element as HTMLOptionElement).value === 'ph'),
    )
    expect(phSelect).toBeDefined()
    expect((phSelect!.element as HTMLSelectElement).value).toBe('ph')

    const ecNode = sensorNode()
    ecNode.data.sensorType = 'EC'
    ecNode.data.conditionCategory = 'ec'
    const ecWrapper = mount(RuleConfigPanel, {
      props: { node: ecNode },
    })
    await flushPromises()

    const ecSelect = ecWrapper.findAll('select.config-select').find(sel =>
      sel.findAll('option').some(o => (o.element as HTMLOptionElement).value === 'ec'),
    )
    expect(ecSelect).toBeDefined()
    expect((ecSelect!.element as HTMLSelectElement).value).toBe('ec')
  })
})
