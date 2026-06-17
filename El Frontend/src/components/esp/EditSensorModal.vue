<script setup lang="ts">
/**
 * EditSensorModal Component
 *
 * Extracted from ESPOrbitalLayout: Modal for editing sensor configuration.
 * Supports:
 * - Name editing
 * - Operating mode (continuous, on_demand, scheduled, paused) with type-default logic
 * - Timeout configuration with override/reset to default
 * - Cron-based scheduling with presets
 * - On-demand measurement trigger
 * - Sensor removal (mock ESPs only)
 */

import { ref, computed, watch } from 'vue'
import { X, Loader2, Trash2 } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { sensorsApi } from '@/api/sensors'
import { useToast } from '@/composables/useToast'
import { SENSOR_TYPE_CONFIG } from '@/utils/sensorDefaults'
import { createLogger } from '@/utils/logger'

const logger = createLogger('EditSensorModal')

/** Sensor data shape for editing */
export interface EditableSensor {
  gpio: number
  sensor_type: string
  name: string | null
  operating_mode?: string | null
  timeout_seconds?: number | null
  schedule_config?: { type: string; expression: string } | null
  measurement_freshness_hours?: number | null
  calibration_interval_days?: number | null
}

interface Props {
  modelValue: boolean
  espId: string
  /** The sensor to edit — pass null to close */
  sensor: EditableSensor | null
  /** Whether the ESP is a mock device (enables delete) */
  isMock: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  saved: []
  deleted: [gpio: number]
}>()

const espStore = useEspStore()
const toast = useToast()

// ── Internal Editing State ───────────────────────────────────────────

const editingSensor = ref<{
  gpio: number
  sensor_type: string
  name: string | null
  operating_mode: string | null
  timeout_seconds: number | null
  schedule_config: { type: string; expression: string } | null
  measurement_freshness_hours: number | null
  calibration_interval_days: number | null
  typeDefaultMode: string
  typeDefaultTimeout: number
} | null>(null)

const isEditSaving = ref(false)
const editError = ref<string | null>(null)
const isMeasuring = ref(false)
const measureSuccess = ref<string | null>(null)

const CRON_PRESETS = [
  { label: 'Jede Stunde', value: '0 * * * *', description: 'Zur vollen Stunde' },
  { label: 'Alle 6 Stunden', value: '0 */6 * * *', description: '00:00, 06:00, 12:00, 18:00' },
  { label: 'Täglich um 8:00', value: '0 8 * * *', description: 'Einmal täglich' },
  { label: 'Alle 15 Minuten', value: '*/15 * * * *', description: '00, 15, 30, 45' },
  { label: 'Alle 30 Minuten', value: '*/30 * * * *', description: '00 und 30' },
  { label: 'Wochentags 9:00', value: '0 9 * * 1-5', description: 'Mo-Fr um 9:00' },
]

// ── Initialize from prop when modal opens ────────────────────────────

watch(() => props.modelValue, (open) => {
  if (open && props.sensor) {
    const typeConfig = SENSOR_TYPE_CONFIG[props.sensor.sensor_type] || {}
    const typeDefaultMode = (typeConfig as any).recommendedMode || 'continuous'
    const typeDefaultTimeout = (typeConfig as any).recommendedTimeout ?? 180

    const existingSchedule = props.sensor.schedule_config as { type?: string; expression?: string } | null
    const scheduleConfig = existingSchedule?.expression
      ? { type: 'cron', expression: existingSchedule.expression }
      : null

    editingSensor.value = {
      gpio: props.sensor.gpio,
      sensor_type: props.sensor.sensor_type,
      name: props.sensor.name || null,
      operating_mode: props.sensor.operating_mode && props.sensor.operating_mode !== typeDefaultMode
        ? props.sensor.operating_mode : null,
      timeout_seconds: props.sensor.timeout_seconds !== undefined && props.sensor.timeout_seconds !== typeDefaultTimeout
        ? props.sensor.timeout_seconds : null,
      schedule_config: scheduleConfig,
      measurement_freshness_hours: props.sensor.measurement_freshness_hours ?? null,
      calibration_interval_days: props.sensor.calibration_interval_days ?? null,
      typeDefaultMode,
      typeDefaultTimeout,
    }
    editError.value = null
    measureSuccess.value = null
  } else if (!open) {
    editingSensor.value = null
  }
}, { immediate: true })

// ── Computed ─────────────────────────────────────────────────────────

const editHasModeOverride = computed(() => editingSensor.value?.operating_mode !== null && editingSensor.value?.operating_mode !== undefined)
const editHasTimeoutOverride = computed(() => editingSensor.value?.timeout_seconds !== null && editingSensor.value?.timeout_seconds !== undefined)

const editEffectiveMode = computed(() => editingSensor.value?.operating_mode ?? editingSensor.value?.typeDefaultMode ?? 'continuous')
const editEffectiveTimeout = computed(() => editingSensor.value?.timeout_seconds ?? editingSensor.value?.typeDefaultTimeout ?? 180)

