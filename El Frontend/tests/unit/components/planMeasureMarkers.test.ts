import { describe, expect, it } from 'vitest'
import {
  buildPlannedMeasureMarkers,
  defaultExecutedMeasureWindowStartMs,
  isPlanPlantMeasureEventType,
} from '@/components/plan-timeline/planMeasureMarkers'
import { buildPlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import type { PlantLifecycleEvent } from '@/types'

const NOW = Date.parse('2026-07-22T12:00:00.000Z')

function evt(partial: Partial<PlantLifecycleEvent> & Pick<PlantLifecycleEvent, 'event_id'>): PlantLifecycleEvent {
  return {
    plant_id: 'p1',
    event_type: 'topping',
    event_timestamp: '2026-07-23T10:00:00.000Z',
    created_at: '2026-07-22T10:00:00.000Z',
    event_status: 'planned',
    ...partial,
  }
}

describe('planMeasureMarkers', () => {
  it('should keep planned + reverted and also show executed measures', () => {
    expect(isPlanPlantMeasureEventType('topping')).toBe(true)
    expect(isPlanPlantMeasureEventType('defoliation')).toBe(true)
    const window = buildPlanTimelineWindow('14d', NOW)
    const markers = buildPlannedMeasureMarkers(
      [
        evt({ event_id: '1', event_status: 'planned' }),
        evt({ event_id: '2', event_status: 'occurred' }),
        evt({
          event_id: '3',
          event_status: 'planned',
          event_type: 'phase_changed',
        }),
        evt({
          event_id: '4',
          event_status: 'reverted',
          event_timestamp: '2026-07-21T10:00:00.000Z',
        }),
      ],
      window,
      (t) => t,
    )
    expect(markers.map((m) => m.eventId).sort()).toEqual(['1', '2', '4'])
    expect(markers.find((m) => m.eventId === '4')?.visualState).toBe('withdrawn')
  })

  it('should render executed measures with a sensor window as a range', () => {
    const window = buildPlanTimelineWindow('14d', NOW)
    const markers = buildPlannedMeasureMarkers(
      [
        evt({
          event_id: 'range',
          event_status: 'occurred',
          event_timestamp: new Date(NOW).toISOString(),
          linked_sensor_window_start: new Date(NOW - 3_600_000).toISOString(),
          linked_sensor_window_end: new Date(NOW + 3_600_000).toISOString(),
          new_phase: 'veg-frueh',
          zone_id: 'z1',
        }),
      ],
      window,
      () => 'Entlauben',
    )
    expect(markers).toHaveLength(1)
    expect(markers[0].widthPct).toBeGreaterThan(0)
    expect(markers[0].phase).toBe('veg-frueh')
    expect(markers[0].zoneId).toBe('z1')
  })

  it('should place markers by event_timestamp percent in window', () => {
    const window = buildPlanTimelineWindow('14d', NOW)
    const markers = buildPlannedMeasureMarkers(
      [evt({ event_id: '1', event_timestamp: new Date(NOW).toISOString() })],
      window,
      () => 'Schnitt',
    )
    expect(markers[0].leftPct).toBeCloseTo(50, 0)
    expect(markers[0].label).toBe('Schnitt')
  })

  it('should clamp default executed window to the current phase start', () => {
    const phaseStart = NOW - 15 * 60 * 1000
    expect(defaultExecutedMeasureWindowStartMs(NOW, phaseStart)).toBe(phaseStart)
    expect(defaultExecutedMeasureWindowStartMs(NOW, NOW - 3 * 60 * 60 * 1000)).toBe(
      NOW - 60 * 60 * 1000,
    )
    expect(defaultExecutedMeasureWindowStartMs(NOW)).toBe(NOW - 60 * 60 * 1000)
  })
})
