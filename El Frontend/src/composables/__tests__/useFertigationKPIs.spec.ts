/**
 * Test Suite: useFertigationKPIs Composable
 *
 * Tests KPI calculation, trend detection, health status, and WebSocket integration.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { ref } from 'vue'
import { useFertigationKPIs } from '../useFertigationKPIs'
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

// =============================================================================
// Mock Sensor Data
// =============================================================================

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

describe('useFertigationKPIs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // =========================================================================
  // Initialization
  // =========================================================================

  it('should initialize with null values', () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    vi.mocked(sensorsApi.queryData).mockResolvedValue(createMockResponse([]))
    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    expect(kpi.value.inflowValue).toBe(null)
    expect(kpi.value.runoffValue).toBe(null)
    expect(kpi.value.difference).toBe(null)
    expect(kpi.value.healthStatus).toBe('ok')
    expect(kpi.value.dataQuality).toBe('error')
  })

  // =========================================================================
  // Data Loading
  // =========================================================================

  it('should load initial data from API', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(2.5, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(3.2, '2026-04-14T10:00:05Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    // Wait for async load
    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.inflowValue).toBe(2.5)
    expect(kpi.value.runoffValue).toBe(3.2)
    expect(kpi.value.difference).toBe(0.7) // 3.2 - 2.5
  })

  // =========================================================================
  // Difference Calculation
  // =========================================================================

  it('should calculate difference correctly', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(2.5, '2026-04-14T10:00:00Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.difference).toBe(1.5)
  })

  it('should set difference to null if one sensor has no data', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.difference).toBe(null)
  })

  // =========================================================================
  // Data Quality
  // =========================================================================

  it('should report good data quality when both sensors have data', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(2.5, '2026-04-14T10:00:00Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.dataQuality).toBe('good')
  })

  it('should report degraded data quality when only one sensor has data', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.dataQuality).toBe('degraded')
  })

  // =========================================================================
  // Health Status
  // =========================================================================

  it('should report ok status when difference is below warning threshold', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(1.2, '2026-04-14T10:00:00Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
      diffWarningThreshold: ref(0.5),
      diffCriticalThreshold: ref(0.8),
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.healthStatus).toBe('ok')
    expect(kpi.value.healthReason).toBe('')
  })

  it('should report warning status when difference is between warning and critical', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(1.6, '2026-04-14T10:00:00Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
      diffWarningThreshold: ref(0.5),
      diffCriticalThreshold: ref(0.8),
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.healthStatus).toBe('warning')
    expect(kpi.value.healthReason).toContain('0.60')
  })

  it('should report alarm status when difference exceeds critical threshold', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(2.0, '2026-04-14T10:00:00Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
      diffWarningThreshold: ref(0.5),
      diffCriticalThreshold: ref(0.8),
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.healthStatus).toBe('alarm')
    expect(kpi.value.healthReason).toContain('1.00')
  })

  // =========================================================================
  // Staleness Detection
  // =========================================================================

  it('should calculate staleness between inflow and runoff measurements', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(2.0, '2026-04-14T10:00:30Z')]) // 30s later

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.stalenessSeconds).toBe(30)
  })

  it('should report warning when staleness exceeds 5 minutes', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(2.0, '2026-04-14T10:10:00Z')]) // 10min later

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(kpi.value.healthStatus).toBe('warning')
    expect(kpi.value.healthReason).toContain('600s')
  })

  // =========================================================================
  // Error Handling
  // =========================================================================

  it('should handle API errors gracefully', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    vi.mocked(sensorsApi.queryData).mockRejectedValue(new Error('API Error'))
    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { kpi, error } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    expect(error.value).toContain('API Error')
    expect(kpi.value.dataQuality).toBe('error')
  })

  // =========================================================================
  // Reload
  // =========================================================================

  it('should provide a reload function to refresh data', async () => {
    const inflowId = ref('sensor-inflow')
    const runoffId = ref('sensor-runoff')

    const inflowData = createMockResponse([createMockReading(1.0, '2026-04-14T10:00:00Z')])
    const runoffData = createMockResponse([createMockReading(2.0, '2026-04-14T10:00:00Z')])

    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    vi.mocked(websocketService.on).mockReturnValue(() => {})

    const { reload } = useFertigationKPIs({
      inflowSensorId: inflowId,
      runoffSensorId: runoffId,
    })

    await new Promise(resolve => setTimeout(resolve, 50))

    // Reset mocks and call reload
    vi.mocked(sensorsApi.queryData).mockClear()
    vi.mocked(sensorsApi.queryData)
      .mockResolvedValueOnce(inflowData)
      .mockResolvedValueOnce(runoffData)

    await reload()

    expect(sensorsApi.queryData).toHaveBeenCalledTimes(2)
  })
})
