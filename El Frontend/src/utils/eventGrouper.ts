/**
 * Event Grouper Utility
 *
 * Groups events by time window for the System Monitor.
 * Events within ±windowMs of each other are grouped together.
 */

import type { UnifiedEvent } from '@/types/websocket-events'
import type { EventGroup, EventOrGroup, GroupingOptions } from '@/types/event-grouping'
import { getEventCategory, type EventCategory } from '@/utils/eventTransformer'

/** Event types that indicate an emergency trigger */
const EMERGENCY_TRIGGER_TYPES = [
  'emergency_stop',
  'actuator_emergency_stop',
  'safety_triggered',
] as const

/** Alert types within actuator_alert that indicate emergency */
const EMERGENCY_ALERT_TYPES = [
  'emergency_stop',
  'safety_triggered',
] as const

/**
 * Groups events by time window.
 *
 * @param events - Events sorted newest-first (as from filteredEvents)
 * @param options - Grouping configuration
 * @returns Array of EventOrGroup items, newest first
 */
export function groupEventsByTimeWindow(
  events: UnifiedEvent[],
  options: GroupingOptions
): EventOrGroup[] {
  if (!options.enabled || events.length === 0) {
    return events.map(e => ({ type: 'event' as const, data: e }))
  }

  // Events come in newest-first. We need to group chronologically,
  // so reverse to oldest-first, group, then reverse result back.
  const sorted = [...events].reverse()

  const result: EventOrGroup[] = []
  let currentGroup: UnifiedEvent[] = []
  let groupHasEmergency = false

  for (const event of sorted) {
    if (currentGroup.length === 0) {
      currentGroup.push(event)
      groupHasEmergency = isEmergencyRelatedEvent(event)
    } else {
      const lastTime = new Date(currentGroup[currentGroup.length - 1].timestamp).getTime()
      const currentTime = new Date(event.timestamp).getTime()
      const isEmergency = isEmergencyRelatedEvent(event)

      // Extended window for emergency sequences (2x normal)
      const effectiveWindow = (groupHasEmergency || isEmergency)
        ? options.windowMs * 2
        : options.windowMs

      if (currentTime - lastTime <= effectiveWindow) {
        currentGroup.push(event)
        if (isEmergency) groupHasEmergency = true
      } else {
        // Finalize current group
        result.push(...finalizeGroup(currentGroup, options))
        currentGroup = [event]
        groupHasEmergency = isEmergency
      }
    }
  }

  // Don't forget the last group
  if (currentGroup.length > 0) {
    result.push(...finalizeGroup(currentGroup, options))
  }

  // Reverse back to newest-first for display
  return result.reverse()
}

function finalizeGroup(events: UnifiedEvent[], options: GroupingOptions): EventOrGroup[] {
  if (events.length < options.minGroupSize) {
    return events.map(e => ({ type: 'event' as const, data: e }))
  }

  return [{
    type: 'group' as const,
    data: createEventGroup(events),
  }]
}

function createEventGroup(events: UnifiedEvent[]): EventGroup {
  const startTime = events[0].timestamp
  const endTime = events[events.length - 1].timestamp
  const timeSpanMs = new Date(endTime).getTime() - new Date(startTime).getTime()

  const espIds = [...new Set(events.map(e => e.esp_id).filter(Boolean) as string[])]
  const dominantCategory = getDominantCategory(events)
  const emergency = isEmergencyGroup(events)
  const emergencyDetails = emergency ? extractEmergencyDetails(events) : undefined

  return {
    id: generateGroupId(events),
    events,
    representative: events[0],
    count: events.length,
    timeSpanMs,
    startTime,
    endTime,
    dominantCategory,
    espIds,
    label: createGroupLabel(events, dominantCategory, emergency),
    isEmergency: emergency,
    emergencyDetails,
  }
}

/**
 * Determines the most common category in a set of events
 */
function getDominantCategory(events: UnifiedEvent[]): EventCategory {
  const counts: Record<string, number> = {}
  for (const event of events) {
    const cat = getEventCategory(event)
    counts[cat] = (counts[cat] || 0) + 1
  }

  let maxCategory: EventCategory = 'system'
  let maxCount = 0
  for (const [cat, count] of Object.entries(counts)) {
    if (count > maxCount) {
      maxCount = count
      maxCategory = cat as EventCategory
    }
  }
  return maxCategory
}

