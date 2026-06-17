/**
 * Database Column Translator Unit Tests
 *
 * Tests for translating database column names to German labels,
 * formatting cell values, and table configuration helpers.
 */

import { describe, it, expect } from 'vitest'
import {
  getColumnLabel,
  getColumnDescription,
  formatCellValue,
  getTableColumns,
  getDefaultVisibleColumns,
  getTableLabel,
  getTableDescription,
  getAvailableTables,
  hasTableConfig,
  getColumnIcon,
  getColumnWidth,
  getTableConfig,
  getPrimaryColumns,
  getDetailOnlyColumns,
  getAllColumnsOrdered,
  getPrimaryColumnKeys,
  getDetailOnlyColumnKeys,
  isPrimaryColumn
} from '@/utils/databaseColumnTranslator'

// =============================================================================
// getColumnLabel
// =============================================================================

describe('getColumnLabel', () => {
  it('returns German label for esp_devices.device_id', () => {
    expect(getColumnLabel('esp_devices', 'device_id')).toBe('Geräte-ID')
  })

  it('returns German label for esp_devices.name', () => {
    expect(getColumnLabel('esp_devices', 'name')).toBe('Name')
  })

  it('returns original column name for unknown column', () => {
    expect(getColumnLabel('esp_devices', 'unknown_col')).toBe('unknown_col')
  })

  it('returns original column name for unknown table', () => {
    expect(getColumnLabel('unknown_table', 'any')).toBe('any')
  })

  it('returns German label for sensor_configs.sensor_type', () => {
    expect(getColumnLabel('sensor_configs', 'sensor_type')).toBe('Typ')
  })
})

// =============================================================================
// getColumnDescription
// =============================================================================

describe('getColumnDescription', () => {
  it('returns description for esp_devices.status', () => {
    const desc = getColumnDescription('esp_devices', 'status')
    expect(desc).toBeDefined()
    expect(typeof desc).toBe('string')
  })

  it('returns undefined for unknown table', () => {
    expect(getColumnDescription('unknown_table', 'any')).toBeUndefined()
  })

  it('returns undefined for unknown column', () => {
    expect(getColumnDescription('esp_devices', 'unknown_col')).toBeUndefined()
  })

  it('returns description for sensor_configs.gpio', () => {
    const desc = getColumnDescription('sensor_configs', 'gpio')
    expect(desc).toBeDefined()
  })
})

// =============================================================================
// formatCellValue
// =============================================================================

describe('formatCellValue', () => {
  it('formats esp_devices.status online', () => {
    expect(formatCellValue('esp_devices', 'status', 'online')).toBe('Online')
  })

  it('formats esp_devices.status offline', () => {
    expect(formatCellValue('esp_devices', 'status', 'offline')).toBe('Offline')
  })

  it('returns dash for null value', () => {
    expect(formatCellValue('esp_devices', 'status', null)).toBe('-')
  })

  it('formats sensor_configs.enabled true', () => {
    expect(formatCellValue('sensor_configs', 'enabled', true)).toBe('Ja')
  })

  it('formats sensor_configs.enabled false', () => {
    expect(formatCellValue('sensor_configs', 'enabled', false)).toBe('Nein')
  })

  it('formats sensor_configs.gpio number', () => {
    const result = formatCellValue('sensor_configs', 'gpio', 4)
    expect(result).toBe('GPIO 4')
  })

  it('formats sensor_configs.sample_interval_ms', () => {
    const result = formatCellValue('sensor_configs', 'sample_interval_ms', 5000)
    expect(result).toBe('5.0 s')
  })

  it('formats audit_logs.event_type', () => {
    const result = formatCellValue('audit_logs', 'event_type', 'device_discovered')
    expect(result).toBe('Gerät entdeckt')
  })

  it('formats audit_logs.severity', () => {
    const result = formatCellValue('audit_logs', 'severity', 'error')
    expect(result).toBe('Fehler')
  })

  it('formats unknown table/column as string', () => {
    expect(formatCellValue('unknown', 'col', 'test')).toBe('test')
  })

  it('formats actuator_configs.max_runtime_seconds', () => {
    const result = formatCellValue('actuator_configs', 'max_runtime_seconds', 3600)
    expect(result).toBe('3600 s')
  })

  it('formats actuator_configs.max_runtime_seconds zero', () => {
    const result = formatCellValue('actuator_configs', 'max_runtime_seconds', 0)
    expect(result).toBe('Unbegrenzt')
  })
})

