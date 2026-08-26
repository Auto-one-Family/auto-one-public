<script setup lang="ts">
/**
 * ActuatorCard — Unified actuator card for config and monitor views
 *
 * Config mode: Name, type, ESP-ID, GPIO, state badge, toggle, settings hint (B1-Werkstatt)
 * Monitor mode: Lagekarte + Schalten ohne Confirm (AUT-1513 A), PWM, linked rules,
 *               last execution. Config öffnet nicht von dieser Karte.
 */
import { computed, ref, watch, onUnmounted } from 'vue'
import {
  Power, ChevronRight, WifiOff, Loader2, CheckCircle,
  ToggleRight, Waves, GitBranch, Fan, Flame, Lightbulb, Cog, Activity,
} from 'lucide-vue-next'
import { isMockEspId } from '@/composables/useZoneGrouping'
import type { ActuatorWithContext } from '@/composables/useZoneGrouping'
import type { LogicRule, ExecutionHistoryItem } from '@/types/logic'
import { getRuleReadableText } from '@/composables/useRuleReadableText'
import { formatRelativeTime, ZONE_STALE_THRESHOLD_MS } from '@/utils/formatters'
import StatusBadge from '@/components/base/StatusBadge.vue'
import { getActuatorTypeInfo } from '@/utils/labels'
import { getSensorLabel, getSensorUnit } from '@/utils/sensorDefaults'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { useToast } from '@/composables/useToast'
import { actuatorsApi } from '@/api/actuators'
import { actuatorDutyToDisplayPercent } from '@/utils/eventTransformer'

const ACTUATOR_COMMAND_TIMEOUT_MS = 15_000

interface Props {
  actuator: ActuatorWithContext
  mode: 'monitor' | 'config'
  dataMode?: 'Live' | 'Hybrid' | 'Snapshot'
  showSnapshotWarning?: boolean
  linkedRules?: LogicRule[]
  lastExecution?: ExecutionHistoryItem | null
}

const props = withDefaults(defineProps<Props>(), {
  dataMode: 'Hybrid',
  showSnapshotWarning: false,
})

const emit = defineEmits<{
  configure: [actuator: ActuatorWithContext]
  toggle: [espId: string, gpio: number, currentState: boolean]
  // AUT-995 Feld 6: one-shot dose — parent sends ON with the given auto-off duration (seconds).
  'dose-now': [espId: string, gpio: number, durationSeconds: number]
}>()

const displayName = computed(() =>
  (() => {
    const name = typeof props.actuator.name === 'string' ? props.actuator.name.trim() : ''
    if (name.length > 0) return name
    const typeLabel = getActuatorTypeInfo(props.actuator.actuator_type, props.actuator.hardware_type).label
    return `${typeLabel} GPIO ${props.actuator.gpio}`
  })()
)

const stateLabel = computed(() => {
  if (isEspOffline.value) return 'ESP offline'
  return props.actuator.state ? 'Ein' : 'Aus'
})

// Scope badge (T13-R3 WP4): only show for non-default scopes with DB config
const scopeBadge = computed(() => {
  const scope = props.actuator.device_scope
  if (!scope || scope === 'zone_local') return null
  if (scope === 'multi_zone') return { text: 'Multi-Zone', cls: 'actuator-card__scope-badge--multi-zone' }
  if (scope === 'mobile') return { text: 'Mobil', cls: 'actuator-card__scope-badge--mobile' }
  return null
})

const scopeTooltip = computed(() => {
  if (scopeBadge.value?.text !== 'Multi-Zone') return ''
  const zones = props.actuator.assigned_zones
  if (!zones?.length) return ''
  return `Bedient: ${zones.join(', ')}`
})

const sourceBadge = computed(() => {
  if (isMockEspId(props.actuator.esp_id ?? '')) {
    return { text: 'Mock', cls: 'actuator-card__source-badge--mock' }
  }
  return { text: 'Real', cls: 'actuator-card__source-badge--real' }
})

// 6.2-A: ESP-Offline indicator (parity with SensorCard)
const isEspOffline = computed(() =>
  !!props.actuator.esp_state && props.actuator.esp_state !== 'OPERATIONAL'
)

