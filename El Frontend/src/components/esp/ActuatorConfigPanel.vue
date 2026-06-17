<script setup lang="ts">
/**
 * ActuatorConfigPanel — Three-Zone Actuator Configuration
 *
 * Zone 1 (Basic, always visible): Control (ON/OFF/PWM), Name, Enabled, Subzone
 * Zone 2 (Accordion): Type-specific settings (Pump/Valve/PWM/Relay)
 * Zone 3 (Accordion - Expert): Safety status, Emergency Stop
 *
 * Used inside ESPSettingsSheet as SlideOver panel (HardwareView only, Route /hardware).
 */

import { ref, computed, onMounted, watch } from 'vue'
import { Save, Power, AlertOctagon, AlertTriangle, Info, Zap, Clock, Shield, Settings, Trash2, FileText, ExternalLink } from 'lucide-vue-next'
import { actuatorsApi } from '@/api/actuators'
import { espApi } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'
import { AccordionSection } from '@/shared/design/primitives'
import { useUiStore } from '@/shared/stores/ui.store'
import { useGpioStatus } from '@/composables/useGpioStatus'
import { supportsAuxGpio, ACTUATOR_TYPE_CONFIG } from '@/utils/actuatorDefaults'
import { getGpioConfig } from '@/utils/gpioConfig'
import type { MockActuator } from '@/types'
import AlertConfigSection from '@/components/devices/AlertConfigSection.vue'
import RuntimeMaintenanceSection from '@/components/devices/RuntimeMaintenanceSection.vue'
import DeviceMetadataSection from '@/components/devices/DeviceMetadataSection.vue'
import LinkedRulesSection from '@/components/devices/LinkedRulesSection.vue'
import ActuatorActionTimeline from '@/components/devices/ActuatorActionTimeline.vue'
import SubzoneAssignmentSection from '@/components/devices/SubzoneAssignmentSection.vue'
import SettingsBreadcrumb from '@/components/settings/SettingsBreadcrumb.vue'
import { deviceContextApi } from '@/api/device-context'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { useLogicStore } from '@/shared/stores/logic.store'
import { normalizeSubzoneId } from '@/utils/subzoneHelpers'
import { createLogger } from '@/utils/logger'
import type { DeviceScope } from '@/types'
import type { DeviceMetadata } from '@/types/device-metadata'
import { parseDeviceMetadata, mergeDeviceMetadata } from '@/types/device-metadata'
import PendingConfigBanner from './PendingConfigBanner.vue'

const configLogger = createLogger('ActuatorConfigPanel')

interface Props {
  espId: string
  gpio: number
  actuatorType: string
  showMetadata?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  showMetadata: true,
})

const emit = defineEmits<{
  deleted: []
  saved: []
  /** AUT-251: User wants to edit zone — open ESP-Settings-Sheet for current device */
  'open-esp-settings': [payload: { espId: string }]
}>()

/** AUT-251: Emit request to open ESP-Settings-Sheet (zone is edited there). */
function requestOpenEspSettings() {
  emit('open-esp-settings', { espId: props.espId })
}

const toast = useToast()
const espStore = useEspStore()
const actuatorStore = useActuatorStore()
const uiStore = useUiStore()
const zoneStore = useZoneStore()
const logicStore = useLogicStore()

// =============================================================================
// State
// =============================================================================
const loading = ref(true)
const saving = ref(false)
const actuatorDbId = ref<string | null>(null)
const commandLoading = ref(false)

const commandInCooldown = computed(() =>
  actuatorStore.isActuatorCommandInCooldown(props.espId, props.gpio)
)
const lastConfigSubjectId = ref<string | null>(null)
const lastConfigCorrelationId = ref<string | null>(null)

// Basic fields
const name = ref('')
const description = ref('')
const enabled = ref(true)

// Device Scope (T13-R3 WP4) — UI auf Aktor-Ebene entfernt (AUT-251),
// Werte werden weiterhin geladen/gespeichert um Backend-Kompatibilitaet zu wahren.
const localScope = ref<DeviceScope>('zone_local')
const localAssignedZones = ref<string[]>([])
const activeZoneId = ref<string | null>(null)

// Subzone
const subzoneId = ref<string | null>(null)

// Type-specific fields
const maxRuntime = ref(3600) // seconds
const minPause = ref(60) // seconds
const maxOpenTime = ref(3600) // seconds
const isNormalClosed = ref(true)
const pwmFrequency = ref(5000) // Hz
const powerLimit = ref(100) // %
const switchDelay = ref(50) // ms
/** aux_gpio for Valve (H-Bridge direction pin). 255 = nicht verwendet */
const auxGpio = ref<number>(255)

// Device Metadata
const metadata = ref<DeviceMetadata>({})

// =============================================================================
// Computed
// =============================================================================
const isMock = computed(() => espApi.isMockEsp(props.espId))
const actuatorTypeNormalized = computed(() => props.actuatorType.toLowerCase())
const isPump = computed(() => actuatorTypeNormalized.value === 'pump')
const isValve = computed(() => actuatorTypeNormalized.value === 'valve')
const isPWM = computed(() => actuatorTypeNormalized.value === 'pwm')
const isRelay = computed(() =>
  ['relay', 'digital', 'binary', 'switch'].includes(actuatorTypeNormalized.value),
)

/** Live actuator state from store */
const liveActuator = computed<MockActuator | null>(() => {
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
  const actuators = (device?.actuators as MockActuator[]) || []
  return actuators.find(a => a.gpio === props.gpio) ?? null
})

const isOn = computed(() => !!liveActuator.value?.state)
const isEmergencyStopped = computed(() => !!liveActuator.value?.emergency_stopped)
const currentPwmValue = ref(0)

