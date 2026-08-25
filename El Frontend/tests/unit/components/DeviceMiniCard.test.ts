import { describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import DeviceMiniCard from '@/components/dashboard/DeviceMiniCard.vue'
import { useEspStore } from '@/stores/esp'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'

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
      <slot name="badge" />
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

  it('should not show sensor or actuator count chips', () => {
    const wrapper = mountCard({
      sensors: [
        { gpio: 4, sensor_type: 'ds18b20', raw_value: 22.1, name: 'Temperatur' },
      ],
      sensor_count: 3,
      actuators: [
        { gpio: 16, actuator_type: 'relay', name: 'Pumpe', state: 'off' },
      ],
      actuator_count: 2,
    })

    expect(wrapper.text()).not.toMatch(/\d+S/)
    expect(wrapper.text()).not.toMatch(/\d+A/)
    expect(wrapper.text()).not.toContain('3S')
    expect(wrapper.text()).not.toContain('2A')
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

  it('should open the notification drawer from the alert chip without emitting card click', async () => {
    const wrapper = mountCard()
    const inboxStore = useNotificationInboxStore()
    inboxStore.notifications = [{
      id: 'alert-1',
      user_id: 1,
      channel: 'websocket',
      severity: 'warning',
      category: 'system',
      title: 'pH hoch',
      body: null,
      metadata: { esp_id: 'ESP_TEST_001' },
      source: 'sensor_threshold',
      is_read: false,
      is_archived: false,
      digest_sent: false,
      parent_notification_id: null,
      fingerprint: null,
      created_at: new Date().toISOString(),
      updated_at: null,
      read_at: null,
      status: 'active',
      acknowledged_at: null,
      acknowledged_by: null,
      resolved_at: null,
      correlation_id: null,
    }]
    await wrapper.vm.$nextTick()

    const openSpy = vi.spyOn(inboxStore, 'openDrawerWithActiveAlertsFocus').mockImplementation(() => {})
    await wrapper.get('[data-testid="device-alert-chip"]').trigger('click')

    expect(openSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('click')).toBeFalsy()
  })
})
