/**
 * Event Type Icons Unit Tests
 *
 * Tests for event type to icon mapping utilities.
 */

import { describe, it, expect, vi } from 'vitest'
import {
  getEventIcon,
  hasEventIcon,
  getAllMappedEventTypes
} from '@/utils/eventTypeIcons'

// Mock lucide-vue-next components (vitest ESM requires explicit exports, no Proxy)
function mockIcon(iconName: string) {
  return { name: iconName, __isComponent: true }
}

vi.mock('lucide-vue-next', () => ({
  Activity: mockIcon('Activity'),
  AlertCircle: mockIcon('AlertCircle'),
  AlertOctagon: mockIcon('AlertOctagon'),
  CheckCircle2: mockIcon('CheckCircle2'),
  Cpu: mockIcon('Cpu'),
  Database: mockIcon('Database'),
  Info: mockIcon('Info'),
  LogIn: mockIcon('LogIn'),
  LogOut: mockIcon('LogOut'),
  Play: mockIcon('Play'),
  Power: mockIcon('Power'),
  Radio: mockIcon('Radio'),
  Server: mockIcon('Server'),
  Settings: mockIcon('Settings'),
  ShieldAlert: mockIcon('ShieldAlert'),
  Square: mockIcon('Square'),
  Thermometer: mockIcon('Thermometer'),
  Wifi: mockIcon('Wifi'),
  WifiOff: mockIcon('WifiOff'),
  XCircle: mockIcon('XCircle'),
  Zap: mockIcon('Zap'),
}))

// =============================================================================
// EVENT ICON MAPPING
// =============================================================================

describe('getEventIcon', () => {
  it('returns Thermometer icon for sensor_data', () => {
    const icon = getEventIcon('sensor_data')
    expect(icon.name).toBe('Thermometer')
  })

  it('returns Power icon for actuator_status', () => {
    const icon = getEventIcon('actuator_status')
    expect(icon.name).toBe('Power')
  })

  it('returns Cpu icon for esp_health', () => {
    const icon = getEventIcon('esp_health')
    expect(icon.name).toBe('Cpu')
  })

  it('returns CheckCircle2 icon for config_response', () => {
    const icon = getEventIcon('config_response')
    expect(icon.name).toBe('CheckCircle2')
  })

  it('returns Radio icon for device_discovered', () => {
    const icon = getEventIcon('device_discovered')
    expect(icon.name).toBe('Radio')
  })

  it('returns Wifi icon for device_online', () => {
    const icon = getEventIcon('device_online')
    expect(icon.name).toBe('Wifi')
  })

  it('returns WifiOff icon for device_offline', () => {
    const icon = getEventIcon('device_offline')
    expect(icon.name).toBe('WifiOff')
  })

  it('returns Zap icon for zone_assignment', () => {
    const icon = getEventIcon('zone_assignment')
    expect(icon.name).toBe('Zap')
  })

  it('returns Server icon for system_event', () => {
    const icon = getEventIcon('system_event')
    expect(icon.name).toBe('Server')
  })

  it('returns AlertCircle icon for error_event', () => {
    const icon = getEventIcon('error_event')
    expect(icon.name).toBe('AlertCircle')
  })

  it('returns LogIn icon for login_success', () => {
    const icon = getEventIcon('login_success')
    expect(icon.name).toBe('LogIn')
  })

  it('returns XCircle icon for login_failed', () => {
    const icon = getEventIcon('login_failed')
    expect(icon.name).toBe('XCircle')
  })

  it('returns Info icon for notification', () => {
    const icon = getEventIcon('notification')
    expect(icon.name).toBe('Info')
  })

  it('returns AlertOctagon icon for contract_mismatch', () => {
    const icon = getEventIcon('contract_mismatch')
    expect(icon.name).toBe('AlertOctagon')
  })

  it('returns default Activity icon for unknown event type', () => {
    const icon = getEventIcon('unknown_event_type')
    expect(icon.name).toBe('Activity')
  })

  it('returns AlertOctagon icon for actuator_alert', () => {
    const icon = getEventIcon('actuator_alert')
    expect(icon.name).toBe('AlertOctagon')
  })

  it('returns Settings icon for config_published', () => {
    const icon = getEventIcon('config_published')
    expect(icon.name).toBe('Settings')
  })

  it('returns Play icon for service_start', () => {
    const icon = getEventIcon('service_start')
    expect(icon.name).toBe('Play')
  })

  it('returns Square icon for service_stop', () => {
    const icon = getEventIcon('service_stop')
    expect(icon.name).toBe('Square')
  })

  it('returns ShieldAlert icon for emergency_stop', () => {
    const icon = getEventIcon('emergency_stop')
    expect(icon.name).toBe('ShieldAlert')
  })

  it('returns Database icon for database_error', () => {
    const icon = getEventIcon('database_error')
    expect(icon.name).toBe('Database')
  })

  it('returns LogOut icon for logout', () => {
    const icon = getEventIcon('logout')
    expect(icon.name).toBe('LogOut')
  })
})

