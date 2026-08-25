/**
 * AUT-1303: Max. Dosis/Tag UI-Heimat am dosierfaehigen Aktor (H-1 generische Pumpe).
 * Persistenz bleibt Regel-Spalte — Panel emittiert nur update:max-dose-ml-per-day.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import RuleConfigPanel from '@/components/rules/RuleConfigPanel.vue'
import type { Node } from '@vue-flow/core'

vi.mock('@/api/actuators', () => ({
  actuatorsApi: {
    get: vi.fn(async () => null),
  },
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

const devicesRef = ref([
  {
    esp_id: 'esp-pump-1',
    id: 'esp-pump-1',
    actuators: [
      {
        gpio: 11,
        actuator_type: 'digital',
        hardware_type: 'pump',
        name: 'pH-Minus',
      },
      {
        gpio: 25,
        actuator_type: 'digital',
        hardware_type: 'relay',
        name: 'Relais',
      },
    ],
  },
])

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: devicesRef.value,
    getDeviceId: (d: { esp_id?: string; id?: string }) => d.esp_id || d.id || '',
  }),
}))

function actuatorNode(gpio: number): Node {
  return {
    id: 'a1',
    type: 'actuator',
    position: { x: 0, y: 0 },
    data: {
      type: 'actuator',
      espId: 'esp-pump-1',
      gpio,
      command: 'ON',
    },
  }
}

function sequenceNode(): Node {
  return {
    id: 's1',
    type: 'sequence',
    position: { x: 0, y: 0 },
    data: {
      type: 'sequence',
      maxDurationSeconds: 120,
      steps: [],
    },
  }
}

describe('RuleConfigPanel maxDoseMlPerDay (AUT-1303)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show Max. Dosis/Tag for pump actuator and emit 0 on clear', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: {
        node: actuatorNode(11),
        maxDoseMlPerDay: 12.5,
        rulePumpActuators: [{ espId: 'esp-pump-1', gpio: 11, name: 'pH-Minus' }],
      },
    })
    await flushPromises()

    const input = wrapper.find('[data-testid="max-dose-ml-per-day"]')
    expect(input.exists()).toBe(true)
    expect((input.element as HTMLInputElement).value).toBe('12.5')

    await input.setValue('')
    const emitted = wrapper.emitted('update:max-dose-ml-per-day')
    expect(emitted).toBeTruthy()
    expect(emitted![emitted!.length - 1]).toEqual([0])
  })

  it('should hide Max. Dosis/Tag for relay actuator', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: {
        node: actuatorNode(25),
        maxDoseMlPerDay: 0,
        rulePumpActuators: [],
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="max-dose-ml-per-day"]').exists()).toBe(false)
  })

  it('should show Max. Dosis/Tag on sequence when rule has pump actuators', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: {
        node: sequenceNode(),
        maxDoseMlPerDay: 0,
        rulePumpActuators: [{ espId: 'esp-pump-1', gpio: 11 }],
      },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="max-dose-ml-per-day"]').exists()).toBe(true)
  })
})