// 6.2-B: Stale detection — ESP heartbeat older than threshold
const isStale = computed(() => {
  const lastSeen = props.actuator.last_seen
  if (!lastSeen) return false
  return Date.now() - new Date(lastSeen).getTime() > ZONE_STALE_THRESHOLD_MS
})

// 6.2-C: Type-specific icon via shared getActuatorTypeInfo (same source as ActuatorSatellite)
// hardware_type carries the ESP32 logical type (relay/pump/valve) for correct icon lookup.
const actuatorIcon = computed(() => {
  const iconName = getActuatorTypeInfo(props.actuator.actuator_type, props.actuator.hardware_type).icon.toLowerCase()
  if (iconName.includes('toggle')) return ToggleRight
  if (iconName.includes('waves') || iconName.includes('pump')) return Waves
  if (iconName.includes('branch') || iconName.includes('valve')) return GitBranch
  if (iconName.includes('fan')) return Fan
  if (iconName.includes('flame') || iconName.includes('heater')) return Flame
  if (iconName.includes('lightbulb') || iconName.includes('light')) return Lightbulb
  if (iconName.includes('cog') || iconName.includes('motor')) return Cog
  if (iconName.includes('activity')) return Activity
  return Power
})

// Fix-U: Actuator-level stale detection (separate from ESP-stale)
const isActuatorStale = computed(() => {
  const lastCmd = props.actuator.last_command_at
  if (!lastCmd) return true
  const ts = new Date(lastCmd).getTime()
  if (ts < new Date('2000-01-01').getTime()) return true
  return false
})

const lastCommandAge = computed(() => {
  const lastCmd = props.actuator.last_command_at
  if (!lastCmd) return 'Nie bestaetigt'
  const ts = new Date(lastCmd).getTime()
  if (ts < new Date('2000-01-01').getTime()) return 'Nie bestaetigt'
  return formatRelativeTime(lastCmd)
})

// Phase 2.3: "Bedient Subzone(n)" — fallback "Zone-weit"
const servedSubzoneLabel = computed(() => {
  const name = props.actuator.subzone_name ?? ''
  const id = props.actuator.subzone_id ?? ''
  if (typeof name === 'string' && name.trim()) return name
  if (typeof id === 'string' && id.trim()) return id
  return 'Zone-weit'
})

// Monitor-mode: show max 2 rules
const displayedRules = computed(() => (props.linkedRules ?? []).slice(0, 2))

// Monitor-mode: PWM percentage badge — only for pwm/fan types (not relay/pump/valve/digital)
const pwmPercent = computed(() => {
  if (props.actuator.actuator_type !== 'pwm' && props.actuator.actuator_type !== 'fan') return null
  const val = props.actuator.pwm_value
  if (val != null && val > 0) return `${actuatorDutyToDisplayPercent(val)}%`
  return null
})

function toRoundedValue(value: unknown): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '?'
  return value.toLocaleString('de-DE', { maximumFractionDigits: 1 })
}