// =============================================================================
// getTableColumns
// =============================================================================

describe('getTableColumns', () => {
  it('returns array of ColumnConfig for esp_devices', () => {
    const columns = getTableColumns('esp_devices')
    expect(Array.isArray(columns)).toBe(true)
    expect(columns.length).toBeGreaterThan(0)
  })

  it('each column has required properties', () => {
    const columns = getTableColumns('esp_devices')
    for (const col of columns) {
      expect(col).toHaveProperty('key')
      expect(col).toHaveProperty('label')
    }
  })

  it('returns empty array for unknown table', () => {
    expect(getTableColumns('unknown')).toEqual([])
  })

  it('returns columns for sensor_configs', () => {
    const columns = getTableColumns('sensor_configs')
    expect(columns.length).toBeGreaterThan(0)
  })
})

// =============================================================================
// getDefaultVisibleColumns
// =============================================================================

describe('getDefaultVisibleColumns', () => {
  it('includes device_id for esp_devices', () => {
    const visible = getDefaultVisibleColumns('esp_devices')
    expect(visible).toContain('device_id')
  })

  it('includes name for esp_devices', () => {
    const visible = getDefaultVisibleColumns('esp_devices')
    expect(visible).toContain('name')
  })

  it('includes status for esp_devices', () => {
    const visible = getDefaultVisibleColumns('esp_devices')
    expect(visible).toContain('status')
  })

  it('does NOT include id (UUID) for esp_devices', () => {
    const visible = getDefaultVisibleColumns('esp_devices')
    expect(visible).not.toContain('id')
  })

  it('returns empty array for unknown table', () => {
    expect(getDefaultVisibleColumns('unknown')).toEqual([])
  })

  it('includes enabled for sensor_configs', () => {
    const visible = getDefaultVisibleColumns('sensor_configs')
    expect(visible).toContain('enabled')
  })
})

// =============================================================================
// getTableLabel
// =============================================================================

describe('getTableLabel', () => {
  it('returns label for esp_devices', () => {
    expect(getTableLabel('esp_devices')).toBe('ESP32-Geräte')
  })

  it('returns label for sensor_configs', () => {
    expect(getTableLabel('sensor_configs')).toBe('Sensorkonfigurationen')
  })

  it('returns label for actuator_configs', () => {
    expect(getTableLabel('actuator_configs')).toBe('Aktorkonfigurationen')
  })

  it('returns label for audit_logs', () => {
    expect(getTableLabel('audit_logs')).toBe('Ereignisprotokoll')
  })

  it('returns original table name for unknown', () => {
    expect(getTableLabel('unknown')).toBe('unknown')
  })
})

// =============================================================================
// getTableDescription
// =============================================================================

describe('getTableDescription', () => {
  it('returns description for esp_devices', () => {
    const desc = getTableDescription('esp_devices')
    expect(desc).toBeDefined()
    expect(typeof desc).toBe('string')
  })

  it('returns undefined for unknown table', () => {
    expect(getTableDescription('unknown')).toBeUndefined()
  })

  it('returns description for sensor_configs', () => {
    const desc = getTableDescription('sensor_configs')
    expect(desc).toBeDefined()
  })
})

// =============================================================================
// getAvailableTables
// =============================================================================

describe('getAvailableTables', () => {
  it('returns array of 4 tables', () => {
    const tables = getAvailableTables()
    expect(Array.isArray(tables)).toBe(true)
    expect(tables).toHaveLength(4)
  })

  it('includes esp_devices', () => {
    const tables = getAvailableTables()
    expect(tables).toContain('esp_devices')
  })

  it('includes sensor_configs', () => {
    const tables = getAvailableTables()
    expect(tables).toContain('sensor_configs')
  })

  it('includes actuator_configs', () => {
    const tables = getAvailableTables()
    expect(tables).toContain('actuator_configs')
  })

  it('includes audit_logs', () => {
    const tables = getAvailableTables()
    expect(tables).toContain('audit_logs')
  })
})

