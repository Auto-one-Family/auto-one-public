import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { nextTick } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ZoneTileInsightBlock from '@/components/monitor/ZoneTileInsightBlock.vue'
import { useEspStore } from '@/stores/esp'
import { pickZoneLeadTemperatureSensor } from '@/utils/zoneTileInsight'
import type { ZoneKPI } from '@/composables/useZoneKPIs'

const getStatsMock = vi.fn()

vi.mock('@/api/sensors', () => ({
  sensorsApi: {
    getStats: (...args: unknown[]) => getStatsMock(...args),
  },
}))

function makeZone(overrides: Partial<ZoneKPI> = {}): ZoneKPI {
  return {
    zoneId: 'zone-wohnzimmer',
    zoneName: 'Zelt Wohnzimmer',
    sensorCount: 2,
    actuatorCount: 0,
    activeSensors: 2,
    activeActuators: 0,
    alarmCount: 0,
    aggregation: {
      sensorTypes: [
        { type: 'temperature', label: 'Temperatur', avg: 24.9, min: 24.9, max: 24.9, count: 1, unit: '°C' },
        { type: 'humidity', label: 'Luftfeuchte', avg: 56, min: 56, max: 56, count: 1, unit: '%RH' },
      ],
      extraTypeCount: 0,
      deviceCount: 1,
      onlineCount: 1,
    },
    lastActivity: new Date().toISOString(),
    healthStatus: 'ok',
    healthReason: '',
    onlineDevices: 1,
    totalDevices: 1,
    mobileGuestCount: 0,
    ...overrides,
  }
}

function makeDevice(rawValue = 24.9) {
  return {
    device_id: 'ESP_TEST_001',
    esp_id: 'ESP_TEST_001',
    name: 'Test ESP',
    zone_id: 'zone-wohnzimmer',
    status: 'online',
    sensors: [
      {
        gpio: 21,
        sensor_type: 'sht31_temp',
        name: 'Temp',
        raw_value: rawValue,
        quality: 'good',
        unit: '°C',
      },
      {
        gpio: 21,
        sensor_type: 'sht31_humidity',
        name: 'Humidity',
        raw_value: 56,
        quality: 'good',
        unit: '%RH',
      },
    ],
    actuators: [],
  }
}

describe('ZoneTileInsightBlock', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    getStatsMock.mockReset()
    getStatsMock.mockResolvedValue({
      stats: { min_value: 21.2, max_value: 26.4, avg_value: 24.0, count: 100 },
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should fetch 24h stats once and not refetch on live sensor value updates', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const espStore = useEspStore()
    espStore.devices = [makeDevice(24.9) as never]

    const wrapper = mount(ZoneTileInsightBlock, {
      props: { zone: makeZone() },
      global: { plugins: [pinia] },
    })

    await flushPromises()
    expect(getStatsMock).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('21,2')
    expect(wrapper.text()).toContain('26,4')

    // Simulate frequent WS sensor_data updates (same lead identity)
    for (let i = 0; i < 5; i++) {
      const device = espStore.devices[0] as { sensors: { raw_value: number }[] }
      device.sensors[0].raw_value = 24.9 + i * 0.1
      // Trigger reactivity like espStore deep updates
      espStore.devices = [...espStore.devices]
      await nextTick()
      await flushPromises()
    }

    expect(getStatsMock).toHaveBeenCalledTimes(1)
    // Values stay visible (no loading flicker to "…")
    expect(wrapper.text()).toContain('21,2')
    expect(wrapper.text()).toContain('Temperatur 24h (Min–Max)')

    wrapper.unmount()
  })

  it('should refetch when lead temperature sensor identity changes', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const espStore = useEspStore()
    espStore.devices = [makeDevice(24.9) as never]

    const wrapper = mount(ZoneTileInsightBlock, {
      props: { zone: makeZone() },
      global: { plugins: [pinia] },
    })

    await flushPromises()
    expect(getStatsMock).toHaveBeenCalledTimes(1)

    getStatsMock.mockResolvedValueOnce({
      stats: { min_value: 20.0, max_value: 25.0, avg_value: 22.5, count: 50 },
    })

    espStore.devices = [
      {
        ...makeDevice(22),
        sensors: [
          {
            gpio: 4,
            sensor_type: 'ds18b20',
            name: 'Temp Probe',
            raw_value: 22,
            quality: 'good',
            unit: '°C',
          },
        ],
      } as never,
    ]

    await nextTick()
    await flushPromises()

    expect(getStatsMock).toHaveBeenCalledTimes(2)
    expect(getStatsMock.mock.calls[1]?.[0]).toBe('ESP_TEST_001')
    expect(getStatsMock.mock.calls[1]?.[1]).toBe(4)

    wrapper.unmount()
  })
})

describe('pickZoneLeadTemperatureSensor', () => {
  it('should pick a stable lead when priorities tie', () => {
    const devices = [
      {
        esp_id: 'ESP_B',
        zone_id: 'z1',
        sensors: [{ gpio: 5, sensor_type: 'ds18b20' }],
      },
      {
        esp_id: 'ESP_A',
        zone_id: 'z1',
        sensors: [{ gpio: 9, sensor_type: 'ds18b20' }],
      },
    ] as never[]

    const getDeviceId = (d: { esp_id: string }) => d.esp_id
    const first = pickZoneLeadTemperatureSensor(devices as never, 'z1', getDeviceId as never)
    const reversed = pickZoneLeadTemperatureSensor(
      [...devices].reverse() as never,
      'z1',
      getDeviceId as never,
    )

    expect(first).toEqual({ espId: 'ESP_A', gpio: 9, sensorType: 'ds18b20' })
    expect(reversed).toEqual(first)
  })
})