function parseTriggerPayload(raw: string): Record<string, unknown> | null {
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{') || !trimmed.endsWith('}')) return null
  try {
    return JSON.parse(trimmed) as Record<string, unknown>
  } catch {
    // Backend liefert teils Python-ähnliche Dict-Strings mit einfachen Quotes.
    try {
      const normalized = trimmed.replace(/'/g, '"')
      return JSON.parse(normalized) as Record<string, unknown>
    } catch {
      return null
    }
  }
}

function formatTriggerReason(reason: string | null | undefined): string {
  const text = typeof reason === 'string' ? reason.trim() : ''
  if (!text) return 'Ausloeser wurde nicht uebermittelt'

  const parsed = parseTriggerPayload(text)
  if (parsed) {
    const sensorType = typeof parsed.sensor_type === 'string' ? parsed.sensor_type : null
    const value = parsed.value
    const zoneId = typeof parsed.zone_id === 'string' ? parsed.zone_id : null
    const subzoneId = typeof parsed.subzone_id === 'string' ? parsed.subzone_id : null
    const sourceEsp = typeof parsed.esp_id === 'string' ? parsed.esp_id : null

    if (sensorType) {
      const label = getSensorLabel(sensorType)
      const unit = getSensorUnit(sensorType)
      const parts = [`${label}: ${toRoundedValue(value)} ${unit}`]
      if (zoneId) parts.push(`Zone ${zoneId}`)
      if (subzoneId) parts.push(`Subzone ${subzoneId}`)
      if (sourceEsp) parts.push(sourceEsp)
      return parts.join(' · ')
    }

    if (sourceEsp) return `Ausgeloest durch ${sourceEsp}`
    return 'Ausloeserdetails liegen vor, konnten aber nicht lesbar aufbereitet werden'
  }

  // Fallback: plain "sensor_type = value" format (e.g. "sht31_humidity = 52.5")
  const plainMatch = /^(\w+)\s*=\s*(.+)$/.exec(text)
  if (plainMatch) {
    const sensorType = plainMatch[1]
    const numValue = parseFloat(plainMatch[2].trim())
    if (!isNaN(numValue)) {
      const label = getSensorLabel(sensorType)
      const unit = getSensorUnit(sensorType)
      return `${label}: ${toRoundedValue(numValue)} ${unit}`
    }
  }

  return text.length > 120 ? `${text.slice(0, 117)}...` : text
}

const lastExecutionReasonLabel = computed(() => formatTriggerReason(props.lastExecution?.trigger_reason))

const dataModeHint = computed(() => {
  if (isEspOffline.value) return 'Kein Live-Status: ESP ist aktuell offline.'
  if (isStale.value || isActuatorStale.value) return 'Letzter bekannter Zustand; Rueckmeldung ist veraltet.'
  if (props.dataMode === 'Snapshot') return 'Snapshot: Anzeige basiert auf dem letzten bekannten Stand.'
  return ''
})

const acknowledgementLabel = computed(() => {
  if (isEspOffline.value || isStale.value || isActuatorStale.value) {
    return 'letzter Stand'
  }
  return 'bestätigt'
})

const actuatorStore = useActuatorStore()
const { warning: toastWarning, error: toastError } = useToast()

const commandIsPending = computed(() =>
  actuatorStore.isActuatorCommandPending(props.actuator.esp_id, props.actuator.gpio)
)

const commandToggleBlocked = computed(() => commandIsPending.value)

const commandIntent = computed(() =>
  actuatorStore.getActuatorIntent(props.actuator.esp_id, props.actuator.gpio)
)

const showWarnBadge = ref(false)
let pendingTimeoutHandle: ReturnType<typeof setTimeout> | null = null

watch(commandIsPending, (pending) => {
  if (pending) {
    pendingTimeoutHandle = setTimeout(() => {
      if (commandIsPending.value) {
        showWarnBadge.value = true
        toastWarning('Keine Bestätigung erhalten — Aktor-Befehl möglicherweise nicht ausgeführt.')
      }
    }, ACTUATOR_COMMAND_TIMEOUT_MS)
  } else {
    if (pendingTimeoutHandle !== null) {
      clearTimeout(pendingTimeoutHandle)
      pendingTimeoutHandle = null
    }
    if (commandIntent.value?.terminalOutcome === 'success') {
      showWarnBadge.value = false
    }
  }
})

onUnmounted(() => {
  if (pendingTimeoutHandle !== null) clearTimeout(pendingTimeoutHandle)
})

function handleClick() {
  if (props.mode === 'config') {
    emit('configure', props.actuator)
  }
}

function handleToggle(event: Event) {
  event.stopPropagation()
  emit('toggle', props.actuator.esp_id, props.actuator.gpio, props.actuator.state)
}

// =============================================================================
// AUT-995 Feld 6: "Jetzt dosieren" (pumps only)
// =============================================================================
const isPump = computed(() => {
  const t = (props.actuator.actuator_type || '').toLowerCase()
  const h = (props.actuator.hardware_type || '').toLowerCase()
  return t === 'pump' || h === 'pump'
})

const doseFormOpen = ref(false)
const doseMl = ref(10)
const doseBusy = ref(false)

function toggleDoseForm(event: Event) {
  event.stopPropagation()
  doseFormOpen.value = !doseFormOpen.value
}

async function confirmDose(event: Event) {
  event.stopPropagation()
  const ml = Number(doseMl.value)
  if (!ml || ml <= 0) {
    toastError('Bitte eine Dosis groesser als 0 ml eingeben.')
    return
  }
  doseBusy.value = true
  try {
    // H-2: flow_rate_ml_s is NOT on the live store actuator object — fetch the config for the ml → duration conversion.
    const cfg = await actuatorsApi.get(props.actuator.esp_id, props.actuator.gpio)
    const flowRate = cfg?.flow_rate_ml_s ?? null
    if (!flowRate || flowRate <= 0) {
      toastError('Pumpe nicht kalibriert (flow_rate_ml_s fehlt) — Dosierung nicht moeglich.')
      return
    }
    const durationSeconds = Math.max(1, Math.ceil(ml / flowRate))
    emit('dose-now', props.actuator.esp_id, props.actuator.gpio, durationSeconds)
    doseFormOpen.value = false
  } catch {
    toastError('Kalibrierung konnte nicht geladen werden.')
  } finally {
    doseBusy.value = false
  }
}
</script>

<template>
  <div
    :class="[
      'actuator-card',
      `actuator-card--${mode}`,
      {
        'actuator-card--emergency': actuator.emergency_stopped,
        'actuator-card--offline': isEspOffline,
        'actuator-card--stale': isStale && !isEspOffline,
      },
    ]"
    @click="handleClick"
  >
    <div class="actuator-card__header">
      <div
        :class="[
          'actuator-card__icon',
          actuator.state ? 'actuator-card__icon--on' : 'actuator-card__icon--off',
          { 'actuator-card__icon--pending': commandIsPending },
        ]"
      >
        <Loader2 v-if="commandIsPending" class="w-5 h-5 actuator-card__pending-spinner" />
        <component v-else :is="actuatorIcon" :class="['w-5 h-5', actuator.state ? 'text-green-400' : 'text-dark-400']" />
      </div>
      <div class="actuator-card__info">
        <div class="actuator-card__title-row">
          <p class="actuator-card__name">{{ displayName }}</p>
          <span :class="[
            'actuator-card__state-primary',
            isEspOffline ? 'actuator-card__state-primary--offline' :
              props.actuator.state ? 'actuator-card__state-primary--on' : 'actuator-card__state-primary--off'
          ]">
            {{ stateLabel }}
          </span>
        </div>
        <p class="actuator-card__meta">{{ actuator.esp_id }} · {{ getActuatorTypeInfo(actuator.actuator_type, actuator.hardware_type).label }}</p>
        <p class="actuator-card__served">
          <span class="actuator-card__served-label">Subzone:</span>
          <span class="actuator-card__served-value">{{ servedSubzoneLabel }}</span>
        </p>
      </div>
      <ChevronRight
        v-if="mode === 'config'"
        class="w-4 h-4 text-dark-500 flex-shrink-0"
      />
    </div>
    <div class="actuator-card__body">
      <div class="actuator-card__badges">
        <span v-if="sourceBadge.text !== 'Real'" :class="['actuator-card__source-badge', sourceBadge.cls]">
          {{ sourceBadge.text }}
        </span>
        <span v-if="mode === 'monitor' && pwmPercent" class="actuator-card__pwm-badge">
          {{ pwmPercent }}
        </span>
        <span v-if="actuator.emergency_stopped" class="badge badge-danger">
          Not-Stopp
        </span>
        <span v-if="commandIsPending" class="actuator-card__badge actuator-card__badge--pending">
          Wird ausgeführt...
        </span>
        <StatusBadge v-if="showWarnBadge && !commandIsPending" level="warning" label-override="Keine Bestätigung" />
        <span v-if="scopeBadge" :class="['actuator-card__scope-badge', scopeBadge.cls]" :title="scopeTooltip">{{ scopeBadge.text }}</span>
        <span v-if="isEspOffline" class="actuator-card__badge actuator-card__badge--offline">
          <WifiOff :size="12" /> ESP offline
        </span>
        <span
          v-if="(isActuatorStale || isStale) && lastCommandAge"
          class="actuator-card__badge actuator-card__badge--stale"
        >
          {{ lastCommandAge }}
        </span>
        <span
          v-if="!commandIsPending && !showWarnBadge"
          class="actuator-card__badge"
          :class="isEspOffline || isStale || isActuatorStale ? 'actuator-card__badge--stale' : 'actuator-card__badge--confirmed'"
          :title="acknowledgementLabel"
          :aria-label="acknowledgementLabel"
        >
          <CheckCircle v-if="!(isEspOffline || isStale || isActuatorStale)" class="w-3 h-3" />
          <template v-else>{{ acknowledgementLabel }}</template>
        </span>
      </div>
      <span v-if="mode === 'monitor' && actuator.actuator_type === 'pwm' && !pwmPercent" class="actuator-card__pwm">
        PWM: 0%
      </span>
      <!-- AUT-1513 A: Toggle auch auf Monitor L2 — Nutzung, kein Confirm, kein B1-Config -->
      <button
        class="btn-secondary btn-sm flex-shrink-0 touch-target"
        :disabled="actuator.emergency_stopped || isEspOffline || isStale || commandToggleBlocked"
        :title="commandIsPending ? 'Befehl wird ausgeführt...' : isEspOffline ? 'ESP ist offline' : isStale ? 'Status veraltet' : ''"
        :aria-label="actuator.state ? 'Ausschalten' : 'Einschalten'"
        @click="handleToggle"
      >
        {{ commandIsPending ? 'Wird ausgeführt...' : (actuator.state ? 'Ausschalten' : 'Einschalten') }}
      </button>

      <!-- Feld 6 (AUT-995): Jetzt dosieren — nur Pumpen, nur Monitor-Kontext (Live-Steuerung). ON mit auto-off duration (dose_ml / flow_rate_ml_s). -->
      <template v-if="mode === 'monitor' && isPump && !actuator.emergency_stopped && !isEspOffline && !isStale">
        <button
          class="btn-secondary btn-sm flex-shrink-0 touch-target"
          :disabled="commandToggleBlocked || doseBusy"
          title="Einmalige Dosis mit automatischer Abschaltung"
          @click="toggleDoseForm"
        >
          Jetzt dosieren
        </button>
        <div v-if="doseFormOpen" class="flex items-center gap-2 mt-2" @click.stop>
          <input
            v-model.number="doseMl"
            type="number"
            min="0"
            step="0.1"
            class="w-20 px-2 py-1 rounded bg-dark-800 border border-dark-600 text-dark-50 text-sm touch-target"
            aria-label="Dosis in Milliliter"
          />
          <span class="text-sm text-dark-400">ml</span>
          <button
            class="btn-primary btn-sm touch-target"
            :disabled="doseBusy || !doseMl || doseMl <= 0"
            @click="confirmDose"
          >
            {{ doseBusy ? '…' : 'Dosieren' }}
          </button>
        </div>
      </template>
    </div>
    <div
      v-if="mode === 'monitor' && showSnapshotWarning"
      class="actuator-card__snapshot-warning"
    >
      Status ggf. veraltet
    </div>

    <!-- Monitor-mode: Linked rules -->
    <div v-if="mode === 'monitor' && linkedRules?.length" class="actuator-card__rules">
      <div v-for="rule in displayedRules" :key="rule.id" class="actuator-card__rule-item">
        <span
          class="actuator-card__rule-dot"
          :class="{
            'is-active': rule.enabled,
            'is-error': rule.last_execution_success === false,
          }"
        />
        <span class="actuator-card__rule-name">{{ rule.name }}</span>
        <span class="actuator-card__rule-condition">{{ getRuleReadableText(rule) }}</span>
      </div>
      <router-link
        v-if="linkedRules.length > 2"
        to="/logic"
        class="actuator-card__rules-more"
      >
        +{{ linkedRules.length - 2 }} weitere
      </router-link>
    </div>

    <!-- Monitor-mode: Last execution -->
    <div v-if="mode === 'monitor' && lastExecution" class="actuator-card__last-execution">
      Zuletzt: {{ formatRelativeTime(lastExecution.triggered_at) }}
      <span
        v-if="lastExecutionReasonLabel"
        class="actuator-card__execution-reason"
        :title="lastExecutionReasonLabel"
      >
        ({{ lastExecutionReasonLabel }})
      </span>
    </div>
    <div v-if="mode === 'monitor' && dataModeHint" class="actuator-card__freshness-hint">
      {{ dataModeHint }}
    </div>
  </div>