// =============================================================================
// hasTableConfig
// =============================================================================

describe('hasTableConfig', () => {
  it('returns true for esp_devices', () => {
    expect(hasTableConfig('esp_devices')).toBe(true)
  })

  it('returns true for sensor_configs', () => {
    expect(hasTableConfig('sensor_configs')).toBe(true)
  })

  it('returns true for actuator_configs', () => {
    expect(hasTableConfig('actuator_configs')).toBe(true)
  })

  it('returns true for audit_logs', () => {
    expect(hasTableConfig('audit_logs')).toBe(true)
  })

  it('returns false for nonexistent table', () => {
    expect(hasTableConfig('nonexistent')).toBe(false)
  })
})

// =============================================================================
// getColumnIcon
// =============================================================================

describe('getColumnIcon', () => {
  it('returns icon for esp_devices.device_id', () => {
    expect(getColumnIcon('esp_devices', 'device_id')).toBe('Cpu')
  })

  it('returns icon for esp_devices.status', () => {
    expect(getColumnIcon('esp_devices', 'status')).toBe('Activity')
  })

  it('returns undefined for column without icon', () => {
    const icon = getColumnIcon('esp_devices', 'id')
    expect(icon).toBeUndefined()
  })

  it('returns undefined for unknown table', () => {
    expect(getColumnIcon('unknown', 'col')).toBeUndefined()
  })
})

// =============================================================================
// getColumnWidth
// =============================================================================

describe('getColumnWidth', () => {
  it('returns narrow for esp_devices.id', () => {
    expect(getColumnWidth('esp_devices', 'id')).toBe('narrow')
  })

  it('returns normal for esp_devices.name', () => {
    expect(getColumnWidth('esp_devices', 'name')).toBe('normal')
  })

  it('returns normal for unknown table (default)', () => {
    expect(getColumnWidth('unknown', 'col')).toBe('normal')
  })

  it('returns wide for columns with JSON data', () => {
    expect(getColumnWidth('esp_devices', 'capabilities')).toBe('wide')
  })
})

// =============================================================================
// getTableConfig
// =============================================================================

describe('getTableConfig', () => {
  it('returns config for esp_devices', () => {
    const config = getTableConfig('esp_devices')
    expect(config).toBeDefined()
    expect(config?.tableName).toBe('esp_devices')
    expect(config?.tableLabel).toBe('ESP32-Geräte')
    expect(config?.columns).toBeDefined()
  })

  it('returns undefined for unknown table', () => {
    expect(getTableConfig('unknown')).toBeUndefined()
  })

  it('config has primaryKey', () => {
    const config = getTableConfig('esp_devices')
    expect(config?.primaryKey).toBe('id')
  })

  it('config has columns object', () => {
    const config = getTableConfig('esp_devices')
    expect(typeof config?.columns).toBe('object')
  })
})

// =============================================================================
// getPrimaryColumns
// =============================================================================

describe('getPrimaryColumns', () => {
  it('returns primary columns for esp_devices', () => {
    const primary = getPrimaryColumns('esp_devices')
    expect(Array.isArray(primary)).toBe(true)
    expect(primary.length).toBeGreaterThan(0)
  })

  it('all returned columns have defaultVisible true', () => {
    const primary = getPrimaryColumns('esp_devices')
    for (const col of primary) {
      expect(col.defaultVisible).toBe(true)
    }
  })

  it('includes device_id in primary', () => {
    const primary = getPrimaryColumns('esp_devices')
    const deviceId = primary.find(col => col.key === 'device_id')
    expect(deviceId).toBeDefined()
  })

  it('returns empty array for unknown table', () => {
    expect(getPrimaryColumns('unknown')).toEqual([])
  })
})

// =============================================================================
// getDetailOnlyColumns
// =============================================================================

