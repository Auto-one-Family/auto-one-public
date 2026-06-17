/**
 * useCalibration Composable
 *
 * Manages pH, EC, and moisture sensor calibration wizard state.
 *
 * pH Calibration (2-point):
 *   Point 1: pH 4.0 buffer → record raw ADC value
 *   Point 2: pH 7.0 buffer → record raw ADC value
 *   Result: slope + offset for linear interpolation
 *
 * EC Calibration (1 or 2-point):
 *   Point 1: Dry electrode (air) → record zero point
 *   Point 2: Calibration solution (e.g., 1413 µS/cm) → record reference
 *   Result: factor for conversion
 *
 * Moisture Calibration (2-point dry/wet):
 *   dry_value: ADC reading in dry soil
 *   wet_value: ADC reading in wet soil
 *   Result: dry/wet boundaries for percentage mapping
 */

import { ref, computed } from 'vue'

export interface CalibrationPoint {
  rawValue: number
  referenceValue: number
  timestamp: number
}

export interface CalibrationResult {
  slope: number
  offset: number
  points: CalibrationPoint[]
  calibratedAt: string
}

export type CalibrationStep = 'idle' | 'point1' | 'point2' | 'complete'

export function useCalibration() {
  const calibrationType = ref<'pH' | 'EC' | 'moisture' | null>(null)
  const step = ref<CalibrationStep>('idle')
  const point1 = ref<CalibrationPoint | null>(null)
  const point2 = ref<CalibrationPoint | null>(null)
  const result = ref<CalibrationResult | null>(null)

  // Moisture-specific refs (dry/wet ADC boundaries)
  const dryValue = ref<number>(3200)
  const wetValue = ref<number>(1500)

  const isActive = computed(() => step.value !== 'idle')
  const isComplete = computed(() => step.value === 'complete')

  /**
   * Start a calibration wizard
   */
  function startCalibration(type: 'pH' | 'EC' | 'moisture') {
    calibrationType.value = type
    step.value = 'point1'
    point1.value = null
    point2.value = null
    result.value = null
  }

  /**
   * Set calibration point 1
   */
  function setPoint1(rawValue: number, referenceValue: number) {
    point1.value = {
      rawValue,
      referenceValue,
      timestamp: Date.now(),
    }
    step.value = 'point2'
  }

  /**
   * Set calibration point 2 and calculate result
   */
  function setPoint2(rawValue: number, referenceValue: number) {
    point2.value = {
      rawValue,
      referenceValue,
      timestamp: Date.now(),
    }

    if (point1.value) {
      const p1 = point1.value
      const p2 = { rawValue, referenceValue }

      // Linear interpolation: y = slope * x + offset
      // where x = rawValue, y = calibrated value
      const slope = (p2.referenceValue - p1.referenceValue) / (p2.rawValue - p1.rawValue)
      const offset = p1.referenceValue - slope * p1.rawValue

      result.value = {
        slope: Math.round(slope * 100000) / 100000,
        offset: Math.round(offset * 100) / 100,
        points: [p1, { rawValue, referenceValue, timestamp: Date.now() }],
        calibratedAt: new Date().toISOString(),
      }
    }

    step.value = 'complete'
  }

  /**
   * Get calibration data for saving to the sensor config
   */
  function getCalibrationData(): Record<string, unknown> | null {
    // Moisture uses dry/wet refs directly, no result.value needed
    if (calibrationType.value === 'moisture') {
      return {
        type: 'moisture_2point',
        dry_value: dryValue.value,
        wet_value: wetValue.value,
        invert: false,
        calibrated_at: new Date().toISOString(),
      }
    }

    if (!result.value) return null

    if (calibrationType.value === 'pH') {
      return {
        type: 'linear_2point',
        slope: result.value.slope,
        offset: result.value.offset,
        point1_raw: point1.value?.rawValue,
        point1_ref: point1.value?.referenceValue,
        point2_raw: point2.value?.rawValue,
        point2_ref: point2.value?.referenceValue,
        calibrated_at: result.value.calibratedAt,
      }
    }

    if (calibrationType.value === 'EC') {
      return {
        type: 'linear_2point',
        slope: result.value.slope,
        offset: result.value.offset,
        point1_raw: point1.value?.rawValue,
        point1_ref: point1.value?.referenceValue,
        point2_raw: point2.value?.rawValue,
        point2_ref: point2.value?.referenceValue,
        calibrated_at: result.value.calibratedAt,
      }
    }

    return null
  }

  /**
   * Reset the calibration wizard
   */
  function resetCalibration() {
    calibrationType.value = null
    step.value = 'idle'
    point1.value = null
    point2.value = null
    result.value = null
  }

  return {
    calibrationType,
    step,
    point1,
    point2,
    result,
    dryValue,
    wetValue,
    isActive,
    isComplete,
    startCalibration,
    setPoint1,
    setPoint2,
    getCalibrationData,
    resetCalibration,
  }
}
