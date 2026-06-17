<script setup lang="ts">
/**
 * CalibrationWizard Component
 *
 * Step-by-step sensor calibration for pH/EC 2-point linear calibration.
 * Flow: Select sensor -> Capture point 1 -> Capture point 2 -> Confirm -> Done
 *
 * State management delegated to useCalibrationWizard composable (F-P1).
 */

import { computed, onUnmounted, ref, watch } from 'vue'
import { Activity, AlertCircle, ArrowLeft, Check, FlaskConical, Loader, Radar, RefreshCw, ShieldCheck, X } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { useCalibrationWizard } from '@/composables/useCalibrationWizard'
import { EC_PRESETS } from '@/composables/useCalibrationWizard'
import type { EcPresetId } from '@/composables/useCalibrationWizard'
import CalibrationStep from './CalibrationStep.vue'

const espStore = useEspStore()

interface Props {
  skipSelect?: boolean
  espId?: string
  gpio?: number
  sensorType?: string
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  skipSelect: false,
  espId: undefined,
  gpio: undefined,
  sensorType: undefined,
  compact: false,
})

// All wizard state from composable
const {
  phase,
  selectedEspId,
  selectedGpio,
  selectedSensorType,
  points,
  calibrationResult,
  errorMessage,
  isSubmitting,
  isMeasuring,
  lastRawValue,
  measurementQuality,
  isFreshMeasurement,
  measurementRequestId,
  lifecycleState,
  lifecycleMessage,
  hasUnsavedWork,
  currentSessionId,
  sensorTypePresets,
  currentPreset,
  getSuggestedReference,
  getReferenceLabel,
  selectSensor,
  onPoint1Captured,
  onPoint2Captured,
  submitCalibration,
  triggerLiveMeasurement,
  deletePoint,
  goBack,
  handleAbort,
  confirmLeave,
  reset,
  sampleProgress,
  sampleTotal,
  calibrationTemperature,
  calibrationTemperatureSource,
  setCalibrationTemperature,
  skipCurrentPoint,
  ecPreset,
  previewEcUsCm,
  previewAvailable,
  lastStable,
  lastAdcStddev,
  lastTemperatureUsed,
} = useCalibrationWizard({
  skipSelect: props.skipSelect,
  espId: props.espId,
  gpio: props.gpio,
  sensorType: props.sensorType,
})

// Available ESPs from store
const availableDevices = computed(() =>
  espStore.devices.filter(d => espStore.getDeviceId(d))
)

const normalizedSelectedType = computed(() => String(selectedSensorType.value || '').toLowerCase())
const ecDerived = computed(() => {
  const cal = calibrationResult.value?.calibration as Record<string, unknown> | undefined
  const derived = cal?.derived
  return (derived && typeof derived === 'object') ? (derived as Record<string, unknown>) : null
})
const phDerived = computed(() => {
  const cal = calibrationResult.value?.calibration as Record<string, unknown> | undefined
  const derived = cal?.derived
  return (derived && typeof derived === 'object') ? (derived as Record<string, unknown>) : null
})
const selectedDevice = computed(() =>
  availableDevices.value.find((device) => espStore.getDeviceId(device) === selectedEspId.value),
)
const selectedSensorContext = computed(() => {
  if (!selectedDevice.value || selectedGpio.value == null) {
    return null
  }
  const sensorTypeNeedle = normalizedSelectedType.value
  const sensor = (selectedDevice.value.sensors ?? []).find((entry: any) =>
    Number(entry.gpio) === selectedGpio.value
    && (
      !sensorTypeNeedle
      || String(entry.sensor_type ?? '').toLowerCase() === sensorTypeNeedle
      || (
        sensorTypeNeedle === 'moisture'
        && String(entry.sensor_type ?? '').toLowerCase() === 'soil_moisture'
      )
    ),
  )
  return sensor ?? null
})
const allSensors = computed(() =>
  espStore.devices.flatMap((device) => Array.isArray(device.sensors) ? device.sensors : []),
)
const linkedTemperatureSensor = computed(() => {
  const linkedConfigId = (selectedSensorContext.value as any)?.temp_sensor_config_id as string | null | undefined
  if (!linkedConfigId) return null
  return allSensors.value.find((sensor: any) => String(sensor.config_id ?? '') === linkedConfigId) ?? null
})
const linkedTemperatureValue = computed<number | null>(() => {
  const sensor: any = linkedTemperatureSensor.value
  if (!sensor) return null
  const candidate = Number(sensor.processed_value ?? sensor.raw_value)
  return Number.isFinite(candidate) ? candidate : null
})
const isEcCalibration = computed(() =>
  (currentPreset.value?.calibrationMethod ?? '').startsWith('ec_'),
)

/**
 * P1b (AUT-490): Human-readable method label for the confirm phase.
 * Derived from currentPreset.calibrationMethod so it is always consistent
 * with the actual method — fixes the bug where ec_linear_2point showed "EC 1-Punkt".
 */
const CALIBRATION_METHOD_LABELS: Record<string, string> = {
  ec_1point: 'EC 1-Punkt',
  ec_2point: 'EC 2-Punkt (mit Luft-Referenz)',
  ec_linear_2point: 'EC 2-Punkt Linear',
  ph_2point: 'pH 2-Punkt',
  moisture_2point: 'Feuchte 2-Punkt',
  linear_2point: '2-Punkt Linear',
}
const confirmMethodLabel = computed((): string => {
  const method = currentPreset.value?.calibrationMethod
  if (!method) return selectedSensorType.value || '—'
  return CALIBRATION_METHOD_LABELS[method] ?? method
})
const usesLinkedTemperature = computed(() =>
  isEcCalibration.value && linkedTemperatureValue.value != null,
)
const calibrationTemperatureHint = computed(() => {
  if (usesLinkedTemperature.value) {
    const source = calibrationTemperatureSource.value || 'config:auto'
    return `Automatisch aus verknuepftem Temperatursensor (${source}).`
  }
  return 'Wird fuer die Temperaturkompensation des Kalibrierwerts verwendet.'
})

const deviceConnectivity = computed(() => {
  if (!selectedDevice.value) return 'offline'
  return (selectedDevice.value as any).is_online ? 'online' : 'offline'
})

