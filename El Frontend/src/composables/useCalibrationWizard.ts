/**
 * useCalibrationWizard Composable
 *
 * Orchestrates the full calibration wizard flow:
 *   select → point1 → point2 → confirm → done | error
 *
 * Consolidates phase machine, EC presets, sensor type presets,
 * device selection, API submission, and navigation logic.
 *
 * Bodenfeuchte nutzt `method: moisture_2point`, damit der Server `derived` mit
 * dry_value/wet_value fuer den MoistureSensorProcessor schreibt (Schema-Alignment).
 *
 * Phase: F-P1 (State-Refactor)
 */

import { ref, computed, onUnmounted, getCurrentInstance, watch, type Ref, type ComputedRef } from 'vue'
import { calibrationApi, normalizeCalibrationSensorType } from '@/api/calibration'
import type { CalibrationPoint, CalibrateResponse } from '@/api/calibration'
import { sensorsApi } from '@/api/sensors'
import { formatUiApiError, toUiApiError } from '@/api/uiApiError'
import { useUiStore } from '@/shared/stores/ui.store'
import { useWebSocket } from '@/composables/useWebSocket'
import type { WebSocketMessage } from '@/services/websocket'

// ─── Types ────────────────────────────────────────────────────────────────────

export type WizardPhase = 'select' | 'point1' | 'point2' | 'confirm' | 'finalizing' | 'done' | 'error'

export type CalibrationSensorType = 'ph' | 'ec' | 'moisture' | 'soil_moisture' | 'temperature'

/** custom = 1-Punkt (ec_single_point / ec_1point) — DEFAULT */
export type EcPresetId = '0_1413' | '1413_12880' | 'custom'

export interface SensorTypePreset {
  label: string
  point1Label: string
  point1Ref: number
  point2Label?: string
  point2Ref?: number
  expectedPoints: 1 | 2
  calibrationMethod: 'moisture_2point' | 'ph_2point' | 'ec_1point' | 'ec_2point' | 'ec_linear_2point' | 'linear_2point'
  /** Number of ADC samples to average for one calibration point. Default: 1 (no averaging). EC sensors use 3. */
  sampleCount?: number
  /** AUT-299: Whether the first point can be skipped (e.g. EC air reference) */
  point1Skippable?: boolean
}

export interface UseCalibrationWizardOptions {
  /** If true, skip the 'select' phase (device already known) */
  skipSelect?: boolean
  /** Pre-selected ESP ID */
  espId?: string
  /** Pre-selected GPIO */
  gpio?: number
  /** Pre-selected sensor type */
  sensorType?: string
}

export interface UseCalibrationWizardReturn {
  // Phase machine
  phase: Ref<WizardPhase>
  isActive: ComputedRef<boolean>

  // Selection state
  selectedEspId: Ref<string>
  selectedGpio: Ref<number | null>
  selectedSensorType: Ref<string>
  ecPreset: Ref<EcPresetId>

  // Data
  points: Ref<CalibrationPoint[]>
  calibrationResult: Ref<CalibrateResponse | null>
  errorMessage: Ref<string>
  isSubmitting: Ref<boolean>

  // F-P2: Live trigger state
  isMeasuring: Ref<boolean>
  lastRawValue: Ref<number | null>
  measurementQuality: Ref<string>
  currentSessionId: Ref<string | null>
  isFreshMeasurement: Ref<boolean>
  lastMeasurementAt: Ref<number | null>
  measurementRequestId: Ref<string | null>
  lifecycleState: Ref<CalibrationLifecycleState>
  lifecycleMessage: Ref<string>
  hasUnsavedWork: ComputedRef<boolean>

  // PKG-03: Sample averaging progress (EC sensors, sampleCount > 1)
  sampleProgress: Ref<number>
  sampleTotal: Ref<number>

  // AUT-299: Calibration temperature for ATC
  calibrationTemperature: Ref<number>
  calibrationTemperatureSource: Ref<string>

  // P1a: EC live preview (AUT-490 / AUT-488)
  previewEcUsCm: Ref<number | null>
  previewAvailable: Ref<boolean>
  lastStable: Ref<boolean | null>
  lastAdcStddev: Ref<number | null>
  lastTemperatureUsed: Ref<number | null>

  // Presets
  sensorTypePresets: Record<string, SensorTypePreset>
  EC_PRESETS: typeof EC_PRESETS
  currentPreset: ComputedRef<SensorTypePreset | undefined>

  // Helpers
  getSuggestedReference: (stepNumber: 1 | 2) => number | undefined
  getReferenceLabel: (stepNumber: 1 | 2) => string | undefined

  // Actions
  selectSensor: (espId: string, gpio: number, sensorType: string) => void
  onPoint1Captured: (point: CalibrationPoint) => Promise<void>
  onPoint2Captured: (point: CalibrationPoint) => Promise<void>
  submitCalibration: () => Promise<void>
  triggerLiveMeasurement: () => Promise<void>
  setCalibrationTemperature: (value: number, source?: string) => void
  setLastRawValue: (rawValue: number | null, quality?: string) => void
  overwritePoint: (role: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'reference_low' | 'reference_high', point: CalibrationPoint) => Promise<void>
  deletePoint: (role: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'reference_low' | 'reference_high') => Promise<void>
  /** AUT-299: Skip current point (e.g. air step for EC) — switches method to ec_1point */
  skipCurrentPoint: () => Promise<void>
  goBack: () => void
  handleAbort: () => Promise<void>
  confirmLeave: () => Promise<boolean>
  reset: () => void
}

// ─── Constants ────────────────────────────────────────────────────────────────

/** EC calibration presets (NIST-certified standards) */
export const EC_PRESETS = {
  '0_1413': { point1: 0, point2: 1413, label: '0 / 1413 µS/cm' },
  '1413_12880': { point1: 1413, point2: 12880, label: '1413 / 12.880 µS/cm' },
} as const


