<script setup lang="ts">
/**
 * CalibrationStep Component
 *
 * A single calibration point capture step.
 * Shows instructions, a live raw-value display, and a reference input.
 *
 * P1a (AUT-490): EC-specific live µS/cm preview from WS calibration_measurement_received.
 * Fields: previewEcUsCm, previewAvailable, stable, adcStddev, temperatureUsed.
 * AUT-488: These fields may not yet exist on the WS payload — optional-chaining + null-safe
 * defaults are used throughout. No crash if backend does not yet send preview_ec_us_cm.
 */

import { ref, computed, watch, onUnmounted } from 'vue'

/** Δ% threshold: below this → green OK, at/above → yellow warning */
const DELTA_WARN_THRESHOLD_PCT = 5

interface Props {
  stepNumber: number
  totalSteps: number
  espId: string
  gpio: number
  sensorType: string
  /** Suggested reference value (e.g. 4.0 for pH buffer) */
  suggestedReference?: number
  /** Label for the reference solution */
  referenceLabel?: string
  /** Latest live raw value from WebSocket */
  lastRawValue?: number | null
  /** Current measurement quality */
  measurementQuality?: string
  /** Loading state while measurement request is in-flight */
  isMeasuring?: boolean
  isFreshMeasurement?: boolean
  /** Label for the capture action button. */
  captureLabel?: string
  /** Require quality === "good" before allowing capture. */
  requireGoodQuality?: boolean

  // ── P1a: EC live preview fields (AUT-490 / AUT-488) ─────────────────────────
  /**
   * Server-computed EC value in µS/cm from calibration measurement response.
   * AUT-488: may be absent if backend does not yet send preview_ec_us_cm — treated as null.
   */
  previewEcUsCm?: number | null
  /**
   * Whether a preview value is currently available.
   * AUT-488: defaults to false when absent (show "Kalibrierung läuft..." placeholder).
   */
  previewAvailable?: boolean
  /**
   * Whether the ADC reading is considered stable (low variance across samples).
   * AUT-457: HW constraint — not a hard gate, user can still capture.
   */
  stable?: boolean | null
  /**
   * ADC standard deviation from the measurement burst.
   * AUT-488: optional — displayed only when present.
   */
  adcStddev?: number | null
  /**
   * Temperature used for EC compensation during this measurement.
   * AUT-488: optional — displayed only when present.
   */
  temperatureUsed?: number | null
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'captured', payload: { raw: number; reference: number }): void
  (e: 'request-measurement'): void
}>()

const rawValue = ref<number | null>(props.lastRawValue ?? null)
const referenceValue = ref<number>(props.suggestedReference ?? 0)

// ── P1a: EC live preview computeds ──────────────────────────────────────────

/** True when sensorType is EC-related (ec, ec_2point, ec_linear_2point). */
const isEcSensor = computed(() => {
  const t = String(props.sensorType ?? '').toLowerCase()
  return t === 'ec' || t.startsWith('ec_')
})

/**
 * Δ% between preview_ec_us_cm and the reference_value (suggestedReference).
 * Only computed when previewEcUsCm is a valid finite number and reference > 0.
 */
const deltaPct = computed<number | null>(() => {
  if (!isEcSensor.value) return null
  const preview = props.previewEcUsCm ?? null
  const ref = props.suggestedReference ?? 0
  if (!Number.isFinite(preview) || preview === null) return null
  if (ref === 0) return null
  return Math.abs(((preview - ref) / ref) * 100)
})

/** Badge variant: 'ok' | 'warn' | null (not enough data). */
const deltaBadge = computed<'ok' | 'warn' | null>(() => {
  const d = deltaPct.value
  if (d === null) return null
  return d <= DELTA_WARN_THRESHOLD_PCT ? 'ok' : 'warn'
})

/** Stable badge: 'stable' | 'unstable' | null (not set = no badge). */
const stableBadge = computed<'stable' | 'unstable' | null>(() => {
  if (!isEcSensor.value) return null
  if (props.stable === null || props.stable === undefined) return null
  return props.stable ? 'stable' : 'unstable'
})
let measurementTimeout: ReturnType<typeof setTimeout> | null = null

function clearMeasurementTimeout() {
  if (measurementTimeout) {
    clearTimeout(measurementTimeout)
    measurementTimeout = null
  }
}

watch(
  () => props.suggestedReference,
  (val) => {
    if (val !== undefined) referenceValue.value = val
  },
  { immediate: false }
)
const readError = ref<string | null>(null)

const canCapture = computed(() =>
  rawValue.value !== null &&
  referenceValue.value !== undefined &&
  props.isFreshMeasurement === true &&
  (!props.requireGoodQuality || String(props.measurementQuality ?? '').toLowerCase() === 'good'),
)

watch(
  () => props.lastRawValue,
  (val) => {
    if (val !== null && val !== undefined && Number.isFinite(val)) {
      rawValue.value = val
      readError.value = null
    }
  },
)

