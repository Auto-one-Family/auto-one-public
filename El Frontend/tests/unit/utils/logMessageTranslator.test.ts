/**
 * Log Message Translator Unit Tests
 *
 * Tests for translating technical log messages to German user-friendly text.
 */

import { describe, it, expect } from 'vitest'
import {
  translateLogMessage,
  canTranslateLogMessage,
  getLogMessageCategory,
  getCategoryIcon,
  getLogCategoryLabel,
  getSeverityIcon,
  getSeverityClass,
  getPatternCount,
  getAllCategories,
  type LogMessageCategory
} from '@/utils/logMessageTranslator'

// =============================================================================
// TRANSLATE LOG MESSAGE
// =============================================================================

describe('translateLogMessage', () => {
  it('translates permission denied message', () => {
    const result = translateLogMessage("Permission denied: 'logs/mosquitto.log'")
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Zugriff verweigert')
    expect(result?.severity).toBe('error')
    expect(result?.category).toBe('file')
  })

  it('translates connection timeout message', () => {
    const result = translateLogMessage('Connection timeout')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Verbindungs-Timeout')
    expect(result?.category).toBe('connection')
  })

  it('translates ESP disconnected message', () => {
    const result = translateLogMessage('ESP_12AB34CD disconnected')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Gerät offline')
    expect(result?.category).toBe('esp')
  })

  it('translates invalid JSON message', () => {
    const result = translateLogMessage('invalid JSON parse error')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Ungültiges JSON')
    expect(result?.category).toBe('validation')
  })

  it('translates out of memory message', () => {
    const result = translateLogMessage('out of memory')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Speicherfehler')
    expect(result?.category).toBe('system')
  })

  it('translates authentication failed message', () => {
    const result = translateLogMessage('authentication failed')
    expect(result).not.toBeNull()
    expect(result?.category).toBe('auth')
  })

  it('translates configuration not found message', () => {
    const result = translateLogMessage('Configuration not found')
    expect(result).not.toBeNull()
    expect(result?.category).toBe('config')
  })

  it('translates database connection error message', () => {
    const result = translateLogMessage('Database connection error')
    expect(result).not.toBeNull()
    expect(result?.category).toBe('database')
  })

  it('translates MQTT broker failed message', () => {
    const result = translateLogMessage('MQTT broker failed')
    expect(result).not.toBeNull()
    expect(result?.category).toBe('mqtt')
  })

  it('returns null for empty message', () => {
    expect(translateLogMessage('')).toBeNull()
  })

  it('returns null for null input', () => {
    expect(translateLogMessage(null as any)).toBeNull()
  })

  it('returns null for unmatched message', () => {
    expect(translateLogMessage('Some random log message')).toBeNull()
  })

  it('translates file not found message', () => {
    const result = translateLogMessage("No such file or directory: '/path/to/file'")
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Datei nicht gefunden')
    expect(result?.category).toBe('file')
  })

  it('translates connection refused message', () => {
    const result = translateLogMessage('Connection refused')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Verbindung abgelehnt')
    expect(result?.category).toBe('connection')
  })

  it('translates ESP timeout message', () => {
    const result = translateLogMessage('ESP_ABCDEF timed out')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Gerät antwortet nicht')
    expect(result?.category).toBe('esp')
  })

  it('translates heartbeat missed message', () => {
    const result = translateLogMessage('heartbeat missed for ESP_12345678')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Heartbeat verpasst')
    expect(result?.category).toBe('esp')
  })

  it('translates validation error message', () => {
    const result = translateLogMessage("validation error: 'field_name'")
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Validierungsfehler')
    expect(result?.category).toBe('validation')
  })

  it('translates schema validation failed message', () => {
    const result = translateLogMessage('schema validation failed')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Schema-Validierung fehlgeschlagen')
    expect(result?.category).toBe('validation')
  })

  it('translates disk full message', () => {
    const result = translateLogMessage('disk full')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Festplatte voll')
    expect(result?.category).toBe('system')
  })

  it('translates token expired message', () => {
    const result = translateLogMessage('token expired')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Sitzung abgelaufen')
    expect(result?.category).toBe('auth')
    expect(result?.severity).toBe('warning')
  })

  it('translates access denied message', () => {
    const result = translateLogMessage('access denied')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Zugriff verweigert')
    expect(result?.category).toBe('auth')
  })

  it('translates invalid configuration message', () => {
    const result = translateLogMessage('invalid configuration')
    expect(result).not.toBeNull()
    expect(result?.title).toBe('Konfigurationsfehler')
    expect(result?.category).toBe('config')
  })

  it('includes original message in result', () => {
    const original = 'Connection timeout'
    const result = translateLogMessage(original)
    expect(result?.original).toBe(original)
  })

  it('includes description in result', () => {
    const result = translateLogMessage('Connection timeout')
    expect(result?.description).toBeDefined()
    expect(typeof result?.description).toBe('string')
  })

  it('includes suggestion in some results', () => {
    const result = translateLogMessage("Permission denied: 'file.log'")
    expect(result?.suggestion).toBeDefined()
  })
})

// =============================================================================
// CAN TRANSLATE
// =============================================================================

