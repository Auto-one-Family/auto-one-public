<script setup lang="ts">
/**
 * DeviceAlertConfigSection — Device-Level Alert Configuration (ISA-18.2)
 *
 * Master toggle: Enable/disable alerts for this ESP device.
 * propagate_to_children: When true, suppression applies to all child sensors/actuators.
 * When disabled: suppression reason, optional note, optional auto-re-enable date.
 *
 * Used inside ESPSettingsSheet. No custom_thresholds or severity_override
 * (those are sensor/actuator-level only).
 */
import { ref, computed, onMounted, watch } from 'vue'
import { BellOff, Bell, Clock, Shield, Layers } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { espApi, type DeviceAlertConfigUpdate } from '@/api/esp'

interface Props {
  espId: string
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

const propagateToChildren = computed({
  get: () => alertConfig.value.propagate_to_children === true,
  set: (val: boolean) => {
    alertConfig.value.propagate_to_children = val
  },
})

const suppressionReason = ref<string>('maintenance')
const suppressionNote = ref<string>('')
const suppressionUntil = ref<string>('')

const SUPPRESSION_REASONS = [
  { value: 'maintenance', label: 'Wartung' },
  { value: 'intentionally_offline', label: 'Absichtlich offline' },
  { value: 'calibration', label: 'Kalibrierung' },
  { value: 'custom', label: 'Benutzerdefiniert' },
]

const loadConfig = async () => {
  if (!props.espId) return
  isLoading.value = true
  try {
    const response = await espApi.getAlertConfig(props.espId)
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
}

async function saveConfig() {
  if (!props.espId || isSaving.value) return

  isSaving.value = true
  try {
    const update: DeviceAlertConfigUpdate = {
      alerts_enabled: alertsEnabled.value,
      propagate_to_children: propagateToChildren.value,
    }

    if (!alertsEnabled.value) {
      update.suppression_reason = suppressionReason.value
      update.suppression_note = suppressionNote.value || undefined
      update.suppression_until = suppressionUntil.value || null
    }

    const response = await espApi.updateAlertConfig(props.espId, update)
    alertConfig.value = response.alert_config || {}
    syncFormFromConfig()
    success('Alert-Konfiguration gespeichert')
  } catch (e) {
    error(e instanceof Error ? e.message : 'Fehler beim Speichern')
  } finally {
    isSaving.value = false
  }
}

onMounted(() => {
  loadConfig()
})

watch(
  () => props.espId,
  (newId, oldId) => {
    if (newId && newId !== oldId) {
      loadConfig()
    }
  }
)
</script>

<template>
  <div class="alert-config">
    <!-- Loading state -->
    <div v-if="isLoading" class="alert-config__loading">
      Lade Konfiguration...
    </div>

    <template v-else>
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

      <!-- propagate_to_children (Device-Level only) -->
      <div class="alert-config__propagate-row">
        <div class="alert-config__propagate-info">
          <Layers class="w-4 h-4 text-muted" />
          <div>
            <span class="alert-config__propagate-label">
              Unterdrückung an Kind-Sensoren/-Aktoren weitergeben
            </span>
            <span class="alert-config__hint">
              Wenn aktiv, werden Alerts für alle Sensoren und Aktoren dieses Geräts unterdrückt (z.B. bei Wartung).
            </span>
          </div>
        </div>
        <label class="alert-config__switch">
          <input
            type="checkbox"
            :checked="propagateToChildren"
            @change="propagateToChildren = ($event.target as HTMLInputElement).checked"
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

/* propagate row */
.alert-config__propagate-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.alert-config__propagate-info {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  flex: 1;
  min-width: 0;
}

.alert-config__propagate-info > div {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.alert-config__propagate-label {
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
  flex-shrink: 0;
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

.alert-config__hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
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

.text-muted { color: var(--color-text-muted); }
.text-success { color: var(--color-success); }
.text-warning { color: var(--color-warning); }
</style>
