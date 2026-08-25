/**
 * useActuatorHistory — Shared constants and helpers for actuator history features.
 *
 * Provides:
 * - ActuatorTimeRange type and its millisecond / entry-limit mappings
 * - isActuatorOn / isActuatorOff helpers — single source of truth for ON/OFF detection
 *   that works with the loose server command_type values (ON, OFF, set, stop, etc.)
 */
import type { ActuatorHistoryEntry } from '@/api/actuators'

// =============================================================================
// Types
// =============================================================================

export type ActuatorTimeRange = '1h' | '6h' | '24h' | '7d'

// =============================================================================
// Constants
// =============================================================================

/** Milliseconds per time range bucket */
export const ACTUATOR_TIME_RANGE_MS: Record<ActuatorTimeRange, number> = {
  '1h': 3_600_000,
  '6h': 21_600_000,
  '24h': 86_400_000,
  '7d': 604_800_000,
}

/** Maximum history entries fetched per time range */
export const ACTUATOR_TIME_RANGE_LIMITS: Record<ActuatorTimeRange, number> = {
  '1h': 100,
  '6h': 200,
  '24h': 300,
  '7d': 500,
}

// =============================================================================
// ON/OFF detection helpers
// =============================================================================

/**
 * Returns true when the entry represents an actuator turning ON.
 *
 * Accepts both legacy ('set') and newer ('ON', 'on') command_type values
 * from the server so that callers do not need to duplicate this logic.
 */
export function isActuatorOn(
  entry: Pick<ActuatorHistoryEntry, 'command_type' | 'value'>
): boolean {
  const cmd = entry.command_type?.toLowerCase() ?? ''
  return (
    cmd !== 'stop' &&
    cmd !== 'off' &&
    cmd !== 'emergency_stop' &&
    entry.value != null &&
    entry.value > 0
  )
}

/**
 * Returns true when the entry represents an actuator turning OFF
 * (explicit stop, emergency stop, or a "set 0" command).
 */
export function isActuatorOff(
  entry: Pick<ActuatorHistoryEntry, 'command_type' | 'value'>
): boolean {
  const cmd = entry.command_type?.toLowerCase() ?? ''
  return (
    cmd === 'stop' ||
    cmd === 'off' ||
    cmd === 'emergency_stop' ||
    entry.value === null ||
    entry.value === 0
  )
}

/**
 * AUT-1132 (A2): true for config-push ack entries (command_type
 * "config_applied"/"config_failed", issued_by "config_response") mirrored
 * into actuator_history by config_handler.py. These carry value=null but are
 * NOT a switch event — isActuatorOff() would otherwise misread every one of
 * them as an OFF, corrupting runtime/on-off-interval computations that
 * consume raw history entries (ActuatorRuntimeWidget, MultiSensorWidget).
 * ActuatorActionTimeline.vue intentionally displays these and does not filter
 * them; every other consumer of getHistory() results should.
 */
export function isConfigAckEntry(
  entry: Pick<ActuatorHistoryEntry, 'command_type'>
): boolean {
  const cmd = entry.command_type?.toLowerCase() ?? ''
  return cmd === 'config_applied' || cmd === 'config_failed'
}
