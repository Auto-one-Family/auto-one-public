/**
 * MultiSensorChart wiring tests — AUT-911 (B1-G3 Multi-Y) + AUT-912 (B2-1/B2-2 crosshair sync).
 *
 * Verifies the implementation contract via the stubbed vue-chartjs <Line> `options` prop
 * (deterministic, no running stack — the behavioural "both values at same X" visual check
 * stays a manual stack step, see VERIFY-PLAN-REPORT V1):
 *  - 3 distinct units → three Y axes (y / y1 / y2)            [B1-G3]
 *  - syncGroup set → crosshair sync wired, own box-zoom off,
 *    interpolate interaction mode                              [B2-1]
 *  - no syncGroup → no crosshair plugin, native 'index' mode  [no regress]
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import MultiSensorChart from '@/components/charts/MultiSensorChart.vue'
import { sensorsApi } from '@/api/sensors'
import type { ChartSensor } from '@/types'

// Chart.js canvas rendering doesn't work in happy-dom — stub the wrapper + lib (pattern: charts.test.ts)
vi.mock('vue-chartjs', () => ({
  Line: { name: 'Line', template: '<canvas class="chartjs-line"></canvas>', props: ['data', 'options', 'plugins'] },
}))
vi.mock('chart.js', () => ({
  Chart: { register: vi.fn() },
  CategoryScale: {}, LinearScale: {}, PointElement: {}, LineElement: {},
  BarElement: {}, Title: {}, Tooltip: {}, Legend: {}, TimeScale: {}, Filler: {},
}))
vi.mock('chartjs-adapter-date-fns', () => ({}))
vi.mock('chartjs-plugin-annotation', () => ({ default: {} }))
vi.mock('chartjs-plugin-zoom', () => ({ default: {} }))
vi.mock('chartjs-plugin-crosshair', () => ({ default: {} }))

// NOTE: vi.mock is hoisted — keep the readings literal inline (no top-level refs).
vi.mock('@/api/sensors', () => ({
  sensorsApi: {
    queryData: vi.fn().mockResolvedValue({
      readings: [
        { timestamp: new Date(Date.now() - 60_000).toISOString(), raw_value: 1, processed_value: 1, unit: 'x', quality: 'good' },
        { timestamp: new Date().toISOString(), raw_value: 2, processed_value: 2, unit: 'x', quality: 'good' },
      ],
    }),
  },
}))
vi.mock('@/services/websocket', () => ({
  websocketService: { subscribe: vi.fn(() => 'sub-1'), unsubscribe: vi.fn() },
}))
vi.mock('@/utils/logger', () => ({
  createLogger: () => ({ debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() }),
}))

// pH / EC / TDS = three distinct units (the runoff use-case)
const threeUnitSensors: ChartSensor[] = [
  { id: 'E1_1_ph', espId: 'E1', gpio: 1, sensorType: 'ph', name: 'pH', unit: 'pH', color: '#ff0000' },
  { id: 'E1_2_ec', espId: 'E1', gpio: 2, sensorType: 'ec', name: 'EC', unit: 'µS/cm', color: '#00ff00' },
  { id: 'E1_3_tds', espId: 'E1', gpio: 3, sensorType: 'tds', name: 'TDS', unit: 'ppm', color: '#0000ff' },
]

async function mountChart(extraProps: Record<string, unknown> = {}) {
  const wrapper = mount(MultiSensorChart, { props: { sensors: threeUnitSensors, ...extraProps } })
  await flushPromises()
  await wrapper.vm.$nextTick()
  await flushPromises()
  return wrapper
}

function lineOptions(wrapper: Awaited<ReturnType<typeof mountChart>>): any {
  const line = wrapper.findComponent({ name: 'Line' })
  expect(line.exists()).toBe(true)
  return line.props('options')
}

function linePlugins(wrapper: Awaited<ReturnType<typeof mountChart>>): unknown[] {
  const line = wrapper.findComponent({ name: 'Line' })
  expect(line.exists()).toBe(true)
  return (line.props('plugins') as unknown[]) ?? []
}

describe('MultiSensorChart — loaded X window', () => {
  it('should set scales.x.min/max to the loaded time window (no first-paint date flash)', async () => {
    const opts = lineOptions(await mountChart())
    expect(typeof opts.scales.x.min).toBe('number')
    expect(typeof opts.scales.x.max).toBe('number')
    expect(opts.scales.x.max - opts.scales.x.min).toBeGreaterThan(0)
    expect(opts.plugins.zoom.zoom.onZoomComplete).toEqual(expect.any(Function))
    expect(opts.plugins.zoom.pan.onPanComplete).toEqual(expect.any(Function))
  })

  it('should emit the next larger timeRange on wheel-out at full window', async () => {
    const wrapper = await mountChart({ timeRange: '24h' })
    const container = wrapper.find('.multi-sensor-chart__container')
    expect(container.exists()).toBe(true)
    await container.trigger('wheel', { deltaY: 120 })
    expect(wrapper.emitted('update:timeRange')?.[0]).toEqual(['7d'])
  })
})

describe('MultiSensorChart — visible-window zoom refetch (AUT-1329)', () => {
  beforeEach(() => {
    vi.mocked(sensorsApi.queryData).mockClear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('should debounced-refetch /sensors/data with finer resolution from the visible X window', async () => {
    const wrapper = await mountChart({ timeRange: '30d' })
    await flushPromises()
    vi.mocked(sensorsApi.queryData).mockClear()

    vi.useFakeTimers()
    const opts = lineOptions(wrapper)
    const end = Date.now()
    const start = end - 6 * 60 * 60 * 1000 // 6h visible → 5m buckets
    opts.plugins.zoom.zoom.onZoomComplete({
      chart: { scales: { x: { min: start, max: end } } },
    })

    // Debounce not fired yet
    expect(vi.mocked(sensorsApi.queryData)).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(400)
    await flushPromises()

    expect(vi.mocked(sensorsApi.queryData)).toHaveBeenCalled()
    const calls = vi.mocked(sensorsApi.queryData).mock.calls.map((c) => c[0])
    expect(calls.length).toBeGreaterThanOrEqual(3) // 3 sensors in fixture
    for (const args of calls) {
      expect(args.resolution).toBe('5m')
      expect(Date.parse(args.start_time as string)).toBe(start)
      expect(Date.parse(args.end_time as string)).toBe(end)
    }

    // x-domain follows the visible window (no jump back to 30d preset)
    const optsAfter = lineOptions(wrapper)
    expect(optsAfter.scales.x.min).toBe(start)
    expect(optsAfter.scales.x.max).toBe(end)
  })
})

describe('MultiSensorChart — multi-axis (AUT-911 B1-G3)', () => {
  it('renders three Y axes for three distinct units', async () => {
    const opts = lineOptions(await mountChart())
    expect(opts.scales.y).toBeDefined()
    expect(opts.scales.y1).toBeDefined()
    expect(opts.scales.y2).toBeDefined()
    expect(opts.scales.y2.position).toBe('right')
  })
})

describe('MultiSensorChart — crosshair sync (AUT-912)', () => {
  it('wires crosshair sync, disables its own zoom and uses interpolate when syncGroup is set', async () => {
    const wrapper = await mountChart({ syncGroup: 'zone-A' })
    const opts = lineOptions(wrapper)
    expect(opts.plugins.crosshair).toBeDefined()
    expect(opts.plugins.crosshair.sync.enabled).toBe(true)
    expect(opts.plugins.crosshair.sync.group).toBe('zone-A')
    expect(opts.plugins.crosshair.zoom.enabled).toBe(false)
    expect(opts.interaction.mode).toBe('interpolate')
    // Plugin is attached PER INSTANCE (not globally) so it cannot crash other chart types.
    expect(linePlugins(wrapper)).toHaveLength(1)
  })

  it('omits crosshair and keeps native index mode without syncGroup', async () => {
    const wrapper = await mountChart()
    const opts = lineOptions(wrapper)
    expect(opts.plugins.crosshair).toBeUndefined()
    expect(opts.interaction.mode).toBe('index')
    // No syncGroup → no per-instance crosshair plugin attached (no global registration either).
    expect(linePlugins(wrapper)).toHaveLength(0)
  })
})