</template>

<style scoped>
.actuator-card {
  cursor: pointer;
  transition: all var(--transition-fast);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  padding: var(--space-3);
}

.actuator-card:hover {
  border-color: var(--color-border-hover, rgba(255, 255, 255, 0.12));
}

.actuator-card--emergency {
  border-color: rgba(248, 113, 113, 0.3);
}

.actuator-card--offline {
  border-left: 3px solid var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 6%, var(--color-bg-tertiary));
}

.actuator-card--stale {
  opacity: 0.7;
  border-left: 3px solid var(--color-warning);
}

.actuator-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-2);
}

.actuator-card__icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.actuator-card__icon--on {
  background: color-mix(in srgb, var(--color-success) 16%, transparent);
}

.actuator-card__icon--off {
  background: var(--color-bg-quaternary, rgba(255, 255, 255, 0.04));
}

.actuator-card__info {
  flex: 1;
  min-width: 0;
}

.actuator-card__name {
  font-weight: 500;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actuator-card__title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.actuator-card__state-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 38px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  font-size: var(--text-xxs);
  font-weight: 700;
  letter-spacing: 0.02em;
}

.actuator-card__state-primary--on {
  color: var(--color-success);
}

.actuator-card__state-primary--off {
  color: var(--color-text-muted);
}

