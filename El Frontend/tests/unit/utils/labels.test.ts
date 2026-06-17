/**
 * Labels Unit Tests
 *
 * Tests for German label translations and label helper functions.
 */

import { describe, it, expect } from 'vitest'
import {
  QUALITY_LABELS,
  STATE_LABELS,
  ACTUATOR_TYPE_LABELS,
  ACTUATOR_STATE_LABELS,
  CONNECTION_LABELS,
  EMAIL_STATUS_LABELS,
  DEVICE_TYPE_LABELS,
  ACTION_LABELS,
  MESSAGE_LABELS,
  getQualityInfo,
  getStateInfo,
  getActuatorTypeInfo,
  getGpioDescription,
  isGpioSafe,
  getUnitExplanation,
  getLabel,
  getQualityLabel,
  getStateLabel,
  getActuatorTypeLabel,
  getConnectionLabel,
  getDeviceTypeLabel,
  getEmailStatusLabel
} from '@/utils/labels'

// =============================================================================
// CONSTANT LABELS
// =============================================================================

describe('QUALITY_LABELS', () => {
  it('contains expected quality keys', () => {
    expect(QUALITY_LABELS.excellent).toBe('Exzellent')
    expect(QUALITY_LABELS.good).toBe('Gut')
    expect(QUALITY_LABELS.fair).toBe('Mittel')
    expect(QUALITY_LABELS.poor).toBe('Schlecht')
    expect(QUALITY_LABELS.stale).toBe('Veraltet')
    expect(QUALITY_LABELS.unknown).toBe('Unbekannt')
  })
})

describe('STATE_LABELS', () => {
  it('contains expected state keys', () => {
    expect(STATE_LABELS.OPERATIONAL).toBe('Betriebsbereit')
    expect(STATE_LABELS.SAFE_MODE).toBe('Sicherheitsmodus')
    expect(STATE_LABELS.ERROR).toBe('Fehler')
    expect(STATE_LABELS.OFFLINE).toBe('Offline')
    expect(STATE_LABELS.CONNECTED).toBe('Verbunden')
  })
})

describe('ACTUATOR_TYPE_LABELS', () => {
  it('contains expected actuator type keys', () => {
    expect(ACTUATOR_TYPE_LABELS.relay).toBe('Relais')
    expect(ACTUATOR_TYPE_LABELS.pwm).toBe('PWM-Ausgang')
    expect(ACTUATOR_TYPE_LABELS.valve).toBe('Ventil')
    expect(ACTUATOR_TYPE_LABELS.pump).toBe('Pumpe')
    expect(ACTUATOR_TYPE_LABELS.fan).toBe('Lüfter (PWM)')
  })
})

describe('CONNECTION_LABELS', () => {
  it('contains expected connection status keys', () => {
    expect(CONNECTION_LABELS.online).toBe('Online')
    expect(CONNECTION_LABELS.offline).toBe('Offline')
    expect(CONNECTION_LABELS.connecting).toBe('Verbinde...')
  })
})

describe('EMAIL_STATUS_LABELS', () => {
  it('contains expected email status keys (Phase C V1.2)', () => {
    expect(EMAIL_STATUS_LABELS.sent).toBe('Zugestellt')
    expect(EMAIL_STATUS_LABELS.failed).toBe('Fehlgeschlagen')
    expect(EMAIL_STATUS_LABELS.pending).toBe('Ausstehend')
    expect(EMAIL_STATUS_LABELS.permanently_failed).toBe('Dauerhaft fehlgeschlagen')
  })
})

describe('DEVICE_TYPE_LABELS', () => {
  it('contains expected device type keys', () => {
    expect(DEVICE_TYPE_LABELS.mock).toBe('Simuliert')
    expect(DEVICE_TYPE_LABELS.real).toBe('Echtes Gerät')
    expect(DEVICE_TYPE_LABELS.ESP32).toBe('ESP32')
  })
})

// =============================================================================
// INFO FUNCTIONS (with colorClass/variant/icon)
// =============================================================================

