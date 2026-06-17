/**
 * useFertigationKPIs — WebSocket Pfad (sensor_data)
 * Läuft in gemounteter Komponente, damit onMounted die Listener registriert.
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

describe('useFertigationKPIs WebSocket', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('wendet sensor_data mit message.data.value auf Inflow/Runoff an', async () => {
    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(2.0, '2026-04-14T10:00:10Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    const sensorDataCallbacks: Array<(msg: { type: string; data: Record<string, unknown> }) => void> = []
    vi.mocked(websocketService.on).mockImplementation((type, cb) => {
      if (type === 'sensor_data') {
        sensorDataCallbacks.push(cb as (msg: { type: string; data: Record<string, unknown> }) => void)
      }
      return () => {}
    })

    const inflowId = ref('sensor-inflow')
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
    expect(sensorDataCallbacks.length).toBe(2)

    sensorDataCallbacks[0]!({
      type: 'sensor_data',
      data: {
        config_id: 'sensor-inflow',
        value: 1.5,
        timestamp: '2026-04-14T10:05:00.000Z',
      },
    })
    sensorDataCallbacks[1]!({
      type: 'sensor_data',
      data: {
        config_id: 'sensor-runoff',
        value: 2.8,
        timestamp: '2026-04-14T10:05:05.000Z',
      },
    })

    const vm = wrapper.vm as unknown as {
      kpi: { inflowValue: number; runoffValue: number; difference: number; dataQuality: string }
    }
    expect(vm.kpi.inflowValue).toBe(1.5)
    expect(vm.kpi.runoffValue).toBe(2.8)
    expect(vm.kpi.difference).toBeCloseTo(1.3, 5)
    expect(vm.kpi.dataQuality).toBe('good')
    wrapper.unmount()
  })
})
