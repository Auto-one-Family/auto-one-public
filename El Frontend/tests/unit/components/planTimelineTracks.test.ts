import { describe, expect, it } from 'vitest'
import {
  assignBandLanes,
  buildFullPlanTimelineWindow,
  buildPlanDateTicks,
  buildPlanDomainRows,
  buildPlanTimelineWindow,
  buildPlanZoneSections,
  mergeAdjacentEqualSegments,
  nowMarkerPercent,
  resolvePlanDateTickLabelCollisions,
  segmentsToBands,
} from '@/components/plan-timeline/planTimelineTracks'
import type { PlanSegment } from '@/types/planSegment'

const NOW = Date.parse('2026-07-22T12:00:00.000Z')

function seg(partial: Partial<PlanSegment> & Pick<PlanSegment, 'id' | 'from_ts'>): PlanSegment {
  return {
    zone_id: 'z1',
    domain: 'nutrient_solution',
    measure: 'target_ec',
    value: 1.8,
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

describe('planTimelineTracks', () => {
  it('should build a symmetric past/future window around now', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    expect(window.nowMs).toBe(NOW)
    expect(window.endMs - window.nowMs).toBe(window.nowMs - window.startMs)
    expect(nowMarkerPercent(window)).toBeCloseTo(50, 5)
  })

  it('should build a full window spanning segment and event anchors', () => {
    const window = buildFullPlanTimelineWindow({
      nowMs: NOW,
      segmentFromTs: ['2026-07-01T00:00:00.000Z'],
      segmentToTs: [null],
      eventTimestamps: ['2026-06-15T12:00:00.000Z'],
    })
    expect(window.nowMs).toBe(NOW)
    expect(window.startMs).toBeLessThanOrEqual(Date.parse('2026-06-15T12:00:00.000Z'))
    expect(window.endMs).toBeGreaterThanOrEqual(NOW)
    expect(window.startMs).toBeLessThan(window.endMs)
  })

  it('should fall back to a padded window when no anchors exist', () => {
    const window = buildFullPlanTimelineWindow({ nowMs: NOW })
    expect(window.endMs - window.startMs).toBeGreaterThanOrEqual(7 * 24 * 60 * 60 * 1000)
    expect(window.startMs).toBeLessThan(NOW)
    expect(window.endMs).toBeGreaterThan(NOW)
  })

  it('should merge adjacent equal measure+value segments into one band (overview helper)', () => {
    const window = buildPlanTimelineWindow('14d', NOW)
    const bands = mergeAdjacentEqualSegments(
      [
        seg({
          id: 'a',
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: '2026-07-21T00:00:00.000Z',
          value: 1.8,
        }),
        seg({
          id: 'b',
          from_ts: '2026-07-21T00:00:00.000Z',
          to_ts: '2026-07-22T00:00:00.000Z',
          value: 1.8,
        }),
        seg({
          id: 'c',
          from_ts: '2026-07-22T00:00:00.000Z',
          to_ts: '2026-07-23T00:00:00.000Z',
          value: 2.0,
        }),
      ],
      window,
    )
    expect(bands).toHaveLength(2)
    expect(bands[0].value).toBe(1.8)
    expect(bands[0].id).toContain('a')
    expect(bands[1].value).toBe(2.0)
  })

  it('should scaffold tracks with 1:1 segment bands for edit (AUT-1235)', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    const sections = buildPlanZoneSections({
      zones: [{ zoneId: 'z1', zoneName: 'Zelt 1' }],
      subzonesByZone: {
        z1: [{ subzoneId: 'sz1', subzoneName: 'Tisch A' }],
      },
      segments: [
        seg({
          id: 's1',
          zone_id: 'z1',
          from_ts: '2026-07-21T00:00:00.000Z',
          to_ts: '2026-07-23T00:00:00.000Z',
        }),
        seg({
          id: 's2',
          zone_id: 'z1',
          from_ts: '2026-07-23T00:00:00.000Z',
          to_ts: '2026-07-24T00:00:00.000Z',
          value: 1.8,
        }),
      ],
      domains: ['nutrient_solution', 'climate'],
      window,
    })

    expect(sections).toHaveLength(1)
    // zone-wide × 2 domains + 1 subzone × 2 domains = 4
    expect(sections[0].tracks).toHaveLength(4)
    const zoneWideNutrient = sections[0].tracks.find(
      (t) => t.subzoneId === null && t.domain === 'nutrient_solution',
    )
    expect(zoneWideNutrient?.isEmpty).toBe(false)
    // adjacent equal values stay separate bands for edit
    expect(zoneWideNutrient?.bands).toHaveLength(2)
    expect(zoneWideNutrient?.bands[0].segmentId).toBe('s1')

    const subzoneTrack = sections[0].tracks.find(
      (t) => t.subzoneId === 'sz1' && t.domain === 'nutrient_solution',
    )
    expect(subzoneTrack?.isEmpty).toBe(true)
  })

  it('should stack concurrent EC and pH on separate lanes (no visual overlap)', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    const bands = segmentsToBands(
      [
        seg({
          id: 'ec1',
          measure: 'target_ec',
          value: 1.6,
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
      ],
      window,
    )

    expect(bands).toHaveLength(2)
    const ec = bands.find((b) => b.measure === 'target_ec')
    const ph = bands.find((b) => b.measure === 'target_ph')
    expect(ec?.laneIndex).toBe(0)
    expect(ph?.laneIndex).toBe(1)
    expect(ec?.laneIndex).not.toBe(ph?.laneIndex)
  })

  it('should stack concurrent temperature and humidity on separate lanes', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    const sections = buildPlanZoneSections({
      zones: [{ zoneId: 'z1', zoneName: 'Zelt Wohnzimmer' }],
      subzonesByZone: {},
      segments: [
        seg({
          id: 't1',
          zone_id: 'z1',
          domain: 'climate',
          measure: 'target_temperature',
          value: 22,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
        }),
        seg({
          id: 'h1',
          zone_id: 'z1',
          domain: 'climate',
          measure: 'target_humidity',
          value: 55,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
        }),
      ],
      domains: ['climate'],
      window,
    })

    const climate = sections[0].tracks.find((t) => t.domain === 'climate')
    expect(climate?.laneCount).toBe(2)
    expect(climate?.bands.find((b) => b.measure === 'target_temperature')?.laneIndex).toBe(0)
    expect(climate?.bands.find((b) => b.measure === 'target_humidity')?.laneIndex).toBe(1)
  })

  it('should build operator domain rows for a single zone', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    const rows = buildPlanDomainRows({
      zoneId: 'z1',
      zoneName: 'Zelt 1',
      segments: [
        seg({
          id: 't1',
          zone_id: 'z1',
          domain: 'climate',
          measure: 'target_temperature',
          value: 22,
          from_ts: '2026-07-20T00:00:00.000Z',
          to_ts: null,
        }),
      ],
      window,
    })
    expect(rows.map((r) => r.key)).toEqual([
      'luft',
      'wasser',
      'boden',
      'licht',
      'pflanze',
    ])
    expect(rows[0].track?.bands).toHaveLength(1)
    expect(rows[1].track?.isEmpty).toBe(true)
    expect(rows[2].kind).toBe('empty')
    expect(rows[2].emptyHint).toBe('kein Plan — keine Bodenspur')
    expect(rows[3].kind).toBe('empty')
    expect(rows[3].emptyHint).toBe('Licht hier nicht planbar')
    expect(rows[4].kind).toBe('measures')
  })

  it('should place day ticks and a heute marker in the window', () => {
    const window = buildPlanTimelineWindow('7d', NOW)
    const ticks = buildPlanDateTicks(window)
    expect(ticks.length).toBeGreaterThan(3)
    expect(ticks.some((t) => t.isToday && t.label === 'heute')).toBe(true)
  })

  it('should keep heute and drop colliding date labels on one line', () => {
    const resolved = resolvePlanDateTickLabelCollisions([
      { ms: 1, leftPct: 48, label: '26.07.', isToday: false },
      { ms: 2, leftPct: 50, label: 'heute', isToday: true },
      { ms: 3, leftPct: 51.5, label: '28.07.', isToday: false },
      { ms: 4, leftPct: 60, label: '30.07.', isToday: false },
    ])
    expect(resolved.filter((t) => t.isToday)).toHaveLength(1)
    expect(resolved.some((t) => t.label === '28.07.')).toBe(false)
    expect(resolved.some((t) => t.label === '30.07.')).toBe(true)
    // No two kept labels closer than gap
    for (let i = 1; i < resolved.length; i++) {
      expect(
        Math.abs(resolved[i].leftPct - resolved[i - 1].leftPct),
      ).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('should not render a calendar date label on the same day as heute', () => {
    const window = buildPlanTimelineWindow('14d', NOW)
    const ticks = buildPlanDateTicks(window)
    const heute = ticks.find((t) => t.isToday)
    expect(heute?.label).toBe('heute')
    const todayDateLabel = new Date(NOW).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
    })
    expect(ticks.some((t) => !t.isToday && t.label === todayDateLabel)).toBe(
      false,
    )
  })

  it('should pack non-overlapping same-measure bands onto one lane', () => {
    const { bands, laneCount } = assignBandLanes([
      {
        id: 'a',
        segmentId: 'a',
        measure: 'target_ec',
        value: 1.5,
        fromMs: 0,
        toMs: 10,
        fromTs: 't0',
        toTs: 't1',
        leftPct: 0,
        widthPct: 10,
        label: 'EC 1.5',
        tooltip: '',
        laneIndex: 0,
      },
      {
        id: 'b',
        segmentId: 'b',
        measure: 'target_ec',
        value: 1.8,
        fromMs: 10,
        toMs: 20,
        fromTs: 't1',
        toTs: 't2',
        leftPct: 10,
        widthPct: 10,
        label: 'EC 1.8',
        tooltip: '',
        laneIndex: 0,
      },
    ])
    expect(laneCount).toBe(1)
    expect(bands.every((b) => b.laneIndex === 0)).toBe(true)
  })
})
