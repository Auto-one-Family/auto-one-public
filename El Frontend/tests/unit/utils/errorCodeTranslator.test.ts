/**
 * Error Code Translator Unit Tests
 *
 * Tests for error code category detection and UI helper functions.
 */

import { describe, it, expect } from 'vitest'
import {
  detectCategory,
  getErrorIcon,
  getErrorColor,
  getErrorBadgeVariant,
  shouldPulse,
  getCategoryLabel,
  getSeverityLabel,
  type ErrorSeverity,
  type ErrorCategory
} from '@/utils/errorCodeTranslator'

// =============================================================================
// CATEGORY DETECTION
// =============================================================================

describe('detectCategory', () => {
  it('detects hardware category (1000-1999)', () => {
    expect(detectCategory(1000)).toBe('hardware')
    expect(detectCategory(1500)).toBe('hardware')
    expect(detectCategory(1999)).toBe('hardware')
  })

  it('detects service category (2000-2999)', () => {
    expect(detectCategory(2000)).toBe('service')
    expect(detectCategory(2500)).toBe('service')
    expect(detectCategory(2999)).toBe('service')
  })

  it('detects communication category (3000-3999)', () => {
    expect(detectCategory(3000)).toBe('communication')
    expect(detectCategory(3500)).toBe('communication')
    expect(detectCategory(3999)).toBe('communication')
  })

  it('detects application category (4000-4999)', () => {
    expect(detectCategory(4000)).toBe('application')
    expect(detectCategory(4500)).toBe('application')
    expect(detectCategory(4999)).toBe('application')
  })

  it('detects server category (5000-5999)', () => {
    expect(detectCategory(5000)).toBe('server')
    expect(detectCategory(5500)).toBe('server')
    expect(detectCategory(5999)).toBe('server')
  })

  it('returns unknown for out-of-range codes', () => {
    expect(detectCategory(999)).toBe('unknown')
    expect(detectCategory(6000)).toBe('unknown')
    expect(detectCategory(0)).toBe('unknown')
    expect(detectCategory(10000)).toBe('unknown')
  })

  it('accepts string numbers', () => {
    expect(detectCategory('1500')).toBe('hardware')
    expect(detectCategory('3000')).toBe('communication')
    expect(detectCategory('5999')).toBe('server')
  })

  it('returns unknown for NaN', () => {
    expect(detectCategory(NaN)).toBe('unknown')
    expect(detectCategory('abc')).toBe('unknown')
    expect(detectCategory('not-a-number')).toBe('unknown')
  })

  it('handles boundary values correctly', () => {
    expect(detectCategory(1999)).toBe('hardware')
    expect(detectCategory(2000)).toBe('service')
    expect(detectCategory(2999)).toBe('service')
    expect(detectCategory(3000)).toBe('communication')
  })
})

// =============================================================================
// UI HELPER FUNCTIONS
// =============================================================================

describe('getErrorIcon', () => {
  it('returns Info icon for info severity', () => {
    expect(getErrorIcon('info')).toBe('Info')
  })

  it('returns AlertTriangle icon for warning severity', () => {
    expect(getErrorIcon('warning')).toBe('AlertTriangle')
  })

  it('returns AlertCircle icon for error severity', () => {
    expect(getErrorIcon('error')).toBe('AlertCircle')
  })

  it('returns AlertOctagon icon for critical severity', () => {
    expect(getErrorIcon('critical')).toBe('AlertOctagon')
  })

  it('returns default AlertCircle for unknown severity', () => {
    expect(getErrorIcon('unknown' as ErrorSeverity)).toBe('AlertCircle')
  })
})

describe('getErrorColor', () => {
  it('returns text-info for info severity', () => {
    expect(getErrorColor('info')).toBe('text-info')
  })

  it('returns text-warning for warning severity', () => {
    expect(getErrorColor('warning')).toBe('text-warning')
  })

  it('returns text-error for error severity', () => {
    expect(getErrorColor('error')).toBe('text-error')
  })

  it('returns text-error for critical severity', () => {
    expect(getErrorColor('critical')).toBe('text-error')
  })

  it('returns text-muted for unknown severity', () => {
    expect(getErrorColor('unknown' as ErrorSeverity)).toBe('text-muted')
  })
})

describe('getErrorBadgeVariant', () => {
  it('returns info variant for info severity', () => {
    expect(getErrorBadgeVariant('info')).toBe('info')
  })

  it('returns warning variant for warning severity', () => {
    expect(getErrorBadgeVariant('warning')).toBe('warning')
  })

  it('returns danger variant for error severity', () => {
    expect(getErrorBadgeVariant('error')).toBe('danger')
  })

  it('returns danger variant for critical severity', () => {
    expect(getErrorBadgeVariant('critical')).toBe('danger')
  })

  it('returns gray variant for unknown severity', () => {
    expect(getErrorBadgeVariant('unknown' as ErrorSeverity)).toBe('gray')
  })
})

describe('shouldPulse', () => {
  it('returns true only for critical severity', () => {
    expect(shouldPulse('critical')).toBe(true)
  })

  it('returns false for all non-critical severities', () => {
    expect(shouldPulse('info')).toBe(false)
    expect(shouldPulse('warning')).toBe(false)
    expect(shouldPulse('error')).toBe(false)
  })

  it('returns false for unknown severity', () => {
    expect(shouldPulse('unknown' as ErrorSeverity)).toBe(false)
  })
})

// =============================================================================
// LABEL TRANSLATIONS (German)
// =============================================================================

describe('getCategoryLabel', () => {
  it('returns German label for hardware category', () => {
    expect(getCategoryLabel('hardware')).toBe('Hardware')
  })

  it('returns German label for service category', () => {
    expect(getCategoryLabel('service')).toBe('Dienste')
  })

  it('returns German label for communication category', () => {
    expect(getCategoryLabel('communication')).toBe('Kommunikation')
  })

  it('returns German label for application category', () => {
    expect(getCategoryLabel('application')).toBe('Anwendung')
  })

  it('returns German label for server category', () => {
    expect(getCategoryLabel('server')).toBe('Server')
  })

  it('returns German label for unknown category', () => {
    expect(getCategoryLabel('unknown')).toBe('Unbekannt')
  })

  it('returns Unbekannt for unmapped category', () => {
    expect(getCategoryLabel('invalid' as ErrorCategory)).toBe('Unbekannt')
  })
})

describe('getSeverityLabel', () => {
  it('returns German label for info severity', () => {
    expect(getSeverityLabel('info')).toBe('Information')
  })

  it('returns German label for warning severity', () => {
    expect(getSeverityLabel('warning')).toBe('Warnung')
  })

  it('returns German label for error severity', () => {
    expect(getSeverityLabel('error')).toBe('Fehler')
  })

  it('returns German label for critical severity', () => {
    expect(getSeverityLabel('critical')).toBe('Kritisch')
  })

  it('returns Unbekannt for unmapped severity', () => {
    expect(getSeverityLabel('unknown' as ErrorSeverity)).toBe('Unbekannt')
  })
})
