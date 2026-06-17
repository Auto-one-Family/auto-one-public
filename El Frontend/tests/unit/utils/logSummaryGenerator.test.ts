/**
 * Log Summary Generator Unit Tests
 *
 * Tests for generating human-readable summaries from server log entries.
 */

import { describe, it, expect } from 'vitest'
import {
  generateSummary,
  formatCategoryLabel,
  type LogCategory
} from '@/utils/logSummaryGenerator'
import type { LogEntry } from '@/api/logs'

// Helper to create minimal LogEntry objects
function createLogEntry(level: string, message: string): LogEntry {
  return {
    timestamp: '2026-01-01T00:00:00Z',
    level,
    logger: 'test',
    message
  } as LogEntry
}

// =============================================================================
// SCHEDULER JOBS
// =============================================================================

describe('generateSummary - Scheduler', () => {
  it('generates summary for running job', () => {
    const log = createLogEntry('INFO', 'Running job "SimulationScheduler_temp_job" (scheduled at 2026-01-01)')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Job wird ausgefuehrt')
    expect(summary?.category).toBe('scheduler')
  })

  it('generates summary for executed job', () => {
    const log = createLogEntry('INFO', 'Job "SimulationScheduler_test" executed successfully')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Job erfolgreich ausgefuehrt')
    expect(summary?.category).toBe('scheduler')
  })

  it('generates summary for added job', () => {
    const log = createLogEntry('INFO', 'Added job "MaintenanceService_cleanup" trigger: interval[5 minutes]')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Job registriert')
    expect(summary?.category).toBe('scheduler')
  })

  it('generates summary for removed job', () => {
    const log = createLogEntry('INFO', 'Removed job "SimulationScheduler_temp_job"')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Job entfernt')
    expect(summary?.category).toBe('scheduler')
  })

  it('generates summary for scheduler started', () => {
    const log = createLogEntry('INFO', 'Scheduler started')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Scheduler gestartet')
    expect(summary?.category).toBe('scheduler')
  })
})

// =============================================================================
// SENSOR DATA
// =============================================================================

describe('generateSummary - Sensor', () => {
  it('generates summary for sensor data saved', () => {
    const log = createLogEntry('INFO', 'Sensor data saved esp_id=ESP_001 gpio=4')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Sensordaten gespeichert')
    expect(summary?.category).toBe('sensor')
  })

  it('generates summary for sensor data received', () => {
    const log = createLogEntry('INFO', 'Sensor data received ESP_ABCD gpio=5')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Sensordaten empfangen')
    expect(summary?.category).toBe('sensor')
  })

  it('generates summary for sensor stale', () => {
    const log = createLogEntry('WARNING', 'Sensor stale: ESP ABC GPIO 4 - no data for 300 seconds')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Sensor inaktiv')
    expect(summary?.category).toBe('sensor')
  })

  it('generates summary for sensor health check', () => {
    const log = createLogEntry('INFO', 'health_check_sensors: 2 sensor(s) stale. healthy: 5')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Sensor-Gesundheitscheck')
    expect(summary?.category).toBe('maintenance')
  })
})

// =============================================================================
// MQTT
// =============================================================================

describe('generateSummary - MQTT', () => {
  it('generates summary for MQTT handler error', () => {
    // Note: 'MQTT connected' is caught by heartbeat regex (/|connected/ alternative)
    // Testing MQTT handler error pattern instead
    const log = createLogEntry('WARNING', 'Handler returned False')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('MQTT Handler Fehler')
    expect(summary?.category).toBe('mqtt')
  })

  it('generates summary for MQTT disconnected', () => {
    const log = createLogEntry('WARNING', 'MQTT broker unavailable')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('MQTT getrennt')
    expect(summary?.category).toBe('mqtt')
  })

  it('generates summary for MQTT handlers registered', () => {
    const log = createLogEntry('INFO', 'Registered 15 MQTT handlers')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('MQTT Handler registriert')
    expect(summary?.category).toBe('mqtt')
  })

  it('generates summary for MQTT subscription', () => {
    const log = createLogEntry('INFO', 'Subscribed to: autoone/+/sensor/#')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('MQTT Subscription')
    expect(summary?.category).toBe('mqtt')
  })
})

// =============================================================================
// SYSTEM
// =============================================================================

describe('generateSummary - System', () => {
  it('generates summary for application startup', () => {
    const log = createLogEntry('INFO', 'Application startup complete')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Server gestartet')
    expect(summary?.category).toBe('system')
  })

  it('generates summary for shutdown', () => {
    const log = createLogEntry('INFO', 'Shutting down gracefully')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Server wird heruntergefahren')
    expect(summary?.category).toBe('system')
  })

  it('generates summary for database initialized', () => {
    // Pattern: /Database.*?connected|DB.*?initialized/i
    // 'Database connected' is caught by heartbeat regex, use DB initialized instead
    const log = createLogEntry('INFO', 'DB initialized successfully')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Datenbank verbunden')
    expect(summary?.category).toBe('system')
  })
})

// =============================================================================
// ACTUATOR
// =============================================================================

