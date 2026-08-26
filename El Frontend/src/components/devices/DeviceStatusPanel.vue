<script setup lang="ts">
/**
 * DeviceStatusPanel — Read-only live status + manual control dock (AUT-1128 S3)
 *
 * Docked next to the config tabs inside ConfigWizardModal (right column). Hosts
 * everything that must act immediately regardless of the config Speichern-button:
 * manual ON/OFF/PWM control, Emergency-Stop, linked-rules read view and live
 * safety state — moved 1:1 out of ActuatorConfigPanel (Steuerung, Verknuepfte
 * Regeln, Safety-Status sections), not rebuilt. Sensor mode mirrors the same
 * shell with a live measurement instead of ON/OFF control.
 */
import { ref, computed, onMounted, watch } from 'vue'
import { Power, AlertOctagon, Clock, Zap, Wifi, WifiOff, Link2 } from 'lucide-vue-next'
import { actuatorsApi } from '@/api/actuators'
import { sensorsApi } from '@/api/sensors'
import { espApi } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'
import LinkedRulesSection from './LinkedRulesSection.vue'
import LiveDataPreview from '@/components/esp/LiveDataPreview.vue'
import { formatRelativeTime } from '@/utils/formatters'
import { formatDoseRoleLabel } from '@/utils/doseRoleDisplay'
import { getActuatorLabel } from '@/utils/actuatorDefaults'
import type { MockActuator, MockSensor } from '@/types'
import { actuatorDutyToDisplayPercent, pwmPercentToNormalizedCommand } from '@/utils/eventTransformer'

interface Props {
  espId: string
  gpio: number
  mode: 'sensor' | 'actuator'
  actuatorType?: string
  sensorType?: string
  unit?: string
  /** Bumped by the parent (ConfigWizardModal) on `saved` to re-pull persisted mirror values. */
  refreshToken?: number
}

const props = withDefaults(defineProps<Props>(), {
  actuatorType: undefined,
  sensorType: undefined,
  unit: '',
  refreshToken: 0,
})

const toast = useToast()
const espStore = useEspStore()

const isMock = computed(() => espApi.isMockEsp(props.espId))

const contextDevice = computed(() =>
  espStore.devices.find(d => espStore.getDeviceId(d) === props.espId),
)
const contextSensor = computed(() => {
  const normalizedType = String(props.sensorType || '').toLowerCase()
  return ((contextDevice.value?.sensors ?? []) as MockSensor[]).find((sensor) =>
    Number(sensor.gpio) === props.gpio
    && String(sensor.sensor_type ?? '').toLowerCase() === normalizedType,
  ) ?? null
})
const deviceName = computed(() => {
  const named = (contextDevice.value as { name?: string | null } | undefined)?.name?.trim()
  return named || ''
})
/**
 * AUT-1523: Aktor-Name steht einmal im Config-Input. Status-Kopf zeigt den
 * Typ (Pumpe/Ventil/…), nicht den Eigennamen und nicht GPIO als Identität.
 */
const primaryName = computed(() => {
  if (props.mode === 'actuator') {
    return getActuatorLabel(props.actuatorType ?? '')
  }
  return deviceName.value
})
/** AUT-1523: Aktor-Meta = nur espId. AUT-1522: Sensor-Identität ist nicht GPIO. */
const statusMeta = computed(() => {
  if (props.mode === 'actuator') return props.espId
  return ''
})
const isDeviceOnline = computed(() =>
  (contextDevice.value as any)?.status === 'online' || (contextDevice.value as any)?.connected === true,
)

// =============================================================================
// Actuator: live state + manual control — moved 1:1 from ActuatorConfigPanel
// (Steuerung-Section) so there is exactly ONE place rendering the ON/OFF/PWM
// control (AUT-1128 Anti-Doppel-Impl).
// =============================================================================
const actuatorTypeNormalized = computed(() => (props.actuatorType ?? '').toLowerCase())
const isPWM = computed(() => actuatorTypeNormalized.value === 'pwm')

const liveActuator = computed<MockActuator | null>(() => {
  if (props.mode !== 'actuator') return null
  const actuators = (contextDevice.value?.actuators as MockActuator[]) || []
  return actuators.find(a => a.gpio === props.gpio) ?? null
})