const lifecycleTone = computed<'neutral' | 'success' | 'warning' | 'critical'>(() => {
  if (lifecycleState.value === 'terminal_success') return 'success'
  if (lifecycleState.value === 'terminal_timeout' || lifecycleState.value === 'pending') return 'warning'
  if (
    lifecycleState.value === 'terminal_failed'
    || lifecycleState.value === 'terminal_integration_issue'
  ) {
    return 'critical'
  }
  return 'neutral'
})

const lifecycleLabel = computed(() => {
  const labels: Record<string, string> = {
    idle: 'Idle',
    accepted: 'Accepted',
    pending: 'Pending',
    terminal_success: 'Terminal Success',
    terminal_failed: 'Terminal Failed',
    terminal_timeout: 'Terminal Timeout',
    terminal_integration_issue: 'Terminal Integration Issue',
  }
  return labels[lifecycleState.value] ?? lifecycleState.value
})

const qualityStatus = computed<'good' | 'suspect' | 'error'>(() => {
  const quality = String(measurementQuality.value ?? '').toLowerCase()
  if (quality === 'error' || lifecycleTone.value === 'critical') return 'error'
  if (quality === 'good' && isFreshMeasurement.value) return 'good'
  return 'suspect'
})

const qualityLabel = computed(() => {
  if (qualityStatus.value === 'good') return 'Good'
  if (qualityStatus.value === 'error') return 'Error'
  return 'Suspect'
})

const ecCellFactor = computed<number | null>(() => {
  const candidate = Number(ecDerived.value?.cell_factor)
  return Number.isFinite(candidate) ? candidate : null
})

const ecCellFactorHint = computed(() => {
  const factor = ecCellFactor.value
  if (factor == null) return ''
  if (factor >= 1.0 && factor <= 4.0) return 'Gut'
  if (factor >= 0.5 && factor <= 10.0) return 'Ausserhalb DFR-Richtwert, bitte Referenz und Sonde pruefen'
  return 'Stark abweichend: Messaufbau, Referenzloesung und Sonde pruefen'
})

const ecValidationWarnings = computed<string[]>(() => {
  const candidate = ecDerived.value?.validation_warnings
  if (!Array.isArray(candidate)) return []
  return candidate.filter((item): item is string => typeof item === 'string' && item.length > 0)
})

type MasteryStageId = 'prep' | 'capture' | 'validate' | 'finalize' | 'terminal'
const phaseRank: Record<string, number> = {
  select: 0,
  point1: 1,
  point2: 1,
  confirm: 2,
  finalizing: 2.5,
  done: 3,
  error: 3,
}
const masteryStages = computed(() => {
  const currentRank = phaseRank[phase.value] ?? 0
  const terminalCta = lifecycleState.value === 'terminal_success'
    ? 'Naechster Sensor oder Betrieb fortsetzen.'
    : lifecycleState.value === 'terminal_timeout'
      ? 'Session pruefen und Kalibrierung erneut ausfuehren.'
      : lifecycleState.value === 'terminal_failed' || lifecycleState.value === 'terminal_integration_issue'
        ? 'Fehlerursache pruefen und letzte Aktion wiederholen.'
        : 'Auf terminale Rueckmeldung warten.'
  const stages: Array<{ id: MasteryStageId; label: string; action: string; rank: number }> = [
    { id: 'prep', label: 'Vorbereitung', action: 'Sensor, Zone und Subzone bestaetigen.', rank: 0 },
    { id: 'capture', label: 'Messpunktaufnahme', action: 'Frische Messung starten und Punkt uebernehmen.', rank: 1 },
    { id: 'validate', label: 'Validierung', action: 'Punkte vergleichen und Kalibrierauftrag senden.', rank: 2 },
    { id: 'terminal', label: 'Terminaler Abschluss', action: terminalCta, rank: 3 },
  ]
  return stages.map((stage) => ({
    ...stage,
    isDone: currentRank > stage.rank,
    isCurrent: currentRank === stage.rank,
  }))
})

const currentNextAction = computed(() =>
  masteryStages.value.find((stage) => stage.isCurrent)?.action
  ?? masteryStages.value[masteryStages.value.length - 1]?.action
  ?? '',
)

const feedbackClass = ref('')
let feedbackTimer: ReturnType<typeof setTimeout> | null = null

watch(lifecycleState, (state) => {
  if (feedbackTimer) {
    clearTimeout(feedbackTimer)
    feedbackTimer = null
  }
  if (state === 'terminal_success') {
    feedbackClass.value = 'calibration-wizard--fx-success'
  } else if (state === 'terminal_timeout') {
    feedbackClass.value = 'calibration-wizard--fx-timeout'
  } else if (state === 'terminal_failed' || state === 'terminal_integration_issue') {
    feedbackClass.value = 'calibration-wizard--fx-error'
  } else {
    feedbackClass.value = ''
  }
  if (feedbackClass.value) {
    feedbackTimer = setTimeout(() => {
      feedbackClass.value = ''
    }, 200)
  }
})

watch(
  [usesLinkedTemperature, linkedTemperatureValue, linkedTemperatureSensor],
  ([autoLinked, tempValue, sensor]) => {
    if (!autoLinked || tempValue == null || !sensor) return
    const source = `config:${String((sensor as any).config_id ?? '')}`
    setCalibrationTemperature(Number(tempValue), source)
  },
  { immediate: true },
)

onUnmounted(() => {
  if (feedbackTimer) {
    clearTimeout(feedbackTimer)
    feedbackTimer = null
  }
})

const availableDeviceSensors = computed(() =>
  availableDevices.value.map((device) => {
    const sensors = (device.sensors ?? []).filter((sensor: any) => {
      if (!normalizedSelectedType.value) {
        return false
      }
      const sensorType = String(sensor.sensor_type ?? '').toLowerCase()
      if (normalizedSelectedType.value === 'moisture') {
        return sensorType === 'moisture' || sensorType === 'soil_moisture'
      }
      return sensorType === normalizedSelectedType.value
    })
    return {
      device,
      sensors,
    }
  }),
)

defineExpose({
  confirmLeave,
  hasUnsavedWork,
})
</script>