describe('canTranslateLogMessage', () => {
  it('returns true for translatable messages', () => {
    expect(canTranslateLogMessage('Connection timeout')).toBe(true)
    expect(canTranslateLogMessage('Permission denied: "file"')).toBe(true)
    expect(canTranslateLogMessage('ESP_123456 disconnected')).toBe(true)
  })

  it('returns false for non-translatable messages', () => {
    expect(canTranslateLogMessage('Random message')).toBe(false)
    expect(canTranslateLogMessage('Unknown error')).toBe(false)
  })

  it('returns false for empty string', () => {
    expect(canTranslateLogMessage('')).toBe(false)
  })
})

// =============================================================================
// GET CATEGORY
// =============================================================================

describe('getLogMessageCategory', () => {
  it('returns category for translatable message', () => {
    expect(getLogMessageCategory('Connection timeout')).toBe('connection')
    expect(getLogMessageCategory('Permission denied: "file"')).toBe('file')
    expect(getLogMessageCategory('ESP_AABB01 disconnected')).toBe('esp')
  })

  it('returns null for non-translatable message', () => {
    expect(getLogMessageCategory('Random message')).toBeNull()
  })
})

// =============================================================================
// CATEGORY ICON
// =============================================================================

describe('getCategoryIcon', () => {
  it('returns FileX icon for file category', () => {
    expect(getCategoryIcon('file')).toBe('FileX')
  })

  it('returns WifiOff icon for connection category', () => {
    expect(getCategoryIcon('connection')).toBe('WifiOff')
  })

  it('returns Cpu icon for esp category', () => {
    expect(getCategoryIcon('esp')).toBe('Cpu')
  })

  it('returns AlertTriangle icon for validation category', () => {
    expect(getCategoryIcon('validation')).toBe('AlertTriangle')
  })

  it('returns Server icon for system category', () => {
    expect(getCategoryIcon('system')).toBe('Server')
  })

  it('returns Lock icon for auth category', () => {
    expect(getCategoryIcon('auth')).toBe('Lock')
  })

  it('returns Settings icon for config category', () => {
    expect(getCategoryIcon('config')).toBe('Settings')
  })

  it('returns Database icon for database category', () => {
    expect(getCategoryIcon('database')).toBe('Database')
  })

  it('returns Radio icon for mqtt category', () => {
    expect(getCategoryIcon('mqtt')).toBe('Radio')
  })
})

// =============================================================================
// CATEGORY LABEL
// =============================================================================

describe('getLogCategoryLabel', () => {
  it('returns German label for file category', () => {
    expect(getLogCategoryLabel('file')).toBe('Dateisystem')
  })

  it('returns German label for connection category', () => {
    expect(getLogCategoryLabel('connection')).toBe('Verbindung')
  })

  it('returns German label for esp category', () => {
    expect(getLogCategoryLabel('esp')).toBe('ESP-Gerät')
  })

  it('returns German label for validation category', () => {
    expect(getLogCategoryLabel('validation')).toBe('Validierung')
  })

  it('returns German label for system category', () => {
    expect(getLogCategoryLabel('system')).toBe('System')
  })

  it('returns German label for auth category', () => {
    expect(getLogCategoryLabel('auth')).toBe('Authentifizierung')
  })

  it('returns German label for config category', () => {
    expect(getLogCategoryLabel('config')).toBe('Konfiguration')
  })

  it('returns German label for database category', () => {
    expect(getLogCategoryLabel('database')).toBe('Datenbank')
  })

  it('returns German label for mqtt category', () => {
    expect(getLogCategoryLabel('mqtt')).toBe('MQTT')
  })
})

// =============================================================================
// SEVERITY ICON
// =============================================================================

describe('getSeverityIcon', () => {
  it('returns XCircle icon for error severity', () => {
    expect(getSeverityIcon('error')).toBe('XCircle')
  })

  it('returns AlertTriangle icon for warning severity', () => {
    expect(getSeverityIcon('warning')).toBe('AlertTriangle')
  })

  it('returns Info icon for info severity', () => {
    expect(getSeverityIcon('info')).toBe('Info')
  })
})

// =============================================================================
// SEVERITY CLASS
// =============================================================================

describe('getSeverityClass', () => {
  it('returns severity-error class for error', () => {
    expect(getSeverityClass('error')).toBe('severity-error')
  })

  it('returns severity-warning class for warning', () => {
    expect(getSeverityClass('warning')).toBe('severity-warning')
  })

  it('returns severity-info class for info', () => {
    expect(getSeverityClass('info')).toBe('severity-info')
  })
})

// =============================================================================
// STATISTICS
// =============================================================================

describe('getPatternCount', () => {
  it('returns number of defined patterns', () => {
    const count = getPatternCount()
    expect(typeof count).toBe('number')
    expect(count).toBe(21)
  })
})

describe('getAllCategories', () => {
  it('returns array of 9 categories', () => {
    const categories = getAllCategories()
    expect(categories).toHaveLength(9)
  })

  it('includes all expected categories', () => {
    const categories = getAllCategories()
    expect(categories).toContain('file')
    expect(categories).toContain('connection')
    expect(categories).toContain('esp')
    expect(categories).toContain('validation')
    expect(categories).toContain('system')
    expect(categories).toContain('auth')
    expect(categories).toContain('config')
    expect(categories).toContain('database')
    expect(categories).toContain('mqtt')
  })
})
