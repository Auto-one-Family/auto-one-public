<script setup lang="ts">
/**
 * ActuatorConfigPanel — Config-only tabs (AUT-1127 S2)
 *
 * Grundlagen | Hardware | Kalibrierung (Pumpe) | Sicherheit | Alerts & Wartung.
 * Manual control, live safety state and linked-rules are NOT rendered here —
 * they moved to DeviceStatusPanel (docked next to this panel in ConfigWizardModal).
 * Changes here only take effect after "Speichern" (unlike the Status-Panel controls).
 */

import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import { Save, Info, Shield, Settings, Cpu, Droplets, Bell, Trash2, FileText, ExternalLink, OctagonAlert } from 'lucide-vue-next'
import { actuatorsApi } from '@/api/actuators'
import { stockMixRecipesApi } from '@/api/stockMixRecipes'
import { espApi } from '@/api/esp'
import { tanksApi } from '@/api/tanks'
import { formatStockConcentrationStatus } from '@/components/plants/stockConcentrationStatus'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'
import { AccordionSection, type TabItem } from '@/shared/design/primitives'
import { useUiStore } from '@/shared/stores/ui.store'
import { useGpioStatus } from '@/composables/useGpioStatus'
import { findIstSensorValue, tankDetailHref } from '@/components/plants/tankIstSollFormat'
import {
  concentrationFromDeltaEc,
  doseDurationSeconds,
  pairScaleFactor,
} from '@/components/esp/recipeMixerCalcs'
import {
  supportsAuxGpio,
  ACTUATOR_TYPE_CONFIG,
  getActuatorTypeOptions,
} from '@/utils/actuatorDefaults'
import {
  DOSE_ROLE_SELECT_OPTIONS,
  formatActuatorDoseLabel,
} from '@/utils/doseRoleDisplay'
import { getGpioConfig } from '@/utils/gpioConfig'
import AlertConfigSection from '@/components/devices/AlertConfigSection.vue'
import RuntimeMaintenanceSection from '@/components/devices/RuntimeMaintenanceSection.vue'
import DeviceMetadataSection from '@/components/devices/DeviceMetadataSection.vue'
import SubzoneAssignmentSection from '@/components/devices/SubzoneAssignmentSection.vue'
import { deviceContextApi } from '@/api/device-context'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { normalizeSubzoneId } from '@/utils/subzoneHelpers'
import { createLogger } from '@/utils/logger'
import type { DeviceScope } from '@/types'
import type { DeviceMetadata } from '@/types/device-metadata'
import { parseDeviceMetadata, mergeDeviceMetadata } from '@/types/device-metadata'
import { getDomainLabel } from '@/components/domains/domainLabels'
import PendingConfigBanner from './PendingConfigBanner.vue'

const configLogger = createLogger('ActuatorConfigPanel')

