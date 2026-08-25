import { describe, it, expect } from 'vitest'
import { formatLivePlanHint, formatPlanOriginLabel } from '@/utils/planOriginDisplay'
import type { AppliedSetpointLog } from '@/types/planSegment'

function log(partial: Partial<AppliedSetpointLog>): AppliedSetpointLog {
  return {
    id: 'log-1',
    zone_id: 'z1',
    subzone_config_id: null,
    domain: 'nutrient_solution',
    measure: 'target_ec',
    applied_value: 1350,
    effective_at: '2026-07-25T12:00:00Z',
    rule_id: 'rule-1',
    segment_id: null,
    origin: 'static_fallback',
    created_at: '2026-07-25T12:00:00Z',
    ...partial,
  }
}

describe('planOriginDisplay', () => {
  it('should not claim plan is off when follows_plan with static_fallback', () => {
    const label = formatPlanOriginLabel({
      followsPlan: true,
      hasZoneDomainMeasure: true,
      isLoading: false,
      log: log({ applied_value: 1350, origin: 'static_fallback' }),
    })
    expect(label).toContain('1350')
    expect(label).toContain('Plan-Abo AN')
    expect(label).toContain('Fallback')
    expect(label).toContain('nicht „Plan aus“')
    expect(label).not.toMatch(/kein Plan-Segment aktiv/)
  })

  it('should surface segment id when origin is plan_segment (trigger feed)', () => {
    const label = formatPlanOriginLabel({
      followsPlan: true,
      hasZoneDomainMeasure: true,
      isLoading: false,
      log: log({
        applied_value: 1400,
        origin: 'plan_segment',
        segment_id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
      }),
    })
    expect(label).toContain('1400')
    expect(label).toContain('aaaaaaaa')
    expect(label).toContain('speist Trigger')
  })

  it('should format live plan@now hint read-only', () => {
    expect(
      formatLivePlanHint({
        value: 1400,
        segmentId: 'seg-12345678-xxxx',
        measure: 'target_ec',
      }),
    ).toContain('1400')
    expect(formatLivePlanHint(null)).toBeNull()
  })
})
