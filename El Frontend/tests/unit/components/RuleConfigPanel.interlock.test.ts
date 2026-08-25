/**
 * AUT-1333: Interlock (not_running) — Zone → Gerät → Aktor statt Freitext-UUID.
 * Persistenz: espId = DB-UUID (nicht ESP_XXXX).
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

const DEVICE_UUID = '0b7e3675-e478-43e4-9758-139a8ba231bb'
const DEVICE_ID = 'ESP_AEAE64'

const devicesRef = ref([
  {
    id: DEVICE_UUID,
    device_id: DEVICE_ID,
    esp_id: DEVICE_ID,
    name: 'Wasserbox',
    zone_id: 'naehrloesung',
    zone_name: 'Nährlösung',
    actuators: [
      {
        gpio: 12,
        actuator_type: 'digital',
        hardware_type: 'relay',
        name: 'Frischwasser',
      },
      {
        gpio: 25,
        actuator_type: 'digital',
        hardware_type: 'pump',
        name: 'Nachfüllpumpe',
      },
    ],
  },
  {
    id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    device_id: 'ESP_OTHER',
    esp_id: 'ESP_OTHER',
    name: 'Anderes Zelt',
    zone_id: 'zelt-1',
    zone_name: 'Zelt 1',
    actuators: [
      {
        gpio: 5,
        actuator_type: 'digital',
        hardware_type: 'relay',
        name: 'Lüfter',
      },
    ],
  },
])

const rulesRef = ref([
  { id: '4df64c75-17e2-4f57-8772-24f71663f6f0', name: 'EC Steuerung' },
  { id: '9e19fa5c-119c-4e0e-8371-b640fc7ac8e1', name: 'PH MINUS' },
])

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    get devices() {
      return devicesRef.value
    },
    getDeviceId: (d: { device_id?: string; esp_id?: string; id?: string }) =>
      d.device_id || d.esp_id || d.id || '',
  }),
}))

vi.mock('@/shared/stores/logic.store', () => ({
  useLogicStore: () => ({
    get rules() {
      return rulesRef.value
    },
  }),
}))

function interlockNode(overrides: Record<string, unknown> = {}): Node {
  return {
    id: 'nr1',
    type: 'not_running',
    position: { x: 0, y: 0 },
    data: {
      target: 'actuator',
      espId: '',
      gpio: null,
      ruleId: '',
      ...overrides,
    },
  }
}

describe('RuleConfigPanel not_running Interlock (AUT-1333)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show zone/device/actuator selects instead of UUID text inputs', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: { node: interlockNode() },
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="interlock-zone-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="interlock-esp-select"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('ESP Device-UUID')
    expect(wrapper.find('input[placeholder*="Device-UUID"]').exists()).toBe(false)
  })

  it('should persist DB UUID when selecting zone → device → actuator', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: { node: interlockNode() },
    })
    await flushPromises()

    const zoneSelect = wrapper.find('[data-testid="interlock-zone-select"]')
    await zoneSelect.setValue('naehrloesung')

    const espSelect = wrapper.find('[data-testid="interlock-esp-select"]')
    expect(espSelect.attributes('disabled')).toBeUndefined()
    await espSelect.setValue(DEVICE_UUID)

    const actuatorSelect = wrapper.find('[data-testid="interlock-actuator-select"]')
    expect(actuatorSelect.exists()).toBe(true)
    await actuatorSelect.setValue('12')

    const updates = wrapper.emitted('update:data') as [string, Record<string, unknown>][]
    expect(updates.length).toBeGreaterThan(0)
    const last = updates[updates.length - 1][1]
    expect(last.espId).toBe(DEVICE_UUID)
    expect(last.gpio).toBe(12)
    expect(last.espId).not.toBe(DEVICE_ID)
  })

  it('should hydrate zone from existing UUID and list actuator by name', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: {
        node: interlockNode({ espId: DEVICE_UUID, gpio: 25 }),
      },
    })
    await flushPromises()

    const zoneSelect = wrapper.find('[data-testid="interlock-zone-select"]')
    expect((zoneSelect.element as HTMLSelectElement).value).toBe('naehrloesung')

    const espSelect = wrapper.find('[data-testid="interlock-esp-select"]')
    expect((espSelect.element as HTMLSelectElement).value).toBe(DEVICE_UUID)

    expect(wrapper.text()).toContain('Nachfüllpumpe')
  })

  it('should offer rule name dropdown for sequence target', async () => {
    const wrapper = mount(RuleConfigPanel, {
      props: { node: interlockNode({ target: 'sequence' }) },
    })
    await flushPromises()

    const ruleSelect = wrapper.find('[data-testid="interlock-rule-select"]')
    expect(ruleSelect.exists()).toBe(true)
    expect(ruleSelect.text()).toContain('EC Steuerung')
    expect(wrapper.find('[data-testid="interlock-zone-select"]').exists()).toBe(false)

    await ruleSelect.setValue('4df64c75-17e2-4f57-8772-24f71663f6f0')
    const updates = wrapper.emitted('update:data') as [string, Record<string, unknown>][]
    const last = updates[updates.length - 1][1]
    expect(last.ruleId).toBe('4df64c75-17e2-4f57-8772-24f71663f6f0')
  })
})
