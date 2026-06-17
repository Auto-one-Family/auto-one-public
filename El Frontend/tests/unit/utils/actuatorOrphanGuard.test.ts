import { describe, expect, it } from 'vitest'
import {
  isMissingCorrelationActuator,
  isOrphanExternalActuatorFailure,
  shouldSuppressActuatorNotFoundErrorToast,
} from '@/utils/actuatorOrphanGuard'
import type { ESPDevice } from '@/api/esp'

const devices: ESPDevice[] = [
  {
    esp_id: 'ESP_TEST',
    name: 'Test',
    actuators: [{ gpio: 25, actuator_type: 'digital', state: false }],
    sensors: [],
  } as ESPDevice,
]

describe('actuatorOrphanGuard', () => {
  it('detects missing server correlation prefix', () => {
    expect(isMissingCorrelationActuator('missing-corr:act:ESP_TEST:1')).toBe(true)
    expect(isMissingCorrelationActuator('corr-uuid')).toBe(false)
  })

  it('flags orphan external actuator failure on unconfigured gpio', () => {
    expect(
      isOrphanExternalActuatorFailure({
        success: false,
        correlationId: 'missing-corr:act:ESP_TEST:1',
        command: 'UNKNOWN_COMMAND',
        espId: 'ESP_TEST',
        gpio: 0,
        devices,
        getDeviceId: d => d.esp_id,
        hasExistingIntent: false,
      }),
    ).toBe(true)
  })

  it('suppresses 1052 toast when gpio is not configured', () => {
    expect(
      shouldSuppressActuatorNotFoundErrorToast({
        errorCode: 1052,
        message: 'Actuator not configured on GPIO 0. Configure via API first.',
        espId: 'ESP_TEST',
        devices,
        getDeviceId: d => d.esp_id,
      }),
    ).toBe(true)
  })
})
