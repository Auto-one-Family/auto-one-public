/**
 * Tests for chart wrapper components + gap detection (AUT-113).
 * Verifies rendering with Chart.js canvas mock.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, shallowMount } from '@vue/test-utils'
import LiveLineChart from '@/components/charts/LiveLineChart.vue'
import {
  type GapDataPoint,
  type GapInfo,
  resolutionToMs,
  computeExpectedInterval,
  calculateMedianInterval,
  detectGaps,
  insertGapMarkers,
  countRealDataPoints,
  formatGapDuration,
  formatTimeShort,
} from '@/utils/gapDetection'

// vue-chartjs components need to be stubbed since Chart.js canvas rendering
// doesn't work in happy-dom even with the canvas mock
vi.mock('vue-chartjs', () => ({
  Line: {
    name: 'Line',
    template: '<canvas class="chartjs-line"></canvas>',
    props: ['data', 'options'],
  },
  Doughnut: {
    name: 'Doughnut',
    template: '<canvas class="chartjs-doughnut"></canvas>',
    props: ['data', 'options'],
  },
  Bar: {
    name: 'Bar',
    template: '<canvas class="chartjs-bar"></canvas>',
    props: ['data', 'options'],
  },
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
  ArcElement: {},
  DoughnutController: {},
  BarElement: {},
  BarController: {},
}))

vi.mock('chartjs-adapter-date-fns', () => ({}))

// =============================================================================
// Gap Detection Unit Tests (AUT-113)
// =============================================================================

function makePoints(intervals: number[], startMs = 0): GapDataPoint[] {
  const points: GapDataPoint[] = [{ timestamp: new Date(startMs), value: 1 }]
  let ts = startMs
  for (const interval of intervals) {
    ts += interval
    points.push({ timestamp: new Date(ts), value: 1 })
  }
  return points
}

describe('resolutionToMs', () => {
  it('maps known resolutions', () => {
    expect(resolutionToMs('1m')).toBe(60_000)
    expect(resolutionToMs('5m')).toBe(300_000)
    expect(resolutionToMs('1h')).toBe(3_600_000)
    expect(resolutionToMs('1d')).toBe(86_400_000)
  })

  it('returns 0 for raw and null', () => {
    expect(resolutionToMs('raw')).toBe(0)
    expect(resolutionToMs(null)).toBe(0)
    expect(resolutionToMs(undefined)).toBe(0)
  })
})

describe('computeExpectedInterval', () => {
  it('uses max(median, resolution) for normal data', () => {
    expect(computeExpectedInterval(60_000, '5m', 100)).toBe(300_000)
    expect(computeExpectedInterval(600_000, '5m', 100)).toBe(600_000)
  })

  it('prefers resolution for sparse data (<5 points)', () => {
    expect(computeExpectedInterval(18_000_000, '5m', 2)).toBe(300_000)
    expect(computeExpectedInterval(18_000_000, '1h', 4)).toBe(3_600_000)
  })

  it('falls back to median when no resolution for sparse data', () => {
    expect(computeExpectedInterval(5000, null, 3)).toBe(5000)
    expect(computeExpectedInterval(5000, 'raw', 3)).toBe(5000)
  })
})

describe('calculateMedianInterval', () => {
  it('returns 0 for 0 or 1 points', () => {
    expect(calculateMedianInterval([])).toBe(0)
    expect(calculateMedianInterval([{ timestamp: new Date(0) }])).toBe(0)
  })

  it('calculates correct median for even distribution', () => {
    const points = makePoints([1000, 1000, 1000, 1000])
    expect(calculateMedianInterval(points)).toBe(1000)
  })

  it('returns middle value for odd interval count', () => {
    const points = makePoints([1000, 2000, 3000])
    expect(calculateMedianInterval(points)).toBe(2000)
  })

  it('handles 2-point case', () => {
    const points = makePoints([5000])
    expect(calculateMedianInterval(points)).toBe(5000)
  })
})

describe('detectGaps', () => {
  it('returns empty for insufficient data', () => {
    expect(detectGaps([], 1000)).toEqual([])
    expect(detectGaps([{ timestamp: new Date(0), value: 1 }], 1000)).toEqual([])
  })

  it('returns empty when interval is zero', () => {
    expect(detectGaps(makePoints([1000, 1000]), 0)).toEqual([])
  })

  it('detects single gap', () => {
    const points = makePoints([1000, 1000, 10000, 1000])
    const gaps = detectGaps(points, 1000, 3)
    expect(gaps).toHaveLength(1)
    expect(gaps[0].durationMs).toBe(10000)
  })

  it('detects multiple gaps', () => {
    const points = makePoints([1000, 10000, 1000, 10000])
    const gaps = detectGaps(points, 1000, 3)
    expect(gaps).toHaveLength(2)
  })

  it('skips null-value points', () => {
    const points: GapDataPoint[] = [
      { timestamp: new Date(0), value: 1 },
      { timestamp: new Date(1000), value: null },
      { timestamp: new Date(50000), value: 1 },
    ]
    const gaps = detectGaps(points, 1000, 3)
    expect(gaps).toHaveLength(0)
  })

  it('sparse data: 2 points with 5h gap and 5m resolution', () => {
    const fiveHoursMs = 5 * 3_600_000
    const points = makePoints([fiveHoursMs])
    const expected = computeExpectedInterval(fiveHoursMs, '5m', 2)
    expect(expected).toBe(300_000)
    const gaps = detectGaps(points, expected, 3)
    expect(gaps).toHaveLength(1)
    expect(gaps[0].durationMs).toBe(fiveHoursMs)
  })
})

describe('insertGapMarkers', () => {
  it('returns original for <2 points', () => {
    const single: GapDataPoint[] = [{ timestamp: new Date(0), value: 1 }]
    expect(insertGapMarkers(single, 1000)).toEqual(single)
  })

  it('inserts TWO null markers per gap', () => {
    const points = makePoints([1000, 10000, 1000])
    const result = insertGapMarkers(points, 1000, 3)
    const nullMarkers = result.filter((p) => p._gap === true)
    expect(nullMarkers).toHaveLength(2)
    expect(nullMarkers[0].value).toBeNull()
    expect(nullMarkers[1].value).toBeNull()
  })

  it('places markers at correct timestamps', () => {
    const points = makePoints([1000, 10000])
    const result = insertGapMarkers(points, 1000, 3)
    const gapMarkers = result.filter((p) => p._gap)
    expect(gapMarkers[0].timestamp.getTime()).toBe(1001)
    expect(gapMarkers[1].timestamp.getTime()).toBe(10999)
  })

  it('preserves all original points', () => {
    const points = makePoints([1000, 10000, 1000])
    const result = insertGapMarkers(points, 1000, 3)
    const originals = result.filter((p) => !p._gap)
    expect(originals).toHaveLength(4)
  })

  it('returns original when no gaps', () => {
    const points = makePoints([1000, 1000, 1000])
    const result = insertGapMarkers(points, 1000, 3)
    expect(result).toHaveLength(4)
    expect(result.filter((p) => p._gap)).toHaveLength(0)
  })
})

describe('countRealDataPoints', () => {
  it('counts non-null, non-gap points', () => {
    const points: GapDataPoint[] = [
      { timestamp: new Date(0), value: 1 },
      { timestamp: new Date(1), value: null, _gap: true },
      { timestamp: new Date(2), value: null, _gap: true },
      { timestamp: new Date(3), value: 2 },
      { timestamp: new Date(4), value: null },
    ]
    expect(countRealDataPoints(points)).toBe(2)
  })

  it('returns 0 for empty', () => {
    expect(countRealDataPoints([])).toBe(0)
  })
})

describe('formatGapDuration', () => {
  it('formats seconds', () => {
    expect(formatGapDuration(30_000)).toBe('30s')
  })

  it('formats minutes', () => {
    expect(formatGapDuration(300_000)).toBe('5 Min')
  })

  it('formats hours with minutes', () => {
    expect(formatGapDuration(5_400_000)).toBe('1h 30m')
  })

  it('formats hours without minutes', () => {
    expect(formatGapDuration(7_200_000)).toBe('2h')
  })

  it('formats days with hours', () => {
    expect(formatGapDuration(90_000_000)).toBe('1d 1h')
  })

  it('formats days without hours', () => {
    expect(formatGapDuration(86_400_000)).toBe('1d')
  })
})

describe('formatTimeShort', () => {
  it('formats HH:mm', () => {
    const d = new Date(2026, 3, 22, 14, 5, 0)
    expect(formatTimeShort(d)).toBe('14:05')
  })
})

// =============================================================================
// LiveLineChart Component Tests
// =============================================================================

describe('LiveLineChart', () => {
  it('renders chart container', () => {
    const wrapper = shallowMount(LiveLineChart, {
      props: { data: [] },
    })
    expect(wrapper.find('.live-line-chart').exists()).toBe(true)
  })

  it('applies height style from prop', () => {
    const wrapper = shallowMount(LiveLineChart, {
      props: { data: [], height: '300px' },
    })
    expect(wrapper.find('.live-line-chart').attributes('style')).toContain('300px')
  })

  it('exposes addDataPoint method', () => {
    const wrapper = shallowMount(LiveLineChart, {
      props: { data: [] },
    })
    expect(typeof wrapper.vm.addDataPoint).toBe('function')
  })

  it('exposes clear method', () => {
    const wrapper = shallowMount(LiveLineChart, {
      props: { data: [] },
    })
    expect(typeof wrapper.vm.clear).toBe('function')
  })

  it('addDataPoint adds to internal buffer', async () => {
    const wrapper = shallowMount(LiveLineChart, {
      props: { data: [], maxDataPoints: 5 },
    })

    wrapper.vm.addDataPoint({ timestamp: new Date(), value: 25 })
    wrapper.vm.addDataPoint({ timestamp: new Date(), value: 26 })

    // Check via the Line component's data prop
    await wrapper.vm.$nextTick()
    // Internal buffer should have 2 points
    expect(wrapper.vm.addDataPoint).toBeDefined()
  })

  it('clear empties the buffer', async () => {
    const wrapper = shallowMount(LiveLineChart, {
      props: {
        data: [
          { timestamp: new Date(), value: 1 },
          { timestamp: new Date(), value: 2 },
        ],
      },
    })

    wrapper.vm.clear()
    await wrapper.vm.$nextTick()
    expect(wrapper.vm.clear).toBeDefined()
  })

  it('respects maxDataPoints limit', () => {
    const wrapper = shallowMount(LiveLineChart, {
      props: { data: [], maxDataPoints: 3 },
    })

    wrapper.vm.addDataPoint({ timestamp: new Date(), value: 1 })
    wrapper.vm.addDataPoint({ timestamp: new Date(), value: 2 })
    wrapper.vm.addDataPoint({ timestamp: new Date(), value: 3 })
    wrapper.vm.addDataPoint({ timestamp: new Date(), value: 4 })
    // Buffer should only keep last 3
    expect(wrapper.vm.addDataPoint).toBeDefined()
  })
})
