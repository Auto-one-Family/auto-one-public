import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useSensorSubzoneCoverage } from '@/composables/useSensorSubzoneCoverage'

vi.mock('@/api/subzones', () => ({
  subzonesApi: {
    getSensorAssignments: vi.fn(),
    assignSensor: vi.fn(),
    removeSensor: vi.fn(),
  },
}))

import { subzonesApi } from '@/api/subzones'

describe('useSensorSubzoneCoverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should list subzones covered by a sensor from junction only', async () => {
    vi.mocked(subzonesApi.getSensorAssignments).mockImplementation(async (_esp, subzoneId) => {
      if (subzoneId === 'topf_1' || subzoneId === 'topf_2') {
        return {
          success: true,
          message: 'ok',
          esp_id: 'ESP_AEAE64',
          subzone_id: subzoneId,
          assignments: [
            {
              id: 'a1',
              sensor_config_id: 'sensor-1',
              subzone_config_id: 'uuid-' + subzoneId,
              assigned_at: '2026-07-23T00:00:00Z',
            },
          ],
          total_count: 1,
        }
      }
      return {
        success: true,
        message: 'ok',
        esp_id: 'ESP_AEAE64',
        subzone_id: subzoneId,
        assignments: [],
        total_count: 0,
      }
    })

    const { listSubzonesForSensor } = useSensorSubzoneCoverage()
    const covered = await listSubzonesForSensor('ESP_AEAE64', 'sensor-1', [
      { id: 'topf_1', name: 'Topf 1' },
      { id: 'topf_2', name: 'Topf 2' },
      { id: 'topf_3', name: 'Topf 3' },
    ])

    expect(covered.map((c) => c.subzoneId)).toEqual(['topf_1', 'topf_2'])
    expect(covered.every((c) => !c.name.includes('uuid'))).toBe(true)
  })

  it('should sync coverage via assign and remove only', async () => {
    vi.mocked(subzonesApi.assignSensor).mockResolvedValue({
      id: 'new',
      sensor_config_id: 'sensor-1',
      subzone_config_id: 'uuid-topf_2',
      assigned_at: '2026-07-23T00:00:00Z',
    })
    vi.mocked(subzonesApi.removeSensor).mockResolvedValue({
      success: true,
      message: 'removed',
      esp_id: 'ESP_AEAE64',
      subzone_id: 'topf_1',
    } as never)

    const { syncSensorCoverage } = useSensorSubzoneCoverage()
    await syncSensorCoverage('ESP_AEAE64', 'sensor-1', ['topf_1'], ['topf_2'])

    expect(subzonesApi.assignSensor).toHaveBeenCalledWith('ESP_AEAE64', 'topf_2', 'sensor-1')
    expect(subzonesApi.removeSensor).toHaveBeenCalledWith('ESP_AEAE64', 'topf_1', 'sensor-1')
  })
})