<template>
  <div class="calibration-wizard" data-testid="calibration-wizard" :class="[{ 'calibration-wizard--compact': compact }, feedbackClass]">
    <div v-if="!compact" class="calibration-wizard__header">
      <FlaskConical :size="20" class="calibration-wizard__icon" />
      <h2 class="calibration-wizard__title">Sensor-Kalibrierung</h2>
    </div>

    <div class="calibration-wizard__hud" role="status" aria-live="polite">
      <div class="calibration-wizard__hud-head">
        <div class="calibration-wizard__hud-chip" :class="`calibration-wizard__hud-chip--${deviceConnectivity}`">
          <Radar :size="14" />
          Device {{ deviceConnectivity === 'online' ? 'Online' : 'Offline' }}
        </div>
        <div class="calibration-wizard__hud-chip" :class="`calibration-wizard__hud-chip--${lifecycleTone}`">
          <Activity :size="14" />
          Contract {{ lifecycleLabel }}
        </div>
        <div class="calibration-wizard__hud-chip" :class="`calibration-wizard__hud-chip--${qualityStatus}`">
          <ShieldCheck :size="14" />
          Qualitaet {{ qualityLabel }}
        </div>
      </div>
      <div class="calibration-wizard__hud-context">
        <span class="calibration-wizard__hud-context-key">Kontext</span>
        <span class="calibration-wizard__summary-mono">{{ selectedEspId || '—' }}</span>
        <span>GPIO {{ selectedGpio ?? '—' }}</span>
        <span>Zone {{ (selectedDevice as any)?.zone_name || (selectedDevice as any)?.zone_id || 'nicht zugewiesen' }}</span>
        <span
          :title="(selectedSensorContext as any)?.subzone_id ? undefined : 'Diese Kalibrierung gilt für alle Sensoren der Zone, unabhängig von Subzone-Zuordnung.'"
          :class="{ 'calibration-wizard__hud-zoneweit': !(selectedSensorContext as any)?.subzone_id }"
        >Subzone {{ (selectedSensorContext as any)?.subzone_id || 'Zone-weit' }}</span>
      </div>
      <p v-if="lifecycleMessage" class="calibration-wizard__hud-message">{{ lifecycleMessage }}</p>
    </div>

    <div class="calibration-wizard__mastery">
      <div class="calibration-wizard__mastery-row">
        <div
          v-for="stage in masteryStages"
          :key="stage.id"
          class="calibration-wizard__mastery-stage"
          :class="{
            'calibration-wizard__mastery-stage--done': stage.isDone,
            'calibration-wizard__mastery-stage--current': stage.isCurrent,
          }"
        >
          {{ stage.label }}
        </div>
      </div>
      <p class="calibration-wizard__mastery-next">
        <strong>Naechste Aktion:</strong> {{ currentNextAction }}
      </p>
    </div>

    <!-- Phase: Select Sensor -->
    <div v-if="phase === 'select'" class="calibration-wizard__phase">
      <p class="calibration-wizard__desc">
        Waehle einen Sensor fuer die 2-Punkt-Kalibrierung.
      </p>

      <div class="calibration-wizard__type-grid">
        <button
          v-for="(preset, type) in sensorTypePresets"
          :key="type"
          class="calibration-wizard__type-card"
          :class="{ 'calibration-wizard__type-card--selected': selectedSensorType === type }"
          @click="selectedSensorType = type as string"
        >
          <span class="calibration-wizard__type-name">{{ preset.label }}</span>
        </button>
      </div>

      <div v-if="selectedSensorType === 'ec'" class="calibration-wizard__ec-preset-row">
        <p class="calibration-wizard__label">EC-Kalibrier-Verfahren</p>
        <div class="calibration-wizard__ec-preset-grid">
          <button
            v-for="(preset, presetId) in EC_PRESETS"
            :key="presetId"
            type="button"
            class="calibration-wizard__ec-preset"
            :class="{ 'calibration-wizard__ec-preset--active': ecPreset === presetId }"
            @click="ecPreset = presetId as EcPresetId"
          >
            {{ preset.label }}
          </button>
          <button
            type="button"
            class="calibration-wizard__ec-preset"
            :class="{ 'calibration-wizard__ec-preset--active': ecPreset === 'custom' }"
            @click="ecPreset = 'custom'"
          >
            Manuell
          </button>
        </div>
      </div>

      <div v-if="selectedSensorType" class="calibration-wizard__device-list">
        <p class="calibration-wizard__label">ESP-Geraet und GPIO waehlen:</p>
        <div v-for="entry in availableDeviceSensors" :key="espStore.getDeviceId(entry.device)" class="calibration-wizard__device-row">
          <span class="calibration-wizard__device-name">{{ entry.device.name || espStore.getDeviceId(entry.device) }}</span>
          <div class="calibration-wizard__gpio-chips">
            <button
              v-for="sensor in entry.sensors"
              :key="`${espStore.getDeviceId(entry.device)}-${(sensor as any).gpio}-${String((sensor as any).sensor_type ?? '')}`"
              class="calibration-wizard__gpio-chip"
              @click="selectSensor(espStore.getDeviceId(entry.device), (sensor as any).gpio, String((sensor as any).sensor_type ?? selectedSensorType))"
            >
              GPIO {{ (sensor as any).gpio }} - {{ String((sensor as any).sensor_type ?? '') }}
            </button>
          </div>
        </div>
        <p v-if="availableDevices.length === 0" class="calibration-wizard__empty">
          Keine ESP-Geraete verbunden.
        </p>
      </div>
    </div>

    <!-- Phase: Capture Point 1 -->
    <div v-if="phase === 'point1'" class="calibration-wizard__phase">
      <div class="calibration-wizard__actions">
        <button class="calibration-wizard__abort-btn" :disabled="isSubmitting" @click="handleAbort">
          <X :size="14" /> Abbrechen
        </button>
        <button class="calibration-wizard__back-btn" :disabled="isSubmitting" @click="goBack">
          <ArrowLeft :size="14" /> Zurueck
        </button>
      </div>
      <!-- Hint texts for each sensor type -->
      <div v-if="selectedSensorType === 'ph'" class="calibration-wizard__hint">
        <p>Sonde mit destilliertem Wasser zwischen den Pufferlösungen spülen. 30 Sekunden stabilisieren lassen.</p>
      </div>
      <div v-if="selectedSensorType === 'ec'" class="calibration-wizard__hint calibration-wizard__conditioning">
        <p><strong>Erstnutzung / lange Lagerung:</strong> Sonde 2–24 Stunden in destilliertem Wasser konditionieren, danach mit destilliertem Wasser spülen.</p>
        <p>Referenzlösung auf Raumtemperatur bringen (25°C ±2°C). Sonde vollständig eintauchen und ≥5s stabilisieren lassen.</p>
      </div>

      <!-- AUT-299: Temperatur-Eingabe (nur EC und pH) -->
      <div
        v-if="normalizedSelectedType === 'ec' || normalizedSelectedType === 'ph' || normalizedSelectedType === 'ec_2point'"
        class="calibration-wizard__temp-input"
      >
        <label class="calibration-wizard__temp-label">
          Lösungstemperatur (°C)
        </label>
        <template v-if="usesLinkedTemperature">
          <div class="calibration-wizard__temp-linked">
            <span class="calibration-wizard__temp-linked-value">{{ calibrationTemperature.toFixed(2) }} °C</span>
            <span class="calibration-wizard__temp-linked-sensor">
              {{ (linkedTemperatureSensor as any)?.name || (linkedTemperatureSensor as any)?.sensor_type || 'Temperatursensor' }}
            </span>
          </div>
        </template>
        <input
          v-else
          v-model.number="calibrationTemperature"
          type="number"
          min="0"
          max="50"
          step="0.1"
          class="calibration-wizard__temp-field"
          placeholder="25.0"
        />
        <span class="calibration-wizard__temp-hint">
          {{ calibrationTemperatureHint }}
        </span>
      </div>

      <!-- AUT-299: Skip-Button für überspringbare Schritte (EC Luft-Referenz) -->
      <div
        v-if="currentPreset?.point1Skippable"
        class="calibration-wizard__skip-row"
      >
        <button
          type="button"
          class="calibration-wizard__skip-btn"
          :disabled="isSubmitting"
          @click="skipCurrentPoint"
        >
          Luft-Schritt überspringen
        </button>
        <span class="calibration-wizard__skip-hint">
          Weiter zur Referenzlösung ohne Luft-Referenz (Standard-Kalibrierung).
        </span>
      </div>

      <!-- PKG-03: Sample-Averaging Fortschritt (nur EC, sampleCount > 1) -->
      <div
        v-if="isMeasuring && sampleTotal > 1"
        class="calibration-wizard__sample-progress"
        role="status"
        aria-live="polite"
      >
        <Loader :size="14" class="calibration-wizard__sample-progress-icon" />
        <span class="calibration-wizard__sample-progress-text">
          Sample {{ sampleProgress }}/{{ sampleTotal }}
        </span>
      </div>

      <CalibrationStep
        :step-number="1"
        :total-steps="currentPreset?.expectedPoints ?? 2"
        :esp-id="selectedEspId"
        :gpio="selectedGpio!"
        :sensor-type="selectedSensorType"
        :suggested-reference="getSuggestedReference(1)"
        :reference-label="getReferenceLabel(1)"
        :last-raw-value="lastRawValue"
        :is-measuring="isMeasuring"
        :measurement-quality="measurementQuality"
        :is-fresh-measurement="isFreshMeasurement"
        :capture-label="currentPreset?.expectedPoints === 1 ? 'Kalibrierung uebernehmen' : 'Punkt uebernehmen'"
        :require-good-quality="isEcCalibration"
        :preview-ec-us-cm="previewEcUsCm"
        :preview-available="previewAvailable"
        :stable="lastStable"
        :adc-stddev="lastAdcStddev"
        :temperature-used="lastTemperatureUsed"
        @captured="onPoint1Captured"
        @request-measurement="triggerLiveMeasurement"
      />
    </div>

    <!-- Phase: Capture Point 2 (nur fuer 2-Punkt-Sensoren) -->
    <div v-if="phase === 'point2' && currentPreset?.expectedPoints === 2" class="calibration-wizard__phase">
      <div class="calibration-wizard__actions">
        <button class="calibration-wizard__abort-btn" :disabled="isSubmitting" @click="handleAbort">
          <X :size="14" /> Abbrechen
        </button>
        <button class="calibration-wizard__back-btn" :disabled="isSubmitting" @click="goBack">
          <ArrowLeft :size="14" /> Zurueck zu Punkt 1
        </button>
      </div>
      <!-- Hint for pH second point -->
      <div v-if="selectedSensorType === 'ph'" class="calibration-wizard__hint">
        <p>Sonde mit destilliertem Wasser zwischen den Pufferlösungen spülen. 30 Sekunden stabilisieren lassen.</p>
      </div>
      <CalibrationStep
        :step-number="2"
        :total-steps="currentPreset?.expectedPoints ?? 2"
        :esp-id="selectedEspId"
        :gpio="selectedGpio!"
        :sensor-type="selectedSensorType"
        :suggested-reference="getSuggestedReference(2)"
        :reference-label="getReferenceLabel(2)"
        :last-raw-value="lastRawValue"
        :is-measuring="isMeasuring"
        :measurement-quality="measurementQuality"
        :is-fresh-measurement="isFreshMeasurement"
        :require-good-quality="isEcCalibration"
        :preview-ec-us-cm="previewEcUsCm"
        :preview-available="previewAvailable"
        :stable="lastStable"
        :adc-stddev="lastAdcStddev"
        :temperature-used="lastTemperatureUsed"
        @captured="onPoint2Captured"
        @request-measurement="triggerLiveMeasurement"
      />
    </div>

    <!-- Phase: Confirm -->
    <div v-if="phase === 'confirm'" class="calibration-wizard__phase">
      <h3 class="calibration-wizard__subtitle">Zusammenfassung</h3>

      <div class="calibration-wizard__summary">
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Sensor</span>
          <span>{{ currentPreset?.label ?? selectedSensorType }}</span>
        </div>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">ESP</span>
          <span class="calibration-wizard__summary-mono">{{ selectedEspId }}</span>
        </div>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">GPIO</span>
          <span class="calibration-wizard__summary-mono">{{ selectedGpio }}</span>
        </div>
        <!-- Dynamic point display based on sensor type -->
      <template v-if="selectedSensorType === 'ph'">
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">High-Buffer</span>
          <span class="calibration-wizard__summary-mono">
            RAW {{ points.find(p => p.point_role === 'buffer_high')?.raw.toFixed(1) ?? '—' }} →
            Ref {{ points.find(p => p.point_role === 'buffer_high')?.reference ?? '—' }}
          </span>
        </div>
        <div v-if="currentSessionId && points.find(p => p.point_role === 'buffer_high')?.point_id" class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">High-Buffer bearbeiten</span>
          <button class="calibration-wizard__inline-action-btn" @click="deletePoint('buffer_high')">
            Loeschen
          </button>
        </div>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Low-Buffer</span>
          <span class="calibration-wizard__summary-mono">
            RAW {{ points.find(p => p.point_role === 'buffer_low')?.raw.toFixed(1) ?? '—' }} →
            Ref {{ points.find(p => p.point_role === 'buffer_low')?.reference ?? '—' }}
          </span>
        </div>
        <div v-if="currentSessionId && points.find(p => p.point_role === 'buffer_low')?.point_id" class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Low-Buffer bearbeiten</span>
          <button class="calibration-wizard__inline-action-btn" @click="deletePoint('buffer_low')">
            Loeschen
          </button>
        </div>
      </template>

      <template v-else-if="selectedSensorType === 'ec'">
        <!-- P1b (AUT-490): EC 2-Punkt linear (ec_linear_2point) — reference_low + reference_high -->
        <template v-if="currentPreset?.calibrationMethod === 'ec_linear_2point'">
          <div class="calibration-wizard__summary-row">
            <span class="calibration-wizard__summary-label">Referenz-Low (1413 µS/cm)</span>
            <span class="calibration-wizard__summary-mono">
              RAW {{ points.find(p => p.point_role === 'reference_low')?.raw.toFixed(1) ?? '—' }} →
              Ref {{ points.find(p => p.point_role === 'reference_low')?.reference ?? '—' }}
            </span>
          </div>
          <div v-if="currentSessionId && points.find(p => p.point_role === 'reference_low')?.point_id" class="calibration-wizard__summary-row">
            <span class="calibration-wizard__summary-label">Referenz-Low bearbeiten</span>
            <button class="calibration-wizard__inline-action-btn" @click="deletePoint('reference_low')">
              Loeschen
            </button>
          </div>
          <div class="calibration-wizard__summary-row">
            <span class="calibration-wizard__summary-label">Referenz-High ({{ currentPreset.point2Ref }} µS/cm)</span>
            <span class="calibration-wizard__summary-mono">
              RAW {{ points.find(p => p.point_role === 'reference_high')?.raw.toFixed(1) ?? '—' }} →
              Ref {{ points.find(p => p.point_role === 'reference_high')?.reference ?? '—' }}
            </span>
          </div>
          <div v-if="currentSessionId && points.find(p => p.point_role === 'reference_high')?.point_id" class="calibration-wizard__summary-row">
            <span class="calibration-wizard__summary-label">Referenz-High bearbeiten</span>
            <button class="calibration-wizard__inline-action-btn" @click="deletePoint('reference_high')">
              Loeschen
            </button>
          </div>
        </template>
        <!-- EC 1-Punkt (custom preset) -->
        <template v-else>
          <div class="calibration-wizard__summary-row">
            <span class="calibration-wizard__summary-label">Referenzloesung</span>
            <span class="calibration-wizard__summary-mono">
              RAW {{ points.find(p => p.point_role === 'reference')?.raw.toFixed(1) ?? '—' }} →
              Ref {{ points.find(p => p.point_role === 'reference')?.reference ?? '—' }}
            </span>
          </div>
          <div v-if="currentSessionId && points.find(p => p.point_role === 'reference')?.point_id" class="calibration-wizard__summary-row">
            <span class="calibration-wizard__summary-label">Referenzloesung bearbeiten</span>
            <button class="calibration-wizard__inline-action-btn" @click="deletePoint('reference')">
              Loeschen
            </button>
          </div>
        </template>
      </template>

      <template v-else>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Punkt 1</span>
          <span class="calibration-wizard__summary-mono">
            RAW {{ points[0]?.raw.toFixed(1) }} → Ref {{ points[0]?.reference }}
          </span>
        </div>
        <div v-if="currentSessionId && points[0]?.point_id" class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Punkt 1 bearbeiten</span>
          <button class="calibration-wizard__inline-action-btn" @click="deletePoint('dry')">
            Punkt 1 loeschen
          </button>
        </div>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Punkt 2</span>
          <span class="calibration-wizard__summary-mono">
            RAW {{ points[1]?.raw.toFixed(1) }} → Ref {{ points[1]?.reference }}
          </span>
        </div>
        <div v-if="currentSessionId && points[1]?.point_id" class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Punkt 2 bearbeiten</span>
          <button class="calibration-wizard__inline-action-btn" @click="deletePoint('wet')">
            Punkt 2 loeschen
          </button>
        </div>
      </template>

      <div class="calibration-wizard__summary-row">
        <span class="calibration-wizard__summary-label">Methode</span>
        <!-- P1b (AUT-490): Method label derived from currentPreset — fixes bug where ec_linear_2point showed "EC 1-Punkt" -->
        <span>{{ confirmMethodLabel }}</span>
      </div>

      <div v-if="currentSessionId" class="calibration-wizard__summary-row">
        <span class="calibration-wizard__summary-label">Session-ID</span>
        <span class="calibration-wizard__summary-mono" :title="`Fuer Rueckverfolgbarkeit: ${currentSessionId}`">
          {{ currentSessionId.substring(0, 8) }}...
        </span>
      </div>
      </div>

      <details class="calibration-wizard__details">
        <summary>Diagnose und Rohdaten</summary>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Mess-Request</span>
          <span class="calibration-wizard__summary-mono">{{ measurementRequestId ?? 'nicht gesetzt' }}</span>
        </div>
      </details>

      <div class="calibration-wizard__actions">
        <button class="calibration-wizard__abort-btn" :disabled="isSubmitting" @click="handleAbort">
          <X :size="14" /> Abbrechen
        </button>
        <button class="calibration-wizard__back-btn" :disabled="isSubmitting" @click="goBack">
          <ArrowLeft :size="14" /> Zurueck
        </button>
        <button
          class="calibration-wizard__submit-btn"
          :disabled="isSubmitting"
          @click="submitCalibration"
        >
          {{ isSubmitting ? 'Kalibriere...' : 'Kalibrierung ausfuehren' }}
        </button>
      </div>
    </div>

    <!-- Phase: Finalizing -->
    <div v-if="phase === 'finalizing'" data-testid="finalizing-phase" class="calibration-wizard__phase calibration-wizard__phase--center">
      <div class="calibration-wizard__finalizing-spinner">
        <Loader :size="40" class="calibration-wizard__spinner-icon" />
      </div>
      <h3 class="calibration-wizard__subtitle">Kalibrierung wird angewendet</h3>
      <p class="calibration-wizard__desc calibration-wizard__finalizing-message">
        {{ lifecycleMessage || 'Bitte warten...' }}
      </p>
      <details v-if="lifecycleState === 'pending'" class="calibration-wizard__details calibration-wizard__finalizing-details">
        <summary>Session-Details anzeigen</summary>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Status</span>
          <span class="calibration-wizard__summary-mono">{{ lifecycleState }}</span>
        </div>
        <div class="calibration-wizard__summary-row">
          <span class="calibration-wizard__summary-label">Nachricht</span>
          <span class="calibration-wizard__summary-mono">{{ lifecycleMessage }}</span>
        </div>
      </details>
      <p v-if="lifecycleState === 'terminal_timeout'" class="calibration-wizard__timeout-notice">
        Maximale Wartezeit ohne terminale Rueckmeldung ueberschritten. Sitzung wird abgebrochen.
      </p>
    </div>

    <!-- Phase: Done -->
    <div v-if="phase === 'done'" data-testid="calibration-success" class="calibration-wizard__phase calibration-wizard__phase--center">
      <div class="calibration-wizard__done-icon">
        <Check :size="32" />
      </div>
      <h3 class="calibration-wizard__subtitle">Kalibrierung erfolgreich</h3>
      <p class="calibration-wizard__desc">
        {{ calibrationResult?.message ?? 'Parameter wurden gespeichert.' }}
      </p>

      <!-- pH-specific results -->
      <template v-if="selectedSensorType === 'ph' && phDerived">
        <div class="calibration-wizard__result-grid grid-auto-sm">
          <div v-if="phDerived.slope !== undefined" class="calibration-wizard__result-item">
            <div class="calibration-wizard__result-label">Slope (mV/pH)</div>
            <div class="calibration-wizard__result-value">{{ Number(phDerived.slope).toFixed(2) }}</div>
            <div class="calibration-wizard__result-hint">Idealwert: -59,16 mV/pH</div>
          </div>
          <div v-if="phDerived.offset !== undefined" class="calibration-wizard__result-item">
            <div class="calibration-wizard__result-label">Offset (mV)</div>
            <div class="calibration-wizard__result-value">{{ Number(phDerived.offset).toFixed(2) }}</div>
            <div class="calibration-wizard__result-hint">Kalibrier-Referenz</div>
          </div>
          <div v-if="phDerived.slope_deviation_pct !== undefined" class="calibration-wizard__result-item">
            <div class="calibration-wizard__result-label">Abweichung</div>
            <div class="calibration-wizard__result-value">{{ Number(phDerived.slope_deviation_pct).toFixed(2) }}%</div>
            <div class="calibration-wizard__result-hint">
              {{ Number(phDerived.slope_deviation_pct) < 5 ? 'Ausgezeichnet' : Number(phDerived.slope_deviation_pct) < 15 ? 'Gut' : 'Abweichend (Signalaufbereitung)' }}
            </div>
          </div>
        </div>

        <!-- Validation warnings from signal conditioning / non-Nernst sensors -->
        <div
          v-if="Array.isArray(phDerived.validation_warnings) && (phDerived.validation_warnings as string[]).length > 0"
          class="calibration-wizard__validation-warnings"
        >
          <div v-for="(warning, i) in (phDerived.validation_warnings as string[])" :key="i" class="calibration-wizard__validation-warning">
            <AlertCircle :size="13" class="calibration-wizard__warning-icon" />
            <span>{{ warning }}</span>
          </div>
        </div>
      </template>

      <!-- EC-specific results -->
      <template v-if="selectedSensorType === 'ec' && ecDerived">
        <div class="calibration-wizard__result-grid">
          <div v-if="ecDerived.cell_factor !== undefined" class="calibration-wizard__result-item">
            <div class="calibration-wizard__result-label">Zellfaktor</div>
            <div class="calibration-wizard__result-value">{{ ecCellFactor != null ? ecCellFactor.toFixed(3) : '—' }}</div>
            <div class="calibration-wizard__result-hint">{{ ecCellFactorHint }}</div>
          </div>
        </div>
        <div
          v-if="ecValidationWarnings.length > 0"
          class="calibration-wizard__validation-warnings"
        >
          <div v-for="(warning, i) in ecValidationWarnings" :key="`ec-warning-${i}`" class="calibration-wizard__validation-warning">
            <AlertCircle :size="13" class="calibration-wizard__warning-icon" />
            <span>{{ warning }}</span>
          </div>
        </div>
      </template>

      <!-- Generic result data -->
      <details v-if="calibrationResult?.calibration" class="calibration-wizard__details calibration-wizard__result-data">
        <summary>Kalibrierparameter (vollstaendig)</summary>
        <pre class="calibration-wizard__result-pre">{{ JSON.stringify(calibrationResult.calibration, null, 2) }}</pre>
      </details>

      <div v-if="currentSessionId" class="calibration-wizard__session-info">
        <small>Session-ID: <code>{{ currentSessionId }}</code></small>
      </div>

      <button class="calibration-wizard__submit-btn" @click="reset">
        <RefreshCw :size="14" /> Weitere Kalibrierung
      </button>
    </div>

    <!-- Phase: Error -->
    <div v-if="phase === 'error'" data-testid="calibration-error" class="calibration-wizard__phase calibration-wizard__phase--center">
      <div class="calibration-wizard__error-icon">
        <AlertCircle :size="32" />
      </div>
      <h3 class="calibration-wizard__subtitle calibration-wizard__subtitle--error">
        {{ lifecycleState === 'terminal_timeout' ? 'Timeout: Kalibrierung nicht abgeschlossen' : 'Fehler' }}
      </h3>
      <p class="calibration-wizard__error-msg">{{ errorMessage }}</p>
      <div class="calibration-wizard__actions">
        <button
          v-if="lifecycleState === 'terminal_timeout'"
          class="calibration-wizard__back-btn"
          @click="goBack"
        >
          <ArrowLeft :size="14" /> Session pruefen
        </button>
        <button
          v-else
          class="calibration-wizard__back-btn"
          @click="goBack"
        >
          <ArrowLeft :size="14" /> Zurueck
        </button>
        <button class="calibration-wizard__submit-btn" @click="reset">
          {{ lifecycleState === 'terminal_timeout' ? 'Erneut versuchen' : 'Neu starten' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calibration-wizard {
  max-width: 600px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.calibration-wizard--compact {
  max-width: 100%;
}

.calibration-wizard__hud {
  padding: 0.75rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.calibration-wizard__hud-head {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
}

.calibration-wizard__hud-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  border-radius: var(--radius-md);
  padding: 0.375rem 0.5rem;
  font-size: 0.75rem;
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  color: var(--color-text-secondary);
}

.calibration-wizard__hud-chip--online,
.calibration-wizard__hud-chip--good,
.calibration-wizard__hud-chip--success {
  border-color: rgba(52, 211, 153, 0.45);
  color: var(--color-success);
}

.calibration-wizard__hud-chip--offline,
.calibration-wizard__hud-chip--critical,
.calibration-wizard__hud-chip--error {
  border-color: rgba(248, 113, 113, 0.45);
  color: var(--color-error);
}

.calibration-wizard__hud-chip--warning,
.calibration-wizard__hud-chip--suspect,
.calibration-wizard__hud-chip--neutral {
  border-color: rgba(251, 191, 36, 0.45);
  color: var(--color-warning);
}

.calibration-wizard__hud-context {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 0.75rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.calibration-wizard__hud-context-key {
  color: var(--color-text-muted);
}

.calibration-wizard__hud-zoneweit {
  text-decoration: underline dotted;
  cursor: help;
}

.calibration-wizard__hud-message {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.calibration-wizard__mastery {
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.calibration-wizard__mastery-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.5rem;
}

.calibration-wizard__mastery-stage {
  padding: 0.45rem 0.5rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  font-size: 0.6875rem;
  text-align: center;
  color: var(--color-text-muted);
}

.calibration-wizard__mastery-stage--current {
  border-color: rgba(167, 139, 250, 0.5);
  color: var(--color-text-primary);
  background: rgba(167, 139, 250, 0.08);
}

.calibration-wizard__mastery-stage--done {
  border-color: rgba(52, 211, 153, 0.45);
  color: var(--color-success);
}

.calibration-wizard__mastery-next {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.calibration-wizard__header {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.calibration-wizard__icon {
  color: var(--color-iridescent-1);
}

.calibration-wizard__title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0;
}

.calibration-wizard__subtitle {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.calibration-wizard__subtitle--error {
  color: var(--color-error);
}

.calibration-wizard__desc {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  line-height: 1.5;
  margin: 0;
}

.calibration-wizard__label {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  margin: 0 0 0.5rem 0;
}

.calibration-wizard__phase {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.calibration-wizard__phase--center {
  align-items: center;
  text-align: center;
}

/* Type selection grid */
.calibration-wizard__type-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.625rem;
}

.calibration-wizard__type-card {
  padding: 0.875rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.15s;
  text-align: center;
}

.calibration-wizard__type-card:hover {
  border-color: var(--color-iridescent-1);
  background: rgba(167,139,250,0.06);
}

.calibration-wizard__type-card--selected {
  border-color: var(--color-iridescent-1);
  background: rgba(167,139,250,0.12);
}

.calibration-wizard__type-name {
  font-size: 0.8125rem;
  font-weight: 600;
}

/* Device list */
.calibration-wizard__device-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.calibration-wizard__device-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.625rem 0.75rem;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
}

.calibration-wizard__device-name {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  font-weight: 500;
}

.calibration-wizard__gpio-chips {
  display: flex;
  gap: 0.375rem;
}

.calibration-wizard__gpio-chip {
  padding: 0.25rem 0.625rem;
  font-size: 0.6875rem;
  font-family: 'JetBrains Mono', monospace;
  border-radius: var(--radius-full);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-tertiary);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.calibration-wizard__gpio-chip:hover {
  border-color: var(--color-iridescent-1);
  color: var(--color-text-primary);
}

.calibration-wizard__empty {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  text-align: center;
  padding: 1rem;
}

/* EC Preset (nur bei sensor_type === ec) */
.calibration-wizard__ec-preset-row {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-top: var(--space-3);
}

.calibration-wizard__ec-preset-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.calibration-wizard__ec-preset--active {
  border-color: var(--color-iridescent-1);
  background: color-mix(in srgb, var(--color-iridescent-1) 12%, transparent);
}

.calibration-wizard__conditioning {
  border-left: 3px solid var(--color-info);
  padding-left: var(--space-3);
}

.calibration-wizard__ec-preset {
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  font-family: inherit;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133, 133, 160, 0.12));
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s;
}

.calibration-wizard__ec-preset:hover,
.calibration-wizard__ec-preset:focus {
  border-color: var(--color-iridescent-1);
}

/* Summary */
.calibration-wizard__summary {
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.calibration-wizard__summary-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}

.calibration-wizard__summary-label {
  color: var(--color-text-muted);
  font-size: 0.75rem;
}

.calibration-wizard__summary-mono {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.8125rem;
}

.calibration-wizard__inline-action-btn {
  padding: 0.375rem 0.625rem;
  font-size: 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-warning);
  background: transparent;
  color: var(--color-warning);
  cursor: pointer;
  transition: all 0.15s;
}

.calibration-wizard__inline-action-btn:hover {
  background: rgba(251, 191, 36, 0.12);
}

/* Actions */
.calibration-wizard__actions {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}

.calibration-wizard__back-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  font-size: 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.15s;
}

.calibration-wizard__back-btn:hover {
  border-color: var(--color-text-muted);
}

.calibration-wizard__back-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.calibration-wizard__abort-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  font-size: 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-text-muted);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.calibration-wizard__abort-btn:hover {
  border-color: var(--color-error);
  color: var(--color-error);
  background: rgba(239, 68, 68, 0.08);
}

.calibration-wizard__abort-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.calibration-wizard__submit-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
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

.calibration-wizard__submit-btn:hover:not(:disabled) {
  filter: brightness(1.1);
  transform: translateY(-1px);
}

.calibration-wizard__submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* Done */
.calibration-wizard__done-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 50%;
  background: rgba(52, 211, 153, 0.15);
  color: var(--color-success);
  display: flex;
  align-items: center;
  justify-content: center;
}

