/**
 * HistoricalChart hover readout — stats row replaces floating tooltip
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'

const queryData = vi.fn()
const getStats = vi.fn()

vi.mock('@/api/sensors', () => ({
  sensorsApi: {
    queryData: (...args: unknown[]) => queryData(...args),
    getStats: (...args: unknown[]) => getStats(...args),
  },
}))

vi.mock('@/stores/esp', () => ({
  useEspStore: () => ({
    devices: [],
  }),
}))

vi.mock('vue-chartjs', () => ({
  Line: defineComponent({
    name: 'Line',
    props: {
      data: { type: Object, required: true },
      options: { type: Object, required: true },
      plugins: { type: Array, default: () => [] },
    },
    setup(props) {
      return () => h('canvas', { class: 'chartjs-line', 'data-tooltip-enabled': String(props.options?.plugins?.tooltip?.enabled !== false) })
    },
  }),
}))

vi.mock('chart.js', () => ({
  Chart: { register: vi.fn() },
  CategoryScale: {},
  LinearScale: {},
  PointElement: {},
  LineElement: {},
  Tooltip: {},
  Filler: {},
  TimeScale: {},
}))

vi.mock('chartjs-adapter-date-fns', () => ({}))
vi.mock('chartjs-plugin-annotation', () => ({ default: {} }))
vi.mock('chartjs-plugin-zoom', () => ({ default: {} }))

import HistoricalChart from '@/components/charts/HistoricalChart.vue'

describe('HistoricalChart hover readout', () => {
  beforeEach(() => {
    queryData.mockReset()
    getStats.mockReset()

    const ts = new Date('2026-07-23T11:00:00.000Z')
    queryData.mockResolvedValue({
      readings: [
        {
          timestamp: ts.toISOString(),
          processed_value: 1396.23,
          raw_value: 1396.23,
          min_value: 1376,
          max_value: 1413,
        },
        {
          timestamp: new Date('2026-07-23T12:00:00.000Z').toISOString(),
          processed_value: 1400,
          raw_value: 1400,
          min_value: 1380,
          max_value: 1420,
        },
      ],
      resolution: '1h',
    })
    getStats.mockResolvedValue({
      stats: {
        min_value: 1185.7,
        max_value: 1436.5,
        avg_value: 1390.99,
        std_dev: 25.78,
        reading_count: 2,
      },
    })
  })

  it('should disable floating Chart.js tooltip', async () => {
    const wrapper = mount(HistoricalChart, {
      props: {
        espId: 'ESP_TEST',
        gpio: 34,
        sensorType: 'ec',
        unit: 'µS/cm',
        timeRange: '24h',
      },
    })
    await flushPromises()

    const line = wrapper.findComponent({ name: 'Line' })
    expect(line.exists()).toBe(true)
    expect(line.props('options').plugins.tooltip.enabled).toBe(false)
  })

  it('should show hover point in stats row instead of summary', async () => {
    const wrapper = mount(HistoricalChart, {
      props: {
        espId: 'ESP_TEST',
        gpio: 34,
        sensorType: 'ec',
        unit: 'µS/cm',
        timeRange: '24h',
        color: '#60a5fa',
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Min')
    // de-DE with thousands separator (formatNumber) — EC values ≥1000
    expect(wrapper.text()).toContain('1.390,99')

    const onHover = wrapper.findComponent({ name: 'Line' }).props('options').onHover as (
      event: unknown,
      elements: Array<{ index: number; datasetIndex: number }>,
    ) => void

    onHover({}, [{ index: 0, datasetIndex: 0 }])
    await flushPromises()

    expect(wrapper.find('.historical-chart__stats--hover').exists()).toBe(true)
    expect(wrapper.text()).toContain('Avg')
    expect(wrapper.text()).toContain('1.396,23')
    expect(wrapper.text()).toContain('1.376,00')
    expect(wrapper.text()).toContain('1.413,00')
    expect(wrapper.text()).not.toContain('Punkte')

    onHover({}, [])
    await flushPromises()
    expect(wrapper.find('.historical-chart__stats--hover').exists()).toBe(false)
    expect(wrapper.text()).toContain('Punkte')
  })
})
