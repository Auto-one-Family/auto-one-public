import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { ESPDevice } from '@/api/esp'
import {
  useActuatorStore,
  ACTUATOR_UI_COMMAND_COOLDOWN_MS,
} from '@/shared/stores/actuator.store'

const mockListIntentOutcomes = vi.fn()

vi.mock('@/api/intentOutcomes', () => ({
  listIntentOutcomes: (...args: unknown[]) => mockListIntentOutcomes(...args),
}))

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  show: vi.fn(),
  dismiss: vi.fn(),
  clear: vi.fn(),
  toasts: { value: [] },
}

vi.mock('@/composables/useToast', () => ({
  useToast: () => mockToast,
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

describe('actuator.store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.clearAllMocks()
    mockListIntentOutcomes.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('terminalisiert REST-started intents deterministisch per timeout', () => {
    const store = useActuatorStore()

    store.registerCommandIntent('ESP_1', 5, 'ON', 'corr-1', 'req-1')
    vi.advanceTimersByTime(30_000)

    const intent = store.getIntentSnapshot().find((entry) => (
      entry.intentType === 'actuator' &&
      entry.subjectId === 'ESP_1:5' &&
      entry.correlationId === 'corr-1'
    ))

    expect(intent).toBeDefined()
    expect(intent?.state).toBe('terminal_timeout')
    expect(intent?.terminalSource).toBe('actuator_timeout')
    expect(mockToast.error).toHaveBeenCalled()
  })

  it('terminalisiert config-intents deterministisch per timeout', () => {
    const store = useActuatorStore()

    const subjectId = store.registerConfigIntentFromRest({
      espId: 'ESP_2',
      scope: 'sensor:4:ds18b20',
      correlationId: 'corr-config-1',
      requestId: 'req-config-1',
    })
    vi.advanceTimersByTime(80_000)

    const intent = store.getIntentSnapshot().find((entry) => (
      entry.intentType === 'config' &&
      entry.subjectId === subjectId &&
      entry.correlationId === 'corr-config-1'
    ))

    expect(intent).toBeDefined()
    expect(intent?.state).toBe('terminal_timeout')
    expect(intent?.terminalSource).toBe('config_timeout')
    expect(mockToast.warning).toHaveBeenCalled()
  })

  it('verwirft stale actuator_status-events nach offline-reset-epoch', () => {
    const store = useActuatorStore()
    let device: ESPDevice = {
      device_id: 'ESP_1',
      esp_id: 'ESP_1',
      actuators: [{ gpio: 5, state: false, pwm_value: 0 }],
      sensors: [],
    } as unknown as ESPDevice

    store.markActuatorResetEpoch('ESP_1', 2_000, 5)

    store.handleActuatorStatus(
      {
        data: {
          esp_id: 'ESP_1',
          gpio: 5,
          state: 'on',
          timestamp: 1_700_000_000, // epoch seconds => 1700000000000 ms
        },
      },
      (_espId, patchFn) => {
        device = patchFn(device)
        return true
      },
    )

    const staleActuator = (device.actuators as Array<{ gpio: number; state: boolean }>).find((a) => a.gpio === 5)
    expect(staleActuator?.state).toBe(true)

    store.markActuatorResetEpoch('ESP_1', 1_700_000_001_000, 5)
    store.handleActuatorStatus(
      {
        data: {
          esp_id: 'ESP_1',
          gpio: 5,
          state: 'off',
          timestamp: 1_700_000_000, // older than reset epoch => ignored
        },
      },
      (_espId, patchFn) => {
        device = patchFn(device)
        return true
      },
    )

    const freshActuator = (device.actuators as Array<{ gpio: number; state: boolean }>).find((a) => a.gpio === 5)
    expect(freshActuator?.state).toBe(true)
  })

  it('akzeptiert relative actuator_status-timestamps und normalisiert uppercase states', () => {
    const store = useActuatorStore()
    let device: ESPDevice = {
      device_id: 'ESP_2',
      esp_id: 'ESP_2',
      actuators: [{ gpio: 9, state: false, pwm_value: 0 }],
      sensors: [],
    } as unknown as ESPDevice

    store.markActuatorResetEpoch('ESP_2', 1_700_000_001_000, 9)

    store.handleActuatorStatus(
      {
        data: {
          esp_id: 'ESP_2',
          gpio: 9,
          state: 'ON',
          timestamp: 123_456, // relative uptime -> not stale-guarded
        },
      },
      (_espId, patchFn) => {
        device = patchFn(device)
        return true
      },
    )

    const actuator = (device.actuators as Array<{ gpio: number; state: boolean }>).find((a) => a.gpio === 9)
    expect(actuator?.state).toBe(true)
  })

  it('lokalisiert actuator_response-Fehler und formatiert logic-Quelle lesbar', () => {
    const store = useActuatorStore()
    const devices = [{ device_id: 'ESP_6B27C8', esp_id: 'ESP_6B27C8', name: 'ESP_6B27C8' }] as ESPDevice[]

    store.handleActuatorResponse(
      {
        data: {
          esp_id: 'ESP_6B27C8',
          gpio: 25,
          success: false,
          command: 'ON',
          message: 'Failed to turn actuator ON',
          issued_by: 'logic:f95b107d-abfb-46b4-adaa-f0e53f3fd959',
          correlation_id: '43b272fa-f1e1-4aaf-95ac-0217a44d3e70',
        },
      },
      devices,
      (d) => d.esp_id ?? d.device_id,
    )

    expect(mockToast.error).toHaveBeenCalled()
    const [toastMessage] = mockToast.error.mock.calls.at(-1) as [string]
    expect(toastMessage).toContain('Quelle: Automationsregel (f95b107d-abfb-46b4-adaa-f0e53f3fd959)')
    expect(toastMessage).toContain('Aktor konnte nicht eingeschaltet werden')
    expect(toastMessage).not.toContain('Failed to turn actuator ON')
  })

  it('lokalisiert actuator_command_failed-Fehler und behaelt Korrelation', () => {
    const store = useActuatorStore()
    const devices = [{ device_id: 'ESP_6B27C8', esp_id: 'ESP_6B27C8', name: 'ESP_6B27C8' }] as ESPDevice[]

    store.handleActuatorCommandFailed(
      {
        data: {
          esp_id: 'ESP_6B27C8',
          gpio: 25,
          command: 'ON',
          error: 'Failed to turn actuator ON',
          issued_by: 'logic:f95b107d-abfb-46b4-adaa-f0e53f3fd959',
          correlation_id: '43b272fa-f1e1-4aaf-95ac-0217a44d3e70',
        },
      },
      devices,
      (d) => d.esp_id ?? d.device_id,
    )

    expect(mockToast.error).toHaveBeenCalled()
    const [toastMessage] = mockToast.error.mock.calls.at(-1) as [string]
    expect(toastMessage).toContain('Aktor konnte nicht eingeschaltet werden')
    expect(toastMessage).toContain('Korrelation: 43b272fa-f1e1-4aaf-95ac-0217a44d3e70')
    expect(toastMessage).not.toContain('Failed to turn actuator ON')
  })

  it('zeigt pro correlation_id genau einen terminalen actuator-toast', () => {
    const store = useActuatorStore()
    const devices = [{ device_id: 'ESP_6B27C8', esp_id: 'ESP_6B27C8', name: 'ESP_6B27C8' }] as ESPDevice[]

    store.handleActuatorResponse(
      {
        data: {
          esp_id: 'ESP_6B27C8',
          gpio: 25,
          success: false,
          command: 'ON',
          message: 'Failed to turn actuator ON',
          issued_by: 'logic:rule-a',
          correlation_id: 'corr-terminal-1',
          request_id: 'req-terminal-1',
        },
      },
      devices,
      (d) => d.esp_id ?? d.device_id,
    )

    store.handleActuatorResponse(
      {
        data: {
          esp_id: 'ESP_6B27C8',
          gpio: 26,
          success: true,
          command: 'OFF',
          issued_by: 'logic:rule-b',
          correlation_id: 'corr-terminal-1',
          request_id: 'req-terminal-1-b',
        },
      },
      devices,
      (d) => d.esp_id ?? d.device_id,
    )

    expect(mockToast.error).toHaveBeenCalledTimes(1)
    expect(mockToast.success).not.toHaveBeenCalled()
  })

  it('wendet optimistischen Aktor-Status an und rollt bei command_failed zurueck', () => {
    const store = useActuatorStore()
    const devices = [{ device_id: 'ESP_6B27C8', esp_id: 'ESP_6B27C8', name: 'ESP_6B27C8' }] as ESPDevice[]
    let device: ESPDevice = {
      device_id: 'ESP_6B27C8',
      esp_id: 'ESP_6B27C8',
      actuators: [{ gpio: 25, state: false, pwm_value: 0 }],
      sensors: [],
    } as unknown as ESPDevice

    const applyDevicePatch = (_espId: string, patchFn: (value: ESPDevice) => ESPDevice) => {
      device = patchFn(device)
      return true
    }

    store.handleActuatorCommand(
      {
        data: {
          esp_id: 'ESP_6B27C8',
          gpio: 25,
          command: 'ON',
          correlation_id: 'corr-opt-1',
        },
      },
      devices,
      (d) => d.esp_id ?? d.device_id,
      applyDevicePatch,
    )

    const optimisticState = (device.actuators as Array<{ gpio: number; state: boolean }>).find((a) => a.gpio === 25)?.state
    expect(optimisticState).toBe(true)

    store.handleActuatorCommandFailed(
      {
        data: {
          esp_id: 'ESP_6B27C8',
          gpio: 25,
          command: 'ON',
          error: 'Failed to turn actuator ON',
          correlation_id: 'corr-opt-1',
        },
      },
      devices,
      (d) => d.esp_id ?? d.device_id,
      applyDevicePatch,
    )

    const rolledBackState = (device.actuators as Array<{ gpio: number; state: boolean }>).find((a) => a.gpio === 25)?.state
    expect(rolledBackState).toBe(false)
  })

  it('reconciliert pending actuator-intents nach reconnect mit terminalem server-outcome', async () => {
    const store = useActuatorStore()
    store.registerCommandIntent('ESP_1', 5, 'ON', 'corr-reconcile-1', 'req-reconcile-1')
    mockListIntentOutcomes.mockResolvedValue([
      {
        intent_id: 'corr-reconcile-1',
        correlation_id: 'corr-reconcile-1',
        esp_id: 'ESP_1',
        flow: 'command',
        outcome: 'failed',
        is_final: true,
        code: 'ESP_DISCONNECTED_BEFORE_OUTCOME',
      },
    ])

    const reconciledCount = await store.reconcilePendingIntentsFromServer({ espIds: ['ESP_1'] })

    expect(reconciledCount).toBe(1)
    const intent = store.getActuatorIntent('ESP_1', 5)
    expect(intent?.state).toBe('terminal_failed')
  })

  it('blockiert zweiten UI-Befehl innerhalb ACTUATOR_UI_COMMAND_COOLDOWN_MS', () => {
    const store = useActuatorStore()

    expect(store.isActuatorCommandInCooldown('ESP_1', 14)).toBe(false)
    store.recordActuatorCommandSent('ESP_1', 14)
    expect(store.isActuatorCommandInCooldown('ESP_1', 14)).toBe(true)
    expect(store.getActuatorCooldownRemainingMs('ESP_1', 14)).toBeGreaterThan(0)

    vi.advanceTimersByTime(ACTUATOR_UI_COMMAND_COOLDOWN_MS)

    expect(store.isActuatorCommandInCooldown('ESP_1', 14)).toBe(false)
    expect(store.getActuatorCooldownRemainingMs('ESP_1', 14)).toBe(0)
  })

  it('cooldown ist pro esp:gpio isoliert', () => {
    const store = useActuatorStore()
    store.recordActuatorCommandSent('ESP_1', 14)

    expect(store.isActuatorCommandInCooldown('ESP_1', 14)).toBe(true)
    expect(store.isActuatorCommandInCooldown('ESP_1', 15)).toBe(false)
    expect(store.isActuatorCommandInCooldown('ESP_2', 14)).toBe(false)
  })

  it('mappt fw_* config_response auf einziges pending Config-Intent pro ESP', () => {
    const store = useActuatorStore()
    const subjectId = store.registerConfigIntentFromRest({
      espId: 'ESP_698EB4',
      scope: 'offline_rules',
      correlationId: '3f0735f0-ab11-4fbf-aa7b-6eafcf15fa92',
      requestId: '3f0735f0-ab11-4fbf-aa7b-6eafcf15fa92',
    })

    store.handleConfigResponse({
      data: {
        esp_id: 'ESP_698EB4',
        status: 'failed',
        correlation_id: 'fw_ESP_698EB4_65170_1',
        message: 'Config contract violation: required correlation_id missing',
        error_code: 'CONTRACT_UNKNOWN_CODE',
      },
    })

    const intent = store.findConfigIntentBySubject(
      subjectId,
      '3f0735f0-ab11-4fbf-aa7b-6eafcf15fa92',
    )
    expect(intent?.state).toBe('terminal_failed')
    expect(mockToast.error).not.toHaveBeenCalledWith(
      expect.stringContaining('Integrationsstoerung (config_response)'),
      expect.anything(),
    )
  })

  it('reconciliert pending config-intents nach reconnect ohne timeout-toast', async () => {
    const store = useActuatorStore()
    const subjectId = store.registerConfigIntentFromRest({
      espId: 'ESP_2',
      scope: 'sensor:4:ds18b20',
      correlationId: 'corr-config-reconcile-1',
      requestId: 'req-config-reconcile-1',
    })
    mockListIntentOutcomes.mockResolvedValue([
      {
        intent_id: 'req-config-reconcile-1',
        correlation_id: 'corr-config-reconcile-1',
        esp_id: 'ESP_2',
        flow: 'config',
        outcome: 'persisted',
        is_final: true,
      },
    ])

    const reconciledCount = await store.reconcilePendingIntentsFromServer({ espIds: ['ESP_2'] })
    vi.advanceTimersByTime(90_000)

    expect(reconciledCount).toBe(1)
    const intent = store.findConfigIntentBySubject(subjectId, 'corr-config-reconcile-1')
    expect(intent?.state).toBe('terminal_success')
    expect(mockToast.warning).not.toHaveBeenCalledWith(
      expect.stringContaining('Konfigurationsauftrag ausstehend'),
      expect.anything(),
    )
  })
})