const pwmDutyPercent = computed(() => {
  const act = liveActuator.value
  if (!act || typeof act.pwm_value !== 'number') return 0
  return actuatorDutyToDisplayPercent(act.pwm_value)
})

/** Live slider override while dragging (before @change commit). */
const sliderDragPercent = ref<number | null>(null)
const displayPwmPercent = computed(() =>
  sliderDragPercent.value !== null ? sliderDragPercent.value : pwmDutyPercent.value,
)

const isOn = computed(() => {
  if (isPWM.value) return pwmDutyPercent.value > 0 || !!liveActuator.value?.state
  return !!liveActuator.value?.state
})
const isEmergencyStopped = computed(() => !!liveActuator.value?.emergency_stopped)

const commandLoading = ref(false)

async function toggleActuator() {
  commandLoading.value = true
  try {
    const command = isOn.value ? 'OFF' : 'ON'
    await espStore.sendActuatorCommand(props.espId, props.gpio, command)
  } catch {
    // Toast handled by store
  } finally {
    commandLoading.value = false
  }
}

async function setPwmValue(percent: number) {
  commandLoading.value = true
  sliderDragPercent.value = percent
  try {
    await espStore.sendActuatorCommand(
      props.espId,
      props.gpio,
      'PWM',
      pwmPercentToNormalizedCommand(percent),
    )
  } catch {
    sliderDragPercent.value = null
  } finally {
    commandLoading.value = false
    sliderDragPercent.value = null
  }
}

async function emergencyStop() {
  commandLoading.value = true
  try {
    if (isMock.value) {
      await espStore.emergencyStop(props.espId, 'Manueller Stopp ueber Status-Panel')
    } else {
      await actuatorsApi.emergencyStop({
        esp_id: props.espId,
        gpio: props.gpio,
        reason: 'Manueller Stopp ueber Status-Panel',
      })
    }
    toast.warning(`${isMock.value ? '[Simulation] ' : ''}Emergency-Stop ausgelöst`)
  } catch {
    toast.error('Emergency-Stop fehlgeschlagen')
  } finally {
    commandLoading.value = false
  }
}

// =============================================================================
// Spiegel effektiv gespeicherter Kernwerte (Zone/Subzone/Kalibrierung/Limits)
// Independent read of the last-saved config — decoupled from the unsaved
// edit-buffer in ActuatorConfigPanel/SensorConfigPanel, refreshed on `saved`
// via refreshToken.
// =============================================================================
const mirrorLoading = ref(true)
const mirrorSubzoneId = ref<string | null>(null)
const mirrorFlowRateMls = ref<number | null>(null)
const mirrorConcentration = ref<number | null>(null)
const mirrorDoseRole = ref<string | null>(null)

/** AUT-1359: Rolle nur aus gespeichertem dose_role (zentraler Helper). */
const doseRoleLabel = computed(() => formatDoseRoleLabel(mirrorDoseRole.value))
const mirrorMaxRuntime = ref<number | null>(null)
const mirrorMinPause = ref<number | null>(null)
const mirrorPowerLimit = ref<number>(100)
const mirrorCalibration = ref<Record<string, unknown> | null>(null)

const zoneLabel = computed(() =>
  (contextDevice.value as any)?.zone_name || (contextDevice.value as any)?.zone_id || 'keine Zone',
)

/** Mirrors SensorConfigPanel.calibrationStatusSummary — same derivation, independent read. */
const calibrationStatusLabel = computed(() => {
  const storeCalibration = contextSensor.value?.calibration
  const data = (storeCalibration && typeof storeCalibration === 'object')
    ? storeCalibration
    : mirrorCalibration.value
  if (!data || typeof data !== 'object') return 'Nicht kalibriert'
  const derived = (data.derived as Record<string, unknown> | undefined) ?? data
  const calibratedAt = (data.metadata as Record<string, unknown> | undefined)?.calibrated_at
    ?? data.calibrated_at
    ?? derived.calibrated_at
  if (calibratedAt) return `Kalibriert ${formatRelativeTime(String(calibratedAt))}`
  if (derived.cell_factor != null) return 'Kalibriert'
  return 'Nicht kalibriert'
})

