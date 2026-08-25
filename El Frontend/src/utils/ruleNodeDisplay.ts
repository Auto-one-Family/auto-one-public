/**
 * AUT-632 / AUT-1248: Canvas-Node-Lesbarkeit — reine Anzeige-Helfer.
 * Primär = vorhandener Config-Name; Kennung sekundär; keine ESP-UUID als Bezeichner.
 * Kein Schema-/Store-Change.
 */

export function faceActuatorPrimary(actuatorName: string | null | undefined): string {
  const name = actuatorName?.trim()
  return name || 'Aktor'
}

export function faceSensorPrimary(
  sensorName: string | null | undefined,
  typeLabel: string,
): string {
  const name = sensorName?.trim()
  return name || typeLabel
}

export function faceDeviceGpioSecondary(
  espName: string | null | undefined,
  gpioLabel: string,
): { text: string; title: string } {
  const device = espName?.trim() || ''
  const parts = [device, gpioLabel].filter(Boolean)
  const text = parts.join(' · ') || '—'
  return { text, title: text }
}

export function faceNotRunningPrimary(opts: {
  target?: string
  actuatorName?: string | null
  ruleName?: string | null
}): string {
  if (opts.target === 'sequence') {
    const ruleName = opts.ruleName?.trim()
    if (ruleName) return `Läuft nicht: ${ruleName}`
    return 'Läuft nicht: Sequenz'
  }
  const actuatorName = opts.actuatorName?.trim()
  if (actuatorName) return `Läuft nicht: ${actuatorName}`
  return 'Läuft nicht'
}

export function faceNotRunningSecondary(opts: {
  target?: string
  ruleId?: string | null
  espName?: string | null
  gpioLabel?: string
}): { text: string; title: string } {
  if (opts.target === 'sequence') {
    const id = opts.ruleId ? String(opts.ruleId) : ''
    return { text: '', title: id }
  }
  return faceDeviceGpioSecondary(opts.espName, opts.gpioLabel || '—')
}

export function faceSensorDiffLabel(opts: {
  configId?: string | null
  sensorName?: string | null
  typeLabel?: string
  resolved: boolean
}): string {
  if (!opts.configId) return '—'
  if (!opts.resolved) return '—'
  const name = opts.sensorName?.trim()
  if (name) return name
  return opts.typeLabel?.trim() || '—'
}

/** Guard for tests / audits: visible face must not contain raw UUID fragments. */
export function containsEspUuidFragment(visibleText: string): boolean {
  return /[0-9a-f]{8}/i.test(visibleText) && visibleText.includes('…')
}
