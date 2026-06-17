<script setup lang="ts">
/**
 * AlertConfigSection — Per-Sensor/Actuator Alert Configuration (ISA-18.2)
 *
 * Master toggle: Enable/disable notifications for this sensor/actuator.
 * When disabled: suppression reason, optional note, optional auto-re-enable date.
 * Custom thresholds: Override global thresholds for this sensor.
 * Severity override: Force all alerts to a specific severity.
 *
 * Used inside SensorConfigPanel and ActuatorConfigPanel AccordionSections.
 */
import { ref, computed, onMounted } from 'vue'
import { BellOff, Bell, Clock, Shield } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { useAlertSuppression } from '@/composables/useAlertSuppression'
import { formatDateTime, formatSuppressionReason } from '@/utils/formatters'
import type { AlertConfigUpdate, AlertConfigResponse } from '@/api/sensors'

interface DeviceAlertConfig {
  propagate_to_children?: boolean
  suppression_until?: string | null
  suppression_reason?: string | null
}

interface Props {
  entityId: string
  entityType: 'sensor' | 'actuator'
  fetchFn: (id: string) => Promise<AlertConfigResponse>
  updateFn: (id: string, config: AlertConfigUpdate) => Promise<AlertConfigResponse>
  /**
   * AUT-255: Optional device-level alert config (parent ESP).
   * When provided, the suppression banner shows the inherited cascade.
   */
  deviceAlertConfig?: DeviceAlertConfig | null
}

const props = defineProps<Props>()
const { success, error } = useToast()

const isLoading = ref(false)
const isSaving = ref(false)
const alertConfig = ref<Record<string, unknown>>({})

// Form state
const alertsEnabled = computed({
  get: () => alertConfig.value.alerts_enabled !== false,
  set: (val: boolean) => {
    alertConfig.value.alerts_enabled = val
  },
})

const suppressionReason = ref<string>('maintenance')
const suppressionNote = ref<string>('')
const suppressionUntil = ref<string>('')
const severityOverride = ref<string>('')

// Custom thresholds
const customWarningMin = ref<number | null>(null)
const customWarningMax = ref<number | null>(null)
const customCriticalMin = ref<number | null>(null)
const customCriticalMax = ref<number | null>(null)

// AUT-255: Suppression cascade view-model (sensor + device).
const sensorAlertConfigRef = computed(() => alertConfig.value as {
  alerts_enabled?: boolean
  suppression_until?: string | null
  suppression_reason?: string | null
})
const deviceAlertConfigRef = computed(() => props.deviceAlertConfig ?? null)
const { suppression } = useAlertSuppression(sensorAlertConfigRef, deviceAlertConfigRef)

const SUPPRESSION_REASONS = [
  { value: 'maintenance', label: 'Wartung' },
  { value: 'intentionally_offline', label: 'Absichtlich offline' },
  { value: 'calibration', label: 'Kalibrierung' },
  { value: 'custom', label: 'Benutzerdefiniert' },
]

const SEVERITY_OPTIONS = [
  { value: '', label: 'Automatisch (Standard)' },
  { value: 'critical', label: 'Kritisch' },
  { value: 'warning', label: 'Warnung' },
  { value: 'info', label: 'Info' },
]

onMounted(async () => {
  await loadConfig()
})

async function loadConfig() {
  isLoading.value = true
  try {
    const response = await props.fetchFn(props.entityId)
    alertConfig.value = response.alert_config || {}
    syncFormFromConfig()
  } catch (e) {
    // Config might not exist yet — that's OK
    alertConfig.value = {}
  } finally {
    isLoading.value = false
  }
}

function syncFormFromConfig() {
  const cfg = alertConfig.value
  suppressionReason.value = (cfg.suppression_reason as string) || 'maintenance'
  suppressionNote.value = (cfg.suppression_note as string) || ''
  suppressionUntil.value = (cfg.suppression_until as string) || ''
  severityOverride.value = (cfg.severity_override as string) || ''

  const thresholds = cfg.custom_thresholds as Record<string, number | null> | undefined
  if (thresholds) {
    customWarningMin.value = thresholds.warning_min ?? null
    customWarningMax.value = thresholds.warning_max ?? null
    customCriticalMin.value = thresholds.critical_min ?? null
    customCriticalMax.value = thresholds.critical_max ?? null
  }
}

