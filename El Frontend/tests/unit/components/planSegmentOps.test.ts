import { describe, expect, it } from 'vitest'
import {
  buildMergePlan,
  buildSplitPlan,
  findMergeCandidate,
} from '@/components/plan-timeline/planSegmentOps'
import type { PlanSegment } from '@/types/planSegment'

function seg(partial: Partial<PlanSegment> & Pick<PlanSegment, 'id' | 'from_ts' | 'to_ts'>): PlanSegment {
  return {
    zone_id: 'z1',
    domain: 'nutrient_solution',
    measure: 'target_ec',
    value: 2.0,
    recipe_ref: null,
    interp: 'step',
    phase_ref: null,
    status: 'planned',
    tolerance: null,
    created_at: '2026-07-01T00:00:00.000Z',
    updated_at: '2026-07-01T00:00:00.000Z',
    ...partial,
  }
}

describe('planSegmentOps', () => {
  it('should build split payloads for Given/When/Then AUT-1235', () => {
    const segment = seg({
      id: 'a',
      from_ts: '2026-07-20T00:00:00.000Z',
      to_ts: '2026-07-22T00:00:00.000Z',
      value: 2.0,
    })
    const splitMs = Date.parse('2026-07-21T00:00:00.000Z')
    const plan = buildSplitPlan(segment, splitMs, 2.4)
    expect(plan).not.toBeNull()
    expect(plan!.leftUpdate.payload.to_ts).toBe('2026-07-21T00:00:00.000Z')
    expect(plan!.rightCreate.from_ts).toBe('2026-07-21T00:00:00.000Z')
    expect(plan!.rightCreate.to_ts).toBe('2026-07-22T00:00:00.000Z')
    expect(plan!.rightCreate.value).toBe(2.4)
    expect(plan!.rightCreate.zone_id).toBe('z1')
  })

  it('should reject split outside the interval', () => {
    const segment = seg({
      id: 'a',
      from_ts: '2026-07-20T00:00:00.000Z',
      to_ts: '2026-07-22T00:00:00.000Z',
    })
    expect(buildSplitPlan(segment, Date.parse('2026-07-20T00:00:00.000Z'), 2.4)).toBeNull()
  })

  it('should find adjacent equal-value merge candidate and build merge plan', () => {
    const a = seg({
      id: 'a',
      from_ts: '2026-07-20T00:00:00.000Z',
      to_ts: '2026-07-21T00:00:00.000Z',
      value: 1.8,
    })
    const b = seg({
      id: 'b',
      from_ts: '2026-07-21T00:00:00.000Z',
      to_ts: '2026-07-22T00:00:00.000Z',
      value: 1.8,
    })
    const candidate = findMergeCandidate(a, [a, b])
    expect(candidate?.id).toBe('b')
    const plan = buildMergePlan(a, b)
    expect(plan?.survivorUpdate.id).toBe('a')
    expect(plan?.survivorUpdate.payload.to_ts).toBe('2026-07-22T00:00:00.000Z')
    expect(plan?.deleteId).toBe('b')
  })
})
