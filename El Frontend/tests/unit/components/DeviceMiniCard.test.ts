import { describe, expect, it, vi, beforeEach } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DeviceMiniCard from '@/components/dashboard/DeviceMiniCard.vue'
import { useEspStore } from '@/stores/esp'

vi.mock('@/composables/useESPStatus', () => ({
  getESPStatus: () => 'online',
  getESPStatusDisplay: () => ({ text: 'Online' }),
}))

const ESPCardBaseStub = defineComponent({
  name: 'ESPCardBase',
  emits: ['click', 'settings', 'change-zone', 'monitor-nav', 'delete'],
  template: `
    <div>
      <button data-testid="emit-click" @click="$emit('click')">click</button>
      <button data-testid="emit-settings" @click="$emit('settings')">settings</button>
      <button data-testid="emit-change-zone" @click="$emit('change-zone')">change-zone</button>
      <button data-testid="emit-monitor-nav" @click="$emit('monitor-nav')">monitor-nav</button>
      <button data-testid="emit-delete" @click="$emit('delete')">delete</button>
      <slot />
    </div>
  `,
})

const device = {
  device_id: 'ESP_TEST_001',
  esp_id: 'ESP_TEST_001',
  name: 'Test Device',
  status: 'online',
  sensors: [],
  actuators: [],
  sensor_count: 0,
  actuator_count: 0,
  last_seen: null,
  last_heartbeat: null,
}

function mountCard(deviceOverrides: Record<string, unknown> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const mergedDevice = { ...device, ...deviceOverrides }
  const espStore = useEspStore()
  espStore.devices = [mergedDevice as any]

  return mount(DeviceMiniCard, {
    props: {
      device: mergedDevice as any,
      isMock: true,
    },
    global: {
      plugins: [pinia],
      stubs: {
        ESPCardBase: ESPCardBaseStub,
      },
    },
  })
}

describe('DeviceMiniCard', () => {
  it('maps delete to device-delete with device id', async () => {
    const wrapper = mountCard()
    await wrapper.get('[data-testid="emit-delete"]').trigger('click')

    expect(wrapper.emitted('device-delete')).toBeTruthy()
    expect(wrapper.emitted('device-delete')?.[0]).toEqual(['ESP_TEST_001'])
  })

  it('forwards settings/change-zone/monitor-nav with full device payload', async () => {
    const wrapper = mountCard()

    await wrapper.get('[data-testid="emit-settings"]').trigger('click')
    await wrapper.get('[data-testid="emit-change-zone"]').trigger('click')
    await wrapper.get('[data-testid="emit-monitor-nav"]').trigger('click')

    expect(wrapper.emitted('settings')?.[0]).toEqual([device])
    expect(wrapper.emitted('change-zone')?.[0]).toEqual([device])
    expect(wrapper.emitted('monitor-nav')?.[0]).toEqual([device])
  })

  it('does not show stale fallback sensor_count when sensors array is empty', () => {
    const wrapper = mountCard({
      sensors: [],
      sensor_count: 2,
      actuators: [],
      actuator_count: 0,
    })

    expect(wrapper.text()).not.toContain('2 Sensoren')
    expect(wrapper.text()).toContain('Keine Sensoren oder Aktoren')
  })
})