/** Storage key prefix for accordion persistence */
const accordionKey = computed(() => `actuator-${props.espId}-${props.gpio}`)

// =============================================================================
// AUT-252: Aktor-Datenblatt (read-only, aus ACTUATOR_TYPE_CONFIG)
// =============================================================================

const actuatorTypeConfig = computed(() => {
  const normalized = actuatorTypeNormalized.value
  if (normalized in ACTUATOR_TYPE_CONFIG) {
    return ACTUATOR_TYPE_CONFIG[normalized]
  }
  if (isRelay.value) {
    return ACTUATOR_TYPE_CONFIG.relay
  }
  return undefined
})

function getDefaultMaxRuntimeSeconds(): number {
  return isPump.value ? 3600 : 0
}

const hasActuatorDatasheet = computed<boolean>(() => {
  const cfg = actuatorTypeConfig.value
  if (!cfg) return false
  return Boolean(
    cfg.manufacturer
    || cfg.maxFlow
    || cfg.nominalVoltage
    || cfg.maintenanceHours != null
    || cfg.datasheetUrl,
  )
})

// Context-Anker fuer SettingsBreadcrumb (AUT-251)
const contextDevice = computed(() =>
  espStore.devices.find(d => espStore.getDeviceId(d) === props.espId),
)
const zoneContextLabel = computed(() =>
  (contextDevice.value as any)?.zone_name
  || (contextDevice.value as any)?.zone_id
  || 'nicht zugewiesen',
)

// Verknuepfte Regeln (AUT-256): prominente Anzeige + Konflikt-Warnung
const linkedRules = computed(() => logicStore.getRulesForActuator(props.espId, props.gpio))
const activeRuleCount = computed(() => linkedRules.value.filter(r => r.enabled).length)
const hasActiveRules = computed(() => activeRuleCount.value > 0)

/** GPIO options for aux_gpio (Valve): "Nicht verwendet" + available pins excluding main gpio */
const { allPinStatuses } = useGpioStatus(computed(() => props.espId))
const auxGpioOptions = computed(() => {
  const meta = allPinStatuses.value
  const pins =
    meta.length > 0
      ? meta.filter(p => p.available && p.gpio !== props.gpio).map(p => p.gpio)
      : getGpioConfig('ESP32_WROOM')
          .filter(p => p.category !== 'avoid')
          .map(p => p.gpio)
          .filter(g => g !== props.gpio)
  const set = new Set(pins)
  if (auxGpio.value !== 255 && auxGpio.value !== props.gpio) {
    set.add(auxGpio.value)
  }
  const sorted = [...set].sort((a, b) => a - b)
  return [
    { value: 255, label: 'Nicht verwendet' },
    ...sorted.map(g => ({ value: g, label: `GPIO ${g}` })),
  ]
})

// =============================================================================
// Load existing config
// =============================================================================
onMounted(async () => {
  const isMock = espApi.isMockEsp(props.espId)

  // Load actuator config from server (real devices only)
  if (!isMock) {
    try {
      const config = await actuatorsApi.get(props.espId, props.gpio)
      if (config) {
        const c = config as unknown as Record<string, unknown>
        const meta = (c.metadata as Record<string, unknown>) || {}

        actuatorDbId.value = c.id ? String(c.id) : null
        name.value = (c.name as string) || ''
        description.value = (c.description as string) || ''
        enabled.value = c.enabled !== false

        // Block A: Backend→Frontend field mapping (max_runtime_seconds, cooldown_seconds, metadata)
        maxRuntime.value = (c.max_runtime_seconds as number) ?? getDefaultMaxRuntimeSeconds()
        minPause.value = (c.cooldown_seconds as number) ?? 60
        maxOpenTime.value =
          (c.max_runtime_seconds as number) ??
          (meta.max_open_time as number) ??
          (meta.max_open_time_seconds as number) ??
          getDefaultMaxRuntimeSeconds()
        isNormalClosed.value =
          meta.inverted_logic !== undefined
            ? !!meta.inverted_logic
            : (c.active_high as boolean) !== true
        pwmFrequency.value =
          (c.pwm_frequency as number) ?? (meta.pwm_frequency as number) ?? 5000
        powerLimit.value = (meta.duty_max as number) ?? 100
        switchDelay.value =
          (meta.switch_delay_ms as number) ?? (meta.switch_delay as number) ?? 50
        auxGpio.value =
          (meta.aux_gpio as number) ?? 255

        if (c.subzone_id) {
          subzoneId.value = c.subzone_id as string
        }

        // Device metadata (manufacturer, model, etc.)
        metadata.value = parseDeviceMetadata(meta)

        // Device Scope (T13-R3 WP4)
        localScope.value = (c.device_scope as DeviceScope) ?? 'zone_local'
        localAssignedZones.value = (c.assigned_zones as string[]) ?? []
      }
    } catch {
      // No existing config
    }
  } else if (liveActuator.value) {
    // Mock device: read config from store
    const act = liveActuator.value as any
    name.value = act.name || ''
    description.value = act.description || ''
    enabled.value = act.enabled !== false
  }
  loading.value = false

  // Load existing subzone from device store (more reliable than config)
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
  if (device?.subzone_id && !subzoneId.value) {
    subzoneId.value = device.subzone_id
  }

  // Load active zone context (T13-R3 WP4)
  if (actuatorDbId.value && localScope.value !== 'zone_local') {
    try {
      const ctx = await deviceContextApi.getContext('actuator', actuatorDbId.value)
      activeZoneId.value = ctx.active_zone_id ?? null
    } catch {
      // No context set yet
    }
  }

  // Ensure zone entities are loaded for the scope section
  if (zoneStore.zoneEntities.length === 0) {
    zoneStore.fetchZoneEntities().catch(() => {})
  }

  // AUT-256: Stelle sicher, dass Regeln geladen sind (fuer linkedRules / Konflikt-Warnung)
  if (logicStore.rules.length === 0) {
    logicStore.fetchRules().catch(() => {})
  }
})