function requestMeasurement() {
  readError.value = null
  clearMeasurementTimeout()
  // Messwerte koennen nach ACK zeitverzoegert eintreffen (MQTT + Persistenz + WS).
  measurementTimeout = setTimeout(() => {
    if (rawValue.value === null && !props.isMeasuring) {
      readError.value = 'Kein aktueller Messwert verfuegbar'
    }
  }, 3000)
  emit('request-measurement')
}

watch(
  () => props.measurementQuality,
  (quality) => {
    if (quality === 'error') {
      clearMeasurementTimeout()
      readError.value = 'Messung fehlgeschlagen'
    }
  },
)

function capture() {
  if (!props.isFreshMeasurement) {
    readError.value = 'Bitte zuerst eine frische Messung ausloesen'
    return
  }
  if (rawValue.value === null) {
    readError.value = 'Bitte zuerst einen Messwert aufnehmen'
    return
  }
  if (props.requireGoodQuality && String(props.measurementQuality ?? '').toLowerCase() !== 'good') {
    readError.value = 'Messqualitaet ist nicht "good". Bitte Messung wiederholen.'
    return
  }
  emit('captured', { raw: rawValue.value, reference: referenceValue.value })
}

watch(
  () => props.lastRawValue,
  (val) => {
    if (val !== null && val !== undefined && Number.isFinite(val)) {
      clearMeasurementTimeout()
    }
  },
)

onUnmounted(() => {
  clearMeasurementTimeout()
})
</script>

<template>
  <div class="calibration-step">
    <div class="calibration-step__header">
      <span class="calibration-step__badge">{{ stepNumber }} / {{ totalSteps }}</span>
      <h3 class="calibration-step__title">
        Kalibrierpunkt {{ stepNumber }}
      </h3>
    </div>

    <p v-if="referenceLabel" class="calibration-step__instruction">
      Sensor in <strong>{{ referenceLabel }}</strong> eintauchen und stabilisieren lassen.
    </p>

    <!-- Live raw value -->
    <div class="calibration-step__reading">
      <div class="calibration-step__reading-label">Aktueller Rohwert (Sensor)</div>
      <div class="calibration-step__reading-value" :class="{ 'calibration-step__reading-value--empty': rawValue === null }">
        {{ rawValue !== null ? rawValue.toFixed(1) : '—' }}
      </div>
      <button
        class="calibration-step__read-btn"
        :disabled="Boolean(isMeasuring)"
        @click="requestMeasurement"
      >
        {{ isMeasuring ? 'Messe...' : 'Messung starten' }}
      </button>
      <div v-if="readError" class="calibration-step__error-row">
        <span class="calibration-step__error">{{ readError }}</span>
        <button
          class="calibration-step__retry-btn"
          :disabled="Boolean(isMeasuring)"
          @click="requestMeasurement"
        >
          Erneut versuchen
        </button>
      </div>
    </div>

    <!-- P1a: EC live µS/cm preview (AUT-490) — only shown for EC sensors -->
    <div v-if="isEcSensor" class="calibration-step__ec-preview">
      <!-- Placeholder when no preview available yet -->
      <template v-if="!previewAvailable">
        <div class="calibration-step__ec-preview-placeholder">
          {{ isMeasuring ? 'Kalibrierung läuft...' : 'Messung starten um Vorschau zu laden' }}
        </div>
      </template>

      <!-- Live preview when available -->
      <template v-else>
        <div class="calibration-step__ec-preview-main">
          <span class="calibration-step__ec-preview-value">
            {{ previewEcUsCm != null ? previewEcUsCm.toFixed(0) : '—' }}
          </span>
          <span class="calibration-step__ec-preview-unit">µS/cm</span>
        </div>

        <!-- Δ-Badge (B7+B8): frontend-computed vs. reference -->
        <div v-if="deltaBadge !== null" class="calibration-step__ec-badges">
          <span
            class="calibration-step__delta-badge"
            :class="{
              'calibration-step__delta-badge--ok': deltaBadge === 'ok',
              'calibration-step__delta-badge--warn': deltaBadge === 'warn',
            }"
          >
            <template v-if="deltaBadge === 'ok'">OK</template>
            <template v-else>Δ {{ deltaPct != null ? deltaPct.toFixed(1) : '?' }}%</template>
          </span>

          <!-- Stable-Badge (B9): AUT-457 — not a hard gate -->
          <span
            v-if="stableBadge !== null"
            class="calibration-step__stable-badge"
            :class="{
              'calibration-step__stable-badge--stable': stableBadge === 'stable',
              'calibration-step__stable-badge--unstable': stableBadge === 'unstable',
            }"
          >
            {{ stableBadge === 'stable' ? 'Stabil' : 'Schwankend' }}
          </span>
        </div>

        <!-- Expert-View: ADC + σ (dezent, sekundär) -->
        <div class="calibration-step__ec-expert">
          <span v-if="adcStddev != null" class="calibration-step__ec-expert-item">
            σ: ±{{ adcStddev.toFixed(1) }}
          </span>
          <span v-if="temperatureUsed != null" class="calibration-step__ec-expert-item">
            T: {{ temperatureUsed.toFixed(1) }}°C
          </span>
          <span v-if="rawValue != null" class="calibration-step__ec-expert-item">
            ADC: {{ rawValue.toFixed(0) }}
          </span>
        </div>
      </template>
    </div>

    <!-- Reference value input -->
    <div class="calibration-step__reference">
      <label class="calibration-step__label" :for="`ref-${stepNumber}`">
        Referenzwert (bekannt)
      </label>
      <input
        :id="`ref-${stepNumber}`"
        v-model.number="referenceValue"
        type="number"
        step="any"
        class="calibration-step__input"
      />
    </div>

    <button
      class="calibration-step__capture-btn"
      :disabled="!canCapture"
      @click="capture"
    >
      {{ captureLabel || 'Punkt uebernehmen' }}
    </button>
  </div>
