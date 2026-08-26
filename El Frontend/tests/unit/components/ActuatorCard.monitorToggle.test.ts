/**
 * ActuatorCard Monitor-L2-Schalt (AUT-1513 A)
 *
 * L2 bleibt Anzeige + Schalten ohne Confirm.
 * Config öffnet nicht von der Monitor-Karte.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ActuatorCard from '@/components/devices/ActuatorCard.vue'
import type { ActuatorWithContext } from '@/composables/useZoneGrouping'

vi.mock('@/api/actuators', () => ({
  actuatorsApi: { get: vi.fn() },
}))
vi.mock('@/composables/useToast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}))

function baseActuator(overrides: Partial<ActuatorWithContext> = {}): ActuatorWithContext {
  return {
    gpio: 5,
    actuator_type: 'relay',
    hardware_type: 'relay',
    name: 'Relais Tank',
    state: false,
    pwm_value: 0,
    emergency_stopped: false,
    esp_id: 'ESP_TEST_001',
    esp_state: 'OPERATIONAL',
    zone_id: 'zone-1',
    zone_name: 'Haus A',
    subzone_id: null,
    subzone_name: '',
    last_seen: new Date().toISOString(),
    last_command_at: new Date().toISOString(),
    ...overrides,
  }
}

function mountCard(
  actuator: ActuatorWithContext,
  mode: 'monitor' | 'config' = 'monitor',
) {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(ActuatorCard, {
    props: { actuator, mode },
    global: {
      plugins: [pinia],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

describe('ActuatorCard — Monitor L2 Schalt (AUT-1513 A)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('should show Einschalten on monitor L2 without a confirm dialog', () => {
    const wrapper = mountCard(baseActuator())
    const toggle = wrapper.get('button[aria-label="Einschalten"]')
    expect(toggle.text()).toBe('Einschalten')
    expect(wrapper.findComponent({ name: 'ConfirmDialog' }).exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Bestätigen')
  })

  it('should emit toggle immediately when the monitor switch is clicked', async () => {
    const wrapper = mountCard(baseActuator({ state: true }))
    await wrapper.get('button[aria-label="Ausschalten"]').trigger('click')
    expect(wrapper.emitted('toggle')).toEqual([['ESP_TEST_001', 5, true]])
    expect(wrapper.emitted('configure')).toBeUndefined()
  })

  it('should not emit configure when the monitor card body is clicked', async () => {
    const wrapper = mountCard(baseActuator())
    await wrapper.get('.actuator-card').trigger('click')
    expect(wrapper.emitted('configure')).toBeUndefined()
  })

  it('should still emit configure from config mode, not from monitor mode', async () => {
    const wrapper = mountCard(baseActuator(), 'config')
    await wrapper.get('.actuator-card').trigger('click')
    expect(wrapper.emitted('configure')?.length).toBe(1)
  })
})