async function saveConfig() {
  isSaving.value = true
  try {
    const update: AlertConfigUpdate = {
      alerts_enabled: alertsEnabled.value,
    }

    if (!alertsEnabled.value) {
      update.suppression_reason = suppressionReason.value
      update.suppression_note = suppressionNote.value || undefined
      update.suppression_until = suppressionUntil.value || null
    }

    // Custom thresholds (only if any value set)
    if (
      customWarningMin.value != null ||
      customWarningMax.value != null ||
      customCriticalMin.value != null ||
      customCriticalMax.value != null
    ) {
      update.custom_thresholds = {
        warning_min: customWarningMin.value,
        warning_max: customWarningMax.value,
        critical_min: customCriticalMin.value,
        critical_max: customCriticalMax.value,
      }
    }

    // Severity override
    update.severity_override = severityOverride.value || null

    const response = await props.updateFn(props.entityId, update)
    alertConfig.value = response.alert_config || {}
    syncFormFromConfig()
    success('Alert-Konfiguration gespeichert')
  } catch (e) {
    error(e instanceof Error ? e.message : 'Fehler beim Speichern')
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <div class="alert-config">
    <!-- Loading state -->
    <div v-if="isLoading" class="alert-config__loading">
      Lade Konfiguration...
    </div>

    <template v-else>
      <!-- AUT-255: Suppression-Banner (sensor + device cascade) -->
      <div v-if="suppression.isActive" class="alert-config__suppression-banner">
        <BellOff class="alert-config__suppression-icon" aria-hidden="true" />
        <div class="alert-config__suppression-body">
          <span class="alert-config__suppression-title">
            Alerts unterdrückt
            <template v-if="suppression.source === 'device' || suppression.source === 'both'">
              (vom Gerät vererbt)
            </template>
          </span>
          <span
            v-if="suppression.deviceReason && (suppression.source === 'device' || suppression.source === 'both')"
            class="alert-config__suppression-reason"
          >
            Grund: {{ formatSuppressionReason(suppression.deviceReason) }}
          </span>
          <span v-if="suppression.effectiveUntil" class="alert-config__suppression-until">
            Reaktivierung: {{ formatDateTime(suppression.effectiveUntil) }}
          </span>
        </div>
      </div>

      <!-- Master Toggle -->
      <div class="alert-config__toggle-row">
        <div class="alert-config__toggle-info">
          <component
            :is="alertsEnabled ? Bell : BellOff"
            class="w-4 h-4"
            :class="alertsEnabled ? 'text-success' : 'text-warning'"
          />
          <span class="alert-config__toggle-label">
            {{ alertsEnabled ? 'Benachrichtigungen aktiv' : 'Benachrichtigungen unterdrückt' }}
          </span>
        </div>
        <label class="alert-config__switch">
          <input
            type="checkbox"
            :checked="alertsEnabled"
            @change="alertsEnabled = ($event.target as HTMLInputElement).checked"
          />
          <span class="alert-config__switch-slider" />
        </label>
      </div>

      <!-- Suppression Details (only when disabled) -->
      <div v-if="!alertsEnabled" class="alert-config__suppression">
        <div class="alert-config__field">
          <label class="alert-config__label">
            <Shield class="w-3.5 h-3.5" />
            Grund
          </label>
          <select v-model="suppressionReason" class="alert-config__input">
            <option
              v-for="reason in SUPPRESSION_REASONS"
              :key="reason.value"
              :value="reason.value"
            >
              {{ reason.label }}
            </option>
          </select>
        </div>

        <div class="alert-config__field">
          <label class="alert-config__label">Notiz (optional)</label>
          <input
            v-model="suppressionNote"
            class="alert-config__input"
            placeholder="z.B. Wartung bis Freitag"
          />
        </div>

        <div class="alert-config__field">
          <label class="alert-config__label">
            <Clock class="w-3.5 h-3.5" />
            Automatisch reaktivieren
          </label>
          <input
            v-model="suppressionUntil"
            type="datetime-local"
            class="alert-config__input"
          />
          <span class="alert-config__hint">
            Leer lassen für manuelle Reaktivierung
          </span>
        </div>
      </div>

      <!-- Override-Schwellen: Nur für Alert-Regeln. Überschreiben die Haupt-Schwellen aus SensorConfigPanel
           für diesen Alert. Haupt-Schwellen: SensorConfigPanel → Grundeinstellungen/Sensor-Schwellwerte (Basis). -->
      <div class="alert-config__section">
        <h4 class="alert-config__section-title">Schwellen-Override für Alerts</h4>
        <span class="alert-config__hint">Überschreiben die Sensor-Basisschwellen nur für Alert-Regeln</span>

        <div class="alert-config__thresholds">
          <div class="alert-config__threshold-row">
            <div class="alert-config__threshold-field">
              <label class="alert-config__label alert-config__label--warning">Warn Min</label>
              <input
                v-model.number="customWarningMin"
                type="number"
                step="any"
                class="alert-config__input alert-config__input--small"
                placeholder="—"
              />
            </div>
            <div class="alert-config__threshold-field">
              <label class="alert-config__label alert-config__label--warning">Warn Max</label>
              <input
                v-model.number="customWarningMax"
                type="number"
                step="any"
                class="alert-config__input alert-config__input--small"
                placeholder="—"
              />
            </div>
          </div>
          <div class="alert-config__threshold-row">
            <div class="alert-config__threshold-field">
              <label class="alert-config__label alert-config__label--critical">Kritisch Min</label>
              <input
                v-model.number="customCriticalMin"
                type="number"
                step="any"
                class="alert-config__input alert-config__input--small"
                placeholder="—"
              />
            </div>
            <div class="alert-config__threshold-field">
              <label class="alert-config__label alert-config__label--critical">Kritisch Max</label>
              <input
                v-model.number="customCriticalMax"
                type="number"
                step="any"
                class="alert-config__input alert-config__input--small"
                placeholder="—"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Severity Override -->
      <div class="alert-config__field">
        <label class="alert-config__label">Severity Override</label>
        <select v-model="severityOverride" class="alert-config__input">
          <option
            v-for="opt in SEVERITY_OPTIONS"
            :key="opt.value"
            :value="opt.value"
          >
            {{ opt.label }}
          </option>
        </select>
        <span class="alert-config__hint">
          Erzwingt diese Stufe für alle Alerts dieses Sensors
        </span>
      </div>

      <!-- Save Button -->
      <button
        class="alert-config__save"
        :disabled="isSaving"
        @click="saveConfig"
      >
        {{ isSaving ? 'Speichern...' : 'Alert-Konfiguration speichern' }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.alert-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.alert-config__loading {
  color: var(--color-text-muted);
  font-size: var(--text-sm);
  padding: var(--space-4) 0;
  text-align: center;
}

/* AUT-255: Suppression-Banner */
.alert-config__suppression-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-warning) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 25%, transparent);
  margin-bottom: var(--space-3);
}