.calibration-wizard__hint {
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
  border-radius: var(--radius-md);
  padding: 0.75rem;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  margin-bottom: 0.5rem;
}

.calibration-wizard__hint p {
  margin: 0;
}

.calibration-wizard__result-grid {
  gap: 1rem;
  margin: 1rem 0;
}

.calibration-wizard__result-item {
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.calibration-wizard__result-label {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  font-weight: 500;
}

.calibration-wizard__result-value {
  font-size: 1.25rem;
  font-family: 'JetBrains Mono', monospace;
  color: var(--color-iridescent-1);
  font-weight: 600;
}

.calibration-wizard__result-hint {
  font-size: 0.7rem;
  color: var(--color-text-secondary);
}

.calibration-wizard__validation-warnings {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-top: 0.5rem;
}

.calibration-wizard__validation-warning {
  display: flex;
  align-items: flex-start;
  gap: 0.375rem;
  font-size: 0.75rem;
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.2);
  border-radius: var(--radius-sm);
  padding: 0.375rem 0.625rem;
  line-height: 1.4;
}

.calibration-wizard__warning-icon {
  flex-shrink: 0;
  margin-top: 0.125rem;
}

.calibration-wizard__session-info {
  font-size: 0.75rem;
  color: var(--color-text-muted);
  text-align: center;
  margin: 0.5rem 0;
}