async function loadMirror() {
  mirrorLoading.value = true
  try {
    if (props.mode === 'actuator') {
      const config = await actuatorsApi.get(props.espId, props.gpio)
      if (config) {
        const c = config as unknown as Record<string, unknown>
        const meta = (c.metadata as Record<string, unknown>) || {}
        mirrorSubzoneId.value = (c.subzone_id as string) ?? null
        mirrorFlowRateMls.value = (c.flow_rate_ml_s as number | null) ?? null
        mirrorConcentration.value = (c.concentration as number | null) ?? null
        mirrorDoseRole.value = (c.dose_role as string | null) ?? null
        mirrorMaxRuntime.value = (c.max_runtime_seconds as number) ?? null
        mirrorMinPause.value = (c.cooldown_seconds as number) ?? null
        mirrorPowerLimit.value = (meta.duty_max as number) ?? 100
      }
    } else {
      const config = await sensorsApi.get(props.espId, props.gpio, props.sensorType)
      if (config) {
        const c = config as unknown as Record<string, unknown>
        mirrorSubzoneId.value = (c.subzone_id as string) ?? null
        mirrorCalibration.value = (c.calibration as Record<string, unknown> | null) ?? null
      }
    }
  } catch {
    // No persisted config yet — mirror stays empty; not a hard error for a read-only panel.
  } finally {
    mirrorLoading.value = false
  }
}

onMounted(loadMirror)
watch(() => [props.espId, props.gpio, props.mode, props.sensorType, props.refreshToken], loadMirror)

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  if (seconds === 0) return 'unbegrenzt'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}
</script>