</template>

<style scoped>
.calibration-step {
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.calibration-step__header {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.calibration-step__badge {
  background: var(--color-iridescent-1);
  color: var(--color-text-inverse);
  font-size: 0.6875rem;
  font-weight: 600;
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-full);
}

.calibration-step__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.calibration-step__instruction {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  line-height: 1.5;
  margin: 0;
}

.calibration-step__reading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1rem;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
}

.calibration-step__reading-label {
  font-size: 0.6875rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.calibration-step__reading-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-iridescent-1);
}

.calibration-step__reading-value--empty {
  color: var(--color-text-muted);
}

.calibration-step__read-btn {
  padding: 0.375rem 1rem;
  font-size: 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.15s;
}

.calibration-step__read-btn:hover:not(:disabled) {
  border-color: var(--color-iridescent-1);
  background: rgba(167,139,250,0.08);
}

.calibration-step__read-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.calibration-step__error {
  font-size: 0.75rem;
  color: var(--color-error);
}

.calibration-step__error-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
}

.calibration-step__retry-btn {
  padding: 0.375rem 1rem;
  font-size: 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-warning);
  background: transparent;
  color: var(--color-warning);
  cursor: pointer;
  transition: all 0.15s;
}

.calibration-step__retry-btn:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.1);
}

.calibration-step__retry-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.calibration-step__reference {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.calibration-step__label {
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

.calibration-step__input {
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  font-family: 'JetBrains Mono', monospace;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color 0.15s;
}

.calibration-step__input:focus {
  border-color: var(--color-iridescent-1);
}

.calibration-step__capture-btn {
  padding: 0.625rem 1.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  border-radius: var(--radius-md);
  border: none;
  background: var(--color-iridescent-1);
  color: var(--color-text-inverse);
  cursor: pointer;
  transition: all 0.15s;
}

.calibration-step__capture-btn:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

.calibration-step__capture-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
}

/* ── P1a: EC live µS/cm preview (AUT-490) ────────────────────────────────── */
.calibration-step__ec-preview {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 0.875rem 1rem;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
}

.calibration-step__ec-preview-placeholder {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  font-style: italic;
}

.calibration-step__ec-preview-main {
  display: flex;
  align-items: baseline;
  gap: 0.375rem;
}

.calibration-step__ec-preview-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 2.25rem;
  font-weight: 700;
  color: var(--color-real);
  line-height: 1;
}

.calibration-step__ec-preview-unit {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.calibration-step__ec-badges {
  display: flex;
  gap: 0.375rem;
  align-items: center;
  flex-wrap: wrap;
  justify-content: center;
}

.calibration-step__delta-badge {
  padding: 0.1875rem 0.5rem;
  border-radius: var(--radius-full);
  font-size: 0.6875rem;
  font-weight: 600;
}

.calibration-step__delta-badge--ok {
  background: rgba(52, 211, 153, 0.15);
  color: var(--color-success);
  border: 1px solid rgba(52, 211, 153, 0.35);
}

.calibration-step__delta-badge--warn {
  background: rgba(251, 191, 36, 0.12);
  color: var(--color-warning);
  border: 1px solid rgba(251, 191, 36, 0.35);
}

.calibration-step__stable-badge {
  padding: 0.1875rem 0.5rem;
  border-radius: var(--radius-full);
  font-size: 0.6875rem;
  font-weight: 600;
}

.calibration-step__stable-badge--stable {
  background: rgba(52, 211, 153, 0.12);
  color: var(--color-success);
  border: 1px solid rgba(52, 211, 153, 0.3);
}

.calibration-step__stable-badge--unstable {
  background: rgba(251, 191, 36, 0.1);
  color: var(--color-warning);
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.calibration-step__ec-expert {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  justify-content: center;
}

.calibration-step__ec-expert-item {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}
</style>
