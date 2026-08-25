import { describe, expect, it } from 'vitest'
import {
  buildPhaseSignature,
  buildPlanCohorts,
  buildCohortPhaseTracks,
} from '@/components/plan-timeline/planCohorts'
import { buildPlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import type { Plant, PlantLifecycleEvent } from '@/types'

const NOW = Date.parse('2026-07-22T12:00:00.000Z')

function plant(partial: Partial<Plant> & Pick<Plant, 'plant_id'>): Plant {
  return {
    qr_code: `QR-${partial.plant_id}`,
    genotype_label: 'Gen',
    phase: 'veg-frueh',
    created_at: '2026-07-01T00:00:00.000Z',
    parent_zone_id: 'z1',
    ...partial,
  }
}

function evt(
  partial: Partial<PlantLifecycleEvent> &
    Pick<
      PlantLifecycleEvent,
      'event_id' | 'plant_id' | 'event_type' | 'event_timestamp'
    >,
): PlantLifecycleEvent {
  return {
    created_at: partial.event_timestamp,
    event_status: 'occurred',
    new_phase: 'veg-frueh',
    ...partial,
  }
}

describe('planCohorts', () => {
  it('should group plants with the same batch_label into one seed cohort', () => {
    const plants = [
      plant({ plant_id: 'p1', batch_label: 'Batch-A', genotype_label: 'A1' }),
      plant({ plant_id: 'p2', batch_label: 'Batch-A', genotype_label: 'A2' }),
    ]
    const cohorts = buildPlanCohorts(plants, new Map())
    expect(cohorts).toHaveLength(1)
    expect(cohorts[0].plantIds).toEqual(['p1', 'p2'])
    expect(cohorts[0].label).toContain('Batch-A')
  })

  it('should keep singleton plants separate when signatures differ', () => {
    const plants = [
      plant({ plant_id: 'p1', genotype_label: 'Solo1' }),
      plant({ plant_id: 'p2', genotype_label: 'Solo2' }),
    ]
    const events = new Map<string, PlantLifecycleEvent[]>([
      [
        'p1',
        [
          evt({
            event_id: 'e1',
            plant_id: 'p1',
            event_type: 'phase_changed',
            event_timestamp: '2026-07-10T00:00:00.000Z',
            new_phase: 'veg-frueh',
          }),
        ],
      ],
      [
        'p2',
        [
          evt({
            event_id: 'e2',
            plant_id: 'p2',
            event_type: 'phase_changed',
            event_timestamp: '2026-07-15T00:00:00.000Z',
            new_phase: 'bluete-stretch',
          }),
        ],
      ],
    ])
    const cohorts = buildPlanCohorts(plants, events)
    expect(cohorts).toHaveLength(2)
  })

  it('should merge singleton plants with identical phase signatures', () => {
    const plants = [
      plant({ plant_id: 'p1', genotype_label: 'Solo1' }),
      plant({ plant_id: 'p2', genotype_label: 'Solo2' }),
    ]
    const events = new Map<string, PlantLifecycleEvent[]>([
      [
        'p1',
        [
          evt({
            event_id: 'e1',
            plant_id: 'p1',
            event_type: 'phase_changed',
            event_timestamp: '2026-07-10T00:00:00.000Z',
            new_phase: 'veg-frueh',
          }),
        ],
      ],
      [
        'p2',
        [
          evt({
            event_id: 'e2',
            plant_id: 'p2',
            event_type: 'phase_changed',
            event_timestamp: '2026-07-10T00:00:00.000Z',
            new_phase: 'veg-frueh',
          }),
        ],
      ],
    ])
    expect(buildPhaseSignature(['p1'], events)).toBe(
      buildPhaseSignature(['p2'], events),
    )
    const cohorts = buildPlanCohorts(plants, events)
    expect(cohorts).toHaveLength(1)
    expect(cohorts[0].plantIds.sort()).toEqual(['p1', 'p2'])
  })

  it('should return empty phase tracks for a zone with no plants', () => {
    const window = buildPlanTimelineWindow('14d', NOW)
    const tracks = buildCohortPhaseTracks([], new Map(), window)
    expect(tracks).toHaveLength(0)
  })
})