.actuator-card__state-primary--offline {
  color: var(--color-warning);
}

.actuator-card__meta {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actuator-card__served {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-top: var(--space-1);
  display: flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 0;
}

.actuator-card__served-label {
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.actuator-card__served-value {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 140px;
}

.actuator-card__body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.actuator-card__badges {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.actuator-card__pwm {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.actuator-card__pwm-badge {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  background: var(--color-bg-quaternary, rgba(255, 255, 255, 0.04));
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.actuator-card__mode-badge {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  padding: 1px 6px;
  font-size: var(--text-xxs);
  line-height: 1.1;
  color: var(--color-text-secondary);
}

.actuator-card__mode-badge--live {
  color: var(--color-success);
}

.actuator-card__mode-badge--hybrid {
  color: var(--color-info);
}

.actuator-card__mode-badge--snapshot {
  color: var(--color-warning);
}

.actuator-card__snapshot-warning {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-warning);
}

/* Rules section */
.actuator-card__rules {
  border-top: 1px solid var(--glass-border);
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.actuator-card__rule-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  min-width: 0;
}

.actuator-card__rule-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-muted);
  flex-shrink: 0;
}

.actuator-card__rule-dot.is-active {
  background: var(--color-status-good);
}

.actuator-card__rule-dot.is-error {
  background: var(--color-status-alarm);
}

.actuator-card__rule-name {
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 1;
  min-width: 0;
}

.actuator-card__rule-condition {
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex-shrink: 2;
  min-width: 0;
}

.actuator-card__rules-more {
  font-size: var(--text-xs);
  color: var(--color-iridescent-2);
  text-decoration: none;
}

.actuator-card__rules-more:hover {
  text-decoration: underline;
}

/* Last execution */
.actuator-card__last-execution {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.actuator-card__execution-reason {
  color: var(--color-text-secondary);
}

.actuator-card__freshness-hint {
  margin-top: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* Scope badges (T13-R3 WP4) */
.actuator-card__scope-badge {
  display: inline-flex;
  align-items: center;
  font-size: var(--text-xxs);
  font-weight: 500;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  white-space: nowrap;
  cursor: default;
}

.actuator-card__scope-badge--multi-zone {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.actuator-card__scope-badge--mobile {
  background: var(--color-accent-bg);
  color: var(--color-accent-bright);
}

.actuator-card__source-badge {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-sm);
  padding: 1px 6px;
  font-size: var(--text-xxs);
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: 0.03em;
}

.actuator-card__source-badge--mock {
  color: var(--color-mock);
  background: var(--color-mock-bg);
}

.actuator-card__source-badge--real {
  color: var(--color-real);
  background: color-mix(in srgb, var(--color-real) 16%, transparent);
}

/* Offline badge */
.actuator-card__badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xxs);
  font-weight: 500;
  padding: 1px 6px;
  border-radius: var(--radius-xs);
  white-space: nowrap;
}

.actuator-card__badge--offline {
  color: var(--color-text-muted);
}

.actuator-card__badge--stale {
  color: var(--color-warning);
}

.actuator-card__badge--confirmed {
  color: var(--color-success);
}

.actuator-card__badge--pending {
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
  border-radius: var(--radius-xs);
}

.actuator-card__badge--warn {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border-radius: var(--radius-xs);
}

.actuator-card__icon--pending {
  background: color-mix(in srgb, var(--color-accent) 12%, transparent);
}

.actuator-card__pending-spinner {
  color: var(--color-accent);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