describe('getQualityInfo', () => {
  it('returns label and colorClass for excellent', () => {
    const info = getQualityInfo('excellent')
    expect(info.label).toBe('Exzellent')
    expect(info.colorClass).toBe('text-success')
  })

  it('returns label and colorClass for good', () => {
    const info = getQualityInfo('good')
    expect(info.label).toBe('Gut')
    expect(info.colorClass).toBe('text-success')
  })

  it('returns label and colorClass for fair', () => {
    const info = getQualityInfo('fair')
    expect(info.label).toBe('Mittel')
    expect(info.colorClass).toBe('text-warning')
  })

  it('returns label and colorClass for poor', () => {
    const info = getQualityInfo('poor')
    expect(info.label).toBe('Schlecht')
    expect(info.colorClass).toBe('text-error')
  })

  it('returns fallback for unknown quality', () => {
    const info = getQualityInfo('invalid')
    expect(info.label).toBe('invalid')
    expect(info.colorClass).toBe('text-muted')
  })
})

describe('getStateInfo', () => {
  it('returns label and variant for OPERATIONAL', () => {
    const info = getStateInfo('OPERATIONAL')
    expect(info.label).toBe('Betriebsbereit')
    expect(info.variant).toBe('success')
  })

  it('returns label and variant for ERROR', () => {
    const info = getStateInfo('ERROR')
    expect(info.label).toBe('Fehler')
    expect(info.variant).toBe('danger')
  })

  it('returns label and variant for SAFE_MODE', () => {
    const info = getStateInfo('SAFE_MODE')
    expect(info.label).toBe('Sicherheitsmodus')
    expect(info.variant).toBe('warning')
  })

  it('returns fallback for unknown state', () => {
    const info = getStateInfo('UNKNOWN_STATE')
    expect(info.label).toBe('UNKNOWN_STATE')
    expect(info.variant).toBe('gray')
  })
})

describe('getActuatorTypeInfo', () => {
  it('returns label and icon for relay', () => {
    const info = getActuatorTypeInfo('relay')
    expect(info.label).toBe('Relais')
    expect(info.icon).toBe('ToggleRight')
  })

  it('returns label and icon for pump', () => {
    const info = getActuatorTypeInfo('pump')
    expect(info.label).toBe('Pumpe')
    expect(info.icon).toBe('Waves')
  })

  it('returns label and icon for fan', () => {
    const info = getActuatorTypeInfo('fan')
    expect(info.label).toBe('Lüfter (PWM)')
    expect(info.icon).toBe('Fan')
  })

  it('returns fallback for unknown type', () => {
    const info = getActuatorTypeInfo('unknown')
    expect(info.label).toBe('unknown')
    expect(info.icon).toBe('Power')
  })
})

// =============================================================================
// GPIO FUNCTIONS
// =============================================================================

describe('getGpioDescription', () => {
  it('returns description for known GPIO pins', () => {
    expect(getGpioDescription(0)).toBe('GPIO0 - Boot-Pin, mit Vorsicht verwenden')
    expect(getGpioDescription(4)).toBe('GPIO4 - Standard I2C SDA')
    expect(getGpioDescription(21)).toBe('GPIO21 - Standard I2C SDA (alternativ)')
  })

  it('returns generic description for unknown GPIO pins', () => {
    expect(getGpioDescription(99)).toBe('GPIO 99')
    expect(getGpioDescription(255)).toBe('GPIO 255')
  })

  it('handles typical safe GPIO pins', () => {
    expect(getGpioDescription(13)).toBe('GPIO13 - Sicher für allgemeine Verwendung')
    expect(getGpioDescription(18)).toBe('GPIO18 - Sicher für allgemeine Verwendung')
  })
})

describe('isGpioSafe', () => {
  it('returns false for unsafe GPIO pins', () => {
    const unsafePins = [0, 1, 3, 6, 7, 8, 9, 10, 11, 12, 15]
    unsafePins.forEach(pin => {
      expect(isGpioSafe(pin)).toBe(false)
    })
  })

  it('returns true for safe GPIO pins', () => {
    const safePins = [2, 4, 5, 13, 14, 16, 17, 18, 19, 21, 22, 23]
    safePins.forEach(pin => {
      expect(isGpioSafe(pin)).toBe(true)
    })
  })

  it('returns true for high GPIO numbers', () => {
    expect(isGpioSafe(25)).toBe(true)
    expect(isGpioSafe(32)).toBe(true)
    expect(isGpioSafe(99)).toBe(true)
  })
})