interface Props {
  espId: string
  gpio: number
  actuatorType: string
  showMetadata?: boolean
  /** AUT-1130 (Verify P10): tab selection now lives in ConfigWizardModal (full-width
   *  header row, spans both panels) — this component only reads which tab is active. */
  activeTab: string
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

// =============================================================================
// State
// =============================================================================
const loading = ref(true)
const saving = ref(false)
const actuatorDbId = ref<string | null>(null)

const lastConfigSubjectId = ref<string | null>(null)
const lastConfigCorrelationId = ref<string | null>(null)

// Basic fields
const name = ref('')
const description = ref('')
const enabled = ref(true)

// Device Scope (T13-R3 WP4) — State bleibt kanonisch hier (AUT-1535).
// UI hängt an localScope im Grundlagen-Tab; DeviceScopeSection bleibt unmounted.
const localScope = ref<DeviceScope>('zone_local')
const localAssignedZones = ref<string[]>([])
const activeZoneId = ref<string | null>(null)
const DEVICE_SCOPE_OPTIONS: ReadonlyArray<{ value: DeviceScope; label: string }> = [
  { value: 'zone_local', label: 'Lokal' },
  { value: 'multi_zone', label: 'Multi-Zone' },
  { value: 'mobile', label: 'Mobil' },
]

// Subzone
const subzoneId = ref<string | null>(null)

// Type-specific fields
const maxRuntime = ref(3600) // seconds
const minPause = ref(60) // seconds
// AO-1 (AUT-990): Pump flow rate calibration in ml/s. Top-level column, nullable (null = uncalibrated).
const flowRateMls = ref<number | null>(null)
// AUT-1355 U4-a: Empiric concentration SSOT (µS/cm rise per ml per L). Nullable.
const concentration = ref<number | null>(null)
/** AUT-1356: provenance for helper copy — seed (~100) vs wizard measurement vs manual. */
const concentrationSource = ref<'unset' | 'seed' | 'wizard' | 'manual'>('unset')
/** AUT-1410/1413: soft stock identity (display/traceability only). */
const stockRecipeRef = ref<string | null>(null)
const stockPreparedAt = ref<string | null>(null)
const stockRecipeLabel = ref<string | null>(null)
/** AUT-1371: full actuator_metadata for save-preserve + auto-cal status. */
const rawActuatorMeta = ref<Record<string, unknown>>({})
/** AUT-1371: ISO timestamp from metadata.concentration_auto_cal.updated_at */
const autoCalUpdatedAt = ref<string | null>(null)
/** AUT-1375 A1.2: manual Ansetzen/Anschließen/Messen — demoted optional fallback. */
const manualAssistOpen = ref(false)
// AUT-1355 U4-a: Structured recipe role (part_a | part_b | ph_down | generic).
// AUT-1359: Anzeige-Labels nur aus doseRoleDisplay (kurz, kein Name in der Rolle).
const doseRole = ref<string | null>(null)
const DOSE_ROLE_OPTIONS = DOSE_ROLE_SELECT_OPTIONS
const maxOpenTime = ref(3600) // seconds
const isInvertedLogic = ref(false)
const pwmFrequency = ref(5000) // Hz
const powerLimit = ref(100) // %
const switchDelay = ref(50) // ms
/** aux_gpio for Valve (H-Bridge direction pin). 255 = nicht verwendet */
const auxGpio = ref<number>(255)

// Device Metadata
const metadata = ref<DeviceMetadata>({})

// =============================================================================
// Editable type (AUT-1302) — seeded from prop (HardwareView prefers hardware_type)
// =============================================================================
const selectedActuatorType = ref(props.actuatorType)
const actuatorTypeOptions = getActuatorTypeOptions()

watch(
  () => props.actuatorType,
  (next) => {
    selectedActuatorType.value = next
  },
)

/** Clear orphaned pump calibration when leaving pump type (local + save). */
function onSelectedActuatorTypeChange(event: Event): void {
  const next = (event.target as HTMLSelectElement).value
  const prev = selectedActuatorType.value.toLowerCase()
  selectedActuatorType.value = next
  if (prev === 'pump' && next.toLowerCase() !== 'pump') {
    flowRateMls.value = null
    concentration.value = null
    doseRole.value = null
  }
}

// =============================================================================
// Computed
// =============================================================================
const isMock = computed(() => espApi.isMockEsp(props.espId))
const contextDevice = computed(() =>
  espStore.devices.find(d => espStore.getDeviceId(d) === props.espId),
)
/** AUT-1535: Report-Domain am Gerät — Anzeige hier, Editor bleibt ESPSettingsSheet. */
const deviceDomainLabel = computed(() => getDomainLabel(contextDevice.value?.domain))
const scopeZoneOptions = computed(() =>
  zoneStore.zoneEntities.filter(z => z.status === 'active'),
)

function onLocalScopeChange(event: Event): void {
  const next = (event.target as HTMLSelectElement).value as DeviceScope
  localScope.value = next
  if (next === 'zone_local') {
    localAssignedZones.value = []
  }
}

function onAssignedZoneToggle(zoneId: string, checked: boolean): void {
  const current = [...localAssignedZones.value]
  if (checked && !current.includes(zoneId)) {
    current.push(zoneId)
  } else if (!checked) {
    const idx = current.indexOf(zoneId)
    if (idx !== -1) current.splice(idx, 1)
  }
  localAssignedZones.value = current
}

const actuatorTypeNormalized = computed(() => selectedActuatorType.value.toLowerCase())
const isPump = computed(() => actuatorTypeNormalized.value === 'pump')
const isValve = computed(() => actuatorTypeNormalized.value === 'valve')
const isPWM = computed(() => actuatorTypeNormalized.value === 'pwm')
const isRelay = computed(() =>
  ['relay', 'digital', 'binary', 'switch'].includes(actuatorTypeNormalized.value),
)

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
// AUT-1127 (S2): 5 Top-Tabs statt Einklapp-Abschnitte. Kalibrierung nur bei
// dosierfaehigen Aktoren (Pumpe) — Relay/Valve/PWM zeigen 4 Tabs.
// AUT-1130 (Verify P10): die Tab-LEISTE selbst rendert ConfigWizardModal in einer
// vollen-Breite Kopfzeile (statt in dieser schmalen Spalte gequetscht) — dieses
// Component liefert per defineExpose nur noch die Tab-Liste, `activeTab` kommt als
// Prop von dort.
// =============================================================================
const tabs = computed<TabItem[]>(() => {
  const list: TabItem[] = [
    { key: 'grundlagen', label: 'Grundlagen', icon: Settings },
    { key: 'hardware', label: 'Hardware', icon: Cpu },
  ]
  if (isPump.value) {
    list.push({ key: 'kalibrierung', label: 'Kalibrierung', icon: Droplets })
  }
  list.push({ key: 'sicherheit', label: 'Sicherheit', icon: Shield })
  list.push({ key: 'alerts', label: 'Alerts & Wartung', icon: Bell })
  return list
})

/**
 * AUT-1359: Einheitliche Geräte-Bezeichnung Name → Typ → (dose_role).
 * Rolle ausschließlich aus gespeichertem Feld — keine Name-Ableitung.
 * Weiterhin gebraucht für Kalibrier-Schritt-Titel (Stock-Rechner selbst ist
 * AUT-1387 in den Nährlösung-Tab gewandert, siehe TankStockMixRecipePanel).
 */
const actuatorDoseLabel = computed(() =>
  formatActuatorDoseLabel({
    name: name.value,
    actuatorType: selectedActuatorType.value,
    doseRole: doseRole.value,
    typeFallback: 'Pumpe',
  }),
)

/** AUT-1413: shared status copy (Kalibrier-Tab). Nachschärfung = gemessen — kein Fehlerzustand. */
const stockConcentrationStatus = computed(() =>
  formatStockConcentrationStatus({
    concentration: concentration.value,
    recipeLabel: stockRecipeLabel.value,
    stockPreparedAt: stockPreparedAt.value,
  }),
)

async function resolveStockRecipeLabel(recipeId: string | null): Promise<void> {
  stockRecipeLabel.value = null
  if (!recipeId) return
  try {
    const recipe = await stockMixRecipesApi.get(recipeId)
    stockRecipeLabel.value = recipe.label || null
  } catch {
    // fail-soft — show status without invented recipe name
    stockRecipeLabel.value = null
  }
}

/** AUT-1371: compact local stand for auto-cal status line. */
function formatAutoCalStand(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function applyRoughConcentrationSeed() {
  concentration.value = 100
  concentrationSource.value = 'seed'
  toast.info('Grober Seed ~100 gesetzt — Wahrheit misst der Konzentrations-Assistent.')
}

// =============================================================================
// AUT-1001 + AUT-1356: Gefuehrter Pumpen-Kalibrier-Assistent.
// Modus Förderrate (Messlauf → Volumen → V/T) ODER Konzentration
// (EC₀ → dose → Settle → EC₁ → concentration). Gleicher ON+duration-Pfad.
// =============================================================================
type CalibMode = 'flow_rate' | 'concentration'
type CalibPhase = 'setup' | 'running' | 'settle' | 'measure' | 'done'

const calibWizardOpen = ref(false)
const calibMode = ref<CalibMode>('flow_rate')
const calibPhase = ref<CalibPhase>('setup')
// Mycodo-Vergleich + Sekunden-Quantelung (AUT-1001-Kommentar): 30-60s Default
// haelt den relativen ±1s-Rundungsfehler klein, frei ueberschreibbar.
const calibDurationSeconds = ref(45)
const calibSecondsLeft = ref(0)
const calibVolumeMl = ref<number | null>(null)
// Concentration-mode fields
const concDoseMl = ref<number>(50)
const concVolumeL = ref<number | null>(null)
const concVolumeHint = ref('')
const concSettleSeconds = ref(30)
const concPairScale = ref(false)
const concEc0 = ref<number | null>(null)
const concEc1 = ref<number | null>(null)
const concComputed = ref<number | null>(null)
let calibTimer: ReturnType<typeof setInterval> | null = null

const calibComputedRate = computed(() => {
  if (calibVolumeMl.value == null || calibVolumeMl.value <= 0) return null
  if (!calibDurationSeconds.value || calibDurationSeconds.value <= 0) return null
  return calibVolumeMl.value / calibDurationSeconds.value
})

const concDoseDuration = computed(() =>
  flowRateMls.value != null ? doseDurationSeconds(concDoseMl.value, flowRateMls.value) : null,
)

const currentTankId = computed((): string | null => {
  const device = espStore.devices.find((d) => espStore.getDeviceId(d) === props.espId)
  const tankId = (device as { tank_id?: string | null } | undefined)?.tank_id
  return typeof tankId === 'string' && tankId.length > 0 ? tankId : null
})

const assignedDeviceIdsForTank = computed((): string[] => {
  const tankId = currentTankId.value
  if (!tankId) return [props.espId]
  return espStore.devices
    .filter((d) => (d as { tank_id?: string | null }).tank_id === tankId)
    .map((d) => espStore.getDeviceId(d))
    .filter((id): id is string => !!id)
})

function readSystemEcUsCm(): number | null {
  return findIstSensorValue(espStore.devices, assignedDeviceIdsForTank.value, 'ec')
}

const liveSystemEcUsCm = computed(() => readSystemEcUsCm())

async function prefillsConcVolumeL(): Promise<void> {
  concVolumeHint.value = ''
  const tankId = currentTankId.value
  if (!tankId) {
    concVolumeHint.value = 'Kein Tank zugeordnet — V_l manuell eintragen.'
    return
  }

  let nominal: number | null = null
  try {
    const tank = await tanksApi.getTank(tankId)
    if (typeof tank.nominal_volume_l === 'number' && tank.nominal_volume_l > 0) {
      nominal = tank.nominal_volume_l
    }
  } catch {
    /* optional */
  }

  // Prefer Ledger V_alt via Assist (no override) — same pattern as SaltCalculatorPanel.
  try {
    const targets = await tanksApi.getTargets(tankId)
    const assigned = targets.assigned_device_ids ?? []
    const ec = findIstSensorValue(espStore.devices, assigned, 'ec')
    const targetRow = targets.targets.find((t) => t.measure === 'target_ec')
    const targetEc = targetRow?.value != null ? Number(targetRow.value) : null
    if (ec != null && targetEc != null && Number.isFinite(targetEc)) {
      try {
        const assist = await tanksApi.computeDoseExpectation(tankId, {
          current_ec_us_cm: ec,
          target_ec_us_cm: targetEc,
          volume_zugabe_l: 0,
        })
        if (assist.volume_alt_l > 0) {
          concVolumeL.value = assist.volume_alt_l
          concVolumeHint.value = `Vorbefüllt: Ledger/Assist ${assist.volume_alt_l} L (${assist.volume_alt_source}, überschreibbar).`
          return
        }
      } catch {
        // Retry with nominal as override if ledger empty (SaltCalculator pattern).
        if (nominal != null) {
          const assist = await tanksApi.computeDoseExpectation(tankId, {
            current_ec_us_cm: ec,
            target_ec_us_cm: targetEc,
            volume_zugabe_l: 0,
            volume_alt_l: nominal,
          })
          if (assist.volume_alt_l > 0) {
            concVolumeL.value = assist.volume_alt_l
            concVolumeHint.value = `Vorbefüllt: ${assist.volume_alt_l} L (${assist.volume_alt_source}, überschreibbar).`
            return
          }
        }
      }
    }
  } catch {
    /* fall through to nominal */
  }

  if (nominal != null) {
    concVolumeL.value = nominal
    concVolumeHint.value = `Vorbefüllt: Tank-Nominal ${nominal} L (überschreibbar).`
  } else {
    concVolumeHint.value = 'Kein Vorbefüll-Wert — V_l manuell eintragen.'
  }
}

/** AUT-1357 UX: Einstieg setzt den Modus — Förderrate oben, Konzentration in Schritt 3. */
function openCalibWizard(mode: CalibMode = 'flow_rate') {
  calibMode.value = mode
  calibWizardOpen.value = true
  calibPhase.value = 'setup'
  calibVolumeMl.value = null
  concEc0.value = null
  concEc1.value = null
  concComputed.value = null
  if (mode === 'concentration') {
    void prefillsConcVolumeL()
  }
}

function stopCalibTimer() {
  if (calibTimer) {
    clearInterval(calibTimer)
    calibTimer = null
  }
}

function closeCalibWizard() {
  stopCalibTimer()
  calibWizardOpen.value = false
  calibPhase.value = 'setup'
  calibVolumeMl.value = null
  concEc0.value = null
  concEc1.value = null
  concComputed.value = null
}

watch(calibMode, (mode) => {
  if (calibWizardOpen.value && mode === 'concentration' && calibPhase.value === 'setup') {
    void prefillsConcVolumeL()
  }
})

async function emergencyStopFromWizard() {
  try {
    await espStore.emergencyStopAll('Notfall-Stopp aus Pumpen-Kalibrier-Assistent')
  } catch {
    // Toast from store
  }
}

async function startCalibRun() {
  const duration = Math.max(1, Math.round(calibDurationSeconds.value))
  try {
    // Gleicher Store-Aufruf wie ActuatorCard.confirmDose/MonitorView.doseActuator —
    // ein MQTT-Roundtrip, ESP32 schaltet nach `duration` Sekunden selbst ab.
    await espStore.sendActuatorCommand(props.espId, props.gpio, 'ON', undefined, duration)
  } catch {
    // Toast/Fehlerbehandlung kommt bereits aus sendActuatorCommand.
    return
  }
  calibPhase.value = 'running'
  calibSecondsLeft.value = duration
  stopCalibTimer()
  calibTimer = setInterval(() => {
    calibSecondsLeft.value--
    if (calibSecondsLeft.value <= 0) {
      stopCalibTimer()
      calibPhase.value = 'measure'
    }
  }, 1000)
}

async function startConcDoseRun() {
  if (flowRateMls.value == null || flowRateMls.value <= 0) {
    toast.error('Förderrate fehlt — zuerst Förderrate kalibrieren.')
    return
  }
  const duration = concDoseDuration.value
  if (duration == null) {
    toast.error('Ungültige Dosis oder Förderrate.')
    return
  }
  if (concVolumeL.value == null || concVolumeL.value <= 0) {
    toast.error('Tankvolumen V_l muss > 0 sein.')
    return
  }
  const ec0 = readSystemEcUsCm()
  if (ec0 == null) {
    toast.error('System-EC fehlt — Tank-EC-Sensor muss Ist liefern.')
    return
  }
  const confirmed = await uiStore.confirm({
    title: 'Konzentrations-Messdosis starten?',
    message:
      `Pumpe GPIO ${props.gpio} dosiert ${concDoseMl.value} ml (~${duration} s) in den Tank. ` +
      `EC₀ = ${ec0.toFixed(0)} µS/cm. Notfall-Stopp bleibt im Assistenten sichtbar.`,
    variant: 'warning',
    confirmText: 'Dosieren',
  })
  if (!confirmed) return

  concEc0.value = ec0
  concEc1.value = null
  concComputed.value = null
  try {
    await espStore.sendActuatorCommand(props.espId, props.gpio, 'ON', undefined, duration)
  } catch {
    return
  }
  calibPhase.value = 'running'
  calibSecondsLeft.value = duration
  stopCalibTimer()
  calibTimer = setInterval(() => {
    calibSecondsLeft.value--
    if (calibSecondsLeft.value <= 0) {
      stopCalibTimer()
      beginConcSettle()
    }
  }, 1000)
}

function beginConcSettle() {
  const settle = Math.max(0, Math.round(concSettleSeconds.value))
  if (settle <= 0) {
    finishConcMeasure()
    return
  }
  calibPhase.value = 'settle'
  calibSecondsLeft.value = settle
  stopCalibTimer()
  calibTimer = setInterval(() => {
    calibSecondsLeft.value--
    if (calibSecondsLeft.value <= 0) {
      stopCalibTimer()
      finishConcMeasure()
    }
  }, 1000)
}

function finishConcMeasure() {
  const ec1 = readSystemEcUsCm()
  concEc1.value = ec1
  if (ec1 == null || concEc0.value == null || concVolumeL.value == null) {
    concComputed.value = null
  } else {
    const raw = concentrationFromDeltaEc(concEc0.value, ec1, concVolumeL.value, concDoseMl.value)
    concComputed.value = raw == null ? null : Math.round(raw * 100) / 100
  }
  calibPhase.value = 'measure'
}

async function applyCalibResult() {
  if (calibComputedRate.value == null) return
  flowRateMls.value = Math.round(calibComputedRate.value * 100) / 100
  await handleSave()
  calibPhase.value = 'done'
}

async function applyConcResult() {
  if (concComputed.value == null || !Number.isFinite(concComputed.value)) return
  if (concComputed.value <= 0) {
    toast.error('Berechnete Konzentration ≤ 0 — Messung prüfen (EC₁ > EC₀?).')
    return
  }
  const seedBefore = concentration.value
  concentration.value = concComputed.value
  concentrationSource.value = 'wizard'

  if (concPairScale.value) {
    await scalePartnerConcentration(concComputed.value, seedBefore)
  }

  await handleSave()
  calibPhase.value = 'done'
}

/** Paar-Messung: k = C / seed_ref skaliert Partner (part_a ↔ part_b) auf demselben Tank. */
async function scalePartnerConcentration(measured: number, seedBefore: number | null) {
  const role = doseRole.value
  if (role !== 'part_a' && role !== 'part_b') {
    toast.info('Paar-Skalierung braucht Rezept-Rolle Teil A oder Teil B.')
    return
  }
  const partnerRole = role === 'part_a' ? 'part_b' : 'part_a'
  const tankId = currentTankId.value
  if (!tankId) {
    toast.info('Paar-Skalierung: kein Tank — nur diese Pumpe gespeichert.')
    return
  }
  const k = pairScaleFactor(measured, seedBefore)
  if (k == null) return

  const devices = espStore.devices.filter(
    (d) => (d as { tank_id?: string | null }).tank_id === tankId,
  )
  for (const device of devices) {
    const espId = espStore.getDeviceId(device)
    const actuators = (device.actuators as { gpio: number }[] | undefined) ?? []
    for (const act of actuators) {
      if (espId === props.espId && act.gpio === props.gpio) continue
      try {
        const cfg = await actuatorsApi.get(espId, act.gpio)
        if ((cfg as { dose_role?: string | null }).dose_role !== partnerRole) continue
        const partnerConc = (cfg as { concentration?: number | null }).concentration
        const base =
          partnerConc != null && Number.isFinite(partnerConc) && partnerConc > 0
            ? partnerConc
            : 100
        const scaled = Math.round(base * k * 100) / 100
        await actuatorsApi.createOrUpdate(espId, act.gpio, {
          esp_id: espId,
          gpio: act.gpio,
          actuator_type: cfg.actuator_type,
          name: cfg.name,
          enabled: cfg.enabled,
          flow_rate_ml_s: cfg.flow_rate_ml_s ?? null,
          concentration: scaled,
          dose_role: cfg.dose_role ?? null,
          max_runtime_seconds: cfg.max_runtime_seconds,
          cooldown_seconds: cfg.cooldown_seconds,
          metadata: cfg.metadata ?? null,
        })
        toast.success(`Partner (${partnerRole}) skaliert ×${k.toFixed(2)} → ${scaled}`)
        return
      } catch {
        // try next actuator
      }
    }
  }
  toast.info('Kein Partner mit passender Rezept-Rolle gefunden.')
}

onUnmounted(() => {
  stopCalibTimer()
})

// =============================================================================
// Load existing config
// =============================================================================
onMounted(async () => {
  // Load actuator config from server for BOTH mock and real devices — DB is the
  // single source of truth (mirrors SensorConfigPanel.onMounted). The store is only
  // a fallback when no DB config exists yet.
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
      // AO-1: flow_rate_ml_s is a top-level response field (NOT metadata).
      flowRateMls.value = (c.flow_rate_ml_s as number | null) ?? null
      // AUT-1355: concentration + dose_role are top-level response fields (NOT metadata).
      concentration.value = (c.concentration as number | null) ?? null
      concentrationSource.value = concentration.value == null ? 'unset' : 'manual'
      // AUT-1410/1413: soft stock identity (display only).
      stockRecipeRef.value = (c.stock_recipe_ref as string | null) ?? null
      stockPreparedAt.value = (c.stock_prepared_at as string | null) ?? null
      await resolveStockRecipeLabel(stockRecipeRef.value)
      rawActuatorMeta.value = { ...meta }
      const autoCal = meta.concentration_auto_cal as Record<string, unknown> | undefined
      autoCalUpdatedAt.value =
        typeof autoCal?.updated_at === 'string' ? autoCal.updated_at : null
      if (autoCal && concentration.value != null) {
        concentrationSource.value = 'wizard'
      }
      doseRole.value = (c.dose_role as string | null) ?? null
      maxOpenTime.value =
        (c.max_runtime_seconds as number) ??
        (meta.max_open_time as number) ??
        (meta.max_open_time_seconds as number) ??
        getDefaultMaxRuntimeSeconds()
      isInvertedLogic.value =
        meta.inverted_logic !== undefined
          ? !!meta.inverted_logic
          : false
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
    // No config in DB yet — Mock fallback: hydrate from the store's live actuator.
    // (liveActuator itself now lives in DeviceStatusPanel — this is a one-shot
    // lookup for the initial-hydration fallback only, not a reactive UI binding.)
    const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
    const act = (device?.actuators as { gpio: number; name?: string; description?: string; enabled?: boolean }[] | undefined)
      ?.find(a => a.gpio === props.gpio)
    if (isMock.value && act) {
      name.value = act.name || ''
      description.value = act.description || ''
      enabled.value = act.enabled !== false
    }
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
})

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
    // Build + persist config for BOTH mock and real devices. DB is the single
    // source of truth (mirrors SensorConfigPanel.handleSave); mock differs only in
    // the post-save handling below (no MQTT device round-trip).
    const config: Record<string, unknown> = {
      esp_id: props.espId,
      gpio: props.gpio,
      // AUT-1302: editable type — ESP32 token triggers capture_hardware_type on server upsert
      actuator_type: selectedActuatorType.value,
      name: name.value || null,
      description: description.value || null,
      enabled: enabled.value,
      subzone_id: normalizeSubzoneId(subzoneId.value),
    }

    // Device Scope (T13-R3 WP4)
    config.device_scope = localScope.value
    config.assigned_zones = localScope.value === 'zone_local' ? [] : localAssignedZones.value

    // Device metadata base — preserve server keys (AUT-1371 concentration_auto_cal).
    const meta: Record<string, unknown> = mergeDeviceMetadata(
      rawActuatorMeta.value,
      metadata.value,
    )

    if (isPump.value) {
      config.max_runtime_seconds = maxRuntime.value
      config.cooldown_seconds = minPause.value
      // AO-1: flow_rate_ml_s is a top-level field (NOT metadata) — mirrors POST /actuators/{esp_id}/{gpio} column.
      config.flow_rate_ml_s = flowRateMls.value
      // AUT-1355: concentration + dose_role — same top-level column pattern as flow_rate.
      config.concentration = concentration.value
      config.dose_role = doseRole.value || null
      meta.inverted_logic = isInvertedLogic.value
    } else {
      // AUT-1302: clear orphaned calibration when type is not dosing-capable (pump)
      config.flow_rate_ml_s = null
      config.concentration = null
      config.dose_role = null
    }

    if (isValve.value) {
      config.max_runtime_seconds = maxOpenTime.value
      meta.inverted_logic = isInvertedLogic.value
      meta.aux_gpio = auxGpio.value
    }

    if (isRelay.value) {
      config.max_runtime_seconds = maxRuntime.value
      config.cooldown_seconds = minPause.value
    }

    if (isPWM.value) {
      config.pwm_frequency = pwmFrequency.value
      meta.duty_max = powerLimit.value
    }

    if (isRelay.value) {
      meta.inverted_logic = isInvertedLogic.value
      meta.switch_delay_ms = switchDelay.value
    }

    config.metadata = meta
    const result = await actuatorsApi.createOrUpdate(props.espId, props.gpio, config as any)

    if (isMock.value) {
      // Mock devices have no MQTT config round-trip; the persist above is the save.
      // Skip the device-confirmation lifecycle and report success directly.
      toast.success('[Simulation] Aktor-Konfiguration gespeichert')
      emit('saved')
      return
    }

    const response = result as unknown as Record<string, unknown>
    const correlationId = typeof response.correlation_id === 'string' ? response.correlation_id : undefined
    const requestId = typeof response.request_id === 'string' ? response.request_id : undefined
    const handles = [correlationId ? `Korrelation: ${correlationId}` : '', requestId ? `Request-ID: ${requestId}` : '']
      .filter(Boolean)
      .join(' | ')
    const scope = `actuator:${props.gpio}:${selectedActuatorType.value}`
    const summary = `Aktor-Konfiguration ${selectedActuatorType.value} an GPIO ${props.gpio}`
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

/** AUT-1130: lets ConfigWizardModal read the tab list for its full-width tab bar. */
defineExpose({ tabs })
</script>

<template>
  <div class="actuator-config" :class="{ 'actuator-config--loading': loading }">
    <div v-if="loading" class="actuator-config__loading">Lade Konfiguration...</div>

    <template v-else>
      <section v-if="isMock" class="actuator-config__simulation-badge" aria-label="Simulation Hinweis">
        [Simulation] Mock-ESP - Aktionen werden simuliert.
      </section>

      <!-- AUT-256/AUT-1128: Steuerung, Verknuepfte Regeln und Safety-Status leben
           jetzt im angedockten DeviceStatusPanel (ConfigWizardModal, rechte Spalte).
           Nur EINE Stelle rendert den Ein/Aus-Knopf (Anti-Doppel-Impl). -->

      <!-- TODO(AUT-1125 offene Frage): Zielort fuer "Letzte Schaltvorgaenge"
           (ActuatorActionTimeline, vormals hier als Akkordeon) ist noch nicht
           entschieden — bewusst NICHT in den Config-Tabs oder im Status-Panel
           wiederangesiedelt, bis die TM/Robin-Entscheidung vorliegt. -->

      <!-- AUT-1127 (S2): 5 Top-Tabs statt Einklapp-Abschnitte. AUT-1130 (Verify P10):
           Tab-Leiste selbst rendert jetzt ConfigWizardModal (volle Modal-Breite,
           siehe defineExpose({ tabs }) oben) — hier nur noch der Tab-Inhalt. -->

      <!-- Tab: Grundlagen -->
      <div v-show="activeTab === 'grundlagen'" class="actuator-config__tab-panel">
        <!-- AUT-1130 / AUT-1535: Zone + Auswertungs-Domäne gehören zum Gerät.
             Anzeige hier; Setzen bleibt ESPSettingsSheet („im Gerät ändern“). -->
        <div class="actuator-config__zone-header">
          <span class="actuator-config__zone-hint">
            Zone wird vom Gerät vererbt.
            Auswertungs-Domäne: {{ deviceDomainLabel }}
          </span>
          <button
            type="button"
            class="actuator-config__zone-link"
            aria-label="Zone und Domäne im Gerät ändern"
            @click="requestOpenEspSettings"
          >
            im Gerät ändern
          </button>
        </div>

        <div class="actuator-config__field">
          <label class="actuator-config__label">Name</label>
          <input
            v-model="name"
            type="text"
            class="actuator-config__input"
            placeholder="z.B. Bewaesserungspumpe Zone A"
            data-testid="actuator-config-name"
            aria-label="Aktor-Name"
          />
        </div>

        <!-- AUT-1355: Rezept-Rolle — explizite Identität für Salzrechner A/B (nicht positional). -->
        <div v-if="isPump" class="actuator-config__field">
          <label class="actuator-config__label" for="actuator-dose-role">Rezept-Rolle</label>
          <select
            id="actuator-dose-role"
            class="actuator-config__select"
            :value="doseRole ?? ''"
            aria-label="Rezept-Rolle der Dosierpumpe"
            @change="doseRole = ($event.target as HTMLSelectElement).value || null"
          >
            <option v-for="opt in DOSE_ROLE_OPTIONS" :key="opt.value || 'unset'" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
          <span class="actuator-config__helper">
            Gespeicherte Rezept-Rolle (Stock A/B, pH-Minus, …) — erscheint nur, wenn gesetzt.
            Keine Ableitung aus dem Gerätenamen. Logic-Zuordnung bleibt unverändert.
          </span>
        </div>

        <div class="actuator-config__field">
          <label class="actuator-config__label">Beschreibung</label>
          <input v-model="description" type="text" class="actuator-config__input" placeholder="Optional" />
        </div>

        <div class="actuator-config__field actuator-config__field--toggle">
          <label class="actuator-config__label">Aktiv</label>
          <button
            type="button"
            role="switch"
            :aria-checked="enabled"
            :class="['toggle-switch touch-target hardware-onoff-control', { 'toggle-switch--on': enabled }]"
            data-testid="actuator-config-enabled-toggle"
            aria-label="Aktor aktivieren"
            @click="enabled = !enabled"
          >
            <span class="toggle-switch__thumb" />
          </button>
        </div>

        <!-- Subzone assignment (with create-new option) -->
        <div class="actuator-config__field">
          <SubzoneAssignmentSection
            v-model="subzoneId"
            :esp-id="espId"
            :gpio="gpio"
            :actuator-config-id="actuatorDbId"
            :zone-id="espStore.devices.find(d => espStore.getDeviceId(d) === espId)?.zone_id ?? null"
          />
        </div>

        <!-- AUT-1535: vorhandenes localScope sichtbar — kein DeviceScopeSection-Mount. -->
        <div class="actuator-config__field" data-testid="actuator-config-device-scope">
          <label class="actuator-config__label" for="actuator-device-scope">Zonen-Reichweite</label>
          <select
            id="actuator-device-scope"
            class="actuator-config__select"
            :value="localScope"
            aria-label="Zonen-Reichweite des Aktors"
            data-testid="actuator-config-device-scope-select"
            @change="onLocalScopeChange"
          >
            <option v-for="opt in DEVICE_SCOPE_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
          <span class="actuator-config__helper">
            Wie weit dieser Aktor Zonen bedient — nicht die Auswertungs-Domäne, nicht an die Firmware.
          </span>
        </div>

        <div
          v-if="localScope !== 'zone_local'"
          class="actuator-config__field"
          data-testid="actuator-config-assigned-zones"
        >
          <label class="actuator-config__label">Zugewiesene Zonen</label>
          <label
            v-for="zone in scopeZoneOptions"
            :key="zone.zone_id"
            class="actuator-config__checkbox"
          >
            <input
              type="checkbox"
              :checked="localAssignedZones.includes(zone.zone_id)"
              :aria-label="`Zone ${zone.name} zuweisen`"
              @change="onAssignedZoneToggle(zone.zone_id, ($event.target as HTMLInputElement).checked)"
            />
            <span>{{ zone.name }}</span>
          </label>
          <span v-if="scopeZoneOptions.length === 0" class="actuator-config__helper">
            Keine aktiven Zonen vorhanden
          </span>
        </div>
      </div>

      <!-- Tab: Hardware (Typ-Einstellungen, feld-gesplittet: GPIO/Invertierte-Logik hierher) -->
      <div v-show="activeTab === 'hardware'" class="actuator-config__tab-panel">
        <!-- AUT-1302: Typ nach Anlegen editierbar (Upsert schreibt hardware_type via capture_hardware_type) -->
        <div class="actuator-config__field">
          <label class="actuator-config__label" for="actuator-config-type">Aktor-Typ</label>
          <select
            id="actuator-config-type"
            class="actuator-config__select"
            :value="selectedActuatorType"
            aria-label="Aktor-Typ"
            data-testid="actuator-config-type-select"
            @change="onSelectedActuatorTypeChange"
          >
            <!-- Keep current value selectable even if it is a legacy/generic token (e.g. digital) -->
            <option
              v-if="!actuatorTypeOptions.some((o) => o.value === selectedActuatorType)"
              :value="selectedActuatorType"
            >
              {{ selectedActuatorType }}
            </option>
            <option
              v-for="opt in actuatorTypeOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </option>
          </select>
          <span class="actuator-config__helper">
            Typ aenderbar — bei Wechsel weg von Pumpe wird die Foerderrate-Kalibrierung geleert.
          </span>
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
          <!-- AUT-997 follow-up: pumps are commonly driven via a relay module, so they need the
               same inverted-logic control as a relay. handleSave()/onMounted already wire
               meta.inverted_logic for isPump — only the toggle was missing from the pump block. -->
          <div class="actuator-config__field actuator-config__field--toggle">
            <label class="actuator-config__label">Invertierte Logik (LOW = ON)</label>
            <button
              type="button"
              role="switch"
              :aria-checked="isInvertedLogic"
              :class="['toggle-switch touch-target', { 'toggle-switch--on': isInvertedLogic }]"
              aria-label="Invertierte Logik"
              @click="isInvertedLogic = !isInvertedLogic"
            >
              <span class="toggle-switch__thumb" />
            </button>
          </div>
          <span class="actuator-config__helper">Fuer ueber ein Relais betriebene Pumpen, deren Relais-Modul bei LOW schaltet (z.B. guenstige Optokoppler-Platinen).</span>
        </template>

        <!-- Valve -->
        <template v-else-if="isValve">
          <div class="actuator-config__field actuator-config__field--toggle">
            <label class="actuator-config__label">Invertierte Logik (LOW = ON)</label>
            <button
              type="button"
              role="switch"
              :aria-checked="isInvertedLogic"
              :class="['toggle-switch touch-target', { 'toggle-switch--on': isInvertedLogic }]"
              aria-label="Invertierte Logik"
              @click="isInvertedLogic = !isInvertedLogic"
            >
              <span class="toggle-switch__thumb" />
            </button>
          </div>
          <span class="actuator-config__helper">Fuer Ventilmodule die bei LOW schalten.</span>
          <!-- aux_gpio: Direction-Pin für H-Bridge (Block B) -->
          <div v-if="supportsAuxGpio(selectedActuatorType)" class="actuator-config__field">
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
        </template>

        <!-- Relay -->
        <template v-else-if="isRelay">
          <div class="actuator-config__field actuator-config__field--toggle">
            <label class="actuator-config__label">Invertierte Logik (LOW = ON)</label>
            <button
              type="button"
              role="switch"
              :aria-checked="isInvertedLogic"
              :class="['toggle-switch touch-target', { 'toggle-switch--on': isInvertedLogic }]"
              aria-label="Invertierte Logik"
              @click="isInvertedLogic = !isInvertedLogic"
            >
              <span class="toggle-switch__thumb" />
            </button>
          </div>
          <span class="actuator-config__helper">Fuer Relais-Module die bei LOW schalten (z.B. guenstige Optokoppler-Platinen).</span>
          <div class="actuator-config__field">
            <label class="actuator-config__label">Schalt-Verzoegerung (Anti-Prellen)</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="switchDelay" type="number" min="0" max="5000" class="actuator-config__input" />
              <span class="actuator-config__unit">ms</span>
            </div>
          </div>
        </template>
      </div>

      <!-- Tab: Kalibrierung — nur dosierfaehige Aktoren (Pumpe). SSOT-Schreibpunkt:
           flow_rate_ml_s bleibt dedizierte Spalte actuator_configs.flow_rate_ml_s,
           NIEMALS zusaetzlich in metadata-JSONB (siehe handleSave). -->
      <div v-if="isPump" v-show="activeTab === 'kalibrierung'" class="actuator-config__tab-panel">
        <!-- Block A: Förderrate + Assistent (AUT-1001) — oben bei der Einstellung -->
        <section class="actuator-config__calib-card" aria-label="Förderrate kalibrieren">
          <h3 class="actuator-config__calib-card-title">Förderrate</h3>
          <p class="actuator-config__calib-hint">
            Gemessene Pumpen-Fördermenge (ml/s) — Basis für Dosis → Laufzeit in Dosier-Regeln.
          </p>
          <div class="actuator-config__field">
            <label class="actuator-config__label">Aktueller Wert</label>
            <div class="actuator-config__input-with-unit">
              <input
                :value="flowRateMls ?? ''"
                type="number"
                min="0"
                step="0.1"
                placeholder="z.B. 2.5"
                class="actuator-config__input"
                aria-label="Förderrate in Millilitern pro Sekunde"
                @input="flowRateMls = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"
              />
              <span class="actuator-config__unit">ml/s</span>
            </div>
            <span v-if="flowRateMls == null" class="actuator-config__helper actuator-config__helper--warn">
              Nicht kalibriert — Assistent nutzen oder Wert eintragen.
            </span>
          </div>

          <div class="actuator-config__calib-wizard">
            <button
              v-if="!(calibWizardOpen && calibMode === 'flow_rate')"
              type="button"
              class="actuator-config__wizard-btn actuator-config__wizard-btn--active"
              aria-label="Förderrate-Assistent starten"
              @click="openCalibWizard('flow_rate')"
            >
              Förderrate kalibrieren
            </button>

            <div v-else class="actuator-config__calib-panel">
              <template v-if="calibPhase === 'setup'">
                <p class="actuator-config__calib-hint">
                  Schlauch entlüften (Priming) und Auffanggefäß bereitstellen. Die Pumpe läuft
                  danach automatisch für die eingestellte Zeit und stoppt selbstständig (Firmware-Timer).
                </p>
                <div class="actuator-config__field">
                  <label class="actuator-config__label">Kalibrier-Laufzeit</label>
                  <div class="actuator-config__input-with-unit">
                    <input v-model.number="calibDurationSeconds" type="number" min="1" max="300" step="1" class="actuator-config__input" aria-label="Kalibrier-Laufzeit in Sekunden" />
                    <span class="actuator-config__unit">Sek.</span>
                  </div>
                  <span class="actuator-config__helper">Empfohlen: 30–60 Sek. — kürzere Läufe haben einen größeren relativen ±1s-Rundungsfehler.</span>
                </div>
                <div class="actuator-config__calib-actions">
                  <button type="button" class="actuator-config__calib-start" :disabled="calibDurationSeconds < 1" @click="startCalibRun">
                    Messlauf starten
                  </button>
                  <button type="button" class="actuator-config__calib-cancel" @click="closeCalibWizard">Abbrechen</button>
                </div>
              </template>

              <template v-else-if="calibPhase === 'running'">
                <p class="actuator-config__calib-hint">Messlauf läuft — Pumpe stoppt automatisch nach Ablauf.</p>
                <div class="actuator-config__calib-countdown">{{ calibSecondsLeft }} s</div>
                <button type="button" class="actuator-config__e-stop" aria-label="Notfall-Stopp" @click="emergencyStopFromWizard">
                  <OctagonAlert class="w-4 h-4" aria-hidden="true" />
                  Notfall-Stopp
                </button>
              </template>

              <template v-else-if="calibPhase === 'measure'">
                <p class="actuator-config__calib-hint">Messlauf beendet. Tatsächlich aufgefangenes Volumen eingeben.</p>
                <div class="actuator-config__field">
                  <label class="actuator-config__label">Gemessenes Volumen</label>
                  <div class="actuator-config__input-with-unit">
                    <input v-model.number="calibVolumeMl" type="number" min="0" step="0.1" placeholder="z.B. 45" class="actuator-config__input" aria-label="Gemessenes Volumen in Millilitern" />
                    <span class="actuator-config__unit">ml</span>
                  </div>
                </div>
                <p v-if="calibComputedRate != null" class="actuator-config__calib-result">
                  Berechnete Förderrate: {{ calibComputedRate.toFixed(2) }} ml/s ({{ calibVolumeMl }} ml / {{ calibDurationSeconds }} s)
                </p>
                <div class="actuator-config__calib-actions">
                  <button type="button" class="actuator-config__calib-start" :disabled="calibComputedRate == null || saving" @click="applyCalibResult">
                    {{ saving ? 'Speichert...' : 'Übernehmen & Speichern' }}
                  </button>
                  <button type="button" class="actuator-config__calib-cancel" @click="closeCalibWizard">Abbrechen</button>
                </div>
              </template>

              <template v-else-if="calibPhase === 'done'">
                <p class="actuator-config__calib-result">Förderrate gespeichert: {{ flowRateMls }} ml/s</p>
                <div class="actuator-config__calib-actions">
                  <button type="button" class="actuator-config__calib-cancel" @click="closeCalibWizard">Fertig</button>
                </div>
              </template>
            </div>
          </div>
        </section>

        <!-- Block B: Konzentration-SSOT (AUT-1355 / AUT-1371 / AUT-1375) — Auto-Cal = Hauptweg -->
        <section class="actuator-config__calib-card" aria-label="Konzentration">
          <h3 class="actuator-config__calib-card-title">Konzentration</h3>
          <p class="actuator-config__calib-hint">
            EC-Anstieg pro ml Stock je Liter Tank. Hauptweg: Auto-Kalibrierung beim nächsten realen Dosier-Einsatz
            (editierbar, falls du manuell überschreiben willst).
          </p>
          <p class="actuator-config__helper" aria-label="Konzentrations-Bezug Pumpe">
            Bezug: {{ actuatorDoseLabel }}
          </p>
          <div class="actuator-config__field">
            <label class="actuator-config__label">Gespeicherter Wert</label>
            <div class="actuator-config__input-with-unit">
              <input
                :value="concentration ?? ''"
                type="number"
                min="0"
                step="1"
                placeholder="z. B. 100"
                class="actuator-config__input"
                aria-label="Konzentration µS/cm Anstieg pro ml Stock je Liter Tank"
                @input="concentration = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value); concentrationSource = concentration == null ? 'unset' : 'manual'"
              />
              <span class="actuator-config__unit">µS/cm pro ml·L</span>
            </div>
            <!-- AUT-1413: Stock-Reset Status (shared helper) + AUT-1371 Auto-Cal Detail -->
            <p
              class="actuator-config__helper"
              :class="{ 'actuator-config__helper--warn': stockConcentrationStatus.kind === 'pending_remeasure' }"
              role="status"
              aria-label="Konzentrations-Zustand Stock"
              data-testid="stock-concentration-status"
            >
              {{ stockConcentrationStatus.label }}
            </p>
            <p
              v-if="concentration != null"
              class="actuator-config__helper"
              role="status"
              aria-label="Auto-Kalibrierungsstatus"
            >
              Wert {{ concentration }}µS/cm·ml⁻¹·L⁻¹<span v-if="autoCalUpdatedAt">, Stand {{ formatAutoCalStand(autoCalUpdatedAt) }}</span>
            </p>
            <span v-if="concentration == null" class="actuator-config__helper">
              Wahrheit kommt aus dem nächsten realen Dosier-Einsatz. Manueller Assistent nur als Notfall-Fallback unten.
            </span>
            <span v-else-if="concentrationSource === 'seed'" class="actuator-config__helper actuator-config__helper--warn">
              Platzhalter/Seed (~{{ concentration }}) — bis Auto-Cal nachschärft.
            </span>
            <span v-else-if="concentrationSource === 'wizard'" class="actuator-config__helper">
              Gemessen (Auto-Cal / manueller Fallback) — SSOT der Pumpe für Logic/Salzrechner.
            </span>
            <span v-else class="actuator-config__helper">
              Manuell überschrieben — SSOT der Pumpe für Logic/Salzrechner (Auto-Cal schärft weiter nach).
            </span>
          </div>
        </section>

        <!-- AUT-1375 A1.2: 3-Schritt-Assistent demoted — optionaler Fallback, nicht Hauptweg -->
        <details
          class="actuator-config__manual-assist"
          :open="manualAssistOpen"
          @toggle="manualAssistOpen = ($event.target as HTMLDetailsElement).open"
        >
          <summary
            class="actuator-config__manual-assist-summary"
            aria-label="Manueller Konzentrations-Assistent — optionaler Fallback"
          >
            Manueller Fallback (Assistent) — nur wenn Auto-Cal nicht reicht
          </summary>
          <p class="actuator-config__helper actuator-config__manual-assist-note">
            Ansetzen / Anschließen / Messen ist ein Notfall-Pfad. Normalfall: Wert oben + Auto-Cal beim nächsten Einsatz.
          </p>
        <ol class="actuator-config__stock-flow" aria-label="Optionaler manueller Assistent — drei Schritte">
          <li class="actuator-config__stock-step">
            <div class="actuator-config__stock-step-head">
              <span class="actuator-config__stock-step-num" aria-hidden="true">1</span>
              <div>
                <h3 class="actuator-config__stock-step-title">Ansetzen — Stock im Nährlösung-Tab</h3>
                <p class="actuator-config__calib-hint">
                  Wasser-Menge, Phase und Gramm-Rechner sind in den Nährlösung-Tab gewandert
                  (zusammen mit dem Rezept-Wochenraster) — hier nur noch der Notfall-Seed.
                </p>
              </div>
            </div>

            <div class="actuator-config__recipe-hint">
              <p class="actuator-config__helper">
                Stock ansetzen (Wasser → Gramm) jetzt im Nährlösung-Tab.
              </p>
              <RouterLink
                v-if="currentTankId"
                :to="tankDetailHref(currentTankId)"
                class="actuator-config__seed-btn"
              >
                Zum Tank im Nährlösung-Tab
              </RouterLink>
              <RouterLink
                v-else
                :to="{ name: 'nutrient-solution' }"
                class="actuator-config__seed-btn"
              >
                Zum Nährlösung-Tab
              </RouterLink>
            </div>

            <div class="actuator-config__seed-secondary">
              <button
                type="button"
                class="actuator-config__seed-btn"
                title="Platzhalter, bis du misst — kein Ersatz für den Assistenten"
                aria-label="Groben Seed etwa 100 setzen — Platzhalter bis zur Messung"
                @click="applyRoughConcentrationSeed"
              >
                Groben Seed (~100) setzen
              </button>
              <span class="actuator-config__helper">
                Optionaler Platzhalter für das Konzentrationsfeld oben — bis Auto-Cal oder manuelle Messung.
              </span>
            </div>
          </li>

          <li class="actuator-config__stock-step">
            <div class="actuator-config__stock-step-head">
              <span class="actuator-config__stock-step-num" aria-hidden="true">2</span>
              <div>
                <h3 class="actuator-config__stock-step-title">Anschließen — {{ actuatorDoseLabel }}</h3>
                <p class="actuator-config__calib-hint">
                  Lösung an {{ actuatorDoseLabel }} anschließen (Schlauch / Kanister).
                </p>
              </div>
            </div>
          </li>

          <li class="actuator-config__stock-step">
            <div class="actuator-config__stock-step-head">
              <span class="actuator-config__stock-step-num" aria-hidden="true">3</span>
              <div>
                <h3 class="actuator-config__stock-step-title">Manuell messen — {{ actuatorDoseLabel }}</h3>
                <p class="actuator-config__calib-hint">
                  Optionaler Extra-Dosierlauf — nur wenn du nicht auf Auto-Cal warten willst.
                </p>
              </div>
            </div>

            <div class="actuator-config__calib-wizard">
              <button
                v-if="!(calibWizardOpen && calibMode === 'concentration')"
                type="button"
                class="actuator-config__wizard-btn"
                aria-label="Manuellen Konzentrations-Assistenten starten (Fallback)"
                @click="openCalibWizard('concentration')"
              >
                Manuell messen (Fallback)
              </button>

              <div v-else class="actuator-config__calib-panel">
                <template v-if="calibPhase === 'setup'">
                  <p class="actuator-config__calib-hint">
                    Empirische Messung: EC₀ (System) → bekannte Dosis → Settle → EC₁ →
                    concentration = (EC₁−EC₀)×V_l/dose_ml. Förderrate muss gesetzt sein.
                  </p>
                  <div class="actuator-config__field">
                    <label class="actuator-config__label">Tankvolumen V_l</label>
                    <div class="actuator-config__input-with-unit">
                      <input
                        v-model.number="concVolumeL"
                        type="number"
                        min="0.1"
                        step="0.1"
                        class="actuator-config__input"
                        aria-label="Tankvolumen in Litern"
                      />
                      <span class="actuator-config__unit">L</span>
                    </div>
                    <span class="actuator-config__helper">{{ concVolumeHint || 'Manuell — Ist-Volumen messen ist der größte Fehlerhebel.' }}</span>
                  </div>
                  <div class="actuator-config__field">
                    <label class="actuator-config__label">Testdosis</label>
                    <div class="actuator-config__input-with-unit">
                      <input v-model.number="concDoseMl" type="number" min="0.1" step="0.1" class="actuator-config__input" aria-label="Testdosis in Millilitern" />
                      <span class="actuator-config__unit">ml</span>
                    </div>
                    <span v-if="concDoseDuration != null" class="actuator-config__helper">
                      Laufzeit ≈ {{ concDoseDuration }} s (ceil(ml / {{ flowRateMls }} ml/s))
                    </span>
                    <span v-else class="actuator-config__helper actuator-config__helper--warn">
                      Förderrate fehlt — zuerst oben „Förderrate kalibrieren“.
                    </span>
                  </div>
                  <div class="actuator-config__field">
                    <label class="actuator-config__label">Settle nach Dosis</label>
                    <div class="actuator-config__input-with-unit">
                      <input v-model.number="concSettleSeconds" type="number" min="0" max="600" step="1" class="actuator-config__input" aria-label="Settle-Sekunden" />
                      <span class="actuator-config__unit">Sek.</span>
                    </div>
                  </div>
                  <label class="actuator-config__checkbox">
                    <input v-model="concPairScale" type="checkbox" />
                    Paar-Messung: Partner-Seed (A↔B) mit gemeinsamem k skalieren
                  </label>
                  <p class="actuator-config__calib-hint">
                    Aktueller System-EC:
                    {{ liveSystemEcUsCm == null ? '—' : `${liveSystemEcUsCm.toFixed(0)} µS/cm` }}
                  </p>
                  <div class="actuator-config__calib-actions">
                    <button
                      type="button"
                      class="actuator-config__calib-start"
                      :disabled="concDoseDuration == null || !concVolumeL || concVolumeL <= 0"
                      @click="startConcDoseRun"
                    >
                      Dosierlauf starten
                    </button>
                    <button type="button" class="actuator-config__calib-cancel" @click="closeCalibWizard">Abbrechen</button>
                  </div>
                </template>

                <template v-else-if="calibPhase === 'running' || calibPhase === 'settle'">
                  <p class="actuator-config__calib-hint">
                    {{ calibPhase === 'running' ? 'Dosierung läuft — Pumpe stoppt automatisch.' : 'Settle — Warte auf Durchmischung vor EC₁.' }}
                  </p>
                  <div class="actuator-config__calib-countdown">{{ calibSecondsLeft }} s</div>
                  <button type="button" class="actuator-config__e-stop" aria-label="Notfall-Stopp" @click="emergencyStopFromWizard">
                    <OctagonAlert class="w-4 h-4" aria-hidden="true" />
                    Notfall-Stopp
                  </button>
                </template>

                <template v-else-if="calibPhase === 'measure'">
                  <p class="actuator-config__calib-hint">Messung abgeschlossen. Prüfe Werte und übernehme.</p>
                  <p class="actuator-config__calib-result">
                    EC₀ {{ concEc0 == null ? '—' : concEc0.toFixed(0) }} →
                    EC₁ {{ concEc1 == null ? '—' : concEc1.toFixed(0) }} µS/cm
                  </p>
                  <p v-if="concComputed != null" class="actuator-config__calib-result">
                    Konzentration: {{ concComputed }} µS/cm pro ml·L
                    (= ({{ concEc1!.toFixed(0) }}−{{ concEc0!.toFixed(0) }}) × {{ concVolumeL }} / {{ concDoseMl }})
                  </p>
                  <p v-else class="actuator-config__helper actuator-config__helper--warn">
                    Kein gültiger Wert — EC₁/EC₀/V_l prüfen.
                  </p>
                  <div class="actuator-config__calib-actions">
                    <button type="button" class="actuator-config__calib-start" :disabled="concComputed == null || saving" @click="applyConcResult">
                      {{ saving ? 'Speichert...' : 'Übernehmen & Speichern' }}
                    </button>
                    <button type="button" class="actuator-config__calib-cancel" @click="finishConcMeasure">
                      EC₁ erneut lesen
                    </button>
                    <button type="button" class="actuator-config__calib-cancel" @click="closeCalibWizard">Abbrechen</button>
                  </div>
                </template>

                <template v-else-if="calibPhase === 'done'">
                  <p class="actuator-config__calib-result">Konzentration gespeichert: {{ concentration }} µS/cm pro ml·L</p>
                  <div class="actuator-config__calib-actions">
                    <button type="button" class="actuator-config__calib-cancel" @click="closeCalibWizard">Fertig</button>
                  </div>
                </template>
              </div>
            </div>
          </li>
        </ol>
        </details>
      </div>

      <!-- Tab: Sicherheit -->
      <div v-show="activeTab === 'sicherheit'" class="actuator-config__tab-panel">
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
            <span class="actuator-config__helper">Mindestabstand zwischen zwei Pumpenlaeufen. 0 = kein Cooldown. Standard: 60 Sek.</span>
          </div>
        </template>

        <template v-else-if="isValve">
          <div class="actuator-config__field">
            <label class="actuator-config__label">Geraete-Sicherheitslimit</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="maxOpenTime" type="number" min="1" class="actuator-config__input" />
              <span class="actuator-config__unit">Sek. ({{ formatDuration(maxOpenTime) }})</span>
            </div>
            <span class="actuator-config__helper">Absolute Sicherheitsgrenze — greift unabhaengig von Regeln, auch bei manuellen Befehlen. Bei Ueberschreitung: Emergency Stop (Ventil gesperrt bis manueller Reset).</span>
          </div>
        </template>

        <template v-else-if="isPWM">
          <div class="actuator-config__field">
            <label class="actuator-config__label">Leistungs-Limit (Safety)</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="powerLimit" type="number" min="0" max="100" class="actuator-config__input" />
              <span class="actuator-config__unit">%</span>
            </div>
          </div>
        </template>

        <template v-else-if="isRelay">
          <div class="actuator-config__field">
            <label class="actuator-config__label">Geraete-Sicherheitslimit</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="maxRuntime" type="number" min="0" class="actuator-config__input" />
              <span class="actuator-config__unit">Sek. ({{ formatDuration(maxRuntime) }})</span>
            </div>
            <span class="actuator-config__helper">Absolute Sicherheitsgrenze fuer Relais/Aktorlaufzeit. 0 = unbegrenzt (empfohlen fuer Dauerlicht).</span>
          </div>
          <div class="actuator-config__field">
            <label class="actuator-config__label">Mindest-Pause zwischen Schaltungen</label>
            <div class="actuator-config__input-with-unit">
              <input v-model.number="minPause" type="number" min="0" class="actuator-config__input" />
              <span class="actuator-config__unit">Sek.</span>
            </div>
            <span class="actuator-config__helper">Mindestabstand zwischen zwei Schaltvorgaengen. 0 = kein Cooldown. Standard: 60 Sek.</span>
          </div>
        </template>
      </div>

      <!-- Tab: Alerts & Wartung -->
      <div v-show="activeTab === 'alerts'" class="actuator-config__tab-panel">
        <!-- AUT-252: Aktor-Datenblatt (read-only, aus ACTUATOR_TYPE_CONFIG) -->
        <AccordionSection
          title="Aktor-Datenblatt"
          :storage-key="`${accordionKey}-datasheet`"
          :icon="FileText"
          :default-open="true"
        >
          <div v-if="hasActuatorDatasheet && actuatorTypeConfig" class="actuator-config__datasheet">
            <div class="actuator-config__datasheet-row">
              <span class="actuator-config__datasheet-label">Typ</span>
              <span class="actuator-config__datasheet-value">{{ actuatorTypeConfig.label }} ({{ selectedActuatorType }})</span>
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
      </div>

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

.actuator-config__simulation-badge {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(167, 139, 250, 0.35);
  background: rgba(167, 139, 250, 0.1);
  color: var(--color-mock);
  font-size: var(--text-xs);
  font-weight: 600;
}

/* AUT-1127 (S2): Tab-Inhalt (ersetzt Akkordeon-Zonen 1+2) */
.actuator-config__tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-top: var(--space-1);
}

.actuator-config__wizard-btn {
  align-self: flex-start;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: not-allowed;
}

/* AUT-1357: einheitliche Kalibrier-Karten + 3-Schritt-Flow */
.actuator-config__calib-card,
.actuator-config__stock-step {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--glass-bg-l1);
  min-width: 0;
  overflow: hidden;
}