/** Reference values and labels per sensor type */
export const SENSOR_TYPE_PRESETS: Record<string, SensorTypePreset> = {
  ph: {
    label: 'pH-Sensor',
    point1Label: 'pH-Pufferloesung (z.B. pH 7,0)',
    point1Ref: 7.0,
    point2Label: 'pH-Pufferloesung (z.B. pH 4,0)',
    point2Ref: 4.0,
    expectedPoints: 2,
    calibrationMethod: 'ph_2point',
  },
  ec: {
    label: 'EC-Sensor',
    point1Label: 'Referenzloesung (z.B. 1413 µS/cm)',
    point1Ref: 1413,
    expectedPoints: 1,
    calibrationMethod: 'ec_1point',
    sampleCount: 1,
  },
  /** AUT-299: EC 2-point with optional air reference step (legacy, kept for backward compat) */
  ec_2point: {
    label: 'EC-Sensor (2-Punkt)',
    point1Label: 'Schritt 1 (optional): Luft-Referenz',
    point1Ref: 0,
    point2Label: 'Schritt 2: Referenzloesung',
    point2Ref: 1413,
    expectedPoints: 2,
    calibrationMethod: 'ec_2point',
    sampleCount: 1,
    point1Skippable: true,
  },
  /**
   * AUT-487: EC 2-point linear (ec_linear_2point) with reference_low + reference_high roles.
   * EC is linear (NOT inverted like pH): ADC_low→1413 µS/cm, ADC_high→12880 µS/cm.
   * reference_low = 1413 µS/cm (NIST KCl standard), reference_high = 12880 µS/cm.
   */
  ec_linear_2point: {
    label: 'EC-Sensor (2-Punkt Linear)',
    point1Label: '1413 µS/cm Standardloesung (Niedrig)',
    point1Ref: 1413,
    point2Label: '12.880 µS/cm Standardloesung (Hoch)',
    point2Ref: 12880,
    expectedPoints: 2,
    calibrationMethod: 'ec_linear_2point',
    sampleCount: 1,
    point1Skippable: false,
  },
  moisture: {
    label: 'Feuchtigkeitssensor',
    point1Label: 'Trockener Zustand (0%)',
    point1Ref: 0,
    point2Label: 'Vollstaendig nass (100%)',
    point2Ref: 100,
    expectedPoints: 2,
    calibrationMethod: 'moisture_2point',
  },
  soil_moisture: {
    label: 'Feuchtigkeitssensor',
    point1Label: 'Trockener Zustand (0%)',
    point1Ref: 0,
    point2Label: 'Vollstaendig nass (100%)',
    point2Ref: 100,
    expectedPoints: 2,
    calibrationMethod: 'moisture_2point',
  },
  temperature: {
    label: 'Temperatursensor',
    point1Label: 'Eiswasser (0°C)',
    point1Ref: 0,
    point2Label: 'Kochendes Wasser (100°C)',
    point2Ref: 100,
    expectedPoints: 2,
    calibrationMethod: 'linear_2point',
  },
}

export type CalibrationLifecycleState =
  | 'idle'
  | 'accepted'
  | 'pending'
  | 'terminal_success'
  | 'terminal_failed'
  | 'terminal_timeout'
  | 'terminal_integration_issue'

interface CalibrationDraft {
  phase: WizardPhase
  selectedEspId: string
  selectedGpio: number | null
  selectedSensorType: string
  ecPreset: EcPresetId
  points: CalibrationPoint[]
  currentSessionId: string | null
}

const DRAFT_STORAGE_KEY = 'calibration.wizard.draft.v2'
const TERMINAL_SESSION_STATUSES = new Set(['applied', 'rejected', 'failed', 'expired'])
const MEASUREMENT_EVENT_FALLBACK_WINDOW_MS = 10_000

/** Mindestabstand nach Mess-HTTP wie SensorValueCard (ESP + MQTT). */
const MEASUREMENT_TRIGGER_COOLDOWN_MS = 2000

// ─── Composable ───────────────────────────────────────────────────────────────

