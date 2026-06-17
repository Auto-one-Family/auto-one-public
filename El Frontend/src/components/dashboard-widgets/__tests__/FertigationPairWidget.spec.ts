/**
 * Test Suite: FertigationPairWidget Component
 *
 * Tests rendering, prop binding, and user interactions.
 */

import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import FertigationPairWidget from '../FertigationPairWidget.vue'

// Mock the composable
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

// Mock HistoricalChart
vi.mock('@/components/charts/HistoricalChart.vue', () => ({
  default: {
    name: 'HistoricalChart',
    template: '<div class="historical-chart-mock"></div>',
    props: ['sensors', 'timeRange', 'height', 'enableLiveUpdates'],
  },
}))

// Mock sensor config
vi.mock('@/utils/sensorDefaults', () => ({
  SENSOR_TYPE_CONFIG: {
    ec: { unit: 'mS/cm', label: 'Elektrische Leitfähigkeit' },
    ph: { unit: 'pH', label: 'pH-Wert' },
  },
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}))

describe('FertigationPairWidget', () => {
  // =========================================================================
  // Rendering
  // =========================================================================

  it('should render with EC sensor type', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('EC Fertigation')
  })

  it('should render with pH sensor type', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ph',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('pH Fertigation')
  })

  it('should use custom title when provided', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
        title: 'Custom Title',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('Custom Title')
  })

  // =========================================================================
  // KPI Display
  // =========================================================================

  it('should display inflow KPI card', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    const inflowCard = wrapper.find('[data-testid="fertigation-inflow-kpi-ec"]')
    expect(inflowCard.exists()).toBe(true)
    expect(inflowCard.text()).toContain('Inflow')
    expect(inflowCard.text()).toContain('2.50')
  })

  it('should display runoff KPI card', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    const runoffCard = wrapper.find('[data-testid="fertigation-runoff-kpi-ec"]')
    expect(runoffCard.exists()).toBe(true)
    expect(runoffCard.text()).toContain('Runoff')
    expect(runoffCard.text()).toContain('3.20')
  })

  it('should display difference value', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    const diffSection = wrapper.find('[data-testid="fertigation-ec-diff-value"]')
    expect(diffSection.exists()).toBe(true)
    expect(diffSection.text()).toContain('0.70')
  })

  // =========================================================================
  // Health Status Colors
  // =========================================================================

  it('should apply ok status styling for good health', async () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    await flushPromises()

    const diffSection = wrapper.find('[data-testid="fertigation-ec-diff-value"]')
    expect(diffSection.classes()).toContain('bg-success-500/20')
  })

  // =========================================================================
  // Zone Label
  // =========================================================================

  it('should display zone label when provided', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
        zoneLabel: 'Zone A / Subzone 1',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('Zone A / Subzone 1')
  })

  // =========================================================================
  // Reference Bands
  // =========================================================================

  it('should display reference bands when provided', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ph',
        referenceBands: [
          { label: 'Ideal', min: 6.0, max: 7.0, color: '#10b981' },
        ],
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('Ideal')
    expect(wrapper.text()).toContain('6.00')
    expect(wrapper.text()).toContain('7.00')
  })

  // =========================================================================
  // Data Quality Indicator
  // =========================================================================

  it('should display data quality status as good', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('Beide Sensoren aktiv')
  })

  // =========================================================================
  // Chart Embedding
  // =========================================================================

  it('should render embedded HistoricalChart', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: { template: '<div class="chart-mock"></div>' },
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.find('.chart-mock').exists()).toBe(true)
  })

  // =========================================================================
  // Reload Button
  // =========================================================================

  it('should have reload button', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    const reloadBtn = wrapper.find('[data-testid="fertigation-reload-ec"]')
    expect(reloadBtn.exists()).toBe(true)
  })

  // =========================================================================
  // Unit Display
  // =========================================================================

  it('should display correct unit for EC', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ec',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('mS/cm')
  })

  it('should display correct unit for pH', () => {
    const wrapper = mount(FertigationPairWidget, {
      props: {
        inflowSensorId: 'sensor-inflow',
        runoffSensorId: 'sensor-runoff',
        sensorType: 'ph',
      },
      global: {
        stubs: {
          HistoricalChart: true,
          TrendingUp: true,
          TrendingDown: true,
          AlertCircle: true,
          Droplet: true,
          Activity: true,
        },
      },
    })

    expect(wrapper.text()).toContain('pH')
  })
})
