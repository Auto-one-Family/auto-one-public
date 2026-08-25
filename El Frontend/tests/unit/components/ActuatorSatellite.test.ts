import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ActuatorSatellite from '@/components/esp/ActuatorSatellite.vue'

vi.mock('@/utils/formatters', () => ({
  formatRelativeTime: (value: string) => `REL:${value}`,
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    sendActuatorCommand: vi.fn(),
  }),
}))

const baseProps = {
  espId: 'ESP_TEST',
  gpio: 5,
  actuatorType: 'relay',
  state: false,
}

function mountSatellite(props: Record<string, unknown> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)

  return mount(ActuatorSatellite, {
    props: { ...baseProps, ...props },
    global: {
      plugins: [pinia],
      stubs: {
        Badge: { template: '<span><slot /></span>' },
      },
    },
  })
}

describe('ActuatorSatellite', () => {
  it('shows last_command_at for Zuletzt and ignores rule trigger timestamps', () => {
    const wrapper = mountSatellite({
      lastCommandAt: '2026-07-06T20:50:00.000Z',
      lastTriggeredAt: '2026-07-06T20:05:00.000Z',
      triggerRuleName: 'EC Steuerung',
    })

    expect(wrapper.text()).toContain('Zuletzt: REL:2026-07-06T20:50:00.000Z')
    expect(wrapper.text()).not.toContain('REL:2026-07-06T20:05:00.000Z')
    expect(wrapper.text()).toContain('EC Steuerung')
  })

  it('does not show Zuletzt when last_command_at is missing even if rule trigger exists', () => {
    const wrapper = mountSatellite({
      lastCommandAt: null,
      lastTriggeredAt: '2026-07-06T20:05:00.000Z',
      triggerRuleName: 'EC Steuerung',
    })

    expect(wrapper.text()).not.toContain('Zuletzt:')
    expect(wrapper.text()).toContain('EC Steuerung')
  })

  it('shows Zuletzt from last_command_at alone', () => {
    const wrapper = mountSatellite({
      lastCommandAt: '2026-07-06T20:50:00.000Z',
    })

    expect(wrapper.text()).toContain('Zuletzt: REL:2026-07-06T20:50:00.000Z')
  })
})
