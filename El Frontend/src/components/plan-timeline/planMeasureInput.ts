/**
 * Typed numeric input constraints per plan measure (AUT-1235 T5 / AUT-1240).
 *
 * Used by PlanSegmentEditorModal + TankEcPhPlanEditor — number inputs with
 * min/max/step, never free-text for numeric setpoints.
 *
 * EC unit = µS/cm (AUT-1268 / E1) — same as sensorDefaults.getSensorUnit('ec'),
 * live sensor_data, and Logic hysteresis. Not mS/cm.
 *
 * No agronomic default values (empty slots until the operator enters a number).
 * min/max are physical input bounds only, not crop targets.
 */

export interface PlanMeasureInputSpec {
  measure: string
  label: string
  unit: string
  min: number
  max: number
  step: number
}

export const PLAN_MEASURE_INPUT_SPECS: Record<string, PlanMeasureInputSpec> = {
  target_ec: {
    measure: 'target_ec',
    label: 'EC',
    // SSOT with SENSOR_TYPE_CONFIG.EC / getSensorUnit('ec')
    unit: 'µS/cm',
    min: 0,
    max: 5000,
    step: 0.1,
  },
  target_ph: {
    measure: 'target_ph',
    label: 'pH',
    unit: '',
    min: 0,
    max: 14,
    step: 0.1,
  },
  target_temperature: {
    measure: 'target_temperature',
    label: 'Temperatur-Ziel',
    unit: '°C',
    min: 0,
    max: 45,
    step: 0.5,
  },
  target_humidity: {
    measure: 'target_humidity',
    label: 'Feuchte-Ziel',
    unit: '%',
    min: 0,
    max: 100,
    step: 1,
  },
  target_co2: {
    measure: 'target_co2',
    label: 'CO₂',
    unit: 'ppm',
    min: 200,
    max: 2000,
    step: 50,
  },
}

export function getPlanMeasureInputSpec(measure: string): PlanMeasureInputSpec | null {
  return PLAN_MEASURE_INPUT_SPECS[measure] ?? null
}

export function clampPlanMeasureValue(measure: string, value: number): number {
  const spec = getPlanMeasureInputSpec(measure)
  if (!spec || Number.isNaN(value)) return value
  const stepped = Math.round(value / spec.step) * spec.step
  const rounded = Number(stepped.toFixed(6))
  return Math.min(spec.max, Math.max(spec.min, rounded))
}

export function isNumericPlanMeasure(measure: string): boolean {
  return measure in PLAN_MEASURE_INPUT_SPECS
}