.alert-config__suppression-icon {
  width: 14px;
  height: 14px;
  color: var(--color-warning);
  flex-shrink: 0;
  margin-top: 1px;
}

.alert-config__suppression-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.alert-config__suppression-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-warning);
}

.alert-config__suppression-reason,
.alert-config__suppression-until {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.alert-config__toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.alert-config__toggle-info {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.alert-config__toggle-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

/* Toggle switch */
.alert-config__switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
}

.alert-config__switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.alert-config__switch-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background-color: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  transition: var(--transition-fast);
}

.alert-config__switch-slider::before {
  content: '';
  position: absolute;
  height: 14px;
  width: 14px;
  left: 2px;
  bottom: 2px;
  background-color: var(--color-text-muted);
  border-radius: 50%;
  transition: var(--transition-fast);
}

.alert-config__switch input:checked + .alert-config__switch-slider {
  background-color: var(--color-success);
  border-color: var(--color-success);
}

.alert-config__switch input:checked + .alert-config__switch-slider::before {
  transform: translateX(16px);
  background-color: white;
}

/* Suppression section */
.alert-config__suppression {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  background: rgba(251, 191, 36, 0.05);
  border: 1px solid rgba(251, 191, 36, 0.15);
  border-radius: var(--radius-sm);
}

/* Fields */
.alert-config__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.alert-config__label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.alert-config__label--warning {
  color: var(--color-warning);
}

.alert-config__label--critical {
  color: var(--color-error);
}

.alert-config__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  transition: border-color var(--transition-fast);
}

.alert-config__input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.alert-config__input--small {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-family: var(--font-mono);
}

.alert-config__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Sections */
.alert-config__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.alert-config__section-title {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

/* Thresholds grid */
.alert-config__thresholds {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.alert-config__threshold-row {
  display: flex;
  gap: var(--space-3);
}

.alert-config__threshold-field {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

/* Save button */
.alert-config__save {
  padding: var(--space-2) var(--space-4);
  background: var(--color-accent);
  color: white;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: opacity var(--transition-fast);
}

.alert-config__save:hover {
  opacity: 0.9;
}

.alert-config__save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
