import { describe, expect, it } from 'vitest'
import {
  averageIst,
  buildPastOverlayDelta,
  historicalSollFromLogs,
  resolveBandVisualState,
  resolveMeasureMarkerVisualState,
} from '@/components/plan-timeline/planPastOverlay'
import type { AppliedSetpointLog, PlanSegment } from '@/types/planSegment'

const NOW = Date.parse('2026-07-22T12:00:00.000Z')

function seg(partial: Partial<PlanSegment> & Pick<PlanSegment, 'id' | 'from_ts'>): PlanSegment {
  return {
    zone_id: 'z1',
    domain: 'nutrient_solution',
    measure: 'target_ec',
    value: 2.5,
    recipe_ref: null,
    to_ts: null,
    interp: 'step',
    phase_ref: null,
    status: 'planned',
    tolerance: null,
    created_at: '2026-07-01T00:00:00.000Z',
    updated_at: '2026-07-01T00:00:00.000Z',
    ...partial,
  }
}

function log(
  partial: Partial<AppliedSetpointLog> & Pick<AppliedSetpointLog, 'id' | 'effective_at'>,
): AppliedSetpointLog {
  return {
    zone_id: 'z1',
    subzone_config_id: null,
    domain: 'nutrient_solution',
    measure: 'target_ec',
    applied_value: 2.0,
    rule_id: null,
    segment_id: null,
    origin: 'plan_segment',
    created_at: partial.effective_at,
    ...partial,
  }
}

describe('planPastOverlay', () => {
  it('should mark withdrawn segments as withdrawn (never hidden)', () => {
    const state = resolveBandVisualState(
      seg({
        id: 'w',
        from_ts: '2026-07-10T00:00:00.000Z',
        to_ts: '2026-07-12T00:00:00.000Z',
        status: 'withdrawn',
      }),
      [],
      NOW,
    )
    expect(state).toBe('withdrawn')
  })

  it('should ghost planned past segments without applied evidence', () => {
    const state = resolveBandVisualState(
      seg({
        id: 'p',
        from_ts: '2026-07-10T00:00:00.000Z',
        to_ts: '2026-07-12T00:00:00.000Z',
        status: 'planned',
        value: 2.0,
      }),
      [],
      NOW,
    )
    expect(state).toBe('ghosted')
  })

  it('should keep planned past solid when applied_setpoint_log evidence exists', () => {
    const state = resolveBandVisualState(
      seg({
        id: 'p',
        from_ts: '2026-07-10T00:00:00.000Z',
        to_ts: '2026-07-12T00:00:00.000Z',
        status: 'planned',
      }),
      [
        log({
          id: 'l1',
          segment_id: 'p',
          applied_value: 2.0,
          effective_at: '2026-07-11T00:00:00.000Z',
        }),
      ],
      NOW,
    )
    expect(state).toBe('solid')
  })

  it('should read historical Soll from applied logs, not current plan value', () => {
    const soll = historicalSollFromLogs(
      [
        log({
          id: 'l1',
          applied_value: 2.0,
          effective_at: '2026-07-11T00:00:00.000Z',
        }),
      ],
      'z1',
      'nutrient_solution',
      'target_ec',
      Date.parse('2026-07-10T00:00:00.000Z'),
      Date.parse('2026-07-15T00:00:00.000Z'),
    )
    expect(soll).toBe(2.0)
  })

  it('should compute Ist/Soll/Delta via tankIstSollFormat helpers', () => {
    const delta = buildPastOverlayDelta({
      logs: [
        log({
          id: 'l1',
          applied_value: 2.0,
          effective_at: '2026-07-11T00:00:00.000Z',
        }),
      ],
      zoneId: 'z1',
      domain: 'nutrient_solution',
      measure: 'target_ec',
      fromMs: Date.parse('2026-07-10T00:00:00.000Z'),
      toMs: Date.parse('2026-07-15T00:00:00.000Z'),
      istReadings: [2.1, 2.1],
    })
    expect(delta.historicalSoll).toBe(2.0)
    expect(delta.istAvg).toBeCloseTo(2.1)
    expect(delta.delta).toBeCloseTo(0.1)
    expect(delta.fromAppliedLog).toBe(true)
    expect(delta.deltaDisplay).toMatch(/\+0/)
  })

  it('should average finite Ist readings only', () => {
    expect(averageIst([1, null, 3, undefined, Number.NaN])).toBe(2)
    expect(averageIst([])).toBeNull()
  })

  it('should ghost past planned plant measures and strike reverted', () => {
    expect(
      resolveMeasureMarkerVisualState('planned', NOW - 60_000, NOW),
    ).toBe('ghosted')
    expect(resolveMeasureMarkerVisualState('reverted', NOW - 60_000, NOW)).toBe(
      'withdrawn',
    )
    expect(
      resolveMeasureMarkerVisualState('planned', NOW + 60_000, NOW),
    ).toBe('solid')
  })
})
