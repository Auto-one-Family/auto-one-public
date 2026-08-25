/**
 * S4 / AUT-1388: empty inflow/runoff IDs skip the KPI fetch (widget stays).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { useFertigationKPIs } from '@/composables/useFertigationKPIs'
import { sensorsApi } from '@/api/sensors'
import { websocketService } from '@/services/websocket'
import type { SensorReading, SensorDataResponse } from '@/types'

vi.mock('@/api/sensors')
vi.mock('@/services/websocket')
vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}))

const createMockReading = (value: number, timestamp: string): SensorReading => ({
  timestamp,
  raw_value: value,
  processed_value: value,
  unit: 'mS/cm',
  quality: 'good',
  sensor_type: 'ec',
})

const createMockResponse = (readings: SensorReading[]): SensorDataResponse => ({
  success: true,
  esp_id: 'ESP_TEST',
  gpio: 34,
  sensor_type: 'ec',
  readings,
  count: readings.length,
  resolution: 'raw',
  time_range: {
    start: '2026-04-14T00:00:00Z',
    end: '2026-04-14T23:59:59Z',
  },
})

describe('useFertigationKPIs empty pair', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(websocketService.on).mockReturnValue(() => {})
  })

  it('should skip fetch when inflow id is empty', async () => {
    const inflowId = ref('')
    const runoffId = ref('sensor-runoff')

    const Wrapper = defineComponent({
      setup() {
        return useFertigationKPIs({
          inflowSensorId: inflowId,
          runoffSensorId: runoffId,
        })
      },
      template: '<div />',
    })

    const wrapper = mount(Wrapper)
    await flushPromises()

    expect(sensorsApi.queryData).not.toHaveBeenCalled()
    expect(wrapper.vm.error).toBe('Sensor IDs nicht konfiguriert')
    wrapper.unmount()
  })

  it('should reset stale KPIs when a configured pair is cleared', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(createMockResponse([
        createMockReading(1.2, '2026-04-14T10:00:00Z'),
      ]))
      .mockResolvedValueOnce(createMockResponse([
        createMockReading(2.4, '2026-04-14T10:00:00Z'),
      ]))

    const sensorDataCallbacks: Array<(msg: { type: string; data: Record<string, unknown> }) => void> = []
    vi.mocked(websocketService.on).mockImplementation((type, cb) => {
      if (type === 'sensor_data') {
        sensorDataCallbacks.push(cb as (msg: { type: string; data: Record<string, unknown> }) => void)
      }
      return () => {}
    })

    const Wrapper = defineComponent({
      setup() {
        return useFertigationKPIs({
          inflowSensorId: inflowId,
          runoffSensorId: runoffId,
        })
      },
      template: '<div />',
    })

    const wrapper = mount(Wrapper)
    await flushPromises()

    expect(wrapper.vm.kpi.inflowValue).toBe(1.2)
    expect(wrapper.vm.kpi.runoffValue).toBe(2.4)
    expect(wrapper.vm.error).toBeNull()

    inflowId.value = ''
    await flushPromises()

    expect(sensorsApi.queryData).toHaveBeenCalledTimes(2)
    expect(wrapper.vm.error).toBe('Sensor IDs nicht konfiguriert')
    expect(wrapper.vm.kpi.inflowValue).toBeNull()
    expect(wrapper.vm.kpi.runoffValue).toBeNull()
    expect(wrapper.vm.kpi.difference).toBeNull()
    expect(wrapper.vm.kpi.lastInflowTime).toBeNull()
    expect(wrapper.vm.kpi.lastRunoffTime).toBeNull()
    expect(wrapper.vm.kpi.dataQuality).toBe('error')
    expect(wrapper.vm.kpi.healthStatus).toBe('ok')
    expect(wrapper.vm.kpi.healthReason).toBe('')

    sensorDataCallbacks[1]!({
      type: 'sensor_data',
      data: {
        config_id: 'sensor-runoff',
        value: 3.1,
        timestamp: '2026-04-14T10:05:00.000Z',
      },
    })

    expect(wrapper.vm.kpi.runoffValue).toBeNull()
    expect(wrapper.vm.kpi.difference).toBeNull()
    wrapper.unmount()
  })
})
