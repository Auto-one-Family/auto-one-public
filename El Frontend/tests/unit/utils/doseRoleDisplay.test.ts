/**
 * AUT-1359: dose_role display helper — Name → Typ → (Rolle)
 */

import { describe, it, expect } from 'vitest'
import {
  formatDoseRoleLabel,
  formatActuatorDoseLabel,
  DOSE_ROLE_DISPLAY_LABELS,
} from '@/utils/doseRoleDisplay'

describe('formatDoseRoleLabel', () => {
  it('should return short label only from saved dose_role', () => {
    expect(formatDoseRoleLabel('part_a')).toBe('Stock A')
    expect(formatDoseRoleLabel('part_b')).toBe('Stock B')
    expect(formatDoseRoleLabel('ph_down')).toBe('pH-Minus')
    expect(formatDoseRoleLabel('generic')).toBe('Allgemein')
  })

  it('should return null when dose_role is unset', () => {
    expect(formatDoseRoleLabel(null)).toBeNull()
    expect(formatDoseRoleLabel(undefined)).toBeNull()
    expect(formatDoseRoleLabel('')).toBeNull()
  })

  it('should return null for unknown role values (no invention)', () => {
    expect(formatDoseRoleLabel('Teil A')).toBeNull()
    expect(formatDoseRoleLabel('stock_a')).toBeNull()
  })

  it('should not embed device names in role labels', () => {
    expect(DOSE_ROLE_DISPLAY_LABELS.part_a).toBe('Stock A')
    expect(DOSE_ROLE_DISPLAY_LABELS.part_a.includes('Teil')).toBe(false)
  })
})

describe('formatActuatorDoseLabel', () => {
  it('should format name + role as "Teil A (Stock A)"', () => {
    expect(
      formatActuatorDoseLabel({
        name: 'Teil A',
        actuatorType: 'pump',
        doseRole: 'part_a',
      }),
    ).toBe('Teil A (Stock A)')
  })

  it('should show name only when dose_role is unset', () => {
    expect(
      formatActuatorDoseLabel({
        name: 'Teil B',
        actuatorType: 'pump',
        doseRole: null,
      }),
    ).toBe('Teil B')
  })

  it('should fall back to type when name is empty', () => {
    expect(
      formatActuatorDoseLabel({
        name: '',
        actuatorType: 'pump',
        doseRole: 'part_b',
      }),
    ).toBe('Pumpe (Stock B)')
  })

  it('should fall back to type without role when both name and role empty', () => {
    expect(
      formatActuatorDoseLabel({
        name: '   ',
        actuatorType: 'pump',
        doseRole: null,
      }),
    ).toBe('Pumpe')
  })

  it('should not produce double labels like "Teil A (Teil A (Stock A))"', () => {
    const label = formatActuatorDoseLabel({
      name: 'Teil A',
      actuatorType: 'pump',
      doseRole: 'part_a',
    })
    expect(label).toBe('Teil A (Stock A)')
    expect(label.includes('Teil A (Teil A')).toBe(false)
    expect(label.match(/Stock A/g)?.length).toBe(1)
  })

  it('should not re-append role if base already ends with role paren', () => {
    expect(
      formatActuatorDoseLabel({
        name: 'Mix (Stock A)',
        actuatorType: 'pump',
        doseRole: 'part_a',
      }),
    ).toBe('Mix (Stock A)')
  })
})