// Watch live PWM value
watch(liveActuator, (act) => {
  if (act && typeof act.pwm_value === 'number') {
    currentPwmValue.value = act.pwm_value
  }
}, { immediate: true, deep: true })

// =============================================================================
// Commands
// =============================================================================
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

async function setPwmValue(value: number) {
  commandLoading.value = true
  try {
    await espStore.sendActuatorCommand(props.espId, props.gpio, 'PWM', value)
    currentPwmValue.value = value
  } catch {
    // Toast handled by store
  } finally {
    commandLoading.value = false
  }
}

async function emergencyStop() {
  commandLoading.value = true
  try {
    if (isMock.value) {
      // Mock: use store emergency stop (debug API)
      await espStore.emergencyStop(props.espId, 'Manueller Stopp ueber Konfigurations-Panel')
    } else {
      // Real: use actuators API
      await actuatorsApi.emergencyStop({
        esp_id: props.espId,
        gpio: props.gpio,
        reason: 'Manueller Stopp ueber Konfigurations-Panel',
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
// Delete
// =============================================================================
const deleting = ref(false)

async function confirmAndDelete() {
  const confirmed = await uiStore.confirm({
    title: 'Aktor entfernen',
    message: 'Der Aktor wird unwiderruflich aus diesem Gerät entfernt. Verknüpfte Automatisierungsregeln werden deaktiviert.',
    variant: 'danger',
    confirmText: 'Entfernen',
  })
  if (!confirmed) return

  deleting.value = true
  try {
    await actuatorsApi.delete(props.espId, props.gpio)
    if (isMock.value) {
      toast.success('[Simulation] Aktor entfernt', {
        dedupeKey: `actuator-delete:${props.espId}:${props.gpio}`,
      })
    } else {
      toast.info('Löschauftrag akzeptiert - warte auf Geräte-Rückmeldung', {
        dedupeKey: `actuator-delete:${props.espId}:${props.gpio}`,
      })
    }
    emit('deleted')
  } catch {
    toast.error('Aktor konnte nicht entfernt werden')
  } finally {
    deleting.value = false
  }
}

// =============================================================================
// Save
// =============================================================================
async function handleSave() {
  saving.value = true
  try {
    if (isMock.value) {
      // Mock: config lives in device_metadata, just show success
      // Name/description changes are cosmetic for mock devices
      toast.success('[Simulation] Aktor-Konfiguration gespeichert')
      emit('saved')
    } else {
      // Real: save to server via actuators API (Backend expects max_runtime_seconds, cooldown_seconds, metadata)
      const config: Record<string, unknown> = {
        esp_id: props.espId,
        gpio: props.gpio,
        actuator_type: props.actuatorType,
        name: name.value || null,
        description: description.value || null,
        enabled: enabled.value,
        subzone_id: normalizeSubzoneId(subzoneId.value),
      }

      // Device Scope (T13-R3 WP4)
      config.device_scope = localScope.value
      config.assigned_zones = localScope.value === 'zone_local' ? [] : localAssignedZones.value

      // Device metadata base (manufacturer, model, etc.)
      const meta: Record<string, unknown> = mergeDeviceMetadata(null, metadata.value)

      if (isPump.value) {
        config.max_runtime_seconds = maxRuntime.value
        config.cooldown_seconds = minPause.value
      }

      if (isValve.value) {
        config.max_runtime_seconds = maxOpenTime.value
        meta.inverted_logic = isNormalClosed.value
        meta.aux_gpio = auxGpio.value
      }

      if (isRelay.value) {
        config.max_runtime_seconds = maxRuntime.value
      }

      if (isPWM.value) {
        config.pwm_frequency = pwmFrequency.value
        meta.duty_max = powerLimit.value
      }

      if (isRelay.value) {
        meta.inverted_logic = isNormalClosed.value
        meta.switch_delay_ms = switchDelay.value
      }

      config.metadata = meta
      const result = await actuatorsApi.createOrUpdate(props.espId, props.gpio, config as any)
      const response = result as unknown as Record<string, unknown>
      const correlationId = typeof response.correlation_id === 'string' ? response.correlation_id : undefined
      const requestId = typeof response.request_id === 'string' ? response.request_id : undefined
      const handles = [correlationId ? `Korrelation: ${correlationId}` : '', requestId ? `Request-ID: ${requestId}` : '']
        .filter(Boolean)
        .join(' | ')
      const scope = `actuator:${props.gpio}:${props.actuatorType}`
      const summary = `Aktor-Konfiguration ${props.actuatorType} an GPIO ${props.gpio}`
      const subjectId = actuatorStore.registerConfigIntentFromRest({
        espId: props.espId,
        scope,
        correlationId,
        requestId,
        summary,
      })
      lastConfigSubjectId.value = subjectId
      lastConfigCorrelationId.value = correlationId ?? null
      toast.info(
        `Konfigurationsauftrag akzeptiert: ${summary}.${handles ? ` ${handles}` : ''}`,
        {
          dedupeKey: `config-accepted:${correlationId ?? requestId ?? `${props.espId}:${scope}`}`,
        },
      )
      const terminal = await actuatorStore.waitForConfigTerminal({
        subjectId,
        correlationId,
        timeoutMs: 65_000,
      })
      if (!terminal) {
        configLogger.info('config_pending_over_timeout: UI-Wartezeit abgelaufen', {
          subject_id: subjectId,
          correlation_id: correlationId,
        })
        toast.warning('Konfigurationsauftrag ausstehend: Noch keine Geräte-Rückmeldung. Status wird im Panel angezeigt.', {
          dedupeKey: `config-await-timeout:${correlationId ?? requestId ?? subjectId}`,
        })
        return
      }
      if (terminal.state === 'terminal_success') {
        lastConfigSubjectId.value = null
        lastConfigCorrelationId.value = null
        toast.success('Aktor-Konfiguration wurde vom Gerät bestätigt')
        emit('saved')
        return
      }
      if (terminal.state === 'terminal_timeout') {
        configLogger.info('config_pending_over_timeout: Store-Timeout erreicht', {
          subject_id: subjectId,
          correlation_id: correlationId,
        })
        toast.warning('Konfigurationsauftrag ausstehend: Gerät hat nicht innerhalb der Frist geantwortet.', {
          dedupeKey: `config-terminal-timeout:${correlationId ?? requestId ?? subjectId}`,
        })
        return
      }
      lastConfigSubjectId.value = null
      lastConfigCorrelationId.value = null
      toast.error('Konfiguration fehlgeschlagen. Details im Event-Monitor prüfen.', {
        persistent: true,
        dedupeKey: `config-terminal-failed:${correlationId ?? requestId ?? subjectId}`,
      })
      return
    }
  } catch (err) {
    const msg = (err as any)?.response?.data?.detail ?? 'Fehler beim Speichern'
    toast.error(msg)
  } finally {
    saving.value = false
  }
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return `${h}h ${m}m`
}
</script>

<template>
  <div class="actuator-config" :class="{ 'actuator-config--loading': loading }">
    <div v-if="loading" class="actuator-config__loading">Lade Konfiguration...</div>

    <template v-else>
      <!-- Settings-Kontextpfad: Zone -> Subzone -> ESP -> GPIO (AUT-251) -->
      <!-- Breadcrumb: Zone + ESP only (subzone/gpio visible as subtitle in modal title) -->
      <SettingsBreadcrumb
        :zone="zoneContextLabel"
        :esp-id="espId"
      />

      <section v-if="isMock" class="actuator-config__simulation-badge" aria-label="Simulation Hinweis">
        [Simulation] Mock-ESP - Aktionen werden simuliert.
      </section>
      <!-- ═══ ZONE 1: BASIC (Control + Identity) ═════════════════════════ -->

      <!-- Control Panel -->
      <section class="actuator-config__section actuator-config__section--control">
        <h3 class="actuator-config__section-title">
          <Power class="w-4 h-4" />
          <span>Steuerung</span>
          <!-- Konflikt-Warnung Pill (AUT-256): mehrere aktive Regeln steuern diesen Aktor -->
          <span v-if="activeRuleCount >= 2" class="actuator-config__conflict-pill">
            <AlertTriangle class="actuator-config__conflict-icon" />
            {{ activeRuleCount }} Regeln steuern diesen Aktor
          </span>
        </h3>

        <div class="actuator-config__state-box" :class="isOn ? 'actuator-config__state-box--on' : 'actuator-config__state-box--off'">
          <div class="actuator-config__state-indicator">
            <span class="actuator-config__state-dot" />
            <span class="actuator-config__state-text">{{ isOn ? 'AN' : 'AUS' }}</span>
          </div>

          <!-- Toggle for non-PWM -->
          <button
            v-if="!isPWM"
            class="actuator-config__toggle-btn"
            :class="{
              'actuator-config__toggle-btn--on': isOn,
              'actuator-config__toggle-btn--emergency': isEmergencyStopped,
            }"
            :disabled="commandLoading || commandInCooldown || isEmergencyStopped"
            :title="commandInCooldown ? 'Bitte kurz warten (min. 2s zwischen Befehlen)' : ''"
            @click="toggleActuator"
          >
            {{ isEmergencyStopped ? 'Not-Stopp aktiv' : commandLoading ? '...' : commandInCooldown ? 'Kurz warten...' : isOn ? 'Ausschalten' : 'Einschalten' }}
          </button>
        </div>

        <!-- AUT-256: Manuelle-Schaltung-Banner (nur wenn aktive Regeln vorhanden) -->
        <div v-if="hasActiveRules" class="actuator-config__manual-banner">
          <Info class="actuator-config__manual-banner-icon" />
          <span>Manuelle Schaltung gilt sofort und überschreibt alle aktiven Regeln — bis zur nächsten automatischen Regelauswertung.</span>
        </div>

        <!-- PWM Slider -->
        <div v-if="isPWM" class="actuator-config__pwm-control">
          <label class="actuator-config__label">PWM-Wert: {{ currentPwmValue }}%</label>
          <input
            type="range"
            min="0"
            :max="powerLimit"
            :value="currentPwmValue"
            class="actuator-config__pwm-slider"
            :disabled="isEmergencyStopped"
            @change="setPwmValue(Number(($event.target as HTMLInputElement).value))"
          />
          <div class="actuator-config__pwm-labels">
            <span>0%</span>
            <span>{{ powerLimit }}%</span>
          </div>
        </div>
      </section>

      <!-- ═══ AUT-256: Verknuepfte Regeln prominent (vor Grundeinstellungen) ═══ -->
      <!--
        AUT-256 Section A: ERSTES Akkordeon (expandiert default), enthaelt
        Rule-level Liste (Priority, Cooldown, Zeitfenster) + inline Warning-Pill
        bei 2+ aktiven Regeln. Header-Pill (Steuerung-Section) bleibt zusaetzlich
        als Sofort-Indikator sichtbar.

        AUT-256 Section C (Konflikt-Erklaerung):
        // TODO: AUT-114 Blocker — `conflict.arbitration` als dedizierter WebSocket-Event fehlt
        //       (existiert aktuell nur als Audit-Log-Eintrag in services/logic_engine.py).
        //       Sobald der Server den Event ueber NotificationRouter/WS broadcastet,
        //       hier eine ausfuehrliche Konflikt-Erklaerung (winner/loser-Regel, Mode,
        //       Resolution) anzeigen. Bis dahin verbleibt die statische Heuristik
        //       "N aktive Regeln steuern diesen Aktor" als Operator-Hinweis.
      -->
      <section class="actuator-config__section actuator-config__section--linked-rules">
        <h3 class="actuator-config__section-title">Verknuepfte Regeln</h3>
        <LinkedRulesSection
          :esp-id="espId"
          :gpio="gpio"
          device-type="actuator"
        />
      </section>

      <!-- ═══ AUT-256 Section D: Last-Action-Timeline (eingeklappt — Erstzugriff) ═══ -->
      <AccordionSection
        title="Letzte Schaltvorgaenge"
        :storage-key="`${accordionKey}-timeline`"
        :icon="Clock"
      >
        <ActuatorActionTimeline
          :esp-id="espId"
          :gpio="gpio"
          :limit="5"
        />
      </AccordionSection>

      <!-- Basic Fields (ausgeklappt — primaere Konfigurationsfelder) -->
      <AccordionSection
        title="Grundeinstellungen"
        :storage-key="`${accordionKey}-basic`"
        :icon="Settings"
        :default-open="true"
      >
        <!-- Zone: read-only, vom Geraet vererbt (Subzone wird unten als Dropdown gepflegt) — AUT-251 -->
        <!-- Zone gehoert zum Geraet, NICHT zum Aktor — "im Geraet aendern" oeffnet ESP-Settings -->
        <div class="actuator-config__zone-header">
          <span class="actuator-config__zone-label">Geraet:</span>
          <span class="actuator-config__zone-value">{{ contextDevice?.name || espId }}</span>
          <span class="actuator-config__zone-hint">(vom Geraet vererbt)</span>
        </div>
        <div class="actuator-config__zone-header">
          <span class="actuator-config__zone-label">Zone:</span>
          <span class="actuator-config__zone-value">{{ contextDevice?.zone_name || contextDevice?.zone_id || 'Keine Zone' }}</span>
          <button
            type="button"
            class="actuator-config__zone-link"
            aria-label="Zone im Geraet aendern"
            @click="requestOpenEspSettings"
          >
            im Geraet aendern
          </button>
        </div>

        <div class="actuator-config__field">
          <label class="actuator-config__label">Name</label>
          <input v-model="name" type="text" class="actuator-config__input" placeholder="z.B. Bewaesserungspumpe Zone A" />
        </div>

        <div class="actuator-config__field">
          <label class="actuator-config__label">Beschreibung</label>
          <input v-model="description" type="text" class="actuator-config__input" placeholder="Optional" />
        </div>

        <div class="actuator-config__field actuator-config__field--toggle">
          <label class="actuator-config__label">Aktiv</label>
          <button
            :class="['actuator-config__toggle', { 'actuator-config__toggle--on': enabled }]"
            @click="enabled = !enabled"
          >
            <span class="actuator-config__toggle-dot" />
          </button>
        </div>

        <!-- Subzone assignment (with create-new option) -->
        <div class="actuator-config__field">
          <SubzoneAssignmentSection
            v-model="subzoneId"
            :esp-id="espId"
            :gpio="gpio"
            :zone-id="espStore.devices.find(d => espStore.getDeviceId(d) === espId)?.zone_id ?? null"
          />
        </div>
      </AccordionSection>

      <!-- ═══ ZONE 2: ADVANCED (Accordion) ════════════════════════════════ -->

      <!-- Type-Specific Settings -->
      <AccordionSection
        title="Typ-Einstellungen"
        :storage-key="`${accordionKey}-type`"
        :icon="Settings"
      >
        <div class="actuator-config__type-badge-row">
          Typ:
          <span class="actuator-config__type-badge">{{ actuatorType }}</span>
        </div>

        <div class="actuator-config__field">
          <label class="actuator-config__label">GPIO Pin</label>
          <select class="actuator-config__select" disabled>
            <option :value="gpio">GPIO {{ gpio }}</option>
          </select>
          <span class="actuator-config__helper">Pin kann nach Erstellung nicht geaendert werden</span>
        </div>

        <!-- Pump -->
        <template v-if="isPump">
          <div class="actuator-config__field">
            <label class="actuator-config__label">Geraete-Sicherheitslimit</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="maxRuntime" type="number" min="0" class="actuator-config__input" />
              <span class="actuator-config__unit">Sek. ({{ formatDuration(maxRuntime) }})</span>
            </div>
            <span class="actuator-config__helper">Absolute Sicherheitsgrenze — greift unabhaengig von Regeln, auch bei manuellen Befehlen. Bei Ueberschreitung: Emergency Stop (Aktor gesperrt bis manueller Reset). 0 = unbegrenzt. Standard: 3600 Sek.</span>
          </div>
          <div class="actuator-config__field">
            <label class="actuator-config__label">Mindest-Pause zwischen Laeufen</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="minPause" type="number" min="0" class="actuator-config__input" />
              <span class="actuator-config__unit">Sek.</span>
            </div>
          </div>
        </template>

        <!-- Valve -->
        <template v-else-if="isValve">
          <div class="actuator-config__field">
            <label class="actuator-config__label">Geraete-Sicherheitslimit</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="maxOpenTime" type="number" min="1" class="actuator-config__input" />
              <span class="actuator-config__unit">Sek. ({{ formatDuration(maxOpenTime) }})</span>
            </div>
            <span class="actuator-config__helper">Absolute Sicherheitsgrenze — greift unabhaengig von Regeln, auch bei manuellen Befehlen. Bei Ueberschreitung: Emergency Stop (Ventil gesperrt bis manueller Reset).</span>
          </div>
          <div class="actuator-config__field actuator-config__field--toggle">
            <label class="actuator-config__label">Normal-Closed (NC)</label>
            <button
              :class="['actuator-config__toggle', { 'actuator-config__toggle--on': isNormalClosed }]"
              @click="isNormalClosed = !isNormalClosed"
            >
              <span class="actuator-config__toggle-dot" />
            </button>
          </div>
          <!-- aux_gpio: Direction-Pin für H-Bridge (Block B) -->
          <div v-if="supportsAuxGpio(actuatorType)" class="actuator-config__field">
            <label class="actuator-config__label">Direction-Pin (H-Bridge)</label>
            <select v-model.number="auxGpio" class="actuator-config__select">
              <option v-for="opt in auxGpioOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <span class="actuator-config__helper">255 = nicht verwendet</span>
          </div>
        </template>

        <!-- PWM -->
        <template v-else-if="isPWM">
          <div class="actuator-config__field">
            <label class="actuator-config__label">Frequenz</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="pwmFrequency" type="number" min="1" max="40000" class="actuator-config__input" />
              <span class="actuator-config__unit">Hz</span>
            </div>
            <span class="actuator-config__helper">Typisch: 1000 Hz (Motoren), 25000 Hz (Luefter)</span>
          </div>
          <div class="actuator-config__field">
            <label class="actuator-config__label">Leistungs-Limit (Safety)</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="powerLimit" type="number" min="0" max="100" class="actuator-config__input" />
              <span class="actuator-config__unit">%</span>
            </div>
          </div>
        </template>

        <!-- Relay -->
        <template v-else-if="isRelay">
          <div class="actuator-config__field">
            <label class="actuator-config__label">Geraete-Sicherheitslimit</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="maxRuntime" type="number" min="0" class="actuator-config__input" />
              <span class="actuator-config__unit">Sek. ({{ formatDuration(maxRuntime) }})</span>
            </div>
            <span class="actuator-config__helper">Absolute Sicherheitsgrenze fuer Relais/Aktorlaufzeit. 0 = unbegrenzt (empfohlen fuer Dauerlicht).</span>
          </div>
          <div class="actuator-config__field actuator-config__field--toggle">
            <label class="actuator-config__label">Normal-Closed (NC)</label>
            <button
              :class="['actuator-config__toggle', { 'actuator-config__toggle--on': isNormalClosed }]"
              @click="isNormalClosed = !isNormalClosed"
            >
              <span class="actuator-config__toggle-dot" />
            </button>
          </div>
          <div class="actuator-config__field">
            <label class="actuator-config__label">Schalt-Verzoegerung (Anti-Prellen)</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="switchDelay" type="number" min="0" max="5000" class="actuator-config__input" />
              <span class="actuator-config__unit">ms</span>
            </div>
          </div>
        </template>
      </AccordionSection>

      <!-- AUT-252: Aktor-Datenblatt (read-only, aus ACTUATOR_TYPE_CONFIG) -->
      <AccordionSection
        title="Aktor-Datenblatt"
        :storage-key="`${accordionKey}-datasheet`"
        :icon="FileText"
      >
        <div v-if="hasActuatorDatasheet && actuatorTypeConfig" class="actuator-config__datasheet">
          <div class="actuator-config__datasheet-row">
            <span class="actuator-config__datasheet-label">Typ</span>
            <span class="actuator-config__datasheet-value">{{ actuatorTypeConfig.label }} ({{ actuatorType }})</span>
          </div>
          <div v-if="actuatorTypeConfig.manufacturer" class="actuator-config__datasheet-row">
            <span class="actuator-config__datasheet-label">Hersteller</span>
            <span class="actuator-config__datasheet-value">{{ actuatorTypeConfig.manufacturer }}</span>
          </div>
          <div v-if="actuatorTypeConfig.maxFlow" class="actuator-config__datasheet-row">
            <span class="actuator-config__datasheet-label">{{ actuatorTypeConfig.isPwm ? 'Max. Last' : 'Max. Durchfluss / Schaltleistung' }}</span>
            <span class="actuator-config__datasheet-value">{{ actuatorTypeConfig.maxFlow }}</span>
          </div>
          <div v-if="actuatorTypeConfig.nominalVoltage" class="actuator-config__datasheet-row">
            <span class="actuator-config__datasheet-label">Nennspannung</span>
            <span class="actuator-config__datasheet-value">{{ actuatorTypeConfig.nominalVoltage }}</span>
          </div>
          <div v-if="actuatorTypeConfig.maintenanceHours != null" class="actuator-config__datasheet-row">
            <span class="actuator-config__datasheet-label">Wartungsintervall</span>
            <span class="actuator-config__datasheet-value">
              {{ actuatorTypeConfig.maintenanceHours.toLocaleString('de-DE') }} Betriebsstunden
            </span>
          </div>
          <div v-if="actuatorTypeConfig.datasheetUrl" class="actuator-config__datasheet-row">
            <span class="actuator-config__datasheet-label">Datenblatt</span>
            <a
              class="actuator-config__datasheet-link"
              :href="actuatorTypeConfig.datasheetUrl"
              target="_blank"
              rel="noopener noreferrer"
            >
              Hersteller-Dokumentation
              <ExternalLink class="actuator-config__datasheet-link-icon" aria-hidden="true" />
            </a>
          </div>
        </div>
        <div v-else class="actuator-config__datasheet-empty">
          <Info class="actuator-config__datasheet-empty-icon" aria-hidden="true" />
          <div>
            <p class="actuator-config__datasheet-empty-title">Datenblatt nicht hinterlegt</p>
            <p class="actuator-config__datasheet-empty-hint">
              Hersteller- und Leistungsdaten werden zentral in der Komponenten-Bibliothek gepflegt.
            </p>
          </div>
        </div>
      </AccordionSection>

      <!-- Safety -->
      <AccordionSection
        title="Safety-Status"
        :storage-key="`${accordionKey}-safety`"
        :icon="Shield"
      >
        <div class="actuator-config__safety-info">
          <div class="actuator-config__safety-row">
            <Clock class="w-3.5 h-3.5" />
            <span>Letzter Befehl: {{ liveActuator?.last_command_at || '&mdash;' }}</span>
          </div>
          <div class="actuator-config__safety-row">
            <Zap class="w-3.5 h-3.5" />
            <span>Zustand: {{ isOn ? 'Aktiv' : 'Inaktiv' }}</span>
          </div>
          <div v-if="isEmergencyStopped" class="actuator-config__safety-row actuator-config__safety-row--alert">
            <AlertOctagon class="w-3.5 h-3.5" />
            <span>Not-Stopp aktiv — Steuerung gesperrt</span>
          </div>
        </div>

        <!-- Emergency Stop -->
        <button
          class="actuator-config__emergency"
          :disabled="commandLoading"
          @click="emergencyStop"
        >
          <AlertOctagon class="w-5 h-5" />
          NOTFALL-STOPP
        </button>
      </AccordionSection>

      <!-- ═══ ALERT CONFIGURATION (Phase 4A.7) ═════════════════════════ -->
      <AccordionSection
        v-if="actuatorDbId"
        title="Alert-Konfiguration"
        :storage-key="`${accordionKey}-alert-config`"
      >
        <AlertConfigSection
          :entity-id="actuatorDbId"
          entity-type="actuator"
          :fetch-fn="actuatorsApi.getAlertConfig"
          :update-fn="actuatorsApi.updateAlertConfig"
        />
      </AccordionSection>

      <!-- ═══ RUNTIME & MAINTENANCE (Phase 4A.8) ══════════════════════ -->
      <AccordionSection
        v-if="actuatorDbId"
        title="Laufzeit & Wartung"
        :storage-key="`${accordionKey}-runtime`"
      >
        <RuntimeMaintenanceSection
          :entity-id="actuatorDbId"
          entity-type="actuator"
          :fetch-fn="actuatorsApi.getRuntime"
          :update-fn="actuatorsApi.updateRuntime"
        />
      </AccordionSection>

      <!-- ═══ DEVICE INFO (Metadata) ═════════════════════════════════════ -->
      <AccordionSection
        v-if="showMetadata"
        title="Geräte-Informationen"
        :storage-key="`${accordionKey}-device-info`"
      >
        <DeviceMetadataSection
          :metadata="metadata"
          @update:metadata="metadata = $event"
        />
      </AccordionSection>

      <!-- AUT-256: Verknuepfte Regeln werden prominent als ERSTE Sektion gezeigt
           (siehe oben, direkt nach der Steuerung). Kein zweiter Eintrag im Akkordeon. -->

      <!-- AUT-251: Zone-Zuordnung wird ausschliesslich auf Geraete-Ebene gepflegt
           (HardwareView -> ESPSettingsSheet). Aktoren erben die Zone vom Geraet
           und besitzen nur eine eigene Subzone (siehe Dropdown oben). -->

      <!-- ═══ PENDING CONFIG STATUS (AUT-64) ═══════════════════════════════ -->
      <PendingConfigBanner
        :subject-id="lastConfigSubjectId"
        :correlation-id="lastConfigCorrelationId"
        @retry="handleSave"
      />

      <!-- ═══ ACTIONS ══════════════════════════════════════════════════════ -->
      <div class="actuator-config__actions">
        <button
          class="actuator-config__save"
          :disabled="saving || loading"
          @click="handleSave"
        >
          <Save class="w-4 h-4" />
          {{ saving ? 'Speichert...' : 'Speichern' }}
        </button>
        <button
          class="actuator-config__delete"
          :disabled="deleting || loading"
          @click="confirmAndDelete"
        >
          <Trash2 class="w-4 h-4" />
          Aktor entfernen
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.actuator-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.actuator-config--loading { opacity: 0.6; }
.actuator-config__loading { padding: var(--space-8); text-align: center; color: var(--color-text-muted); }

/* Sections */
.actuator-config__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--glass-border);
}

.actuator-config__simulation-badge {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(167, 139, 250, 0.35);
  background: rgba(167, 139, 250, 0.1);
  color: var(--color-mock);
  font-size: var(--text-xs);
  font-weight: 600;
}

.actuator-config__section:last-of-type { border-bottom: none; }

.actuator-config__section-title {
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

/* AUT-256: Konflikt-Warnung Pill (neben Steuerung-Titel) */
.actuator-config__conflict-pill {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: 500;
  text-transform: none;
  letter-spacing: 0;
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
}

.actuator-config__conflict-icon {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
}

/* AUT-256: Hinweis-Banner fuer manuelle Schaltung (Priority -1000) */
.actuator-config__manual-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in srgb, var(--color-info) 25%, transparent);
  background: color-mix(in srgb, var(--color-info) 8%, transparent);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.actuator-config__manual-banner-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-info);
}

