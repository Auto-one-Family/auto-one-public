import { describe, it, expect } from 'vitest'
import {
  effectiveBandFromPlan,
  extractNodeBand,
  formatDeadbandEdge,
  formatEffectiveDeadbandLabel,
  nodeBandFromFlowSensorData,
  planMeasureToSensorType,
  recenterBand,
  recenterHysteresisBand,
} from '@/utils/planDeadbandDisplay'

describe('planDeadbandDisplay', () => {
  it('should recenter between-band preserving half-width (server formula)', () => {
    // Node 1300–1400 (center 1350, ±50) + Plan 1400 → 1350–1450
    const r = recenterBand(1400, 1300, 1400)
    expect(r.halfWidth).toBe(50)
    expect(r.low).toBe(1350)
    expect(r.high).toBe(1450)
  })

  it('should extract hysteresis band from conditions', () => {
    const band = extractNodeBand(
      [
        {
          type: 'hysteresis',
          sensor_type: 'ec',
          activate_above: 1400,
          deactivate_below: 1300,
        },
      ],
      'ec',
    )
    expect(band).toMatchObject({ kind: 'hysteresis_cooling', low: 1300, high: 1400 })
  })

  it('should format effective deadband in plain operator language', () => {
    const band = extractNodeBand(
      {
        type: 'sensor',
        sensor_type: 'ec',
        operator: 'between',
        min: 1300,
        max: 1400,
      },
      'ec',
    )
    const label = formatEffectiveDeadbandLabel({
      followsPlan: true,
      planValue: 1400,
      nodeBand: band,
      origin: 'plan_segment',
      unit: 'µS/cm',
      sensorType: 'ec',
    })
    expect(label).toContain('Aktuell: Soll 1400 µS/cm')
    expect(label).toContain('Ein/Aus-Band 1350–1450 µS/cm')
    expect(label).not.toContain('plan-abgeleitet')
    expect(label).not.toContain('Node-eigen')
    expect(label).not.toContain('1300–1400')
  })

  it('should map plan measure to sensor type', () => {
    expect(planMeasureToSensorType('target_ec')).toBe('ec')
    expect(planMeasureToSensorType('target_ph')).toBe('ph')
  })

  it('should build effective band from plan setpoint (between)', () => {
    const eff = effectiveBandFromPlan(1400, {
      kind: 'between',
      low: 1300,
      high: 1400,
      nodeCenter: 1350,
    })
    expect(eff.low).toBe(1350)
    expect(eff.high).toBe(1450)
    expect(eff.source).toBe('plan_segment')
  })

  it('should anchor cooling hysteresis OFF to setpoint (upper gap only)', () => {
    // gap 100: Node Aus 1300 / Ein 1400 → Plan 1400 → Aus 1400 / Ein 1500
    const r = recenterHysteresisBand(1400, 1300, 1400, 'hysteresis_cooling')
    expect(r.low).toBe(1400)
    expect(r.high).toBe(1500)
    expect(r.halfWidth).toBe(100)

    const band = nodeBandFromFlowSensorData({
      operator: 'hysteresis',
      activateAbove: 1400,
      deactivateBelow: 1300,
    })
    const eff = effectiveBandFromPlan(1400, band!)
    expect(eff.low).toBe(1400)
    expect(eff.high).toBe(1500)
  })

  it('should anchor heating hysteresis OFF to setpoint (lower gap only)', () => {
    const band = nodeBandFromFlowSensorData({
      operator: 'hysteresis',
      activateBelow: 1300,
      deactivateAbove: 1400,
    })
    expect(band).toMatchObject({ kind: 'hysteresis_heating', low: 1300, high: 1400 })
    const eff = effectiveBandFromPlan(1400, band!)
    expect(eff.low).toBe(1300)
    expect(eff.high).toBe(1400)
  })

  it('should format pH plan deadband as Aus=Soll, Ein=Soll+gap', () => {
    // Tank-Soll 6.0, Totband nur nach oben 0.2 → Aus 6.00 / Ein 6.20
    const band = {
      kind: 'hysteresis_cooling' as const,
      low: 5.8,
      high: 6.0,
      nodeCenter: 5.9,
    }
    const eff = effectiveBandFromPlan(6, band)
    expect(formatDeadbandEdge(eff.low, 'ph')).toBe('6,00')
    expect(formatDeadbandEdge(eff.high, 'ph')).toBe('6,20')
    expect(formatDeadbandEdge(6.199999999999999, 'ph')).toBe('6,20')

    const label = formatEffectiveDeadbandLabel({
      followsPlan: true,
      planValue: 6,
      nodeBand: band,
      origin: 'plan_segment',
      unit: 'pH',
      sensorType: 'ph',
    })
    expect(label).toBe('Aktuell: Soll 6,00 pH, Ein/Aus-Band 6,00–6,20 pH')
    expect(label).not.toContain('9999')
    expect(label).not.toContain('0000')
  })
})
