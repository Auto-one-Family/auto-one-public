import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import FertigationPairWidget from '@/components/dashboard-widgets/FertigationPairWidget.vue'

const INFLOW_CONFIG_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const RUNOFF_CONFIG_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'

vi.mock('@/composables/useFertigationKPIs', () => ({
  useFertigationKPIs: () => ({
    kpi: ref({
      inflowValue: 2.5,
      runoffValue: 3.2,
      difference: 0.7,
      differenceTrend: 'stable',
      healthStatus: 'ok',
      healthReason: '',
      lastInflowTime: '2026-04-14T10:00:00Z',
      lastRunoffTime: '2026-04-14T10:00:05Z',
      stalenessSeconds: 5,
      dataQuality: 'good',
    }),
    isLoading: ref(false),
    error: ref(null),
    reload: vi.fn(),
  }),
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [
      {
        sensors: [
          {
            config_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
            gpio: 34,
            sensor_type: 'ec',
            name: 'Zufluss',
            unit: 'mS/cm',
          },
          {
            config_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
            gpio: 35,
            sensor_type: 'ec',
            name: 'Ablauf',
            unit: 'mS/cm',
          },
        ],
      },
    ],
    getDeviceId: () => 'ESP_REAL',
  }),
}))

vi.mock('@/utils/sensorDefaults', () => ({
  getSensorConfig: () => ({ unit: 'mS/cm', decimals: 2 }),
}))

describe('FertigationPairWidget chart', () => {
  it('should chart store config_id sensors instead of mock-esp', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: INFLOW_CONFIG_ID,
        runoffSensorId: RUNOFF_CONFIG_ID,
        sensorType: 'ec',
      },
      global: {
        stubs: {
          MultiSensorChart: {
            name: 'MultiSensorChart',
            props: ['sensors'],
            template: '<div class="multi-sensor-chart-stub" />',
          },
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    const chart = wrapper.findComponent({ name: 'MultiSensorChart' })
    const sensors = chart.props('sensors') as Array<{ espId: string; gpio: number }>
    expect(sensors).toHaveLength(2)
    expect(sensors.every((row) => row.espId === 'ESP_REAL')).toBe(true)
    expect(sensors.some((row) => row.espId === 'mock-esp')).toBe(false)
    expect(sensors.map((row) => row.gpio).sort()).toEqual([34, 35])
  })
})