/* AUT-251: Zone-Header (read-only, vom Geraet vererbt) */
.actuator-config__zone-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
}

.actuator-config__zone-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-muted);
}

.actuator-config__zone-value {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.actuator-config__zone-hint {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  font-style: italic;
}

.actuator-config__zone-link {
  margin-left: auto;
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--color-iridescent-1);
  font-size: var(--text-xs);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: underline;
  text-decoration-style: dotted;
  text-underline-offset: 2px;
}

.actuator-config__zone-link:hover {
  color: var(--color-text-primary);
  border-color: var(--color-iridescent-1);
  background: var(--color-bg-tertiary);
}

.actuator-config__zone-link:focus-visible {
  outline: 2px solid var(--color-iridescent-1);
  outline-offset: 2px;
}

/* Control Panel */
.actuator-config__state-box {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
}

.actuator-config__state-box--on {
  background: rgba(34, 197, 94, 0.06);
  border-color: rgba(34, 197, 94, 0.3);
}

.actuator-config__state-box--off {
  background: var(--color-bg-tertiary);
}

.actuator-config__state-indicator {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.actuator-config__state-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-status-offline);
}

.actuator-config__state-box--on .actuator-config__state-dot {
  background: var(--color-status-good);
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
}

.actuator-config__state-text {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--color-text-primary);
}