.actuator-config__calib-card-title,
.actuator-config__stock-step-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: var(--leading-normal);
  word-break: break-word;
}

.actuator-config__manual-assist {
  margin-top: var(--space-3);
  border: 1px solid var(--color-border-subtle, var(--color-border));
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-elevated, transparent);
}

.actuator-config__manual-assist-summary {
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
  list-style-position: outside;
}

.actuator-config__manual-assist-note {
  margin: var(--space-2) 0 var(--space-3);
}

.actuator-config__stock-flow {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.actuator-config__stock-step-head {
  display: flex;
  gap: var(--space-2);
  align-items: flex-start;
  min-width: 0;
}

.actuator-config__stock-step-head > div {
  min-width: 0;
  flex: 1;
}

.actuator-config__stock-step-num {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: var(--radius-full);
  background: var(--color-iridescent-1);
  color: var(--color-bg-primary);
  font-size: var(--text-xs);
  font-weight: 700;
}

.actuator-config__stock-step-title {
  margin: 0 0 var(--space-1);
}

/* AUT-1387: Rezept-Rechner ist in den Nährlösung-Tab gewandert (TankStockMixRecipePanel) —
   hier nur noch der Hinweis-Link + Notfall-Seed, siehe .actuator-config__recipe-hint. */
.actuator-config__recipe-hint {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-2);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  min-width: 0;
}

