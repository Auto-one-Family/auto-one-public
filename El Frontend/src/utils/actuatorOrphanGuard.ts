import type { ESPDevice } from '@/api/esp'

export const MISSING_CORR_ACTUATOR_PREFIX = 'missing-corr:act:'
const UNKNOWN_ACTUATOR_COMMAND = 'UNKNOWN_COMMAND'
export const ERROR_ACTUATOR_NOT_FOUND = 1052

export function isMissingCorrelationActuator(correlationId?: string | null): boolean {
  return typeof correlationId === 'string' && correlationId.startsWith(MISSING_CORR_ACTUATOR_PREFIX)
}

export function deviceHasActuatorConfig(
  devices: ESPDevice[],
  espId: string,
  gpio: number,
  getDeviceId: (device: ESPDevice) => string,
): boolean {
  const device = devices.find(d => getDeviceId(d) === espId)
  return (device?.actuators ?? []).some(a => a.gpio === gpio)
}

export function parseGpioFromActuatorErrorMessage(message?: string | null): number | null {
  if (!message) return null
  const match = message.match(/GPIO\s+(\d+)/i)
  if (!match) return null
  const parsed = parseInt(match[1], 10)
  return Number.isFinite(parsed) ? parsed : null
}

export function isOrphanExternalActuatorFailure(params: {
  success: boolean
  correlationId?: string | null
  command?: string
  espId: string
  gpio: number
  devices: ESPDevice[]
  getDeviceId: (device: ESPDevice) => string
  hasExistingIntent: boolean
}): boolean {
  if (params.success) return false
  const hasConfig = deviceHasActuatorConfig(
    params.devices,
    params.espId,
    params.gpio,
    params.getDeviceId,
  )
  if (hasConfig && params.hasExistingIntent) return false
  if (hasConfig) return false
  if (isMissingCorrelationActuator(params.correlationId)) return true
  if (params.command === UNKNOWN_ACTUATOR_COMMAND) return true
  return false
}

export function shouldSuppressActuatorNotFoundErrorToast(params: {
  errorCode?: number
  message?: string
  contextGpio?: number | null
  espId?: string
  devices: ESPDevice[]
  getDeviceId: (device: ESPDevice) => string
}): boolean {
  if (params.errorCode !== ERROR_ACTUATOR_NOT_FOUND || !params.espId) return false
  const gpio =
    typeof params.contextGpio === 'number'
      ? params.contextGpio
      : parseGpioFromActuatorErrorMessage(params.message)
  if (gpio === null) return false
  return !deviceHasActuatorConfig(params.devices, params.espId, gpio, params.getDeviceId)
}