.actuator-config__toggle-btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
  border: 1px solid var(--color-status-good);
  background: transparent;
  color: var(--color-status-good);
}

.actuator-config__toggle-btn:hover { background: rgba(34, 197, 94, 0.1); }

.actuator-config__toggle-btn--on {
  border-color: var(--color-status-alarm);
  color: var(--color-status-alarm);
}

.actuator-config__toggle-btn--on:hover { background: rgba(239, 68, 68, 0.1); }
.actuator-config__toggle-btn--emergency {
  border-color: var(--color-status-alarm);
  color: var(--color-status-alarm);
  opacity: 0.7;
}
.actuator-config__toggle-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* PWM */
.actuator-config__pwm-control {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.actuator-config__pwm-slider {
  width: 100%;
  accent-color: var(--color-accent);
}

.actuator-config__pwm-labels {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

/* Fields */
.actuator-config__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.actuator-config__field--toggle {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.actuator-config__label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.actuator-config__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-family: var(--font-body);
}

.actuator-config__input:focus { outline: none; border-color: var(--color-accent); }
.actuator-config__input:disabled { opacity: 0.5; }

.actuator-config__select {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-base);
}

.actuator-config__input-with-unit {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.actuator-config__input-with-unit .actuator-config__input { flex: 1; }

.actuator-config__unit {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.actuator-config__helper {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.actuator-config__type-badge-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: 600;
}

.actuator-config__type-badge {
  display: inline-block;
  padding: 1px 6px;
  background: var(--color-accent-dim);
  color: var(--color-accent-bright);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
}

/* Toggle */
.actuator-config__toggle {
  position: relative;
  width: 40px;
  height: 22px;
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.actuator-config__toggle--on { background: var(--color-status-good); border-color: transparent; }

.actuator-config__toggle-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: white;
  border-radius: 50%;
  transition: transform var(--transition-fast);
}

.actuator-config__toggle--on .actuator-config__toggle-dot { transform: translateX(18px); }

/* Safety */
.actuator-config__safety-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.actuator-config__safety-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.actuator-config__safety-row--alert {
  color: var(--color-status-alarm);
  font-weight: 600;
}

.actuator-config__emergency {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: rgba(239, 68, 68, 0.1);
  border: 2px solid var(--color-status-alarm);
  border-radius: var(--radius-md);
  color: var(--color-status-alarm);
  font-size: var(--text-base);
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.actuator-config__emergency:hover {
  background: rgba(239, 68, 68, 0.2);
  box-shadow: 0 0 16px rgba(239, 68, 68, 0.3);
}

.actuator-config__emergency:disabled { opacity: 0.5; cursor: not-allowed; }

/* Actions */
.actuator-config__actions { padding-top: var(--space-2); display: flex; flex-direction: column; gap: var(--space-2); }

.actuator-config__save {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  justify-content: center;
  padding: var(--space-3) var(--space-4);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-base);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.actuator-config__save:hover:not(:disabled) { filter: brightness(1.1); }
.actuator-config__save:disabled { opacity: 0.5; cursor: not-allowed; }

.actuator-config__delete {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  justify-content: center;
  padding: var(--space-2) var(--space-4);
  background: transparent;
  border: 1px solid var(--color-status-critical);
  border-radius: var(--radius-sm);
  color: var(--color-status-critical);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.actuator-config__delete:hover:not(:disabled) { background: rgba(239, 68, 68, 0.1); }
.actuator-config__delete:disabled { opacity: 0.5; cursor: not-allowed; }

/* ═══════════════════════════════════════════════════════════════════════════
   AUT-252: Aktor-Datenblatt (read-only)
   ═══════════════════════════════════════════════════════════════════════════ */

.actuator-config__datasheet {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.actuator-config__datasheet-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--glass-border);
}

.actuator-config__datasheet-row:last-child {
  border-bottom: none;
}

.actuator-config__datasheet-label {
  flex: 0 0 180px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 500;
}

.actuator-config__datasheet-value {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.actuator-config__datasheet-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-accent-bright);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.actuator-config__datasheet-link:hover {
  color: var(--color-iridescent-2);
  text-decoration: underline;
}

.actuator-config__datasheet-link-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.actuator-config__datasheet-empty {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
}

.actuator-config__datasheet-empty-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-info);
}

.actuator-config__datasheet-empty-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.actuator-config__datasheet-empty-hint {
  margin: var(--space-1) 0 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: var(--leading-normal);
}
</style>