.actuator-config__seed-secondary {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-top: var(--space-1);
  padding-top: var(--space-2);
  border-top: 1px dashed var(--glass-border);
}

.actuator-config__seed-btn {
  align-self: flex-start;
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: pointer;
}

.actuator-config__seed-btn:hover {
  color: var(--color-text-secondary);
  border-color: var(--color-text-muted);
}

.actuator-config__checkbox {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.actuator-config__e-stop {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  align-self: center;
  padding: var(--space-2) var(--space-3);
  background: var(--color-danger);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-sm);
  font-weight: 700;
  cursor: pointer;
}

.actuator-config__e-stop:hover {
  filter: brightness(1.1);
}

/* AUT-1001: Gefuehrter Kalibrier-Assistent */
.actuator-config__wizard-btn--active {
  border-style: solid;
  color: var(--color-iridescent-1);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.actuator-config__wizard-btn--active:hover {
  color: var(--color-text-primary);
  border-color: var(--color-iridescent-1);
  background: var(--color-bg-tertiary);
}

.actuator-config__calib-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
  min-width: 0;
}

.actuator-config__calib-panel .actuator-config__field {
  margin: 0;
}

.actuator-config__calib-panel .actuator-config__helper {
  margin-top: var(--space-1);
}

.actuator-config__calib-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.actuator-config__calib-hint {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-normal);
}

.actuator-config__calib-countdown {
  align-self: center;
  font-size: var(--text-2xl);
  font-weight: 700;
  font-family: var(--font-mono);
  color: var(--color-iridescent-1);
}

.actuator-config__calib-result {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.actuator-config__calib-start {
  padding: var(--space-2) var(--space-3);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.actuator-config__calib-start:hover:not(:disabled) { filter: brightness(1.1); }
.actuator-config__calib-start:disabled { opacity: 0.5; cursor: not-allowed; }

.actuator-config__calib-cancel {
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.actuator-config__calib-cancel:hover { color: var(--color-text-primary); border-color: var(--color-text-secondary); }

.actuator-config__helper--warn {
  color: var(--color-warning);
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

/* Config toggles use shared .toggle-switch from main.css */

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