// =============================================================================
// EVENT ICON CHECK
// =============================================================================

describe('hasEventIcon', () => {
  it('returns true for sensor_data', () => {
    expect(hasEventIcon('sensor_data')).toBe(true)
  })

  it('returns true for actuator_status', () => {
    expect(hasEventIcon('actuator_status')).toBe(true)
  })

  it('returns true for esp_health', () => {
    expect(hasEventIcon('esp_health')).toBe(true)
  })

  it('returns true for device_discovered', () => {
    expect(hasEventIcon('device_discovered')).toBe(true)
  })

  it('returns true for config_response', () => {
    expect(hasEventIcon('config_response')).toBe(true)
  })

  it('returns false for nonexistent event type', () => {
    expect(hasEventIcon('nonexistent')).toBe(false)
  })

  it('returns false for empty string', () => {
    expect(hasEventIcon('')).toBe(false)
  })

  it('returns false for unknown_type', () => {
    expect(hasEventIcon('unknown_type')).toBe(false)
  })
})

// =============================================================================
// ALL MAPPED EVENT TYPES
// =============================================================================

describe('getAllMappedEventTypes', () => {
  it('returns array of event types', () => {
    const types = getAllMappedEventTypes()
    expect(Array.isArray(types)).toBe(true)
  })

  it('returns 34 mapped event types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toHaveLength(34)
  })

  it('includes sensor_data in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('sensor_data')
  })

  it('includes actuator_status in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('actuator_status')
  })

  it('includes esp_health in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('esp_health')
  })

  it('includes device_discovered in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('device_discovered')
  })

  it('includes zone_assignment in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('zone_assignment')
  })

  it('includes system_event in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('system_event')
  })

  it('includes error_event in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('error_event')
  })

  it('includes login_success in mapped types', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('login_success')
  })

  it('includes all lifecycle events', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('device_discovered')
    expect(types).toContain('device_rediscovered')
    expect(types).toContain('device_approved')
    expect(types).toContain('device_rejected')
    expect(types).toContain('device_online')
    expect(types).toContain('device_offline')
    expect(types).toContain('lwt_received')
  })

  it('includes all actuator events', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('actuator_status')
    expect(types).toContain('actuator_response')
    expect(types).toContain('actuator_alert')
    expect(types).toContain('actuator_command')
    expect(types).toContain('actuator_command_failed')
  })

  it('includes all config events', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('config_response')
    expect(types).toContain('config_published')
    expect(types).toContain('config_failed')
  })

  it('includes all auth events', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('login_success')
    expect(types).toContain('login_failed')
    expect(types).toContain('logout')
  })

  it('includes contract integrity events', () => {
    const types = getAllMappedEventTypes()
    expect(types).toContain('contract_mismatch')
    expect(types).toContain('contract_unknown_event')
  })
})