// =============================================================================
// UNIT EXPLANATIONS
// =============================================================================

describe('getUnitExplanation', () => {
  it('returns explanation for known units', () => {
    expect(getUnitExplanation('°C')).toBe('Grad Celsius - Temperatureinheit')
    expect(getUnitExplanation('pH')).toBe('pH-Wert - Maß für Säure/Base (0-14)')
    expect(getUnitExplanation('% RH')).toBe('Relative Luftfeuchtigkeit in Prozent')
    expect(getUnitExplanation('hPa')).toBe('Hektopascal - Luftdruckeinheit')
  })

  it('returns unit itself for unknown units', () => {
    expect(getUnitExplanation('unknown')).toBe('unknown')
    expect(getUnitExplanation('xyz')).toBe('xyz')
  })
})

// =============================================================================
// GENERIC HELPER FUNCTIONS
// =============================================================================

describe('getLabel', () => {
  it('returns label from map if exists', () => {
    const map = { key1: 'Value 1', key2: 'Value 2' }
    expect(getLabel('key1', map)).toBe('Value 1')
    expect(getLabel('key2', map)).toBe('Value 2')
  })

  it('returns original value if not in map', () => {
    const map = { key1: 'Value 1' }
    expect(getLabel('unknown', map)).toBe('unknown')
  })
})

describe('getQualityLabel', () => {
  it('returns quality label', () => {
    expect(getQualityLabel('excellent')).toBe('Exzellent')
    expect(getQualityLabel('poor')).toBe('Schlecht')
  })

  it('returns original value for unknown quality', () => {
    expect(getQualityLabel('unknown_quality')).toBe('unknown_quality')
  })
})

describe('getStateLabel', () => {
  it('returns state label', () => {
    expect(getStateLabel('OPERATIONAL')).toBe('Betriebsbereit')
    expect(getStateLabel('ERROR')).toBe('Fehler')
  })

  it('returns original value for unknown state', () => {
    expect(getStateLabel('UNKNOWN_STATE')).toBe('UNKNOWN_STATE')
  })
})

describe('getActuatorTypeLabel', () => {
  it('returns actuator type label', () => {
    expect(getActuatorTypeLabel('relay')).toBe('Relais')
    expect(getActuatorTypeLabel('valve')).toBe('Ventil')
  })

  it('returns original value for unknown type', () => {
    expect(getActuatorTypeLabel('unknown')).toBe('unknown')
  })
})

describe('getConnectionLabel', () => {
  it('returns connection status label', () => {
    expect(getConnectionLabel('online')).toBe('Online')
    expect(getConnectionLabel('offline')).toBe('Offline')
  })

  it('returns original value for unknown status', () => {
    expect(getConnectionLabel('unknown')).toBe('unknown')
  })
})

describe('getEmailStatusLabel', () => {
  it('returns email status label', () => {
    expect(getEmailStatusLabel('sent')).toBe('Zugestellt')
    expect(getEmailStatusLabel('failed')).toBe('Fehlgeschlagen')
    expect(getEmailStatusLabel('pending')).toBe('Ausstehend')
    expect(getEmailStatusLabel('permanently_failed')).toBe('Dauerhaft fehlgeschlagen')
  })

  it('returns original value for unknown status', () => {
    expect(getEmailStatusLabel('unknown')).toBe('unknown')
  })
})

describe('getDeviceTypeLabel', () => {
  it('returns device type label', () => {
    expect(getDeviceTypeLabel('mock')).toBe('Simuliert')
    expect(getDeviceTypeLabel('ESP32')).toBe('ESP32')
  })

  it('returns original value for unknown type', () => {
    expect(getDeviceTypeLabel('unknown')).toBe('unknown')
  })
})