export function useCalibrationWizard(
  options: UseCalibrationWizardOptions = {},
): UseCalibrationWizardReturn {
  const uiStore = useUiStore()

  // ── Phase machine ───────────────────────────────────────────────────────
  const phase = ref<WizardPhase>(options.skipSelect ? 'point1' : 'select')

  const isActive = computed(() => phase.value !== 'select')

  // ── Selection state ─────────────────────────────────────────────────────
  const selectedEspId = ref(options.espId ?? '')
  const selectedGpio = ref<number | null>(options.gpio ?? null)
  const selectedSensorType = ref(options.sensorType ?? '')
  // B6 / P0a: Default = 'custom' (1-Punkt) — bewährter Standard für Einzelkalibrierung
  const ecPreset = ref<EcPresetId>('custom')

  // ── Data ────────────────────────────────────────────────────────────────
  const points = ref<CalibrationPoint[]>([])
  const calibrationResult = ref<CalibrateResponse | null>(null)
  const errorMessage = ref('')
  const isSubmitting = ref(false)

  // ── F-P2: Live Trigger state ───────────────────────────────────────────
  const isMeasuring = ref(false)
  const lastRawValue = ref<number | null>(null)
  const measurementQuality = ref('unknown')
  const currentSessionId = ref<string | null>(null)
  const isFreshMeasurement = ref(false)
  const lastMeasurementAt = ref<number | null>(null)
  const measurementRequestId = ref<string | null>(null)
  const measurementTriggerAt = ref<number | null>(null)
  const measureCooldownTimerId = ref<ReturnType<typeof setTimeout> | null>(null)
  const lifecycleState = ref<CalibrationLifecycleState>('idle')
  const lifecycleMessage = ref('')

  // PKG-03: Sample averaging counters (shown in UI during multi-sample EC measurement)
  const sampleProgress = ref(0)
  const sampleTotal = ref(0)

  // AUT-299: Calibration temperature for temperature compensation
  const calibrationTemperature = ref<number>(25.0)
  const calibrationTemperatureSource = ref<string>('manual')

  // ── P1a: EC live preview (AUT-490 / AUT-488) ────────────────────────────────
  // AUT-488: These fields may not yet exist in the WS payload —
  // optional-chaining + null-safe defaults prevent crashes on missing fields.
  const previewEcUsCm = ref<number | null>(null)
  const previewAvailable = ref<boolean>(false)
  const lastStable = ref<boolean | null>(null)
  const lastAdcStddev = ref<number | null>(null)
  const lastTemperatureUsed = ref<number | null>(null)

  function clearMeasureCooldownTimer(): void {
    if (measureCooldownTimerId.value !== null) {
      clearTimeout(measureCooldownTimerId.value)
      measureCooldownTimerId.value = null
    }
  }

  const ws = useWebSocket({
    filters: {
      types: ['calibration_measurement_received', 'calibration_measurement_failed'],
    },
  })

  /** IDs aus WS-Payload + Top-Level correlation_id (Server broadcast) fuer Messung↔Request-Zuordnung. */
  function measurementCorrelationCandidates(
    message: WebSocketMessage,
    data: Record<string, unknown>,
  ): string[] {
    const out: string[] = []
    const push = (v: unknown): void => {
      if (typeof v === 'string' && v.length > 0) out.push(v)
    }
    push(message.correlation_id)
    push(data.intent_id)
    push(data.correlation_id)
    push(data.request_id)
    return out
  }

  function matchesActiveMeasurementRequest(
    message: WebSocketMessage,
    data: Record<string, unknown>,
  ): boolean {
    const expected = measurementRequestId.value
    if (!expected) return false
    return measurementCorrelationCandidates(message, data).some((id) => id === expected)
  }

  /**
   * Fallback when server event has no correlation/request IDs:
   * accept only while we have an active measurement window on the same sensor/session.
   */
  function canFallbackMatchMeasurementByContext(data: Record<string, unknown>): boolean {
    if (!isMeasuring.value) return false
    if (measurementTriggerAt.value == null) return false
    if (Date.now() - measurementTriggerAt.value > MEASUREMENT_EVENT_FALLBACK_WINDOW_MS) return false
    if (
      currentSessionId.value &&
      data.session_id &&
      data.session_id !== currentSessionId.value
    ) {
      return false
    }
    return true
  }

  const unsubscribeMeasurement = ws.on('calibration_measurement_received', (message: WebSocketMessage) => {
    const data = message.data ?? {}
    if (
      data.esp_id !== selectedEspId.value ||
      data.gpio !== selectedGpio.value
    ) {
      return
    }
    if (
      currentSessionId.value &&
      data.session_id &&
      data.session_id !== currentSessionId.value
    ) {
      return
    }

    if (!measurementRequestId.value) {
      return
    }

    const ids = measurementCorrelationCandidates(message, data)
    if (ids.length === 0) {
      if (!canFallbackMatchMeasurementByContext(data)) {
        isFreshMeasurement.value = false
        lifecycleState.value = 'terminal_integration_issue'
        lifecycleMessage.value = 'Messung ohne zuordenbare Request-ID (intent/correlation) erhalten und verworfen.'
        return
      }
      lifecycleMessage.value = 'Messung ohne Korrelation-ID empfangen (Fallback-Zuordnung aktiv).'
    }

    if (ids.length > 0 && !matchesActiveMeasurementRequest(message, data)) {
      return
    }

    const eventReceivedAt = Date.now()
    const rawValue = Number(data.raw_value ?? data.raw)
    if (Number.isFinite(rawValue)) {
      setLastRawValue(rawValue, String(data.quality ?? 'good'))
      lastMeasurementAt.value = eventReceivedAt
      isFreshMeasurement.value = true
      measurementTriggerAt.value = null
      lifecycleState.value = 'pending'
      lifecycleMessage.value = 'Frische Messung empfangen.'

      // P1a: Extract EC preview fields (AUT-490 / AUT-488 optional-chaining).
      // preview_ec_us_cm may be absent when backend does not yet compute it.
      const ecPreview = typeof data.preview_ec_us_cm === 'number' ? data.preview_ec_us_cm : null
      previewEcUsCm.value = ecPreview
      // preview_available defaults to true when we have a valid raw value and no explicit false flag.
      previewAvailable.value = typeof data.preview_available === 'boolean'
        ? data.preview_available
        : Number.isFinite(ecPreview) && ecPreview !== null
      lastStable.value = typeof data.stable === 'boolean' ? data.stable : null
      lastAdcStddev.value = typeof data.adc_stddev === 'number' ? data.adc_stddev : null
      lastTemperatureUsed.value = typeof data.temperature_used === 'number' ? data.temperature_used : null
    }
  })

  const unsubscribeMeasurementFailed = ws.on('calibration_measurement_failed', (message: WebSocketMessage) => {
    const data = message.data ?? {}
    if (
      data.esp_id !== selectedEspId.value ||
      data.gpio !== selectedGpio.value
    ) {
      return
    }

    if (!measurementRequestId.value) {
      return
    }

    const ids = measurementCorrelationCandidates(message, data)
    if (ids.length === 0) {
      if (!canFallbackMatchMeasurementByContext(data)) {
        lifecycleState.value = 'terminal_integration_issue'
        lifecycleMessage.value = 'Messfehler ohne zuordenbare Request-ID erhalten.'
        return
      }
      lifecycleMessage.value = 'Messfehler ohne Korrelation-ID empfangen (Fallback-Zuordnung aktiv).'
    }

    if (ids.length > 0 && !matchesActiveMeasurementRequest(message, data)) {
      return
    }

    measurementQuality.value = 'error'
    isFreshMeasurement.value = false
    measurementTriggerAt.value = null
    lifecycleState.value = 'terminal_failed'
    errorMessage.value = String(data.error ?? 'Messung fehlgeschlagen')
  })

  const cleanupWebSocketBindings = () => {
    clearMeasureCooldownTimer()
    unsubscribeMeasurement()
    unsubscribeMeasurementFailed()
    ws.cleanup()
  }

  if (getCurrentInstance()) {
    onUnmounted(() => {
      cleanupWebSocketBindings()
    })
  }

  // ── Computed ────────────────────────────────────────────────────────────
  const currentPreset = computed((): SensorTypePreset | undefined => {
    if (selectedSensorType.value === 'ec') {
      if (ecPreset.value === '1413_12880') {
        // AUT-487: ec_linear_2point — reference_low=1413, reference_high=12880
        return {
          ...SENSOR_TYPE_PRESETS.ec_linear_2point,
          point1Label: '1413 µS/cm Standardloesung (Referenz-Low)',
          point1Ref: 1413,
          point2Label: '12.880 µS/cm Standardloesung (Referenz-High)',
          point2Ref: 12880,
          calibrationMethod: 'ec_linear_2point',
        }
      }
      if (ecPreset.value === '0_1413') {
        // AUT-487: ec_linear_2point with 0+1413 — reference_low=0, reference_high=1413
        return {
          ...SENSOR_TYPE_PRESETS.ec_linear_2point,
          point1Label: 'Luft / trocken (0 µS/cm, Referenz-Low)',
          point1Ref: 0,
          point2Label: '1413 µS/cm Standardloesung (Referenz-High)',
          point2Ref: 1413,
          calibrationMethod: 'ec_linear_2point',
          point1Skippable: false,
        }
      }
      // custom = 1-Punkt (ec_1point) — DEFAULT (B6 / P0a)
      return SENSOR_TYPE_PRESETS.ec
    }
    return SENSOR_TYPE_PRESETS[selectedSensorType.value]
  })
  const hasUnsavedWork = computed(() =>
    Boolean(currentSessionId.value) ||
    points.value.length > 0 ||
    ['point1', 'point2', 'confirm'].includes(phase.value),
  )

  /** EC reference values from preset, or undefined for custom */
  const ecPointRefs = computed(() => {
    if (selectedSensorType.value !== 'ec') return null
    if (ecPreset.value === 'custom') return { point1: undefined, point2: undefined }
    const preset = EC_PRESETS[ecPreset.value]
    return preset ? { point1: preset.point1, point2: preset.point2 } : null
  })

  // ── Helpers ─────────────────────────────────────────────────────────────

  function getSuggestedReference(stepNumber: 1 | 2): number | undefined {
    const preset = currentPreset.value
    const expectedPoints = preset?.expectedPoints ?? 2

    // For 1-point sensors (EC), only return point1
    if (expectedPoints === 1) {
      return stepNumber === 1 ? preset?.point1Ref : undefined
    }

    // For EC with custom preset, use ecPointRefs
    if (selectedSensorType.value === 'ec' && ecPointRefs.value) {
      return stepNumber === 1 ? ecPointRefs.value.point1 : ecPointRefs.value.point2
    }

    // For others (pH, moisture)
    return stepNumber === 1 ? preset?.point1Ref : preset?.point2Ref
  }

  function getReferenceLabel(stepNumber: 1 | 2): string | undefined {
    const preset = currentPreset.value
    const expectedPoints = preset?.expectedPoints ?? 2

    // For 1-point sensors (EC), only return point1 label
    if (expectedPoints === 1) {
      return stepNumber === 1 ? preset?.point1Label : undefined
    }

    // For EC with preset
    if (selectedSensorType.value === 'ec' && ecPreset.value !== 'custom') {
      const ecPresetData = EC_PRESETS[ecPreset.value as keyof typeof EC_PRESETS]
      if (ecPresetData) {
        return stepNumber === 1
          ? `${ecPresetData.point1} µS/cm KCl-Standard`
          : `${ecPresetData.point2} µS/cm KCl-Standard`
      }
    }

    // For others (pH, moisture)
    return stepNumber === 1 ? preset?.point1Label : preset?.point2Label
  }

  // ── Actions ─────────────────────────────────────────────────────────────

  function selectSensor(espId: string, gpio: number, sensorType: string) {
    const normalizedSensorType = normalizeCalibrationSensorType(sensorType)
    if (!SENSOR_TYPE_PRESETS[normalizedSensorType]) {
      phase.value = 'error'
      errorMessage.value = `Sensor-Typ '${sensorType}' wird im Kalibrierwizard nicht unterstuetzt.`
      return
    }

    if (!Number.isInteger(gpio) || gpio < 0 || gpio > 48) {
      phase.value = 'error'
      errorMessage.value = `GPIO '${gpio}' ist ungueltig.`
      return
    }

    selectedEspId.value = espId
    selectedGpio.value = gpio
    selectedSensorType.value = normalizedSensorType
    points.value = []
    calibrationResult.value = null
    errorMessage.value = ''
    phase.value = 'point1'
    lifecycleState.value = 'idle'
    lifecycleMessage.value = ''
    isFreshMeasurement.value = false
    measurementRequestId.value = null
    measurementTriggerAt.value = null
    clearMeasureCooldownTimer()
    isMeasuring.value = false
  }

  async function ensureSessionStarted(): Promise<string> {
    if (currentSessionId.value) return currentSessionId.value
    const preset = currentPreset.value
    if (!preset) {
      throw new Error('Sensortyp-Preset nicht gefunden')
    }
    const session = await calibrationApi.startSession({
      esp_id: selectedEspId.value,
      gpio: selectedGpio.value ?? 0,
      sensor_type: selectedSensorType.value,
      method: preset.calibrationMethod,
      expected_points: preset.expectedPoints,
      calibration_temperature: calibrationTemperature.value,
      calibration_temperature_source: calibrationTemperatureSource.value,
    })
    currentSessionId.value = session.id
    return session.id
  }

  async function persistPoint(
    role: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'reference_low' | 'reference_high',
    point: CalibrationPoint,
    options: { confirmOverwrite?: boolean } = {},
  ): Promise<boolean> {
    if (selectedGpio.value === null || !selectedEspId.value || !selectedSensorType.value) {
      throw new Error('Sensorauswahl unvollstaendig')
    }

    const sessionId = await ensureSessionStarted()
    const hasExistingRole = points.value.some((existing) => existing.point_role === role)
    if (hasExistingRole && options.confirmOverwrite) {
      const roleLabel = role === 'buffer_high' ? 'High-Buffer'
        : role === 'buffer_low' ? 'Low-Buffer'
        : role === 'reference' ? 'Referenzloesung'
        : role === 'reference_low' ? 'Referenz-Low (1413 µS/cm)'
        : role === 'reference_high' ? 'Referenz-High (12880 µS/cm)'
        : role === 'dry' ? 'Trockenzustand'
        : 'Nasszustand'
      const overwriteConfirmed = await uiStore.confirm({
        title: 'Kalibrierpunkt ueberschreiben?',
        message: `Der Punkt '${roleLabel}' existiert bereits. Soll er durch den neuen Messwert ersetzt werden?`,
        variant: 'warning',
        confirmText: 'Ueberschreiben',
      })
      if (!overwriteConfirmed) {
        return false
      }
    }
    const sessionState = await calibrationApi.addPoint(sessionId, {
      raw_value: point.raw,
      reference_value: point.reference,
      point_role: role as any,
      overwrite: hasExistingRole,
      quality: measurementQuality.value || 'good',
    })
    const persistedPoints = Array.isArray(sessionState.calibration_points?.points)
      ? sessionState.calibration_points.points
      : []
    const persisted = persistedPoints.find((candidate) => candidate.point_role === role)

    const normalizedPoint: CalibrationPoint = {
      ...point,
      point_role: role,
      point_id: typeof persisted?.id === 'string' ? persisted.id : undefined,
    }
    isFreshMeasurement.value = false

    if (hasExistingRole) {
      points.value = points.value.map((existing) =>
        existing.point_role === role ? normalizedPoint : existing,
      )
      return true
    }

    // Append new point in proper order
    points.value = [...points.value, normalizedPoint]
    return true
  }

  async function onPoint1Captured(point: CalibrationPoint): Promise<void> {
    const preset = currentPreset.value

    let pointRole: 'buffer_high' | 'dry' | 'reference' | 'reference_low'
    if (selectedSensorType.value === 'ph') {
      pointRole = 'buffer_high'
    } else if (selectedSensorType.value === 'ec') {
      if (preset?.calibrationMethod === 'ec_linear_2point') {
        // AUT-487: EC 2-point linear — point1 = reference_low (the lower concentration)
        pointRole = 'reference_low'
      } else {
        // EC 1-point (custom/default)
        pointRole = 'reference'
      }
    } else {
      pointRole = 'dry'
    }

    const persisted = await persistPoint(pointRole, point, { confirmOverwrite: true })
    if (persisted) {
      // EC 1-point: go directly to confirm
      // pH & Moisture 2-point, EC 2-point: go to point2
      if (preset?.expectedPoints === 1) {
        await submitCalibration()
      } else {
        phase.value = 'point2'
      }
    }
  }

  async function onPoint2Captured(point: CalibrationPoint): Promise<void> {
    const preset = currentPreset.value

    let pointRole: 'buffer_low' | 'wet' | 'reference_high'
    if (selectedSensorType.value === 'ph') {
      pointRole = 'buffer_low'
    } else if (selectedSensorType.value === 'ec' && preset?.calibrationMethod === 'ec_linear_2point') {
      // AUT-487: EC 2-point linear — point2 = reference_high (the higher concentration)
      pointRole = 'reference_high'
    } else {
      pointRole = 'wet'
    }

    const persisted = await persistPoint(pointRole, point, { confirmOverwrite: true })
    if (persisted) {
      phase.value = 'confirm'
    }
  }

  async function submitCalibration(): Promise<void> {
    if (selectedGpio.value === null) return

    const preset = currentPreset.value
    if (!preset) {
      phase.value = 'error'
      errorMessage.value = 'Sensortyp-Preset nicht gefunden.'
      return
    }

    const validPoints = points.value.filter((point) =>
      Number.isFinite(point.raw) && Number.isFinite(point.reference),
    )
    if (validPoints.length < preset.expectedPoints) {
      phase.value = 'error'
      errorMessage.value = `Kalibrierung benötigt ${preset.expectedPoints} gueltige Punkte, vorhanden: ${validPoints.length}.`
      return
    }

    isSubmitting.value = true
    lifecycleState.value = 'accepted'
    lifecycleMessage.value = 'Kalibrierauftrag akzeptiert.'
    errorMessage.value = ''
    phase.value = 'finalizing'
    try {
      const sessionId = await ensureSessionStarted()

      // Get required roles based on sensor type and calibration method
      let requiredRoles: Array<string> = []
      if (selectedSensorType.value === 'ph') {
        requiredRoles = ['buffer_high', 'buffer_low']
      } else if (selectedSensorType.value === 'ec') {
        if (preset.calibrationMethod === 'ec_linear_2point') {
          // AUT-487: EC 2-point linear uses reference_low + reference_high
          requiredRoles = ['reference_low', 'reference_high']
        } else {
          requiredRoles = ['reference']
        }
      } else {
        requiredRoles = ['dry', 'wet']
      }

      const hasAllRoles = requiredRoles.every((role) =>
        points.value.some((point) => point.point_role === role),
      )
      if (!hasAllRoles) {
        for (let index = 0; index < requiredRoles.length; index += 1) {
          const role = requiredRoles[index]
          const point = validPoints[index]
          if (!points.value.some((entry) => entry.point_role === role)) {
            await persistPoint(role as any, point)
          }
        }
      }

      lifecycleState.value = 'pending'
      lifecycleMessage.value = 'Kalibrierung wird finalisiert...'
      await calibrationApi.finalizeSession(sessionId)
      lifecycleMessage.value = 'Kalibrierung wird angewendet...'
      await calibrationApi.applySession(sessionId)
      const sessionState = await waitForTerminalSession(sessionId)
      const normalizedStatus = String(sessionState.status || '').toLowerCase()

      if (!TERMINAL_SESSION_STATUSES.has(normalizedStatus)) {
        lifecycleState.value = 'terminal_timeout'
        lifecycleMessage.value = `Keine terminale Session-Rueckmeldung erhalten (Status: ${normalizedStatus || 'unbekannt'}).`
        phase.value = 'error'
        errorMessage.value = lifecycleMessage.value
        return
      }

      calibrationResult.value = {
        success: normalizedStatus === 'applied',
        calibration: sessionState.calibration_result ?? {},
        sensor_type: sessionState.sensor_type,
        method: sessionState.method,
        saved: normalizedStatus === 'applied',
        message: sessionState.failure_reason ?? null,
      }
      if (normalizedStatus === 'applied') {
        lifecycleState.value = 'terminal_success'
        lifecycleMessage.value = 'Kalibrierung erfolgreich terminal bestaetigt.'
      } else {
        lifecycleState.value = normalizedStatus === 'expired' ? 'terminal_timeout' : 'terminal_failed'
        lifecycleMessage.value = calibrationResult.value.message ?? `Kalibrierung endete mit Status '${normalizedStatus}'.`
      }
      phase.value = calibrationResult.value.success ? 'done' : 'error'
      if (!calibrationResult.value.success) {
        errorMessage.value = lifecycleMessage.value
      }
    } catch (err: unknown) {
      phase.value = 'error'
      lifecycleState.value = 'terminal_failed'
      const uiError = toUiApiError(err, 'Kalibrierung fehlgeschlagen')
      lifecycleMessage.value = formatUiApiError(uiError)
      errorMessage.value = lifecycleMessage.value
    } finally {
      isSubmitting.value = false
    }
  }

  async function waitForTerminalSession(sessionId: string): Promise<Awaited<ReturnType<typeof calibrationApi.getSession>>> {
    const maxAttempts = 15
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      const session = await calibrationApi.getSession(sessionId)
      const normalizedStatus = String(session.status || '').toLowerCase()
      if (TERMINAL_SESSION_STATUSES.has(normalizedStatus)) {
        return session
      }
      await new Promise((resolve) => setTimeout(resolve, 500))
    }
    return calibrationApi.getSession(sessionId)
  }

  /**
   * F-P2 + PKG-03: Trigger a live measurement via MQTT command.
   *
   * Sends POST /sensors/{esp_id}/{gpio}/measure to the server,
   * which publishes a sensor command via MQTT. The ESP32 responds
   * on sensor/{gpio}/response, and the CalibrationResponseHandler (S-P5)
   * processes it and broadcasts via WebSocket (S-P6).
   *
   * PKG-03 (EC sensors, sampleCount > 1): triggers N measurements sequentially,
   * collects raw_values, and stores the median (robust against outliers) as
   * lastRawValue. Progress is visible via sampleProgress / sampleTotal refs and
   * lifecycleMessage. All other sensor types use a single measurement (unchanged).
   *
   * The raw value is stored in lastRawValue for the wizard to display.
   * The actual point capture still requires user confirmation with a reference value.
   */
  async function triggerLiveMeasurement(): Promise<void> {
    if (selectedGpio.value === null || !selectedEspId.value) return
    if (isMeasuring.value) return

    const preset = currentPreset.value
    const targetSampleCount = preset?.sampleCount != null && preset.sampleCount > 1
      ? preset.sampleCount
      : 1

    clearMeasureCooldownTimer()
    isMeasuring.value = true
    isFreshMeasurement.value = false
    lifecycleState.value = 'accepted'
    lifecycleMessage.value = 'Messauftrag akzeptiert.'
    errorMessage.value = ''
    sampleProgress.value = 0
    sampleTotal.value = targetSampleCount

    try {
      // A4 / P0b: Session-Start beim ersten Capture-Trigger.
      // calibration_temperature wird via ensureSessionStarted() mitgesendet (nicht separat PATCH).
      // ensureSessionStarted() ist idempotent: gibt bestehende Session-ID zurück wenn vorhanden.
      await ensureSessionStarted()

      if (targetSampleCount <= 1) {
        measurementTriggerAt.value = Date.now()
        const measureOptions: Parameters<typeof sensorsApi.triggerMeasurement>[2] = {
          sensor_type: selectedSensorType.value,
        }
        const normalizedType = selectedSensorType.value.toLowerCase()
        if (normalizedType === 'ec' || normalizedType === 'ph' || normalizedType === 'ec_2point') {
          measureOptions.sample_count = 30
          measureOptions.sample_delay_ms = 100
          measureOptions.timeout_ms = 15000
        }
        const triggerResult = await sensorsApi.triggerMeasurement(
          selectedEspId.value,
          selectedGpio.value,
          measureOptions,
        )
        measurementRequestId.value = triggerResult.request_id
        lifecycleState.value = 'pending'
        lifecycleMessage.value = `Messung angefordert (30 ADC-Samples, Request-ID: ${triggerResult.request_id}).`
      } else {
        // PKG-03: Multi-sample robust path (EC: sampleCount=3)
        const collectedRaw: number[] = []
        const SAMPLE_TIMEOUT_MS = 8_000

        for (let sampleIndex = 0; sampleIndex < targetSampleCount; sampleIndex += 1) {
          sampleProgress.value = sampleIndex + 1
          lifecycleState.value = 'pending'
          lifecycleMessage.value = `Messung ${sampleIndex + 1}/${targetSampleCount} laeuft...`

          const prevMeasurementAt = lastMeasurementAt.value
          measurementTriggerAt.value = Date.now()
          const triggerResult = await sensorsApi.triggerMeasurement(selectedEspId.value, selectedGpio.value)
          measurementRequestId.value = triggerResult.request_id

          // Wait for the WS handler (calibration_measurement_received) to signal a new measurement.
          // Use lastMeasurementAt timestamp instead of raw value so that consecutive identical
          // ADC readings (stable EC solution) are not mistaken for "no new measurement".
          const sampleReceived = await new Promise<number | null>((resolve) => {
            const start = Date.now()
            const poll = setInterval(() => {
              if (lastMeasurementAt.value !== prevMeasurementAt && lastMeasurementAt.value !== null) {
                clearInterval(poll)
                resolve(lastRawValue.value)
              } else if (Date.now() - start > SAMPLE_TIMEOUT_MS) {
                clearInterval(poll)
                resolve(null)
              }
            }, 50)
          })

          if (sampleReceived === null) {
            throw new Error(`Keine Antwort fuer Messung ${sampleIndex + 1}/${targetSampleCount} (Timeout nach ${SAMPLE_TIMEOUT_MS / 1000}s)`)
          }

          collectedRaw.push(sampleReceived)

          // Brief pause between samples so ESP32 and MQTT settle
          if (sampleIndex < targetSampleCount - 1) {
            await new Promise<void>((resolve) => setTimeout(resolve, MEASUREMENT_TRIGGER_COOLDOWN_MS))
          }
        }

        // Use median as robust estimator so one noisy sample does not dominate.
        const sortedRaw = [...collectedRaw].sort((a, b) => a - b)
        const middleIndex = Math.floor(sortedRaw.length / 2)
        const medianRaw = sortedRaw.length % 2 === 0
          ? Math.round((sortedRaw[middleIndex - 1] + sortedRaw[middleIndex]) / 2)
          : sortedRaw[middleIndex]
        const meanRaw = Math.round(
          collectedRaw.reduce((sum, v) => sum + v, 0) / collectedRaw.length,
        )
        setLastRawValue(medianRaw, measurementQuality.value || 'good')
        isFreshMeasurement.value = true
        lifecycleState.value = 'pending'
        lifecycleMessage.value = `Median aus ${targetSampleCount} Messungen: ${medianRaw} (Mittelwert: ${meanRaw}, Werte: ${collectedRaw.join(', ')})`
        sampleProgress.value = targetSampleCount
      }
    } catch (err: unknown) {
      errorMessage.value = err instanceof Error ? err.message : 'Messung fehlgeschlagen'
      measurementQuality.value = 'error'
      lifecycleState.value = 'terminal_failed'
      lifecycleMessage.value = errorMessage.value
    } finally {
      sampleProgress.value = 0
      sampleTotal.value = 0
      clearMeasureCooldownTimer()
      measureCooldownTimerId.value = setTimeout(() => {
        isMeasuring.value = false
        measureCooldownTimerId.value = null
      }, MEASUREMENT_TRIGGER_COOLDOWN_MS)
    }
  }

  function setLastRawValue(rawValue: number | null, quality = 'good'): void {
    lastRawValue.value = rawValue
    measurementQuality.value = quality
  }

  function setCalibrationTemperature(value: number, source = 'manual'): void {
    calibrationTemperature.value = value
    calibrationTemperatureSource.value = source
  }

  async function overwritePoint(role: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'reference_low' | 'reference_high', point: CalibrationPoint): Promise<void> {
    if (!currentSessionId.value) {
      throw new Error('Keine aktive Kalibrier-Session vorhanden')
    }
    await persistPoint(role, point, { confirmOverwrite: true })
  }

  async function deletePoint(role: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'reference_low' | 'reference_high'): Promise<void> {
    if (!currentSessionId.value) {
      throw new Error('Keine aktive Kalibrier-Session vorhanden')
    }
    const roleLabel = role === 'buffer_high' ? 'High-Buffer'
      : role === 'buffer_low' ? 'Low-Buffer'
      : role === 'reference' ? 'Referenzloesung'
      : role === 'reference_low' ? 'Referenz-Low (1413 µS/cm)'
      : role === 'reference_high' ? 'Referenz-High (12880 µS/cm)'
      : role === 'dry' ? 'Trockenzustand'
      : 'Nasszustand'
    const confirmed = await uiStore.confirm({
      title: 'Kalibrierpunkt loeschen?',
      message: `Soll der Punkt '${roleLabel}' wirklich aus der Session entfernt werden?`,
      variant: 'warning',
      confirmText: 'Loeschen',
    })
    if (!confirmed) return

    const target = points.value.find((point) => point.point_role === role && point.point_id)
    if (!target?.point_id) {
      throw new Error(`Kalibrierpunkt '${role}' hat keine Point-ID`)
    }
    await calibrationApi.deletePoint(currentSessionId.value, target.point_id)
    points.value = points.value.filter((point) => point.point_role !== role)

    // Determine which phase to go back to
    if (role === 'reference' || role === 'reference_low' || role === 'buffer_high' || role === 'dry') {
      phase.value = 'point1'
    } else {
      // wet, reference_high, buffer_low
      phase.value = 'point2'
    }
  }

  /**
   * AUT-299: Skip the current point (air step for EC 2-point).
   * Switches session method to ec_1point so the server does not expect the air reference.
   * Transitions directly to point2 (reference solution step).
   */
  async function skipCurrentPoint(): Promise<void> {
    if (phase.value !== 'point1') return
    const preset = currentPreset.value
    if (!preset?.point1Skippable) return

    // If a session is already open, we cannot easily switch method. Guard: only skip if no session yet.
    if (currentSessionId.value) {
      // Session already started — abort and restart with ec_1point
      try {
        await calibrationApi.rejectSession(currentSessionId.value, 'User skipped air reference — switching to 1-point method')
      } catch {
        // Best-effort
      }
      currentSessionId.value = null
      points.value = []
    }

    // Override to ec_1point by temporarily setting selectedSensorType to 'ec'
    // (ec preset = 1-point, no air reference)
    selectedSensorType.value = 'ec'
    phase.value = 'point2'
  }

  /** Navigate back one phase */
  function goBack() {
    if (isSubmitting.value) return

    const confirmTarget: WizardPhase =
      (currentPreset.value?.expectedPoints ?? 2) === 1 ? 'point1' : 'point2'

    const backMap: Partial<Record<WizardPhase, WizardPhase>> = {
      point1: 'select',
      point2: 'point1',
      confirm: confirmTarget,
      finalizing: 'confirm',
      error: 'confirm',
    }
    const target = backMap[phase.value]
    if (target) {
      // If going back past select and skipSelect was used, stay at point1
      if (target === 'select' && options.skipSelect) return
      phase.value = target
    }
  }

  /** Abort with confirmation if data captured */
  async function handleAbort(): Promise<void> {
    if (isSubmitting.value) return

    if (points.value.length > 0) {
      const confirmed = await uiStore.confirm({
        title: 'Kalibrierung abbrechen?',
        message: 'Erfasste Daten gehen verloren. Wirklich abbrechen?',
        variant: 'danger',
      })
      if (!confirmed) return
    }

    if (currentSessionId.value) {
      try {
        await calibrationApi.deleteSession(currentSessionId.value, 'User aborted calibration flow')
      } catch {
        // Best-effort discard, keep local reset deterministic.
      }
    }
    reset()
  }

  async function confirmLeave(): Promise<boolean> {
    if (!hasUnsavedWork.value || isSubmitting.value) {
      return true
    }
    return uiStore.confirm({
      title: 'Kalibrierung verlassen?',
      message: 'Es gibt einen laufenden Kalibriervorgang. Entwurf bleibt gespeichert, wirklich verlassen?',
      variant: 'warning',
      confirmText: 'Verlassen',
    })
  }

  function saveDraft(): void {
    const draft: CalibrationDraft = {
      phase: phase.value,
      selectedEspId: selectedEspId.value,
      selectedGpio: selectedGpio.value,
      selectedSensorType: selectedSensorType.value,
      ecPreset: ecPreset.value,
      points: points.value,
      currentSessionId: currentSessionId.value,
    }
    sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft))
  }

  function clearDraft(): void {
    sessionStorage.removeItem(DRAFT_STORAGE_KEY)
  }

  function restoreDraft(): void {
    const rawDraft = sessionStorage.getItem(DRAFT_STORAGE_KEY)
    if (!rawDraft) {
      return
    }
    try {
      const parsed = JSON.parse(rawDraft) as Partial<CalibrationDraft>
      if (!parsed || !parsed.selectedEspId || parsed.selectedGpio == null || !parsed.selectedSensorType) {
        return
      }
      if (
        options.espId &&
        options.gpio !== undefined &&
        options.sensorType &&
        (
          options.espId !== parsed.selectedEspId ||
          options.gpio !== parsed.selectedGpio ||
          normalizeCalibrationSensorType(options.sensorType) !== normalizeCalibrationSensorType(parsed.selectedSensorType)
        )
      ) {
        return
      }
      selectedEspId.value = parsed.selectedEspId
      selectedGpio.value = parsed.selectedGpio
      selectedSensorType.value = normalizeCalibrationSensorType(parsed.selectedSensorType)
      // B6 / P0a: default to 'custom' (1-Punkt) when restoring draft without explicit preset
      ecPreset.value = parsed.ecPreset ?? 'custom'
      points.value = Array.isArray(parsed.points) ? parsed.points : []
      currentSessionId.value = parsed.currentSessionId ?? null
      phase.value = parsed.phase ?? (options.skipSelect ? 'point1' : 'select')
      lifecycleState.value = 'pending'
      lifecycleMessage.value = 'Entwurf wiederhergestellt.'
    } catch {
      // Invalid draft payload, ignore.
    }
  }

  function handleBeforeUnload(event: BeforeUnloadEvent): void {
    if (!hasUnsavedWork.value) {
      return
    }
    saveDraft()
    event.preventDefault()
    event.returnValue = ''
  }

  if (typeof window !== 'undefined') {
    restoreDraft()
    window.addEventListener('beforeunload', handleBeforeUnload)
  }

  watch(
    [phase, points, selectedEspId, selectedGpio, selectedSensorType, currentSessionId],
    () => {
      if (hasUnsavedWork.value) {
        saveDraft()
      } else {
        clearDraft()
      }
    },
    { deep: true },
  )

  /** Reset to initial state */
  function reset() {
    phase.value = options.skipSelect ? 'point1' : 'select'
    if (!options.espId) selectedEspId.value = ''
    if (options.gpio === undefined) selectedGpio.value = null
    if (!options.sensorType) selectedSensorType.value = ''
    // B6 / P0a: reset to default 1-Punkt preset
    ecPreset.value = 'custom'
    points.value = []
    calibrationResult.value = null
    errorMessage.value = ''
    clearMeasureCooldownTimer()
    isMeasuring.value = false
    lastRawValue.value = null
    measurementQuality.value = 'unknown'
    currentSessionId.value = null
    isFreshMeasurement.value = false
    lastMeasurementAt.value = null
    measurementRequestId.value = null
    measurementTriggerAt.value = null
    lifecycleState.value = 'idle'
    lifecycleMessage.value = ''
    sampleProgress.value = 0
    sampleTotal.value = 0
    calibrationTemperature.value = 25.0
    calibrationTemperatureSource.value = 'manual'
    // P1a: Reset EC preview state
    previewEcUsCm.value = null
    previewAvailable.value = false
    lastStable.value = null
    lastAdcStddev.value = null
    lastTemperatureUsed.value = null
    clearDraft()
  }

  if (getCurrentInstance()) {
    onUnmounted(() => {
      if (typeof window !== 'undefined') {
        window.removeEventListener('beforeunload', handleBeforeUnload)
      }
      clearMeasureCooldownTimer()
    })
  }

  return {
    // Phase machine
    phase,
    isActive,

    // Selection state
    selectedEspId,
    selectedGpio,
    selectedSensorType,
    ecPreset,

    // Data
    points,
    calibrationResult,
    errorMessage,
    isSubmitting,

    // F-P2: Live trigger state
    isMeasuring,
    lastRawValue,
    measurementQuality,
    currentSessionId,
    isFreshMeasurement,
    lastMeasurementAt,
    measurementRequestId,
    lifecycleState,
    lifecycleMessage,
    hasUnsavedWork,

    // PKG-03: Sample averaging progress
    sampleProgress,
    sampleTotal,

    // AUT-299: Calibration temperature for ATC
    calibrationTemperature,
    calibrationTemperatureSource,

    // P1a: EC live preview (AUT-490 / AUT-488)
    previewEcUsCm,
    previewAvailable,
    lastStable,
    lastAdcStddev,
    lastTemperatureUsed,

    // Presets
    sensorTypePresets: SENSOR_TYPE_PRESETS,
    EC_PRESETS,
    currentPreset,

    // Helpers
    getSuggestedReference,
    getReferenceLabel,

    // Actions
    selectSensor,
    onPoint1Captured,
    onPoint2Captured,
    submitCalibration,
    triggerLiveMeasurement,
    setCalibrationTemperature,
    setLastRawValue,
    overwritePoint,
    deletePoint,
    skipCurrentPoint,
    goBack,
    handleAbort,
    confirmLeave,
    reset,
  }
}
