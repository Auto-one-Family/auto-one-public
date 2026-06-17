import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import {
  CONTRACT_OPERATOR_ACTION,
  buildContractIntegritySignal,
  validateContractEvent,
} from '@/utils/contractEventMapper'
import { getOperatorActionGuidance } from '@/utils/eventTransformer'

const toastMocks = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  show: vi.fn(),
  dismiss: vi.fn(),
  dismissAll: vi.fn(),
}

vi.mock('@/composables/useToast', () => ({
  useToast: vi.fn(() => toastMocks),
}))

interface MinimalDevice {
  device_id: string
  name: string
  actuators: Array<{ gpio: number }>
}

const devices: MinimalDevice[] = [
  {
    device_id: 'ESP_TEST_001',
    name: 'ESP Test',
    actuators: [{ gpio: 5 }],
  },
]

const getDeviceId = (device: MinimalDevice): string => device.device_id

describe('Intent Contract Matrix T1-T6', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('T1: duplicate terminal actuator_response bleibt idempotent', () => {
    const store = useActuatorStore()
    const responseMessage = {
      data: {
        esp_id: 'ESP_TEST_001',
        gpio: 5,
        command: 'ON',
        success: true,
        correlation_id: 'corr-t1',
      },
    }

    store.handleActuatorResponse(responseMessage, devices, getDeviceId)
    store.handleActuatorResponse(responseMessage, devices, getDeviceId)

    expect(toastMocks.success).toHaveBeenCalledTimes(1)
  })

  it('T2: timeout ist non-terminaler Hinweis, spaete Response bleibt terminal', () => {
    const store = useActuatorStore()

    store.handleActuatorCommand(
      {
        data: {
          esp_id: 'ESP_TEST_001',
          gpio: 5,
          command: 'ON',
          correlation_id: 'corr-t2',
        },
      },
      devices,
      getDeviceId,
    )

    // ACTUATOR_RESPONSE_TIMEOUT_MS ist 30s; Timeout-Toast ist terminal (error), keine warning
    vi.advanceTimersByTime(30_001)
    expect(toastMocks.error).toHaveBeenCalledTimes(1)
    expect(toastMocks.warning).not.toHaveBeenCalled()

    store.handleActuatorResponse(
      {
        data: {
          esp_id: 'ESP_TEST_001',
          gpio: 5,
          command: 'ON',
          success: true,
          correlation_id: 'corr-t2',
        },
      },
      devices,
      getDeviceId,
    )

    expect(toastMocks.success).toHaveBeenCalledTimes(1)
  })

  it('T3: unbekannter WS Event-Typ wird als unknown_event erkannt', () => {
    const validation = validateContractEvent('future_event_type', {})
    expect(validation.kind).toBe('unknown_event')
  })

  it('T4: schema mismatch wird bei fehlendem Pflichtfeld erkannt', () => {
    const validation = validateContractEvent('actuator_response', {
      esp_id: 'ESP_TEST_001',
      gpio: 5,
      command: 'ON',
    })
    expect(validation.kind).toBe('mismatch')
  })

  it('T5: unknown_event erzeugt kritisches Integrationssignal', () => {
    const signal = buildContractIntegritySignal({
      kind: 'unknown_event',
      incomingEventType: 'future_event_type',
      reason: 'Unbekannter Event-Typ "future_event_type"',
      incomingData: { payload: 'raw' },
      correlationId: 'corr-t5',
      requestId: 'req-t5',
    })

    expect(signal.eventType).toBe('contract_unknown_event')
    expect(signal.severity).toBe('critical')
    expect(signal.data.operator_action).toBe(CONTRACT_OPERATOR_ACTION)
  })

  it('T6: contract_mismatch liefert Operator-Guidance mit Prioritaet critical', () => {
    const guidance = getOperatorActionGuidance({
      id: 'evt-6',
      timestamp: '2026-04-04T12:00:00Z',
      event_type: 'contract_mismatch',
      severity: 'critical',
      source: 'system',
      message: 'Integrationsstoerung',
      data: {
        original_event_type: 'config_response',
        mismatch_reason: 'config_response ohne status',
      },
    })

    expect(guidance).not.toBeNull()
    expect(guidance?.classification).toBe('integrationsproblem')
    expect(guidance?.priority).toBe('critical')
    expect(guidance?.nextAction).toContain(CONTRACT_OPERATOR_ACTION)
  })
})
