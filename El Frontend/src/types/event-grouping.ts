/**
 * Event Grouping Types
 *
 * Types for time-window based event grouping in the System Monitor.
 * Events within a configurable time window are grouped together
 * and can be expanded/collapsed.
 */

import type { UnifiedEvent } from './websocket-events'

/**
 * A group of temporally related events
 */
export interface EventGroup {
  /** Unique group ID */
  id: string
  /** All events in this group (chronologically sorted, oldest first) */
  events: UnifiedEvent[]
  /** Representative event (first event in group) */
  representative: UnifiedEvent
  /** Number of events */
  count: number
  /** Time span in milliseconds */
  timeSpanMs: number
  /** Earliest timestamp */
  startTime: string
  /** Latest timestamp */
  endTime: string
  /** Dominant category */
  dominantCategory: 'esp-status' | 'sensors' | 'actuators' | 'system'
  /** All involved ESP IDs */
  espIds: string[]
  /** Display label */
  label: string
  /** Is this an emergency group (Emergency-Stop)? */
  isEmergency: boolean
  /** Emergency details (only when isEmergency = true) */
  emergencyDetails?: {
    /** The triggering emergency event */
    triggerEvent: UnifiedEvent
    /** All affected GPIO pins */
    affectedGpios: number[]
    /** Reason for the emergency stop */
    reason: string
    /** Who/what triggered the stop */
    triggeredBy: string
  }
}

/**
 * Union type for rendering: either a single event or a group
 */
export type EventOrGroup =
  | { type: 'event'; data: UnifiedEvent }
  | { type: 'group'; data: EventGroup }

/**
 * Grouping options
 */
export interface GroupingOptions {
  /** Enable/disable grouping */
  enabled: boolean
  /** Time window in milliseconds (default: 5000) */
  windowMs: number
  /** Minimum events for a group (default: 2) */
  minGroupSize: number
}
