import { describe, expect, it } from 'vitest'
import {
  buildVpdOverlayBands,
  calculateVpdKpa,
} from '@/components/plan-timeline/planVpdOverlay'
import { buildPlanTimelineWindow } from '@/components/plan-timeline/planTimelineTracks'
import type { PlanSegment } from '@/types/planSegment'

const NOW = Date.parse('2026-07-22T12:00:00.000Z')

function seg(partial: Partial<PlanSegment> & Pick<PlanSegment, 'id' | 'from_ts' | 'measure'>): PlanSegment {
  return {
    zone_id: 'z1',
    domain: 'climate',
    value: null,
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

describe('planVpdOverlay', () => {
  it('should compute Magnus-Tetens VPD matching server formula shape', () => {
    const vpd = calculateVpdKpa(25, 60)
    expect(vpd).not.toBeNull()
    expect(vpd!).toBeGreaterThan(0.5)
    expect(vpd!).toBeLessThan(2)
  })

  it('should derive computable VPD band when T and RH overlap', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    const bands = buildVpdOverlayBands(
      [
        seg({
          id: 't1',
          measure: 'target_temperature',
          value: 24,
          from_ts: '2026-07-21T00:00:00.000Z',
          to_ts: '2026-07-23T00:00:00.000Z',
        }),
        seg({
          id: 'h1',
          measure: 'target_humidity',
          value: 60,
          from_ts: '2026-07-21T00:00:00.000Z',
          to_ts: '2026-07-23T00:00:00.000Z',
        }),
      ],
      'z1',
      window,
    )
    expect(bands.length).toBeGreaterThan(0)
    expect(bands.every((b) => b.computable)).toBe(true)
    expect(bands[0].vpdKpa).not.toBeNull()
  })

  it('should mark missing humidity explicitly (anti-silence)', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    const bands = buildVpdOverlayBands(
      [
        seg({
          id: 't1',
          measure: 'target_temperature',
          value: 24,
          from_ts: '2026-07-21T00:00:00.000Z',
          to_ts: '2026-07-23T00:00:00.000Z',
        }),
      ],
      'z1',
      window,
    )
    expect(bands.length).toBeGreaterThan(0)
    expect(bands[0].computable).toBe(false)
    expect(bands[0].reason).toBe('missing_target_humidity')
    expect(bands[0].label).toContain('Feuchte-Ziel fehlt')
  })
})