<template>
  <div class="status-panel">
    <!-- Header: Typ (Aktor) / Gerätename (Sensor) · ESP · Online. GPIO nicht als Aktor-Identität. -->
    <div class="status-panel__header">
      <span v-if="primaryName" class="status-panel__name">{{ primaryName }}</span>
      <span v-if="statusMeta" class="status-panel__meta">{{ statusMeta }}</span>
      <span
        class="status-panel__online"
        :class="isDeviceOnline ? 'status-panel__online--on' : 'status-panel__online--off'"
      >
        <Wifi v-if="isDeviceOnline" class="w-3.5 h-3.5" />
        <WifiOff v-else class="w-3.5 h-3.5" />
        {{ isDeviceOnline ? 'Online' : 'Offline' }}
      </span>
    </div>

    <section v-if="isMock" class="status-panel__simulation-badge">
      [Simulation] Mock-ESP
    </section>

    <!-- ═══ ACTUATOR: manuelle Steuerung (moved from ActuatorConfigPanel) ═══ -->
    <section v-if="mode === 'actuator'" class="status-panel__section">
      <h3 class="status-panel__section-title">
        <Power class="w-4 h-4" />
        <span>Steuerung</span>
      </h3>

      <div class="status-panel__state-box" :class="isOn ? 'status-panel__state-box--on' : 'status-panel__state-box--off'">
        <div class="status-panel__state-indicator">
          <span class="status-panel__state-dot" />
          <span class="status-panel__state-text">
            {{ isPWM ? (displayPwmPercent > 0 ? `${displayPwmPercent}%` : 'AUS') : (isOn ? 'AN' : 'AUS') }}
          </span>
        </div>

        <button
          v-if="!isPWM"
          type="button"
          class="status-panel__toggle-btn touch-target hardware-onoff-control"
          :class="{
            'status-panel__toggle-btn--on': isOn,
            'status-panel__toggle-btn--emergency': isEmergencyStopped,
          }"
          data-testid="status-panel-power-toggle"
          :disabled="commandLoading || isEmergencyStopped"
          :aria-label="isOn ? 'Ausschalten' : 'Einschalten'"
          @click="toggleActuator"
        >
          {{ isEmergencyStopped ? 'Not-Stopp aktiv' : commandLoading ? '...' : isOn ? 'Ausschalten' : 'Einschalten' }}
        </button>
      </div>

      <div v-if="isPWM" class="status-panel__pwm-control">
        <label class="status-panel__label">PWM-Wert: {{ displayPwmPercent }}%</label>
        <input
          type="range"
          min="0"
          :max="mirrorPowerLimit"
          :value="displayPwmPercent"
          class="status-panel__pwm-slider"
          :disabled="isEmergencyStopped || commandLoading"
          @input="sliderDragPercent = Number(($event.target as HTMLInputElement).value)"
          @change="setPwmValue(Number(($event.target as HTMLInputElement).value))"
        />
        <div class="status-panel__pwm-labels">
          <span>0%</span>
          <span>{{ mirrorPowerLimit }}%</span>
        </div>
      </div>

      <!-- Emergency Stop (moved from Safety-Status accordion) -->
      <button
        class="status-panel__emergency"
        :disabled="commandLoading"
        @click="emergencyStop"
      >
        <AlertOctagon class="w-4 h-4" />
        NOTFALL-STOPP
      </button>
    </section>

    <!-- ═══ SENSOR: Live-Messwert (moved from SensorConfigPanel Live-Vorschau) ═══ -->
    <section v-else class="status-panel__section">
      <h3 class="status-panel__section-title">
        <Zap class="w-4 h-4" />
        <span>Messwert</span>
      </h3>
      <LiveDataPreview :esp-id="espId" :gpio="gpio" :sensor-type="sensorType" :unit="unit" />
    </section>

    <!-- ═══ Verknuepfte Regeln (read-only, moved from Config-Panel) ═══ -->
    <section class="status-panel__section">
      <h3 class="status-panel__section-title">
        <Link2 class="w-4 h-4" />
        <span>{{ mode === 'actuator' ? 'Steuert das gerade' : 'Verknüpfte Regeln' }}</span>
      </h3>
      <LinkedRulesSection :esp-id="espId" :gpio="gpio" :device-type="mode" />
    </section>

    <!-- ═══ ACTUATOR: Safety-Live (moved from Safety-Status accordion) ═══ -->
    <section v-if="mode === 'actuator'" class="status-panel__section">
      <h3 class="status-panel__section-title">
        <Clock class="w-4 h-4" />
        <span>Safety-Live</span>
      </h3>
      <div class="status-panel__safety-info">
        <div class="status-panel__safety-row">
          <Clock class="w-3.5 h-3.5" />
          <span>Letzter Befehl: {{ liveActuator?.last_command_at || '&mdash;' }}</span>
        </div>
        <div class="status-panel__safety-row">
          <Zap class="w-3.5 h-3.5" />
          <span>Zustand: {{ isOn ? 'Aktiv' : 'Inaktiv' }}</span>
        </div>
        <div v-if="isEmergencyStopped" class="status-panel__safety-row status-panel__safety-row--alert">
          <AlertOctagon class="w-3.5 h-3.5" />
          <span>Not-Stopp aktiv — Steuerung gesperrt</span>
        </div>
        <!-- TODO(AUT-1132 Paket B): config_status-Ack (Sicherheitslimit/Mindest-Pause vom Geraet
             bestaetigt/abgelehnt) dockt hier als weitere Safety-Live-Zeile an. -->
      </div>
    </section>

    <!-- ═══ Spiegel effektiv gespeicherter Kernwerte ═══ -->
    <section class="status-panel__section">
      <h3 class="status-panel__section-title">Gespeicherter Stand</h3>
      <div v-if="mirrorLoading" class="status-panel__mirror-loading">Lade…</div>
      <div v-else class="status-panel__mirror">
        <div class="status-panel__mirror-row">
          <span class="status-panel__mirror-label">Zone</span>
          <span class="status-panel__mirror-value">{{ zoneLabel }}</span>
        </div>
        <div class="status-panel__mirror-row">
          <span class="status-panel__mirror-label">Subzone</span>
          <span class="status-panel__mirror-value">{{ mirrorSubzoneId || 'keine' }}</span>
        </div>
        <template v-if="mode === 'actuator'">
          <div v-if="mirrorFlowRateMls != null" class="status-panel__mirror-row">
            <span class="status-panel__mirror-label">Foerderrate</span>
            <span class="status-panel__mirror-value">{{ mirrorFlowRateMls }} ml/s</span>
          </div>
          <div v-if="mirrorConcentration != null" class="status-panel__mirror-row">
            <span class="status-panel__mirror-label">Konzentration</span>
            <span class="status-panel__mirror-value">{{ mirrorConcentration }} µS/ml·L</span>
          </div>
          <div v-if="doseRoleLabel" class="status-panel__mirror-row">
            <span class="status-panel__mirror-label">Rezept-Rolle</span>
            <span class="status-panel__mirror-value">{{ doseRoleLabel }}</span>
          </div>
          <div class="status-panel__mirror-row">
            <span class="status-panel__mirror-label">Sicherheitslimit</span>
            <span class="status-panel__mirror-value">{{ formatDuration(mirrorMaxRuntime) }}</span>
          </div>
          <div v-if="mirrorMinPause != null" class="status-panel__mirror-row">
            <span class="status-panel__mirror-label">Mindest-Pause</span>
            <span class="status-panel__mirror-value">{{ formatDuration(mirrorMinPause) }}</span>
          </div>
        </template>
        <div v-else class="status-panel__mirror-row">
          <span class="status-panel__mirror-label">Kalibrierung</span>
          <span class="status-panel__mirror-value">{{ calibrationStatusLabel }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.status-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.status-panel__header {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.status-panel__name {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--color-text-primary);
}

.status-panel__meta {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
}

.status-panel__online {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  width: fit-content;
  margin-top: var(--space-1);
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xxs);
  font-weight: 600;
  text-transform: uppercase;
}