.calibration-wizard__session-info code {
  font-family: 'JetBrains Mono', monospace;
  background: var(--color-bg-secondary);
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
  word-break: break-all;
}

.calibration-wizard__result-data {
  width: 100%;
  max-width: 400px;
}

.calibration-wizard__result-pre {
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 0.75rem;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.75rem;
  color: var(--color-text-primary);
  overflow-x: auto;
  text-align: left;
}

.calibration-wizard__error-msg {
  font-size: 0.875rem;
  color: var(--color-error);
  margin: 0;
}

.calibration-wizard__error-icon {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 50%;
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-error);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Finalizing Phase */
.calibration-wizard__finalizing-spinner {
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 50%;
  background: rgba(167, 139, 250, 0.15);
  color: var(--color-iridescent-1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.calibration-wizard__spinner-icon {
  animation: spin 1s linear infinite;
}

.calibration-wizard__finalizing-message {
  font-size: 0.875rem;
  color: var(--color-text-secondary);
  margin: 0;
}

.calibration-wizard__finalizing-details {
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 0.625rem;
  background: var(--color-bg-secondary);
  width: 100%;
  max-width: 400px;
}

.calibration-wizard__timeout-notice {
  font-size: 0.8125rem;
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
  border: 1px solid rgba(251, 191, 36, 0.3);
  border-radius: var(--radius-sm);
  padding: 0.625rem 0.75rem;
  margin: 0;
  line-height: 1.4;
}

.calibration-wizard__details {
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  padding: 0.625rem;
  background: var(--color-bg-secondary);
}

.calibration-wizard__details summary {
  cursor: pointer;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}

.calibration-wizard--fx-success {
  animation: calibrationWizardSuccess 180ms ease-out;
}

.calibration-wizard--fx-timeout {
  animation: calibrationWizardTimeout 200ms ease-out;
}

.calibration-wizard--fx-error {
  animation: calibrationWizardError 180ms ease-out;
}

@keyframes calibrationWizardSuccess {
  0% { transform: scale(1); }
  50% { transform: scale(1.008); }
  100% { transform: scale(1); }
}

@keyframes calibrationWizardTimeout {
  0% { transform: translateX(0); }
  35% { transform: translateX(3px); }
  70% { transform: translateX(-3px); }
  100% { transform: translateX(0); }
}

@keyframes calibrationWizardError {
  0% { filter: brightness(1); }
  50% { filter: brightness(1.12); }
  100% { filter: brightness(1); }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* AUT-299: Temperature input */
.calibration-wizard__temp-input {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
}

.calibration-wizard__temp-label {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.calibration-wizard__temp-field {
  width: 8rem;
  padding: 0.375rem 0.625rem;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border, rgba(133,133,160,0.12));
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: 0.875rem;
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
}

.calibration-wizard__temp-hint {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

.calibration-wizard__temp-linked {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.calibration-wizard__temp-linked-value {
  font-family: var(--font-mono, 'JetBrains Mono', monospace);
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.calibration-wizard__temp-linked-sensor {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}

/* AUT-299: Skip row */
.calibration-wizard__skip-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0.75rem;
  border: 1px dashed rgba(251, 191, 36, 0.35);
  border-radius: var(--radius-md);
  background: rgba(251, 191, 36, 0.04);
}

.calibration-wizard__skip-btn {
  flex-shrink: 0;
  padding: 0.375rem 0.75rem;
  border-radius: var(--radius-sm);
  border: 1px solid rgba(251, 191, 36, 0.4);
  background: transparent;
  color: var(--color-warning);
  font-size: 0.75rem;
  cursor: pointer;
  transition: background 0.15s;
}

.calibration-wizard__skip-btn:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.1);
}

.calibration-wizard__skip-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.calibration-wizard__skip-hint {
  font-size: 0.6875rem;
  color: var(--color-text-muted);
}
</style>