const editSupportsOnDemand = computed(() => {
  if (!editingSensor.value) return false
  const config = SENSOR_TYPE_CONFIG[editingSensor.value.sensor_type]
  return (config as any)?.supportsOnDemand ?? false
})

function getSensorLabel(sensorType: string): string {
  const config = SENSOR_TYPE_CONFIG[sensorType]
  return config?.label || sensorType
}

// ── Actions ──────────────────────────────────────────────────────────

function close() {
  emit('update:modelValue', false)
}

function resetToTypeDefault(field: 'operating_mode' | 'timeout_seconds') {
  if (!editingSensor.value) return
  if (field === 'operating_mode') editingSensor.value.operating_mode = null
  else editingSensor.value.timeout_seconds = null
}

function setOverrideValue(field: 'operating_mode' | 'timeout_seconds', value: string | number) {
  if (!editingSensor.value) return
  if (field === 'operating_mode') editingSensor.value.operating_mode = value as string
  else editingSensor.value.timeout_seconds = value as number
}

function setCronExpression(expression: string) {
  if (!editingSensor.value) return
  editingSensor.value.schedule_config = expression ? { type: 'cron', expression } : null
}

async function saveEditSensor() {
  if (!editingSensor.value) return
  isEditSaving.value = true
  editError.value = null

  try {
    const scheduleConfig = editingSensor.value.operating_mode === 'scheduled' && editingSensor.value.schedule_config
      ? editingSensor.value.schedule_config : undefined
    const gpio = editingSensor.value.gpio

    await espStore.updateSensorConfig(props.espId, gpio, {
      name: editingSensor.value.name,
      operating_mode: editingSensor.value.operating_mode,
      timeout_seconds: editingSensor.value.timeout_seconds,
      schedule_config: scheduleConfig,
      measurement_freshness_hours: editingSensor.value.measurement_freshness_hours,
      calibration_interval_days: editingSensor.value.calibration_interval_days,
    })

    toast.success(`Sensor "${getSensorLabel(editingSensor.value.sensor_type)}" (GPIO ${gpio}) aktualisiert`)
    close()
    emit('saved')
    await espStore.fetchAll()
  } catch (err: any) {
    logger.error('Failed to update sensor', err)
    editError.value = err.message || 'Fehler beim Speichern der Sensor-Konfiguration'
  } finally {
    isEditSaving.value = false
  }
}

async function removeSensor() {
  if (!editingSensor.value || !props.isMock) return
  try {
    await espStore.removeSensor(props.espId, editingSensor.value.gpio)
    toast.success(`Sensor GPIO ${editingSensor.value.gpio} entfernt`)
    const gpio = editingSensor.value.gpio
    close()
    emit('deleted', gpio)
    await espStore.fetchAll()
  } catch (err: any) {
    logger.error('Failed to remove sensor', err)
    editError.value = err.message || 'Fehler beim Entfernen des Sensors'
  }
}

