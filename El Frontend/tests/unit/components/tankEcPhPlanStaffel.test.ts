import { describe, expect, it } from 'vitest'
import type { PlanSegment } from '@/types/planSegment'
import {
  buildClimateStaffeln,
  buildEcPhStaffeln,
  dateInputToIsoStart,
  findActiveClimateStaffel,
  findActiveEcPhStaffel,
  formatMeasureValue,
  formatStaffelRange,
  isoToDateInput,
  segmentCoversAt,
} from '@/components/plants/tankEcPhPlanStaffel'

function seg(
  partial: Partial<PlanSegment> &
    Pick<PlanSegment, 'id' | 'measure' | 'from_ts' | 'to_ts' | 'value'>,
): PlanSegment {
  return {
    zone_id: 'zelt_wohnzimmer',
    domain: 'nutrient_solution',
    recipe_ref: null,
    interp: 'step',
    phase_ref: null,
    status: 'planned',
    tolerance: null,
    created_at: '2026-07-01T00:00:00Z',
    updated_at: '2026-07-01T00:00:00Z',
    ...partial,
  }
}

describe('tankEcPhPlanStaffel', () => {
  it('should pair EC and pH sharing the same window into one staffel', () => {
    const staffeln = buildEcPhStaffeln(
      [
        seg({
          id: 'ec1',
          measure: 'target_ec',
          value: 1.8,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
        }),
        seg({
          id: 'ph1',
          measure: 'target_ph',
          value: 6.0,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
        }),
        seg({
          id: 'ec2',
          measure: 'target_ec',
          value: 2.0,
          from_ts: '2026-08-01T00:00:00.000Z',
          to_ts: '2026-09-01T00:00:00.000Z',
        }),
      ],
      'zelt_wohnzimmer',
    )

    expect(staffeln).toHaveLength(2)
    expect(staffeln[0]?.ec?.value).toBe(1.8)
    expect(staffeln[0]?.ph?.value).toBe(6.0)
    expect(staffeln[0]?.toTs).toBeNull()
    expect(staffeln[1]?.ec?.value).toBe(2.0)
    expect(staffeln[1]?.ph).toBeNull()
  })

  it('should ignore climate / other zones', () => {
    const staffeln = buildEcPhStaffeln(
      [
        seg({
          id: 'other-zone',
          zone_id: 'other',
          measure: 'target_ec',
          value: 1,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
        }),
        {
          ...seg({
            id: 'climate',
            measure: 'target_temperature',
            value: 24,
            from_ts: '2026-07-20T00:00:00.000Z',
            to_ts: null,
          }),
          domain: 'climate',
        },
      ],
      'zelt_wohnzimmer',
    )
    expect(staffeln).toHaveLength(0)
  })

  it('should resolve active staffel @now with open-ended to_ts', () => {
    const staffeln = buildEcPhStaffeln(
      [
        seg({
          id: 'ec1',
          measure: 'target_ec',
          value: 1.5,
          from_ts: '2026-07-01T00:00:00.000Z',
          to_ts: '2026-07-15T00:00:00.000Z',
        }),
        seg({
          id: 'ec2',
          measure: 'target_ec',
          value: 1.8,
          from_ts: '2026-07-15T00:00:00.000Z',
          to_ts: null,
        }),
        seg({
          id: 'ph2',
          measure: 'target_ph',
          value: 6.0,
          from_ts: '2026-07-15T00:00:00.000Z',
          to_ts: null,
        }),
      ],
      'zelt_wohnzimmer',
    )
    const at = Date.parse('2026-07-20T12:00:00.000Z')
    const active = findActiveEcPhStaffel(staffeln, at)
    expect(active?.ec?.value).toBe(1.8)
    expect(active?.ph?.value).toBe(6.0)
  })

  it('should use half-open cover [from, to)', () => {
    const s = seg({
      id: 'ec1',
      measure: 'target_ec',
      value: 1,
      from_ts: '2026-07-01T00:00:00.000Z',
      to_ts: '2026-07-10T00:00:00.000Z',
    })
    expect(segmentCoversAt(s, Date.parse('2026-07-01T00:00:00.000Z'))).toBe(true)
    expect(segmentCoversAt(s, Date.parse('2026-07-09T23:59:59.000Z'))).toBe(true)
    expect(segmentCoversAt(s, Date.parse('2026-07-10T00:00:00.000Z'))).toBe(false)
  })

  it('should pair temperature and humidity sharing the same climate window', () => {
    const staffeln = buildClimateStaffeln(
      [
        {
          ...seg({
            id: 't1',
            measure: 'target_temperature',
            value: 24,
            from_ts: '2026-07-20T00:00:00.000Z',
            to_ts: null,
          }),
          domain: 'climate',
        },
        {
          ...seg({
            id: 'h1',
            measure: 'target_humidity',
            value: 60,
            from_ts: '2026-07-20T00:00:00.000Z',
            to_ts: null,
          }),
          domain: 'climate',
        },
        seg({
          id: 'ec-ignored',
          measure: 'target_ec',
          value: 1.8,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
        }),
      ],
      'zelt_wohnzimmer',
    )
    expect(staffeln).toHaveLength(1)
    expect(staffeln[0]?.temperature?.value).toBe(24)
    expect(staffeln[0]?.humidity?.value).toBe(60)
  })

  it('should resolve active climate staffel @now', () => {
    const staffeln = buildClimateStaffeln(
      [
        {
          ...seg({
            id: 't1',
            measure: 'target_temperature',
            value: 22,
            from_ts: '2026-07-15T00:00:00.000Z',
            to_ts: null,
          }),
          domain: 'climate',
        },
      ],
      'zelt_wohnzimmer',
    )
    const active = findActiveClimateStaffel(
      staffeln,
      Date.parse('2026-07-20T12:00:00.000Z'),
    )
    expect(active?.temperature?.value).toBe(22)
    expect(active?.humidity).toBeNull()
  })

  it('should format range and values for humans', () => {
    expect(formatStaffelRange('2026-07-20T00:00:00.000Z', null)).toMatch(/^ab /)
    expect(formatMeasureValue(null)).toBe('—')
    expect(formatMeasureValue(1.8)).toBe('1.8')
    expect(isoToDateInput('2026-07-20T22:00:00.000Z')).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(dateInputToIsoStart('2026-07-20')).toMatch(/^\d{4}-\d{2}-\d{2}T/)
    expect(dateInputToIsoStart('bad')).toBeNull()
  })
})