.status-panel__online--on {
  color: var(--color-status-good);
  background: rgba(34, 197, 94, 0.1);
}

.status-panel__online--off {
  color: var(--color-text-muted);
  background: var(--color-bg-tertiary);
}

.status-panel__simulation-badge {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(167, 139, 250, 0.35);
  background: rgba(167, 139, 250, 0.1);
  color: var(--color-mock);
  font-size: var(--text-xs);
  font-weight: 600;
}

.status-panel__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--glass-border);
}

.status-panel__section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.status-panel__section-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

/* Control */
.status-panel__state-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
}

.status-panel__state-box--on {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.3);
}

.status-panel__state-box--off {
  background: var(--color-bg-tertiary);
}

.status-panel__state-indicator {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.status-panel__state-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-status-offline);
}

.status-panel__state-box--on .status-panel__state-dot {
  background: var(--color-status-good);
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
}

.status-panel__state-text {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text-primary);
}

.status-panel__toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-2) var(--space-4);
  min-height: var(--touch-min-target);
  min-width: var(--touch-min-target);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid var(--color-status-good);
  background: transparent;
  color: var(--color-status-good);
}

.status-panel__toggle-btn:hover { background: rgba(34, 197, 94, 0.1); }

.status-panel__toggle-btn--on {
  border-color: var(--color-status-alarm);
  color: var(--color-status-alarm);
}

.status-panel__toggle-btn--on:hover { background: rgba(239, 68, 68, 0.1); }
.status-panel__toggle-btn--emergency {
  border-color: var(--color-status-alarm);
  color: var(--color-status-alarm);
  opacity: 0.7;
}
.status-panel__toggle-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.status-panel__pwm-control {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.status-panel__pwm-slider {
  width: 100%;
  accent-color: var(--color-accent);
}

.status-panel__pwm-labels {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.status-panel__label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.status-panel__emergency {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-4);
  background: rgba(239, 68, 68, 0.1);
  border: 2px solid var(--color-status-alarm);
  border-radius: var(--radius-md);
  color: var(--color-status-alarm);
  font-size: var(--text-sm);
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.status-panel__emergency:hover {
  background: rgba(239, 68, 68, 0.2);
  box-shadow: 0 0 16px rgba(239, 68, 68, 0.3);
}

.status-panel__emergency:disabled { opacity: 0.5; cursor: not-allowed; }

/* Safety */
.status-panel__safety-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.status-panel__safety-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.status-panel__safety-row--alert {
  color: var(--color-status-alarm);
  font-weight: 600;
}

/* Mirror */
.status-panel__mirror-loading {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.status-panel__mirror {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.status-panel__mirror-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: var(--text-xs);
}

.status-panel__mirror-label {
  color: var(--color-text-muted);
}

.status-panel__mirror-value {
  color: var(--color-text-primary);
  font-weight: 500;
  font-family: var(--font-mono);
}
</style>