async function triggerMeasureNow() {
  if (!editingSensor.value) return
  isMeasuring.value = true
  measureSuccess.value = null
  try {
    await sensorsApi.triggerMeasurement(props.espId, editingSensor.value.gpio)
    measureSuccess.value = 'Messung angefordert'
    setTimeout(() => { measureSuccess.value = null }, 3000)
  } catch (err: any) {
    editError.value = err.message || 'Messung fehlgeschlagen'
  } finally {
    isMeasuring.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="modelValue && editingSensor" class="modal-overlay" @click.self="close">
      <div class="modal-content">
        <div class="modal-header modal-header--edit">
          <div>
            <h3 class="modal-title">Sensor bearbeiten</h3>
            <p class="modal-subtitle">GPIO {{ editingSensor.gpio }} · {{ getSensorLabel(editingSensor.sensor_type) }}</p>
          </div>
          <button class="modal-close" @click="close"><X :size="20" /></button>
        </div>

        <div class="modal-body">
          <!-- Name -->
          <div class="form-group">
            <label class="form-label">Name (optional)</label>
            <input v-model="editingSensor.name" type="text" class="form-input" placeholder="z.B. Temperatur Gewächshaus 1" />
          </div>

          <!-- Operating Mode -->
          <div class="form-group">
            <div class="form-label-row">
              <label class="form-label">Betriebsmodus</label>
              <button v-if="editHasModeOverride" class="btn-reset" @click="resetToTypeDefault('operating_mode')">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                Type-Default
              </button>
            </div>
            <select :value="editEffectiveMode" class="form-select" @change="setOverrideValue('operating_mode', ($event.target as HTMLSelectElement).value)">
              <option value="continuous">Kontinuierlich</option>
              <option value="on_demand" :disabled="!editSupportsOnDemand">Auf Abruf {{ !editSupportsOnDemand ? '(nicht unterstützt)' : '' }}</option>
              <option value="scheduled">Geplant</option>
              <option value="paused">Pausiert</option>
            </select>
            <p :class="['form-hint', editHasModeOverride ? 'form-hint--warning' : '']">
              <template v-if="editHasModeOverride">⚠️ Individuell angepasst (Default: {{ editingSensor.typeDefaultMode }})</template>
              <template v-else>Verwendet Type-Default: {{ editingSensor.typeDefaultMode }}</template>
            </p>
          </div>

          <!-- Timeout -->
          <div v-if="editEffectiveMode === 'continuous'" class="form-group">
            <div class="form-label-row">
              <label class="form-label">Timeout (Sekunden)</label>
              <button v-if="editHasTimeoutOverride" class="btn-reset" @click="resetToTypeDefault('timeout_seconds')">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                Type-Default
              </button>
            </div>
            <input :value="editEffectiveTimeout" type="number" min="0" max="86400" class="form-input" placeholder="180"
              @input="setOverrideValue('timeout_seconds', parseInt(($event.target as HTMLInputElement).value) || 0)" />
            <p :class="['form-hint', editHasTimeoutOverride ? 'form-hint--warning' : '']">
              <template v-if="editHasTimeoutOverride">⚠️ Individuell (Default: {{ editingSensor.typeDefaultTimeout }}s)</template>
              <template v-else>Type-Default: {{ editingSensor.typeDefaultTimeout }}s</template>
            </p>
          </div>

          <!-- Sensor-Lifecycle: Freshness & Calibration (AUT-39) -->
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">Mess-Alter (Stunden)</label>
              <input
                v-model.number="editingSensor.measurement_freshness_hours"
                type="number"
                min="0"
                step="1"
                class="form-input"
                placeholder="leer = kein Limit"
              />
              <p class="form-hint">Ab wann ein Messwert als veraltet gilt</p>
            </div>
            <div class="form-group">
              <label class="form-label">Kalibrier-Intervall (Tage)</label>
              <input
                v-model.number="editingSensor.calibration_interval_days"
                type="number"
                min="0"
                step="1"
                class="form-input"
                placeholder="leer = keine Erinnerung"
              />
              <p class="form-hint">Empfohlener Rekalibrierungszyklus</p>
            </div>
          </div>

          <!-- Mode-specific info boxes -->
          <div v-if="editEffectiveMode !== 'continuous'" class="info-box">
            <template v-if="editEffectiveMode === 'on_demand'">
              <div class="info-box__content">
                <p>ℹ️ <strong>Auf Abruf:</strong> Sensor misst nur bei manueller Anforderung.</p>
                <button class="btn btn--accent btn--sm" :disabled="isMeasuring" @click="triggerMeasureNow">
                  <Loader2 v-if="isMeasuring" class="animate-spin" :size="14" /><span v-else>📏</span>
                  {{ isMeasuring ? 'Messe...' : 'Jetzt messen' }}
                </button>
              </div>
            </template>
            <template v-else-if="editEffectiveMode === 'paused'">ℹ️ <strong>Pausiert:</strong> Sensor deaktiviert, GPIO reserviert.</template>
            <template v-else-if="editEffectiveMode === 'scheduled'">
              <div class="schedule-config">
                <p class="schedule-config__info">ℹ️ <strong>Geplant:</strong> Server-gesteuerte Messung.</p>
                <div class="schedule-config__presets">
                  <label class="form-label">Zeitplan-Vorlagen:</label>
                  <div class="preset-buttons">
                    <button v-for="preset in CRON_PRESETS" :key="preset.value" class="preset-btn"
                      :class="{ 'preset-btn--active': editingSensor?.schedule_config?.expression === preset.value }"
                      :title="preset.description" @click="setCronExpression(preset.value)">{{ preset.label }}</button>
                  </div>
                </div>
                <div class="schedule-config__custom">
                  <label class="form-label">Cron-Expression:</label>
                  <input :value="editingSensor?.schedule_config?.expression || ''" type="text" class="form-input form-input--mono"
                    placeholder="z.B. 0 */6 * * *" @input="setCronExpression(($event.target as HTMLInputElement).value)" />
                  <p class="form-hint">Format: Minute Stunde Tag Monat Wochentag</p>
                </div>
                <div v-if="editingSensor?.schedule_config?.expression" class="schedule-config__current">
                  <span class="schedule-label">Aktuell:</span>
                  <code class="schedule-value">{{ editingSensor.schedule_config.expression }}</code>
                </div>
              </div>
            </template>
          </div>

          <!-- Alerts -->
          <div v-if="editError" class="alert alert--error">
            <span>⚠️ {{ editError }}</span>
            <button class="alert__close" @click="editError = null">×</button>
          </div>
          <div v-if="measureSuccess" class="alert alert--success"><span>✅ {{ measureSuccess }}</span></div>
        </div>

        <!-- Footer -->
        <div class="modal-footer modal-footer--with-delete">
          <button v-if="isMock" class="btn btn-danger btn--icon" :disabled="isEditSaving" @click="removeSensor">
            <Trash2 :size="16" />Entfernen
          </button>
          <div class="modal-footer__spacer" />
          <button class="btn btn-secondary" :disabled="isEditSaving" @click="close">Abbrechen</button>
          <button class="btn btn-primary" :disabled="isEditSaving" @click="saveEditSensor">
            <Loader2 v-if="isEditSaving" class="animate-spin" :size="16" />
            {{ isEditSaving ? 'Speichere...' : 'Speichern' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
/* All form/modal/button styles provided globally by styles/forms.css */
</style>