describe('getDetailOnlyColumns', () => {
  it('returns detail-only columns for esp_devices', () => {
    const detail = getDetailOnlyColumns('esp_devices')
    expect(Array.isArray(detail)).toBe(true)
    expect(detail.length).toBeGreaterThan(0)
  })

  it('all returned columns have defaultVisible false or undefined', () => {
    const detail = getDetailOnlyColumns('esp_devices')
    for (const col of detail) {
      expect(col.defaultVisible).not.toBe(true)
    }
  })

  it('includes id (UUID) in detail-only', () => {
    const detail = getDetailOnlyColumns('esp_devices')
    const id = detail.find(col => col.key === 'id')
    expect(id).toBeDefined()
  })

  it('includes zone_id in detail-only', () => {
    const detail = getDetailOnlyColumns('esp_devices')
    const zoneId = detail.find(col => col.key === 'zone_id')
    expect(zoneId).toBeDefined()
  })

  it('returns empty array for unknown table', () => {
    expect(getDetailOnlyColumns('unknown')).toEqual([])
  })
})

// =============================================================================
// getAllColumnsOrdered
// =============================================================================

describe('getAllColumnsOrdered', () => {
  it('returns primary columns first, then detail', () => {
    const all = getAllColumnsOrdered('esp_devices')
    const primary = getPrimaryColumns('esp_devices')
    const detail = getDetailOnlyColumns('esp_devices')
    expect(all.length).toBe(primary.length + detail.length)
  })

  it('first columns are primary (defaultVisible true)', () => {
    const all = getAllColumnsOrdered('esp_devices')
    const primary = getPrimaryColumns('esp_devices')
    for (let i = 0; i < primary.length; i++) {
      expect(all[i].defaultVisible).toBe(true)
    }
  })

  it('returns empty array for unknown table', () => {
    expect(getAllColumnsOrdered('unknown')).toEqual([])
  })
})

// =============================================================================
// getPrimaryColumnKeys
// =============================================================================

describe('getPrimaryColumnKeys', () => {
  it('returns string array of primary column keys', () => {
    const keys = getPrimaryColumnKeys('esp_devices')
    expect(Array.isArray(keys)).toBe(true)
    expect(keys.length).toBeGreaterThan(0)
    for (const key of keys) {
      expect(typeof key).toBe('string')
    }
  })

  it('includes device_id', () => {
    const keys = getPrimaryColumnKeys('esp_devices')
    expect(keys).toContain('device_id')
  })

  it('includes name', () => {
    const keys = getPrimaryColumnKeys('esp_devices')
    expect(keys).toContain('name')
  })

  it('includes status', () => {
    const keys = getPrimaryColumnKeys('esp_devices')
    expect(keys).toContain('status')
  })

  it('returns empty array for unknown table', () => {
    expect(getPrimaryColumnKeys('unknown')).toEqual([])
  })
})

// =============================================================================
// getDetailOnlyColumnKeys
// =============================================================================

describe('getDetailOnlyColumnKeys', () => {
  it('returns string array of detail-only column keys', () => {
    const keys = getDetailOnlyColumnKeys('esp_devices')
    expect(Array.isArray(keys)).toBe(true)
    expect(keys.length).toBeGreaterThan(0)
    for (const key of keys) {
      expect(typeof key).toBe('string')
    }
  })

  it('includes id', () => {
    const keys = getDetailOnlyColumnKeys('esp_devices')
    expect(keys).toContain('id')
  })

  it('includes zone_id', () => {
    const keys = getDetailOnlyColumnKeys('esp_devices')
    expect(keys).toContain('zone_id')
  })

  it('returns empty array for unknown table', () => {
    expect(getDetailOnlyColumnKeys('unknown')).toEqual([])
  })
})

// =============================================================================
// isPrimaryColumn
// =============================================================================

describe('isPrimaryColumn', () => {
  it('returns true for esp_devices.device_id', () => {
    expect(isPrimaryColumn('esp_devices', 'device_id')).toBe(true)
  })

  it('returns true for esp_devices.name', () => {
    expect(isPrimaryColumn('esp_devices', 'name')).toBe(true)
  })

  it('returns false for esp_devices.id (UUID)', () => {
    expect(isPrimaryColumn('esp_devices', 'id')).toBe(false)
  })

  it('returns false for esp_devices.zone_id', () => {
    expect(isPrimaryColumn('esp_devices', 'zone_id')).toBe(false)
  })

  it('returns false for unknown table', () => {
    expect(isPrimaryColumn('unknown', 'col')).toBe(false)
  })

  it('returns false for unknown column', () => {
    expect(isPrimaryColumn('esp_devices', 'unknown_col')).toBe(false)
  })
})