/**
 * Creates a human-readable label for a group
 */
function createGroupLabel(events: UnifiedEvent[], dominantCategory: EventCategory, isEmergency = false): string {
  // Emergency has highest priority
  if (isEmergency) {
    return 'Notfall-Stopp'
  }

  // Check for specific patterns
  const types = new Set(events.map(e => e.event_type))

  if (types.has('config_published') || types.has('config_response')) {
    return 'Config-Update'
  }
  if (types.has('actuator_command') || types.has('actuator_response')) {
    return 'Aktor-Steuerung'
  }
  if (types.has('actuator_alert')) {
    return 'Aktor-Alarm'
  }

  // Fall back to category-based labels
  const categoryLabels: Record<EventCategory, string> = {
    'esp-status': 'Geräte-Status',
    'sensors': 'Sensor-Daten',
    'actuators': 'Aktor-Ereignisse',
    'system': 'System-Ereignisse',
  }

  return categoryLabels[dominantCategory] || 'Ereignis-Gruppe'
}

/**
 * Generates a unique ID for a group based on its events
 */
function generateGroupId(events: UnifiedEvent[]): string {
  const first = events[0]
  const last = events[events.length - 1]
  return `group-${first.timestamp}-${last.timestamp}-${events.length}`
}

/**
 * Checks if an event is emergency-related (for extended time window grouping)
 */
function isEmergencyRelatedEvent(event: UnifiedEvent): boolean {
  if ((EMERGENCY_TRIGGER_TYPES as readonly string[]).includes(event.event_type)) return true
  if (event.event_type === 'actuator_alert') {
    const alertType = (event.data as Record<string, unknown>)?.alert_type
    if ((EMERGENCY_ALERT_TYPES as readonly string[]).includes(alertType as string)) return true
  }
  return event.severity === 'critical'
}

/**
 * Checks if a group of events qualifies as an emergency group.
 *
 * A group is emergency if:
 * 1. Contains an explicit emergency trigger event, OR
 * 2. Contains an actuator_alert with alert_type 'emergency_stop' or 'safety_triggered', OR
 * 3. Has 3+ actuator_alert events (implicit emergency)
 */
function isEmergencyGroup(events: UnifiedEvent[]): boolean {
  for (const e of events) {
    if ((EMERGENCY_TRIGGER_TYPES as readonly string[]).includes(e.event_type)) return true
    if (e.event_type === 'actuator_alert') {
      const alertType = (e.data as Record<string, unknown>)?.alert_type
      if ((EMERGENCY_ALERT_TYPES as readonly string[]).includes(alertType as string)) return true
    }
  }

  // 3+ actuator_alerts in a group = likely emergency
  const alertCount = events.filter(e => e.event_type === 'actuator_alert').length
  return alertCount >= 3
}

/**
 * Extracts emergency details from a group of events.
 */
function extractEmergencyDetails(events: UnifiedEvent[]): EventGroup['emergencyDetails'] {
  // Find trigger event (explicit emergency > first alert > first event)
  const triggerEvent =
    events.find(e => (EMERGENCY_TRIGGER_TYPES as readonly string[]).includes(e.event_type)) ||
    events.find(e => {
      if (e.event_type !== 'actuator_alert') return false
      const alertType = (e.data as Record<string, unknown>)?.alert_type
      return (EMERGENCY_ALERT_TYPES as readonly string[]).includes(alertType as string)
    }) ||
    events.find(e => e.event_type === 'actuator_alert') ||
    events[0]

  // Collect affected GPIOs
  const gpios = new Set<number>()
  for (const event of events) {
    if (event.gpio !== undefined) gpios.add(event.gpio)
    const data = event.data as Record<string, unknown> | undefined
    if (typeof data?.gpio === 'number') gpios.add(data.gpio)
    if (Array.isArray(data?.affected_gpios)) {
      for (const g of data.affected_gpios as number[]) gpios.add(g)
    }
  }

  const data = triggerEvent.data as Record<string, unknown> | undefined
  const reason = String(
    data?.reason || triggerEvent.message || data?.message || 'Unbekannter Grund'
  )
  const triggeredBy = String(
    data?.triggered_by || data?.source || 'System'
  )

  return {
    triggerEvent,
    affectedGpios: [...gpios].sort((a, b) => a - b),
    reason,
    triggeredBy,
  }
}
