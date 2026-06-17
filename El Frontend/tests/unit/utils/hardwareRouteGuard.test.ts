import { describe, expect, it } from 'vitest'
import { shouldFallbackToHardwareOverview } from '@/utils/hardwareRouteGuard'

describe('hardwareRouteGuard', () => {
  it('returns true when L2 device disappears', () => {
    expect(
      shouldFallbackToHardwareOverview({
        currentLevel: 2,
        selectedEspId: 'ESP_0001',
        nextDeviceExists: false,
        previousDeviceExists: true,
      }),
    ).toBe(true)
  })

  it('returns false while device still exists', () => {
    expect(
      shouldFallbackToHardwareOverview({
        currentLevel: 2,
        selectedEspId: 'ESP_0001',
        nextDeviceExists: true,
        previousDeviceExists: true,
      }),
    ).toBe(false)
  })

  it('returns false for initial missing device states', () => {
    expect(
      shouldFallbackToHardwareOverview({
        currentLevel: 2,
        selectedEspId: 'ESP_0001',
        nextDeviceExists: false,
        previousDeviceExists: false,
      }),
    ).toBe(false)
  })
})