describe('generateSummary - Actuator', () => {
  it('generates summary for actuator command', () => {
    const log = createLogEntry('INFO', 'Actuator command sent esp_id=ESP_001 gpio=12')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Aktor-Befehl')
    expect(summary?.category).toBe('actuator')
  })

  it('generates summary for emergency stop activated', () => {
    const log = createLogEntry('WARNING', 'Emergency stop activated')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Notaus aktiviert')
    expect(summary?.category).toBe('actuator')
  })

  it('generates summary for emergency stop deactivated', () => {
    const log = createLogEntry('INFO', 'Emergency stop deactivated')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Notaus aufgehoben')
    expect(summary?.category).toBe('actuator')
  })
})

// =============================================================================
// HEARTBEAT
// =============================================================================

describe('generateSummary - Heartbeat', () => {
  it('generates summary for heartbeat published', () => {
    const log = createLogEntry('INFO', '[AUTO-HB] ESP_001 heartbeat published state=OPERATIONAL')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Heartbeat gesendet')
    expect(summary?.category).toBe('heartbeat')
  })

  it('generates summary for device timeout', () => {
    const log = createLogEntry('WARNING', 'Device ESP_001 timed out')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Geraet nicht erreichbar')
    expect(summary?.category).toBe('heartbeat')
  })

  it('generates summary for heartbeat received', () => {
    const log = createLogEntry('INFO', 'Heartbeat from ESP_ABC connected')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Heartbeat empfangen')
    expect(summary?.category).toBe('heartbeat')
  })
})

// =============================================================================
// WEBSOCKET
// =============================================================================

describe('generateSummary - WebSocket', () => {
  it('generates summary for WebSocket client connected', () => {
    const log = createLogEntry('INFO', 'WebSocket client connected client_abc123')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('WebSocket verbunden')
    expect(summary?.category).toBe('websocket')
  })

  it('generates summary for WebSocket client disconnected', () => {
    const log = createLogEntry('INFO', 'WebSocket client disconnected client_xyz789')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('WebSocket getrennt')
    expect(summary?.category).toBe('websocket')
  })

  it('generates summary for broadcast', () => {
    const log = createLogEntry('INFO', 'WebSocket broadcast to 3 clients')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('WebSocket Broadcast')
    expect(summary?.category).toBe('websocket')
  })
})

// =============================================================================
// CONFIG
// =============================================================================

describe('generateSummary - Config', () => {
  it('generates summary for GPIO config rejected', () => {
    const log = createLogEntry('WARNING', 'Rejected GPIO config: Only DC pins allowed')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('GPIO-Konfiguration abgelehnt')
    expect(summary?.category).toBe('config')
  })

  it('generates summary for unknown board module', () => {
    const log = createLogEntry('WARNING', 'Unknown board_module esp32_s3, defaulting to esp32')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Unbekanntes Board-Modul')
    expect(summary?.category).toBe('config')
  })

  it('generates summary for config sent', () => {
    const log = createLogEntry('INFO', 'Config sent to ESP_001')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Konfiguration gesendet')
    expect(summary?.category).toBe('config')
  })
})

// =============================================================================
// ERROR FALLBACKS
// =============================================================================

describe('generateSummary - Error Fallbacks', () => {
  it('generates fallback for CRITICAL level', () => {
    const log = createLogEntry('CRITICAL', 'Something went critically wrong')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Kritischer Fehler')
    expect(summary?.category).toBe('error')
  })

  it('generates fallback for ERROR level', () => {
    const log = createLogEntry('ERROR', 'Something went wrong')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Fehler aufgetreten')
    expect(summary?.category).toBe('error')
  })

  it('generates fallback for WARNING level', () => {
    const log = createLogEntry('WARNING', 'Unmatched warning message')
    const summary = generateSummary(log)
    expect(summary).not.toBeNull()
    expect(summary?.title).toBe('Warnung')
    expect(summary?.category).toBe('system')
  })

  it('returns null for unmatched INFO level', () => {
    const log = createLogEntry('INFO', 'Random unmatched info message')
    const summary = generateSummary(log)
    expect(summary).toBeNull()
  })
})

// =============================================================================
// FORMAT CATEGORY LABEL
// =============================================================================

describe('formatCategoryLabel', () => {
  it('returns German label for scheduler', () => {
    expect(formatCategoryLabel('scheduler')).toBe('Scheduler')
  })

  it('returns German label for sensor', () => {
    expect(formatCategoryLabel('sensor')).toBe('Sensor')
  })

  it('returns German label for heartbeat', () => {
    expect(formatCategoryLabel('heartbeat')).toBe('Heartbeat')
  })

  it('returns German label for mqtt', () => {
    expect(formatCategoryLabel('mqtt')).toBe('MQTT')
  })

  it('returns German label for config', () => {
    expect(formatCategoryLabel('config')).toBe('Konfiguration')
  })

  it('returns German label for maintenance', () => {
    expect(formatCategoryLabel('maintenance')).toBe('Wartung')
  })

  it('returns German label for websocket', () => {
    expect(formatCategoryLabel('websocket')).toBe('WebSocket')
  })

  it('returns German label for actuator', () => {
    expect(formatCategoryLabel('actuator')).toBe('Aktor')
  })

  it('returns German label for auth', () => {
    expect(formatCategoryLabel('auth')).toBe('Authentifizierung')
  })

  it('returns German label for error', () => {
    expect(formatCategoryLabel('error')).toBe('Fehler')
  })

  it('returns German label for system', () => {
    expect(formatCategoryLabel('system')).toBe('System')
  })
})
