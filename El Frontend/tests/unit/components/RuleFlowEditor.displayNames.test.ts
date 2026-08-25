/**
 * AUT-632: Canvas-Node-Lesbarkeit — Name primär, Kennung sekundär, keine ESP-UUID.
 * Pure Helfer (Pattern sequenceStepDisplay) — kein VueFlow-Slot nötig.
 */
import { describe, it, expect } from 'vitest'
import {
  faceActuatorPrimary,
  faceSensorPrimary,
  faceDeviceGpioSecondary,
  faceNotRunningPrimary,
  faceNotRunningSecondary,
  faceSensorDiffLabel,
  containsEspUuidFragment,
} from '@/utils/ruleNodeDisplay'

const ESP_UUID = 'af2fc332-1111-2222-3333-444444444444'

describe('ruleNodeDisplay (AUT-632)', () => {
  it('should prefer actuator.name and fall back to category without inventing a device name', () => {
    expect(faceActuatorPrimary('Nachfüllpumpe')).toBe('Nachfüllpumpe')
    expect(faceActuatorPrimary(null)).toBe('Aktor')
    expect(faceActuatorPrimary('')).toBe('Aktor')
  })

  it('should prefer sensor.name and keep type label only when name missing', () => {
    expect(faceSensorPrimary('EC Tank', 'Leitfähigkeit')).toBe('EC Tank')
    expect(faceSensorPrimary(null, 'Leitfähigkeit')).toBe('Leitfähigkeit')
  })

  it('should put device name + GPIO secondary without UUID', () => {
    const secondary = faceDeviceGpioSecondary('Wasserbox', 'GPIO 12')
    expect(secondary.text).toBe('Wasserbox · GPIO 12')
    expect(secondary.text).not.toContain('af2fc332')
    expect(faceDeviceGpioSecondary('', 'Kanal 0').text).toBe('Kanal 0')
  })

  it('should format interlock as Läuft nicht: name and hide ESP UUID from primary', () => {
    const primary = faceNotRunningPrimary({
      target: 'actuator',
      actuatorName: 'Nachfüllpumpe',
    })
    expect(primary).toBe('Läuft nicht: Nachfüllpumpe')
    expect(primary).not.toContain(ESP_UUID)
    expect(containsEspUuidFragment(`${ESP_UUID.slice(0, 8)}… · GPIO 25`)).toBe(true)
    expect(containsEspUuidFragment(primary)).toBe(false)

    const secondary = faceNotRunningSecondary({
      target: 'actuator',
      espName: 'Wasserbox',
      gpioLabel: 'GPIO 25',
    })
    expect(secondary.text).toBe('Wasserbox · GPIO 25')
    expect(secondary.text).not.toContain('af2fc332')
  })

  it('should keep GPIO secondary when actuator name missing', () => {
    expect(faceNotRunningPrimary({ target: 'actuator', actuatorName: null })).toBe('Läuft nicht')
    const secondary = faceNotRunningSecondary({
      target: 'actuator',
      espName: '',
      gpioLabel: 'GPIO 16',
    })
    expect(secondary.text).toBe('GPIO 16')
  })

  it('should resolve sequence interlock via rule name; rule id only in tooltip', () => {
    expect(
      faceNotRunningPrimary({
        target: 'sequence',
        ruleName: 'Dosier-Sequenz A→B',
      }),
    ).toBe('Läuft nicht: Dosier-Sequenz A→B')

    expect(faceNotRunningPrimary({ target: 'sequence', ruleName: null })).toBe(
      'Läuft nicht: Sequenz',
    )

    const secondary = faceNotRunningSecondary({
      target: 'sequence',
      ruleId: 'rule-seq-1',
    })
    expect(secondary.text).toBe('')
    expect(secondary.title).toBe('rule-seq-1')
  })

  it('should resolve sensor_diff labels without showing unresolved UUIDs as primary', () => {
    expect(
      faceSensorDiffLabel({
        configId: 'cfg-1',
        resolved: true,
        sensorName: 'EC A',
        typeLabel: 'Leitfähigkeit',
      }),
    ).toBe('EC A')

    expect(
      faceSensorDiffLabel({
        configId: ESP_UUID,
        resolved: false,
      }),
    ).toBe('—')
  })
})
