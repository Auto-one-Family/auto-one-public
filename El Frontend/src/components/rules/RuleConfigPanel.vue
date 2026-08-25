<script setup lang="ts">
/**
 * RuleConfigPanel
 *
 * Right sidebar for configuring selected node properties.
 * Dynamically renders form fields based on node type:
 * - sensor: ESP, GPIO, sensor type, operator, value
 * - time: start/end hour+minute, days of week
 * - logic: AND/OR toggle
 * - actuator: ESP, GPIO, command, value, duration
 * - notification: channel, target, message
 * - delay: seconds
 * - plugin: plugin selection with dynamic config from schema
 */

import { computed, watch, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  X,
  Thermometer,
  Clock,
  GitMerge,
  Power,
  Bell,
  Timer,
  Puzzle,
  Trash2,
  Copy,
  Download,
  ListOrdered,
  GripVertical,
  ShieldOff,
  ArrowLeftRight,
} from 'lucide-vue-next'
import { VueDraggable } from 'vue-draggable-plus'
import { useEspStore } from '@/stores/esp'
import { useLogicStore } from '@/shared/stores/logic.store'
import { getSensorUnit, isMultiValueBaseType, getSensorAggCategory } from '@/utils/sensorDefaults'
import { resolveActuatorSemanticType, isPumpActuatorType } from '@/utils/actuatorDefaults'
import { useSensorOptions } from '@/composables/useSensorOptions'
import { pluginsApi, type PluginDTO } from '@/api/plugins'
import { sensorsApi } from '@/api/sensors'
import { actuatorsApi } from '@/api/actuators'
import { useToast } from '@/composables/useToast'
import type { Node } from '@vue-flow/core'
import type { MockActuator } from '@/types'
import type { SequenceStepDraft } from '@/types/logic'
import { sequenceStepNumber, sequenceStepTypeLabel } from '@/utils/sequenceStepDisplay'
import {
  doseDriveModeLabel,
  doseMlToDurationSeconds,
  durationSecondsToMlEquivalent,
  isStepDurationReadonly,
  resolveDoseDriveMode,
  resolveStepDoseMode,
  stepDoseModeHelp,
  stepDoseModeOptionLabel,
  stepEffectiveModeBadgeLabel,
  type StepDoseMode,
} from '@/utils/sequenceDoseDisplay'
import MeasureBindingEditor from '@/components/rules/MeasureBindingEditor.vue'
import BaseToggle from '@/shared/design/primitives/BaseToggle.vue'
import BaseSelect from '@/shared/design/primitives/BaseSelect.vue'
import {
  createEmptyBinding,
  measureBindingFromNodeData,
  measureBindingToNodeData,
  setMeasureBindings,
} from '@/utils/measureBindings'
import { coerceLocaleNumberInput, parseLocaleNumber } from '@/utils/parseLocaleNumber'

interface SelectOption {
  value: string
  label: string
}

interface Props {
  node: Node | null
  validationErrors?: Record<string, string[]>
  /** AUT-1134 (B7): rule-level rule_metadata (dose_config, paired_rule_id, ...) — read-only mirror,
   * updated via 'update:rule-metadata' since it lives on the rule, not on this node. */
  ruleMetadata?: Record<string, unknown>
  /** AUT-1284: Pumpen-Aktoren der GESAMTEN Regel in Rule-Reihenfolge (Top-Level-Actions +
   * Sequenz-Schritte zusammen gezaehlt, identisch zur Server-Positionslogik in
   * logic_engine.py::_compute_chemistry_dose_ml) — Index i entspricht Chemie-Komponente Ki.
   * Wird von LogicView.vue aus dem aktuellen Graph berechnet (kein zweiter Schreibpfad hier). */
  rulePumpActuators?: { espId: string; gpio: number; name?: string }[]
  /**
   * AUT-1303: Max. Dosis/Tag (ml) — Regel-Spalte `max_dose_ml_per_day`, UI nur bei dosierfaehigem
   * Aktor (H-1: generische Pumpe). Canonical write in LogicView.saveRule; hier nur Edit-Oberflaeche.
   * Default 0 = kein Limit (Server rate_limiter: falsy → unlimited).
   */
  maxDoseMlPerDay?: number
  /**
   * AUT-1389: Tank-Plan (regelweit follows_plan) — State lebt in LogicView.
   * UI nur Tank-Wahl; Zone/Subzone/Domain/Measure werden abgeleitet.
   */
  followsPlan?: boolean
  planTankId?: string
  planTankOptions?: SelectOption[]
  /** Menschenlesbare Wirksam-Zeile */
  planEffectiveDeadbandLabel?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  maxDoseMlPerDay: 0,
  followsPlan: false,
  planTankOptions: () => [],
  planEffectiveDeadbandLabel: null,
})

const emit = defineEmits<{
  'update:data': [nodeId: string, data: Record<string, unknown>]
  'update:rule-metadata': [metadata: Record<string, unknown>]
  'update:max-dose-ml-per-day': [value: number]
  'update:follows-plan': [value: boolean]
  'update:plan-tank-id': [value: string | undefined]
  close: []
  'delete-node': [nodeId: string]
  'duplicate-node': [nodeId: string]
}>()

const espStore = useEspStore()
const logicStore = useLogicStore()
const router = useRouter()
const toast = useToast()
const { groupedSensorOptions } = useSensorOptions()

/** ESP_XXXX oder DB-UUID — not_running speichert UUID, Aktor-Nodes device_id. */
function findDeviceByEspRef(espRef: string | undefined) {
  if (!espRef) return undefined
  return espStore.devices.find(
    (d) => espStore.getDeviceId(d) === espRef || d.id === espRef,
  )
}

// Load available plugins for plugin node config
const availablePlugins = ref<PluginDTO[]>([])
const pluginsLoaded = ref(false)

async function loadPlugins() {
  if (pluginsLoaded.value) return
  try {
    availablePlugins.value = await pluginsApi.list()
    pluginsLoaded.value = true
  } catch {
    // Non-critical — show empty list
  }
}

const nodeTypeLabels: Record<string, string> = {
  sensor: 'Sensor-Bedingung',
  time: 'Zeitfenster',
  logic: 'Logik-Verknüpfung',
  actuator: 'Aktor-Aktion',
  notification: 'Benachrichtigung',
  delay: 'Verzögerung',
  plugin: 'Plugin-Aktion',
  // AUT-1281: "Unbekannt"-Bug — Sequenz-Node hatte keinen Label/Icon-Eintrag.
  sequence: 'Sequenz',
  not_running: 'Nicht laufend (Interlock)',
  // AUT-1399: sensor_diff umgewidmet → Mess-Bindung (nie „Unbekannt“)
  sensor_diff: 'Mess-Bindung',
}

const nodeTypeIcons: Record<string, typeof Thermometer> = {
  sensor: Thermometer,
  time: Clock,
  logic: GitMerge,
  actuator: Power,
  notification: Bell,
  delay: Timer,
  plugin: Puzzle,
  sequence: ListOrdered,
  not_running: ShieldOff,
  sensor_diff: ArrowLeftRight,
}

const operatorOptions = [
  { value: '>', label: 'größer als (>)' },
  { value: '>=', label: 'größer gleich (≥)' },
  { value: '<', label: 'kleiner als (<)' },
  { value: '<=', label: 'kleiner gleich (≤)' },
  { value: '==', label: 'gleich (=)' },
  { value: '!=', label: 'ungleich (≠)' },
  { value: 'between', label: 'zwischen (↔)' },
  { value: 'hysteresis', label: 'Hysterese (Ein/Aus-Schwellen)' },
]

const sensorTypeOptions = [
  { value: 'DS18B20', label: 'DS18B20 (Temperatur)' },
  { value: 'sht31_temp', label: 'SHT31 Temperatur (°C)' },
  { value: 'sht31_humidity', label: 'SHT31 Luftfeuchtigkeit (%RH)' },
  { value: 'bmp280_temp', label: 'BMP280 Temperatur (°C)' },
  { value: 'bmp280_pressure', label: 'BMP280 Druck (hPa)' },
  { value: 'bme280_temp', label: 'BME280 Temperatur (°C)' },
  { value: 'bme280_humidity', label: 'BME280 Luftfeuchtigkeit (%RH)' },
  { value: 'bme280_pressure', label: 'BME280 Druck (hPa)' },
  { value: 'pH', label: 'pH-Sensor' },
  { value: 'EC', label: 'EC (Leitfähigkeit)' },
  { value: 'moisture', label: 'Bodenfeuchte' },
  { value: 'light', label: 'Lichtsensor' },
  { value: 'co2', label: 'CO2-Sensor' },
  { value: 'flow', label: 'Durchflusssensor' },
  { value: 'level', label: 'Füllstandsensor' },
]

// Maps each conditionCategory to a sensor-type predicate for filtering
const CONDITION_CATEGORY_FILTER: Record<string, (st: string) => boolean> = {
  humidity:    (st) => getSensorAggCategory(st) === 'humidity',
  ph:          (st) => getSensorAggCategory(st) === 'ph',
  ec:          (st) => getSensorAggCategory(st) === 'ec',
  co2:         (st) => getSensorAggCategory(st) === 'co2',
  moisture:    (st) => getSensorAggCategory(st) === 'moisture',
  light:       (st) => getSensorAggCategory(st) === 'light',
  temperature: (st) => getSensorAggCategory(st) === 'temperature',
  level:       (st) => st === 'level',
}

const commandOptions = [
  { value: 'ON', label: 'Einschalten (ON)' },
  { value: 'OFF', label: 'Ausschalten (OFF)' },
  { value: 'PWM', label: 'PWM-Wert setzen' },
  { value: 'TOGGLE', label: 'Umschalten (TOGGLE)' },
]

const channelOptions = [
  { value: 'websocket', label: 'WebSocket (Dashboard)' },
  { value: 'email', label: 'E-Mail' },
  { value: 'webhook', label: 'Webhook' },
]

const dayLabels = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

// Local editable copy of node data
const localData = ref<Record<string, unknown>>({})

// Sync when node changes
watch(
  () => props.node,
  (newNode) => {
    if (newNode) {
      localData.value = { ...newNode.data }
      // Lazy-load plugins when a plugin node is selected
      if (newNode.type === 'plugin') {
        loadPlugins()
      }
    }
  },
  { immediate: true, deep: true }
)

// Emit on changes
function updateField(key: string, value: unknown) {
  localData.value[key] = value
  if (props.node) {
    emit('update:data', props.node.id, { ...localData.value })
  }
}

function updateStep(idx: number, field: string, value: unknown): void {
  const steps = [...((localData.value.steps ?? []) as SequenceStepDraft[])]
  steps[idx] = { ...steps[idx], [field]: value }
  updateField('steps', steps)
}

function addStep(stepType: 'actuator' | 'delay'): void {
  const steps = [...((localData.value.steps ?? []) as SequenceStepDraft[])]
  if (stepType === 'actuator') {
    steps.push({ stepType: 'actuator', command: 'ON', duration: 30 })
  } else {
    steps.push({ stepType: 'delay', seconds: 60 })
  }
  updateField('steps', steps)
}

function removeStep(idx: number): void {
  const steps = [...((localData.value.steps ?? []) as SequenceStepDraft[])]
  steps.splice(idx, 1)
  updateField('steps', steps)
}

// AUT-1281: ziehbare Kette — VueDraggable v-model auf einer writable computed, die ueber
// updateField zurueck ins node.data schreibt (Pattern analog zu rulePairedRuleId in LogicView.vue).
// vue-draggable-plus emittiert bei jeder Sortierung 'update:modelValue' mit dem neu geordneten
// Array (siehe PlantSubzoneArea.vue fuer das cross-list Pendant) — hier reicht die Computed-Bruecke.
const sequenceSteps = computed<SequenceStepDraft[]>({
  get: () => (localData.value.steps ?? []) as SequenceStepDraft[],
  set: (v) => updateField('steps', v),
})

// AUT-1281: Dosis-Modus je Sequenz-Schritt — nur fuer Pumpen relevant (Foerderrate).
// Lookup aus espStore (device.actuators), analog zu availableActuators/selectedActuatorType oben,
// aber schritt-lokal (jeder Schritt kann einen anderen Aktor ansteuern).
// AUT-1302: prefer hardware_type over server-normalized actuator_type ("digital").
function stepActuatorType(step: SequenceStepDraft): string | null {
  if (!step.espId || step.gpio == null) return null
  const device = espStore.devices.find((d) => espStore.getDeviceId(d) === step.espId)
  const actuator = (device?.actuators as MockActuator[] | undefined)?.find((a) => a.gpio === step.gpio)
  if (!actuator) return null
  const semantic = resolveActuatorSemanticType(actuator.actuator_type, actuator.hardware_type)
  return semantic || null
}

function isStepPump(step: SequenceStepDraft): boolean {
  return stepActuatorType(step) === 'pump'
}

// AUT-1281/AUT-1284: Cache der Foerderrate je "espId:gpio" — vermeidet doppelte
// GET /actuators/{esp}/{gpio}, wenn mehrere Sequenz-Schritte ODER Chemie-Komponenten
// denselben Aktor referenzieren. null = geladen, aber nicht kalibriert.
const flowRateCache = ref<Record<string, number | null>>({})
/** AUT-1390: concentration parallel zum flow_rate-Cache (ein GET, zwei Felder). */
const concentrationCache = ref<Record<string, number | null>>({})

async function fetchFlowRateFor(espId: string, gpio: number): Promise<void> {
  const key = `${espId}:${gpio}`
  if (key in flowRateCache.value) return
  try {
    const cfg = await actuatorsApi.get(espId, gpio)
    flowRateCache.value = { ...flowRateCache.value, [key]: cfg?.flow_rate_ml_s ?? null }
    concentrationCache.value = {
      ...concentrationCache.value,
      [key]: cfg?.concentration ?? null,
    }
  } catch {
    flowRateCache.value = { ...flowRateCache.value, [key]: null }
    concentrationCache.value = { ...concentrationCache.value, [key]: null }
  }
}

function getFlowRateFor(espId: string | undefined, gpio: number | undefined): number | null | undefined {
  if (!espId || gpio == null) return undefined
  return flowRateCache.value[`${espId}:${gpio}`]
}

function getConcentrationFor(
  espId: string | undefined,
  gpio: number | undefined,
): number | null | undefined {
  if (!espId || gpio == null) return undefined
  return concentrationCache.value[`${espId}:${gpio}`]
}

// Nachlade-Watch (AUT-1281): sobald ein Sequenz-Schritt einen Aktor (espId+gpio) trägt, dessen
// Foerderrate noch nicht im Cache steht, wird sie einmalig nachgeladen (kein Fetch im Template).
watch(
  () => (localData.value.steps as SequenceStepDraft[] | undefined),
  (steps) => {
    for (const step of steps ?? []) {
      if (step.stepType === 'actuator' && step.espId && step.gpio != null) {
        void fetchFlowRateFor(step.espId, step.gpio)
      }
    }
  },
  { immediate: true, deep: true },
)

function getStepFlowRate(step: SequenceStepDraft): number | null | undefined {
  return getFlowRateFor(step.espId, step.gpio)
}

function getStepConcentration(step: SequenceStepDraft): number | null | undefined {
  return getConcentrationFor(step.espId, step.gpio)
}

// AUT-1281 / AUT-1376 A2.3: ml↔s-Äquivalente — Anzeige-only, Server/FW bleiben duration-basiert.
function stepDerivedDurationSeconds(step: SequenceStepDraft): number | null {
  return doseMlToDurationSeconds(step.dose_ml, getStepFlowRate(step))
}

function stepDerivedMlFromDuration(step: SequenceStepDraft): number | null {
  const mode = resolveStepDoseMode(step.dose_mode, step.dose_ml)
  if (mode === 'ml' || (mode === 'target_optimal' && isStepDurationReadonly(
    step.dose_mode,
    step.dose_ml,
    getStepFlowRate(step),
  ))) {
    return null
  }
  if (resolveDoseDriveMode(step.dose_ml) === 'ml_driven' && mode !== 'duration') return null
  return durationSecondsToMlEquivalent(step.duration, getStepFlowRate(step))
}

/** AUT-1390: wirksamer Badge-Text (Modus-Intent + Runtime-Matrix fuer target_optimal). */
function stepDoseModeLabel(step: SequenceStepDraft): string {
  return stepEffectiveModeBadgeLabel(
    step.dose_mode,
    step.dose_ml,
    getStepFlowRate(step),
    getStepConcentration(step),
  )
}

function stepDoseModeValue(step: SequenceStepDraft): StepDoseMode {
  return resolveStepDoseMode(step.dose_mode, step.dose_ml)
}

function isStepMlDriven(step: SequenceStepDraft): boolean {
  return isStepDurationReadonly(step.dose_mode, step.dose_ml, getStepFlowRate(step))
}

const STEP_DOSE_MODE_OPTIONS: StepDoseMode[] = ['duration', 'ml', 'target_optimal']

const topLevelDoseModeLabel = computed(() =>
  doseDriveModeLabel(resolveDoseDriveMode(localData.value.dose_ml as number | undefined)),
)

const isTopLevelMlDriven = computed(
  () => resolveDoseDriveMode(localData.value.dose_ml as number | undefined) === 'ml_driven',
)

function updateStepDoseMl(idx: number, raw: string): void {
  const v = parseLocaleNumber(raw)
  updateStep(idx, 'dose_ml', Number.isFinite(v) && v > 0 ? v : undefined)
}

/**
 * AUT-1390: Modus-Selektor — setzt Meta-Flag dose_mode.
 * duration → dose_ml leeren (sonst Server-Präzedenz ml).
 * ml / target_optimal → Flag setzen; Felder bleiben editierbar.
 */
function updateStepDoseMode(idx: number, mode: StepDoseMode): void {
  const steps = [...((localData.value.steps ?? []) as SequenceStepDraft[])]
  const prev = steps[idx]
  if (!prev) return
  const next: SequenceStepDraft = { ...prev, dose_mode: mode }
  if (mode === 'duration') {
    next.dose_ml = undefined
  }
  steps[idx] = next
  updateField('steps', steps)
}

const planThresholdsLocked = computed(
  () => props.followsPlan === true,
)

function parseNumericOrNull(value: string): number | string | null {
  return coerceLocaleNumberInput(value)
}

function toggleDay(day: number) {
  const days = (localData.value.daysOfWeek as number[]) || []
  const idx = days.indexOf(day)
  const updated = idx >= 0 ? days.filter((d) => d !== day) : [...days, day].sort()
  updateField('daysOfWeek', updated)
}

function isDayActive(day: number): boolean {
  const days = (localData.value.daysOfWeek as number[]) || []
  return days.includes(day)
}

const nodeType = computed(() => props.node?.type || '')
const hasValidationErrors = computed(() => Object.keys(props.validationErrors ?? {}).length > 0)

function fieldError(field: string): string | null {
  const list = props.validationErrors?.[field]
  return list?.[0] ?? null
}

// Warn when rule uses base type (SHT31, BME280) instead of explicit sub-type
const showMultiValueBaseTypeWarning = computed(() => {
  if (nodeType.value !== 'sensor') return false
  const st = localData.value.sensorType as string
  return st ? isMultiValueBaseType(st) : false
})
/** AUT-1273: canonical unit for threshold inputs (EC → µS/cm via sensorDefaults SSOT) */
const thresholdUnit = computed(() => {
  const st = localData.value.sensorType as string | undefined
  if (!st) return ''
  const unit = getSensorUnit(st)
  return unit && unit !== 'raw' ? unit : ''
})
const typeLabel = computed(() => nodeTypeLabels[nodeType.value] || 'Unbekannt')
const typeIcon = computed(() => nodeTypeIcons[nodeType.value] || Thermometer)

// Available ESP devices for selectors (with zone context + fallback for unknown IDs)
const espDevices = computed(() => {
  const devices = espStore.devices.map((d) => {
    const id = espStore.getDeviceId(d)
    const baseName = d.name || id
    const zoneName = d.zone_name || d.zone_id
    return {
      id,
      name: zoneName ? `${baseName} — ${zoneName}` : baseName,
    }
  })
  // If the node's saved espId is not in the device list, show it as unknown
  const currentEspId = localData.value.espId as string
  if (currentEspId && !devices.find(d => d.id === currentEspId)) {
    devices.unshift({ id: currentEspId, name: `${currentEspId} (nicht gefunden)` })
  }
  return devices
})

// All sensors on the selected ESP, unfiltered (used for fallback detection)
const allAvailableSensors = computed(() => {
  const espId = localData.value.espId as string
  if (!espId) return []
  const result: { gpio: number; sensorType: string; config_id?: string; label: string }[] = []
  for (const group of groupedSensorOptions.value) {
    for (const subgroup of group.subgroups) {
      for (const opt of subgroup.options) {
        if (opt.espId !== espId) continue
        result.push({
          gpio: opt.gpio,
          sensorType: opt.sensorType,
          config_id: opt.configId,
          label: `${opt.label} (GPIO ${opt.gpio})`,
        })
      }
    }
  }
  return result
})

// Device-aware: sensors on the selected ESP, filtered by conditionCategory when set
const availableSensors = computed(() => {
  const conditionCategory = localData.value.conditionCategory as string | undefined
  const categoryFilter = conditionCategory ? CONDITION_CATEGORY_FILTER[conditionCategory] : null
  if (!categoryFilter) return allAvailableSensors.value
  return allAvailableSensors.value.filter(s => categoryFilter(s.sensorType))
})

// Sensor type options for fallback manual mode, filtered by conditionCategory when set
const filteredSensorTypeOptions = computed(() => {
  const conditionCategory = localData.value.conditionCategory as string | undefined
  if (!conditionCategory) return sensorTypeOptions
  const categoryFilter = CONDITION_CATEGORY_FILTER[conditionCategory]
  if (!categoryFilter) return sensorTypeOptions
  return sensorTypeOptions.filter(opt => categoryFilter(opt.value))
})

// Device-aware: actuators on the currently selected ESP (actuator + interlock config)
const availableActuators = computed(() => {
  const espId = localData.value.espId as string
  if (!espId) return []
  const device = findDeviceByEspRef(espId)
  if (!device?.actuators) return []
  return (device.actuators as MockActuator[]).map(a => {
    const semanticType = resolveActuatorSemanticType(a.actuator_type, a.hardware_type) || a.actuator_type
    return {
      gpio: a.gpio,
      actuatorType: semanticType,
      name: a.name || `${semanticType} (GPIO ${a.gpio})`,
      label: a.name
        ? `${a.name} – ${semanticType} (GPIO ${a.gpio})`
        : `${semanticType} (GPIO ${a.gpio})`,
    }
  })
})

// AUT-1333: Interlock — Zone → Gerät → Aktor (esp_id = DB-UUID, nicht ESP_XXXX)
const UNASSIGNED_ZONE = '__none__'
const interlockZoneId = ref('')

const interlockZoneOptions = computed(() => {
  const zones = new Map<string, string>()
  for (const d of espStore.devices) {
    if (!d.id || !d.actuators?.length) continue
    const zid = d.zone_id || UNASSIGNED_ZONE
    const zname = d.zone_name || d.zone_id || 'Ohne Zone'
    if (!zones.has(zid)) zones.set(zid, zname)
  }
  return Array.from(zones.entries())
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name, 'de'))
})

const interlockDevicesInZone = computed(() => {
  const zone = interlockZoneId.value
  return espStore.devices
    .filter((d) => {
      if (!d.id || !d.actuators?.length) return false
      if (!zone) return true
      return (d.zone_id || UNASSIGNED_ZONE) === zone
    })
    .map((d) => ({
      uuid: d.id as string,
      name: d.name || espStore.getDeviceId(d),
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'de'))
})

const interlockRuleOptions = computed(() =>
  logicStore.rules
    .map((r) => ({ id: r.id, name: r.name }))
    .sort((a, b) => a.name.localeCompare(b.name, 'de')),
)

watch(
  () => [nodeType.value, localData.value.espId] as const,
  ([type, espId]) => {
    if (type !== 'not_running') return
    const device = findDeviceByEspRef(espId as string | undefined)
    if (device) {
      interlockZoneId.value = device.zone_id || UNASSIGNED_ZONE
    }
  },
  { immediate: true },
)

function handleInterlockZoneChange(zoneId: string): void {
  interlockZoneId.value = zoneId
  updateField('espId', '')
  updateField('gpio', undefined)
}

function handleInterlockEspChange(uuid: string): void {
  updateField('espId', uuid)
  updateField('gpio', undefined)
}

function handleInterlockTargetChange(target: string): void {
  updateField('target', target)
  if (target === 'sequence') {
    updateField('espId', '')
    updateField('gpio', undefined)
  } else {
    updateField('ruleId', '')
  }
}

// AUT-995 Feld 5/2b: actuator type of the currently selected actuator node (from store live data).
// AUT-1302: semantic type (hardware_type preferred) so isPumpActuator works for digital+pump rows.
const selectedActuatorType = computed<string | null>(() => {
  if (nodeType.value !== 'actuator' || localData.value.gpio == null) return null
  return availableActuators.value.find(a => a.gpio === localData.value.gpio)?.actuatorType ?? null
})

// AUT-995 Feld 5 / AUT-1131 (A1): informative effect-direction label (display-only).
// Reads the actuator's real actuator_metadata.inverted_logic (fetched alongside flow_rate_ml_s
// in fetchActuatorFlowRate() below) instead of assuming a fixed polarity per actuator_type —
// the DB value is the only source of truth (see ActuatorConfigPanel.vue toggle binding).
function getActuatorDirectionLabel(actuatorType: string): string {
  const type = actuatorType.toLowerCase()
  const inverted = selectedActuatorInvertedLogic.value === true
  if (['relay', 'digital', 'binary', 'switch'].includes(type)) {
    return inverted
      ? 'Schaltausgang — invertierte Logik aktiv: ON oeffnet den Kontakt, OFF schliesst ihn.'
      : 'Schaltausgang — ON schliesst den Kontakt, OFF oeffnet ihn.'
  }
  const invertedSuffix = inverted ? ' (invertierte Logik aktiv)' : ''
  if (type === 'pump') return `Pumpe dosiert Fluessigkeit — ON startet, OFF stoppt (oder duration/Dosis laeuft ab).${invertedSuffix}`
  if (type === 'valve') return `Ventil steuert Wasserfluss — ON oeffnet, OFF schliesst.${invertedSuffix}`
  if (type === 'pwm') return `Leistungsregelung (0–100 %) ueber den PWM-Wert.${invertedSuffix}`
  return ''
}

// Handle ESP change in sensor config → reset sensor-specific fields
function handleSensorEspChange(espId: string) {
  updateField('espId', espId)
  updateField('gpio', undefined)
  updateField('sensorType', '')
}

// Handle ESP change in actuator config → reset actuator-specific fields
function handleActuatorEspChange(espId: string) {
  updateField('espId', espId)
  updateField('gpio', undefined)
}

// L3-FE-3 reactivated as AUT-1133: Duration vs. device safety limit warning.
// max_runtime_seconds/cooldown_seconds are on MockActuatorConfig (config push),
// not on MockActuator (live state in store) — fetched via fetchActuatorFlowRate()
// (same ActuatorConfigResponse as flow_rate_ml_s, no extra API call).

// Computed for sensor dropdown: value "gpio:sensorType" for multi-value disambiguation
const sensorDropdownValue = computed({
  get: () => {
    const gp = localData.value.gpio as number | undefined
    const st = localData.value.sensorType as string | undefined
    if (gp === undefined || gp === null) return ''
    const match = availableSensors.value.find(s => s.gpio === gp && s.sensorType === st)
    if (match) return `${gp}:${st}`
    // Base type (SHT31, BME280): don't auto-select — force user to choose explicit sub-type
    if (st && isMultiValueBaseType(st)) return ''
    // Fallback: first sensor with same gpio (legacy rules without sensorType)
    const fallback = availableSensors.value.find(s => s.gpio === gp)
    return fallback ? `${gp}:${fallback.sensorType}` : ''
  },
  set: (v: string | number) => selectSensor(v),
})

// Select sensor from device-aware dropdown → auto-fill gpio + sensorType
// Value format: "gpio:sensorType" (e.g. "0:sht31_humidity") for multi-value disambiguation
function selectSensor(value: string | number) {
  if (value === '' || value === undefined || value === null) {
    updateField('gpio', undefined)
    updateField('sensorType', '')
    return
  }
  let gpio: number
  let sensorType: string
  const strVal = String(value)
  if (strVal.includes(':')) {
    const [g, t] = strVal.split(':')
    gpio = parseInt(g, 10)
    sensorType = t || ''
  } else {
    gpio = typeof value === 'number' ? value : parseInt(strVal, 10)
    sensorType = availableSensors.value.find(s => s.gpio === gpio)?.sensorType ?? ''
  }
  const sensor = availableSensors.value.find(s => s.gpio === gpio && s.sensorType === sensorType)
  if (sensor) {
    updateField('gpio', sensor.gpio)
    updateField('sensorType', sensor.sensorType)
  }
}

// Select actuator from device-aware dropdown → auto-fill gpio
function selectActuator(value: string) {
  if (!value) {
    updateField('gpio', undefined)
    return
  }
  const gpio = Number(value)
  const actuator = availableActuators.value.find(a => a.gpio === gpio)
  if (actuator) {
    updateField('gpio', actuator.gpio)
  }
}

// =============================================================================
// AUT-246: Sync rule trigger value with sensor base threshold
// =============================================================================
//
// The rule's `value` field is INDEPENDENT from SensorConfig.thresholds by design
// (a rule can deliberately use a different threshold than the sensor alert).
// This helper allows the operator to opt-in to syncing — one-shot copy,
// no automatic re-sync. A small indicator shows whether the rule value
// matches the sensor's warning threshold.

interface SensorBaseThresholdsRule {
  warning_min: number | null
  warning_max: number | null
  alarm_min: number | null
  alarm_max: number | null
}

const ruleSensorBaseThresholds = ref<SensorBaseThresholdsRule | null>(null)
const ruleSensorBaseLoadedFor = ref<string | null>(null)
const isLoadingRuleThreshold = ref(false)

function ruleSensorKey(): string | null {
  const espId = localData.value.espId as string | undefined
  const gpio = localData.value.gpio as number | undefined
  const sensorType = localData.value.sensorType as string | undefined
  if (!espId || gpio == null || !sensorType) return null
  return `${espId}:${gpio}:${sensorType}`
}

async function fetchRuleSensorBase(): Promise<void> {
  const espId = localData.value.espId as string | undefined
  const gpio = localData.value.gpio as number | undefined
  const sensorType = localData.value.sensorType as string | undefined
  if (!espId || gpio == null || !sensorType) {
    ruleSensorBaseThresholds.value = null
    return
  }
  const key = `${espId}:${gpio}:${sensorType}`
  if (ruleSensorBaseLoadedFor.value === key && ruleSensorBaseThresholds.value) return
  try {
    const cfg = await sensorsApi.get(espId, gpio, sensorType)
    if (cfg) {
      ruleSensorBaseThresholds.value = {
        warning_min: cfg.warning_min ?? null,
        warning_max: cfg.warning_max ?? null,
        alarm_min: cfg.threshold_min ?? null,
        alarm_max: cfg.threshold_max ?? null,
      }
    } else {
      ruleSensorBaseThresholds.value = null
    }
  } catch {
    ruleSensorBaseThresholds.value = null
  } finally {
    ruleSensorBaseLoadedFor.value = key
  }
}

watch(
  () => ruleSensorKey(),
  (key) => {
    if (key) {
      void fetchRuleSensorBase()
    } else {
      ruleSensorBaseThresholds.value = null
      ruleSensorBaseLoadedFor.value = null
    }
  },
  { immediate: true },
)

// AUT-995 Feld 2b: flow_rate_ml_s of the selected actuator for the live dose_ml → duration display.
// H-2: flow_rate_ml_s is NOT carried on the live store actuator object (like max_runtime_seconds),
// so we fetch it explicitly via GET /actuators/{esp_id}/{gpio} (mirrors fetchRuleSensorBase).
const selectedActuatorFlowRate = ref<number | null>(null)
const actuatorFlowRateLoadedFor = ref<string | null>(null)
// AUT-1133 (B1): Geräte-Sicherheitslimit + Mindest-Pause read-only im Aktor-Aktion-Panel —
// same ActuatorConfigResponse as flow_rate_ml_s above (L3-FE-3 reactivated, no extra API call).
const selectedActuatorMaxRuntimeSeconds = ref<number | null>(null)
const selectedActuatorCooldownSeconds = ref<number | null>(null)
// AUT-1131 (A1): actuator_metadata.inverted_logic — same ActuatorConfigResponse.metadata as
// ActuatorConfigPanel.vue's toggle binding, fetched here read-only for the direction label.
const selectedActuatorInvertedLogic = ref<boolean | null>(null)

async function fetchActuatorFlowRate(): Promise<void> {
  const espId = localData.value.espId as string | undefined
  const gpio = localData.value.gpio as number | undefined
  if (nodeType.value !== 'actuator' || !espId || gpio == null) {
    selectedActuatorFlowRate.value = null
    selectedActuatorMaxRuntimeSeconds.value = null
    selectedActuatorCooldownSeconds.value = null
    selectedActuatorInvertedLogic.value = null
    return
  }
  const key = `${espId}:${gpio}`
  if (actuatorFlowRateLoadedFor.value === key) return
  try {
    const cfg = await actuatorsApi.get(espId, gpio)
    selectedActuatorFlowRate.value = cfg?.flow_rate_ml_s ?? null
    selectedActuatorMaxRuntimeSeconds.value = cfg?.max_runtime_seconds ?? null
    selectedActuatorCooldownSeconds.value = cfg?.cooldown_seconds ?? null
    selectedActuatorInvertedLogic.value = !!cfg?.metadata?.inverted_logic
    // Only mark as loaded on success — a transient failure must stay retryable, otherwise
    // the guard above would freeze the node in an "uncalibrated" state forever.
    actuatorFlowRateLoadedFor.value = key
  } catch {
    selectedActuatorFlowRate.value = null
    selectedActuatorMaxRuntimeSeconds.value = null
    selectedActuatorCooldownSeconds.value = null
    selectedActuatorInvertedLogic.value = null
  }
}

watch(
  () => (nodeType.value === 'actuator' && localData.value.gpio != null
    ? `${localData.value.espId as string}:${localData.value.gpio as number}`
    : ''),
  (key) => {
    if (key) {
      void fetchActuatorFlowRate()
    } else {
      selectedActuatorFlowRate.value = null
      selectedActuatorMaxRuntimeSeconds.value = null
      selectedActuatorCooldownSeconds.value = null
      selectedActuatorInvertedLogic.value = null
      actuatorFlowRateLoadedFor.value = null
    }
  },
  { immediate: true },
)

// AUT-1133 (B1): "bearbeiten"-Link — reuses the existing hardware-esp navigation
// (same route + zone_id-fallback pattern as ESPHealthWidget.vue::navigateToDevice()).
function openActuatorInHardwarePanel(): void {
  const espId = localData.value.espId as string | undefined
  if (!espId) return
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === espId)
  if (device?.zone_id) {
    router.push({ name: 'hardware-esp', params: { zoneId: device.zone_id, espId } })
  } else {
    router.push({ name: 'hardware', query: { openSettings: espId } })
  }
}

// AUT-995 Feld 2: dose_ml input is only shown for pumps (needs flow_rate_ml_s to convert to duration).
const isPumpActuator = computed(() => isPumpActuatorType(selectedActuatorType.value))

// AUT-1303: Max. Dosis/Tag nur bei dosierfaehigem Kontext (H-1 generische Pumpe) —
// Einzel-Aktor-Pumpe ODER Sequenz mit mindestens einer Pumpe in der Regel.
const showMaxDoseMlPerDay = computed(
  () =>
    isPumpActuator.value ||
    (nodeType.value === 'sequence' && (props.rulePumpActuators?.length ?? 0) > 0),
)

/** AUT-1303: 0/leer = kein Limit persistieren (ge=0-Pfad, AUT-993). */
function updateMaxDoseMlPerDay(raw: string): void {
  if (raw === '') {
    emit('update:max-dose-ml-per-day', 0)
    return
  }
  const v = Number(raw)
  emit('update:max-dose-ml-per-day', Number.isFinite(v) && v >= 0 ? v : 0)
}

// AUT-995 Feld 2b: derived duration = ceil(dose_ml / flow_rate_ml_s). Display-only; server computes authoritative value.
const derivedDurationSeconds = computed<number | null>(() => {
  const doseMl = localData.value.dose_ml as number | undefined
  const flowRate = selectedActuatorFlowRate.value
  if (!doseMl || doseMl <= 0 || !flowRate || flowRate <= 0) return null
  return Math.ceil(doseMl / flowRate)
})

// AUT-995 Feld 2: only store a positive dose; empty/zero/negative clears the field (no bogus payload).
function updateDoseMl(raw: string): void {
  const v = Number(raw)
  updateField('dose_ml', v > 0 ? v : undefined)
}

// =============================================================================
// AUT-1134 (B4/B7): Chemie-Dosierung — rule_metadata.dose_config (RULE-level, not node-level).
// =============================================================================
//
// dose_config is ONE object per rule; its components[] are matched positionally to actuator
// actions server-side (_compute_chemistry_dose_ml in logic_engine.py) — NOT per-node state.
// This node panel is only the editing surface for the currently selected pump action; the
// canonical value lives in LogicView.vue's ruleMetadata ref, round-tripped via props/emit.

const doseConfig = computed<Record<string, unknown>>(
  () => (props.ruleMetadata?.dose_config as Record<string, unknown>) ?? {}
)
const doseComponents = computed<Record<string, unknown>[]>(
  () => (doseConfig.value.components as Record<string, unknown>[]) ?? []
)

function updateDoseConfig(key: string, value: unknown): void {
  const next = { ...doseConfig.value, [key]: value }
  emit('update:rule-metadata', { ...(props.ruleMetadata ?? {}), dose_config: next })
}

function updateDoseComponent(idx: number, field: string, value: unknown): void {
  const components = [...doseComponents.value]
  components[idx] = { ...(components[idx] ?? {}), [field]: value }
  updateDoseConfig('components', components)
}

function addDoseComponent(): void {
  if (doseComponents.value.length >= 2) return
  updateDoseConfig('components', [...doseComponents.value, { concentration: undefined, ratio_share: undefined }])
}

function removeDoseComponent(idx: number): void {
  updateDoseConfig('components', doseComponents.value.filter((_, i) => i !== idx))
}

/** AUT-1397: hint for Frischwasser preset — prefer GPIO25 / name match, else first pump. */
const refillPumpHint = computed(() => {
  const pumps = props.rulePumpActuators ?? []
  const byGpio = pumps.find((p) => p.gpio === 25)
  if (byGpio) return { espId: byGpio.espId, gpio: byGpio.gpio, name: byGpio.name }
  const byName = pumps.find((p) => {
    const n = (p.name ?? '').toLowerCase()
    return n.includes('frisch') || n.includes('nachfüll') || n.includes('nachfuell')
  })
  if (byName) return { espId: byName.espId, gpio: byName.gpio, name: byName.name }
  return null
})

/** AUT-1399: node-native Mess-Bindung — Editor sieht ein Binding aus Node-Daten. */
const measureBindingNodeMetadata = computed(() =>
  setMeasureBindings({}, [measureBindingFromNodeData(localData.value)]),
)

function onMeasureBindingNodeUpdate(metadata: Record<string, unknown>): void {
  if (!props.node) return
  const list = Array.isArray(metadata.measure_bindings)
    ? metadata.measure_bindings
    : []
  const binding = (list[0] as ReturnType<typeof createEmptyBinding> | undefined)
    ?? createEmptyBinding()
  const nodeData = measureBindingToNodeData(binding)
  // Preserve operator-facing Klarname if user set one
  const label = typeof localData.value.label === 'string' ? localData.value.label : ''
  const next = { ...localData.value, ...nodeData, label }
  localData.value = next
  emit('update:data', props.node.id, next)
}

// =============================================================================
// AUT-1284: Chemie ↔ Foerderrate Kopplung — Vorschau-ml + gekoppelte Laufzeit je Komponente.
// =============================================================================
//
// Formel identisch zu calculate_dose_ml() (linear_dose_calculator.py) fuer GENAU EINE Komponente:
// dose = |delta| * volume_l * ratio_share * safety_factor / concentration. Delta = max_delta_per_dose
// (Ist/Soll-Messwert liegt im Editor nicht vor — reine Anzeige-Vorschau, der Server rechnet beim
// Ausloesen autoritativ mit dem echten Messwert). Kein zweiter Schreibpfad fuer flow_rate.

// AUT-1284: Komponente Ki -> i-ter Pumpen-Aktor der Regel (Prop von LogicView.vue durchgereicht).
function componentPumpRef(idx: number): { espId: string; gpio: number; name?: string } | null {
  return props.rulePumpActuators?.[idx] ?? null
}

// Nachlade-Watch: Foerderraten aller positionell zugeordneten Pumpen-Aktoren vorab laden.
watch(
  () => props.rulePumpActuators,
  (refs) => {
    for (const r of refs ?? []) {
      if (r.espId && r.gpio != null) void fetchFlowRateFor(r.espId, r.gpio)
    }
  },
  { immediate: true, deep: true },
)

function getComponentFlowRate(idx: number): number | null | undefined {
  const ref = componentPumpRef(idx)
  if (!ref) return undefined
  return getFlowRateFor(ref.espId, ref.gpio)
}

function componentPreviewMl(idx: number): number | null {
  const component = doseComponents.value[idx] as Record<string, unknown> | undefined
  if (!component) return null
  const concentration = Number(component.concentration)
  const volumeL = Number(doseConfig.value.volume_l)
  const maxDelta = doseConfig.value.max_delta_per_dose != null ? Number(doseConfig.value.max_delta_per_dose) : null
  if (!concentration || concentration <= 0 || !volumeL || volumeL <= 0 || !maxDelta || maxDelta <= 0) return null
  const ratioShare = component.ratio_share != null ? Number(component.ratio_share) : 1.0
  const safetyFactor = doseConfig.value.safety_factor != null ? Number(doseConfig.value.safety_factor) : 1.0
  return (maxDelta * volumeL * ratioShare * safetyFactor) / concentration
}

function componentDerivedDurationSeconds(idx: number): number | null {
  const ml = componentPreviewMl(idx)
  const flowRate = getComponentFlowRate(idx)
  if (ml == null || ml <= 0 || !flowRate || flowRate <= 0) return null
  return Math.ceil(ml / flowRate)
}

/**
 * AUT-246: Pick the most relevant sensor threshold for the current operator.
 * Operator semantics:
 *   '>' / '>=' → warn high or alarm high (above-threshold breach)
 *   '<' / '<=' → warn low or alarm low (below-threshold breach)
 *   '==' / '!='/'between' → warn high (default)
 */
function getRuleSyncTargetValue(): number | null {
  const base = ruleSensorBaseThresholds.value
  if (!base) return null
  const op = String(localData.value.operator || '>')
  if (op === '<' || op === '<=') {
    return base.warning_min ?? base.alarm_min ?? null
  }
  return base.warning_max ?? base.alarm_max ?? null
}

/**
 * AUT-246: Indicator state — synced (●) when rule.value === target, else independent (◯).
 * Returns null when no sensor base threshold is available (no indicator shown).
 */
const ruleSyncState = computed<'synced' | 'independent' | null>(() => {
  if (nodeType.value !== 'sensor') return null
  if (localData.value.operator === 'between' || localData.value.operator === 'hysteresis') {
    return null
  }
  const target = getRuleSyncTargetValue()
  if (target == null) return null
  const current = localData.value.value
  if (current == null || current === '') return 'independent'
  const cur = Number(current)
  if (Number.isNaN(cur)) return 'independent'
  return Math.abs(cur - target) < 1e-6 ? 'synced' : 'independent'
})

const ruleSyncTargetLabel = computed<string>(() => {
  const base = ruleSensorBaseThresholds.value
  if (!base) return ''
  const op = String(localData.value.operator || '>')
  if (op === '<' || op === '<=') {
    return base.warning_min != null ? 'Warn Low' : 'Alarm Low'
  }
  return base.warning_max != null ? 'Warn High' : 'Alarm High'
})

async function loadRuleValueFromSensorBase(): Promise<void> {
  isLoadingRuleThreshold.value = true
  try {
    await fetchRuleSensorBase()
    const target = getRuleSyncTargetValue()
    if (target == null) {
      toast.error('Keine Sensor-Schwelle gefunden')
      return
    }
    updateField('value', target)
    toast.success(`Wert aus Sensor-Schwelle übernommen (${ruleSyncTargetLabel.value})`)
  } catch {
    toast.error('Sensor-Schwelle konnte nicht geladen werden')
  } finally {
    isLoadingRuleThreshold.value = false
  }
}
</script>

<template>
  <Transition name="config-slide">
    <div v-if="node" class="config-panel">
      <!-- Header -->
      <div class="config-panel__header">
        <div class="config-panel__type">
          <div class="config-panel__type-icon" :class="`config-panel__type-icon--${nodeType}`">
            <component :is="typeIcon" class="w-4 h-4" />
          </div>
          <span class="config-panel__type-label">{{ typeLabel }}</span>
        </div>
        <button class="config-panel__close" @click="emit('close')">
          <X class="w-4 h-4" />
        </button>
      </div>

      <!-- Body -->
      <div class="config-panel__body">
        <div v-if="hasValidationErrors" class="config-validation-summary">
          <strong>Validierungsfehler:</strong>
          <ul>
            <li v-for="(messages, field) in validationErrors" :key="field">
              {{ field }}: {{ messages[0] }}
            </li>
          </ul>
        </div>
        <!-- ======================== SENSOR CONFIG ======================== -->
        <template v-if="nodeType === 'sensor'">
          <div class="config-field">
            <label class="config-label">ESP-Gerät</label>
            <select
              class="config-select"
              :class="{ 'config-input--invalid': fieldError('espId') }"
              :value="localData.espId"
              @change="handleSensorEspChange(($event.target as HTMLSelectElement).value)"
            >
              <option value="">-- ESP wählen --</option>
              <option v-for="esp in espDevices" :key="esp.id" :value="esp.id">
                {{ esp.name }}
              </option>
            </select>
            <p v-if="fieldError('espId')" class="config-hint config-hint--error">{{ fieldError('espId') }}</p>
          </div>

          <!-- Device-aware sensor selection -->
          <template v-if="localData.espId && availableSensors.length > 0">
            <div class="config-field">
              <label class="config-label">Sensor</label>
              <select
                class="config-select"
                :value="sensorDropdownValue"
                @change="selectSensor(($event.target as HTMLSelectElement).value)"
              >
                <option value="">-- Sensor wählen --</option>
                <option v-for="s in availableSensors" :key="`${s.gpio}-${s.sensorType}`" :value="`${s.gpio}:${s.sensorType}`">
                  {{ s.label }}
                </option>
              </select>
              <p v-if="localData.gpio != null && localData.sensorType" class="config-hint">
                GPIO {{ localData.gpio }} · {{ localData.sensorType }}
              </p>
              <p v-if="showMultiValueBaseTypeWarning" class="config-hint config-hint--warn">
                Diese Regel nutzt den Basis-Sensortyp „{{ localData.sensorType }}“. Bitte wählen Sie explizit einen Subtyp (z. B. SHT31 Temperatur oder SHT31 Luftfeuchtigkeit) für zuverlässige Auswertung.
              </p>
            </div>
          </template>

          <!-- No matching sensors for conditionCategory, but ESP has other sensors -->
          <template v-else-if="localData.espId && allAvailableSensors.length > 0">
            <div class="config-field">
              <p class="config-hint config-hint--warn">
                Kein passender Sensor für diesen Konditionstyp auf diesem ESP.
                Für andere Sensortypen den Baustein „Sensor (Erweitert)" verwenden.
              </p>
            </div>
          </template>

          <!-- Fallback: manual input when ESP has no sensor data at all -->
          <template v-else-if="localData.espId">
            <div class="config-field">
              <p class="config-hint config-hint--warn">Keine Sensoren konfiguriert – manuelle Eingabe</p>
            </div>
            <div class="config-field">
              <label class="config-label">GPIO Pin</label>
              <input
                type="number"
                class="config-input"
                :value="localData.gpio"
                min="0"
                max="39"
                @input="updateField('gpio', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="config-field">
              <label class="config-label">Sensor-Typ</label>
              <select
                class="config-select"
                :value="localData.sensorType"
                @change="updateField('sensorType', ($event.target as HTMLSelectElement).value)"
              >
                <option v-for="opt in filteredSensorTypeOptions" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
            </div>
          </template>

          <!-- No ESP selected hint -->
          <div v-else class="config-field">
            <p class="config-hint">Wähle zuerst ein ESP-Gerät aus.</p>
          </div>

          <div class="config-field">
            <label class="config-label">Operator</label>
            <select
              class="config-select"
              :class="{ 'config-input--invalid': fieldError('operator') }"
              :value="localData.operator"
              @change="(e) => {
                const v = (e.target as HTMLSelectElement).value
                updateField('operator', v)
                updateField('isHysteresis', v === 'hysteresis')
              }"
            >
              <option v-for="opt in operatorOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <p v-if="fieldError('operator')" class="config-hint config-hint--error">{{ fieldError('operator') }}</p>
          </div>

          <!-- AUT-1389: Tank-Plan — regelweit; UI nur Tank (Zone/Measure abgeleitet) -->
          <div class="config-field config-plan-abo" data-testid="sensor-plan-abo">
            <div class="config-label-row">
              <label class="config-label">Tank-Plan (ganze Regel)</label>
              <BaseToggle
                :model-value="followsPlan"
                size="sm"
                active-color="purple"
                aria-label="Sollwerte aus dem Plan des gewählten Tanks übernehmen (gilt für die ganze Regel)"
                @update:model-value="(v: boolean) => emit('update:follows-plan', v)"
              />
            </div>
            <div v-if="followsPlan" class="config-plan-abo__fields">
              <BaseSelect
                :model-value="planTankId ?? ''"
                :options="planTankOptions"
                label="Tank"
                placeholder="— Tank wählen —"
                required
                aria-label="Tank für den Nährlösungs-Plan"
                @update:model-value="(v) => emit('update:plan-tank-id', String(v) || undefined)"
              />
              <p
                v-if="planEffectiveDeadbandLabel"
                class="config-hint config-hint--plan-effective"
                data-testid="sensor-plan-effective-deadband"
              >
                {{ planEffectiveDeadbandLabel }}
              </p>
            </div>
          </div>

          <!-- Hysterese: Kühlung (Ein > X, Aus < Y) oder Heizung (Ein < X, Aus > Y) -->
          <template v-if="localData.operator === 'hysteresis' || localData.isHysteresis === true">
            <template v-if="planThresholdsLocked">
              <p class="config-hint config-hint--plan-locked">
                Die Schwellen kommen vom Tank-Plan und lassen sich hier nicht ändern.
              </p>
            </template>
            <template v-else>
              <p class="config-hint">Kühlung: Ein wenn Wert über Schwellwert, Aus wenn unter.</p>
              <div class="config-field-row">
                <div class="config-field config-field--half">
                  <label class="config-label">
                    Ein wenn &gt; (Kühlung)
                    <span v-if="thresholdUnit" class="config-unit">{{ thresholdUnit }}</span>
                  </label>
                  <input
                    type="text"
                    inputmode="decimal"
                    class="config-input"
                    :value="localData.activateAbove"
                    placeholder="z.B. 28"
                    :aria-label="thresholdUnit ? `Ein wenn größer, Einheit ${thresholdUnit}` : 'Ein wenn größer (Kühlung)'"
                    @input="updateField('activateAbove', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                  />
                </div>
                <div class="config-field config-field--half">
                  <label class="config-label">
                    Aus wenn &lt; (Kühlung)
                    <span v-if="thresholdUnit" class="config-unit">{{ thresholdUnit }}</span>
                  </label>
                  <input
                    type="text"
                    inputmode="decimal"
                    class="config-input"
                    :value="localData.deactivateBelow"
                    placeholder="z.B. 24"
                    :aria-label="thresholdUnit ? `Aus wenn kleiner, Einheit ${thresholdUnit}` : 'Aus wenn kleiner (Kühlung)'"
                    @input="updateField('deactivateBelow', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                  />
                </div>
              </div>
              <p class="config-hint">Heizung: Ein wenn Wert unter Schwellwert, Aus wenn über.</p>
              <div class="config-field-row">
                <div class="config-field config-field--half">
                  <label class="config-label">
                    Ein wenn &lt; (Heizung)
                    <span v-if="thresholdUnit" class="config-unit">{{ thresholdUnit }}</span>
                  </label>
                  <input
                    type="text"
                    inputmode="decimal"
                    class="config-input"
                    :value="localData.activateBelow"
                    placeholder="z.B. 18"
                    :aria-label="thresholdUnit ? `Ein wenn kleiner, Einheit ${thresholdUnit}` : 'Ein wenn kleiner (Heizung)'"
                    @input="updateField('activateBelow', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                  />
                </div>
                <div class="config-field config-field--half">
                  <label class="config-label">
                    Aus wenn &gt; (Heizung)
                    <span v-if="thresholdUnit" class="config-unit">{{ thresholdUnit }}</span>
                  </label>
                  <input
                    type="text"
                    inputmode="decimal"
                    class="config-input"
                    :value="localData.deactivateAbove"
                    placeholder="z.B. 22"
                    :aria-label="thresholdUnit ? `Aus wenn größer, Einheit ${thresholdUnit}` : 'Aus wenn größer (Heizung)'"
                    @input="updateField('deactivateAbove', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                  />
                </div>
              </div>
            </template>
          </template>

          <div
            v-else-if="localData.operator === 'between' && !planThresholdsLocked"
            class="config-field-row"
          >
            <div class="config-field config-field--half">
              <label class="config-label">Min</label>
              <input
                type="text"
                inputmode="decimal"
                class="config-input"
                :value="localData.min"
                @input="updateField('min', coerceLocaleNumberInput(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="config-field config-field--half">
              <label class="config-label">Max</label>
              <input
                type="text"
                inputmode="decimal"
                class="config-input"
                :value="localData.max"
                @input="updateField('max', coerceLocaleNumberInput(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>

          <div v-else-if="!planThresholdsLocked" class="config-field">
            <div class="config-label-row">
              <label class="config-label">Schwellwert</label>
              <!-- AUT-246: Sync indicator (read-only) — '● synced' / '◯ unabhängig' -->
              <span
                v-if="ruleSyncState"
                :class="[
                  'rule-sync-indicator',
                  ruleSyncState === 'synced'
                    ? 'rule-sync-indicator--synced'
                    : 'rule-sync-indicator--independent',
                ]"
                :title="
                  ruleSyncState === 'synced'
                    ? `Synchron mit Sensor-Schwelle (${ruleSyncTargetLabel})`
                    : 'Regel-Schwelle weicht von der Sensor-Schwelle ab — bewusste Entkopplung möglich.'
                "
              >
                <span class="rule-sync-indicator__dot">{{ ruleSyncState === 'synced' ? '●' : '◯' }}</span>
                {{ ruleSyncState === 'synced' ? 'synced' : 'unabhängig' }}
              </span>
            </div>
            <div class="rule-sync-row">
              <input
                type="text"
                inputmode="decimal"
                class="config-input rule-sync-row__input"
                :class="{ 'config-input--invalid': fieldError('value') }"
                :value="localData.value"
                @input="updateField('value', coerceLocaleNumberInput(($event.target as HTMLInputElement).value))"
              />
              <!-- AUT-246: One-shot sync button — copies sensor base threshold into rule value -->
              <button
                v-if="localData.espId && localData.gpio != null && localData.sensorType"
                type="button"
                class="rule-sync-btn"
                :disabled="isLoadingRuleThreshold"
                :title="
                  ruleSensorBaseThresholds
                    ? `Wert aus Sensor-Schwelle (${ruleSyncTargetLabel}) übernehmen`
                    : 'Sensor-Schwelle wird geladen...'
                "
                @click="loadRuleValueFromSensorBase"
              >
                <Download :size="13" />
                <span>Aus Sensor-Schwelle übernehmen</span>
              </button>
            </div>
            <p v-if="fieldError('value')" class="config-hint config-hint--error">{{ fieldError('value') }}</p>
            <p
              v-else-if="ruleSyncState === 'independent' && ruleSensorBaseThresholds"
              class="config-hint"
            >
              Hinweis: Regel-Schwelle ist unabhängig von der Sensor-Schwelle — Rule-Engine triggert beim hier eingegebenen Wert.
            </p>
          </div>

          <!-- Feld 4 (AUT-995): Freshness-Gate — nur mit frischen Sensordaten ausloesen (conditions[].require_fresh_data) -->
          <div class="config-field">
            <label class="config-label">Nur mit frischen Daten ausloesen</label>
            <button
              type="button"
              role="switch"
              :aria-checked="!!localData.require_fresh_data"
              :class="['toggle-switch touch-target', { 'toggle-switch--on': localData.require_fresh_data }]"
              aria-label="Nur mit frischen Daten ausloesen"
              @click="updateField('require_fresh_data', !localData.require_fresh_data)"
            >
              <span class="toggle-switch__thumb" />
            </button>
            <p class="config-hint">
              Verhindert Dosierung, wenn der Messwert aelter als die konfigurierte Frischgrenze ist (nur on-demand/geplante Sensoren; kontinuierliche Sensoren bleiben unberuehrt).
            </p>
          </div>
        </template>

        <!-- ======================== TIME CONFIG ======================== -->
        <template v-if="nodeType === 'time'">
          <div class="config-field-row">
            <div class="config-field config-field--half">
              <label class="config-label">Von (Stunde)</label>
              <input
                type="number"
                class="config-input"
                :value="localData.startHour ?? 0"
                min="0"
                max="23"
                @input="updateField('startHour', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="config-field config-field--half">
              <label class="config-label">Von (Minute)</label>
              <input
                type="number"
                class="config-input"
                :value="localData.startMinute ?? 0"
                min="0"
                max="59"
                @input="updateField('startMinute', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>

          <div class="config-field-row">
            <div class="config-field config-field--half">
              <label class="config-label">Bis (Stunde)</label>
              <input
                type="number"
                class="config-input"
                :value="localData.endHour ?? 23"
                min="0"
                max="23"
                @input="updateField('endHour', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
            <div class="config-field config-field--half">
              <label class="config-label">Bis (Minute)</label>
              <input
                type="number"
                class="config-input"
                :value="localData.endMinute ?? 0"
                min="0"
                max="59"
                @input="updateField('endMinute', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
          </div>
          <p class="config-hint">Für punktuelle Ausführung: 1-Minuten-Fenster nutzen, z. B. 07:00–07:01.</p>

          <div class="config-field">
            <label class="config-label">Wochentage</label>
            <div class="config-days">
              <button
                v-for="(label, idx) in dayLabels"
                :key="idx"
                class="config-day"
                :class="{ 'config-day--active': isDayActive(idx) }"
                @click="toggleDay(idx)"
              >
                {{ label }}
              </button>
            </div>
          </div>
        </template>

        <!-- ======================== LOGIC CONFIG ======================== -->
        <template v-if="nodeType === 'logic'">
          <div class="config-field">
            <label class="config-label">Verknüpfung</label>
            <div class="config-toggle-group">
              <button
                class="config-toggle-btn"
                :class="{ 'config-toggle-btn--active': localData.operator === 'AND' }"
                @click="updateField('operator', 'AND')"
              >
                UND
              </button>
              <button
                class="config-toggle-btn"
                :class="{ 'config-toggle-btn--active': localData.operator === 'OR' }"
                @click="updateField('operator', 'OR')"
              >
                ODER
              </button>
            </div>
            <p class="config-hint">
              {{ localData.operator === 'AND'
                ? 'UND gilt online auf dem Server. Alle verbundenen Bedingungen müssen erfüllt sein. Offline auf dem ESP gibt es keine UND-Verknüpfung.'
                : 'ODER gilt online auf dem Server. Mindestens eine verbundene Bedingung muss erfüllt sein.'
              }}
            </p>
          </div>
        </template>

        <!-- ======================== NOT RUNNING (Interlock, AUT-1333) ======================== -->
        <template v-if="nodeType === 'not_running'">
          <div class="config-field">
            <label class="config-label">Ziel</label>
            <select
              class="config-select"
              :value="localData.target || 'actuator'"
              aria-label="Interlock-Ziel"
              @change="handleInterlockTargetChange(($event.target as HTMLSelectElement).value)"
            >
              <option value="actuator">Aktor</option>
              <option value="sequence">Sequenz (andere Regel)</option>
            </select>
            <p class="config-hint">
              AND-Interlock: Regel feuert nur, wenn das Ziel idle ist (kein Abbruch laufender Vorgänge).
            </p>
          </div>
          <template v-if="(localData.target || 'actuator') === 'sequence'">
            <div class="config-field">
              <label class="config-label">Regel</label>
              <select
                class="config-select"
                data-testid="interlock-rule-select"
                :value="localData.ruleId || ''"
                aria-label="Interlock-Sequenzregel"
                @change="updateField('ruleId', ($event.target as HTMLSelectElement).value)"
              >
                <option value="">-- Regel wählen --</option>
                <option v-for="r in interlockRuleOptions" :key="r.id" :value="r.id">
                  {{ r.name }}
                </option>
              </select>
              <p v-if="!interlockRuleOptions.length" class="config-hint config-hint--warn">
                Keine Regeln geladen — Sequenz-Interlock braucht eine bestehende Regel mit Sequenz.
              </p>
            </div>
          </template>
          <template v-else>
            <div class="config-field">
              <label class="config-label">Zone</label>
              <select
                class="config-select"
                data-testid="interlock-zone-select"
                :value="interlockZoneId"
                aria-label="Interlock-Zone"
                @change="handleInterlockZoneChange(($event.target as HTMLSelectElement).value)"
              >
                <option value="">-- Zone wählen --</option>
                <option v-for="z in interlockZoneOptions" :key="z.id" :value="z.id">
                  {{ z.name }}
                </option>
              </select>
            </div>
            <div class="config-field">
              <label class="config-label">ESP-Gerät</label>
              <select
                class="config-select"
                data-testid="interlock-esp-select"
                :value="localData.espId || ''"
                :disabled="!interlockZoneId"
                aria-label="Interlock-ESP-Gerät"
                @change="handleInterlockEspChange(($event.target as HTMLSelectElement).value)"
              >
                <option value="">-- Gerät wählen --</option>
                <option v-for="esp in interlockDevicesInZone" :key="esp.uuid" :value="esp.uuid">
                  {{ esp.name }}
                </option>
              </select>
              <p v-if="!interlockZoneId" class="config-hint">Zuerst eine Zone wählen.</p>
              <p v-else-if="interlockZoneId && !interlockDevicesInZone.length" class="config-hint config-hint--warn">
                In dieser Zone sind keine Geräte mit Aktoren vorhanden.
              </p>
            </div>
            <template v-if="localData.espId && availableActuators.length > 0">
              <div class="config-field">
                <label class="config-label">Aktor</label>
                <select
                  class="config-select"
                  data-testid="interlock-actuator-select"
                  :value="localData.gpio ?? ''"
                  aria-label="Interlock-Aktor"
                  @change="selectActuator(($event.target as HTMLSelectElement).value)"
                >
                  <option value="">-- Aktor wählen --</option>
                  <option v-for="a in availableActuators" :key="a.gpio" :value="a.gpio">
                    {{ a.label }}
                  </option>
                </select>
                <p v-if="localData.gpio != null" class="config-hint">
                  GPIO {{ localData.gpio }} · {{ availableActuators.find(a => a.gpio === localData.gpio)?.actuatorType || '' }}
                </p>
              </div>
            </template>
            <template v-else-if="localData.espId">
              <div class="config-field">
                <p class="config-hint config-hint--warn">Keine Aktoren auf diesem Gerät konfiguriert.</p>
              </div>
            </template>
          </template>
        </template>

        <!-- ======================== ACTUATOR CONFIG ======================== -->
        <template v-if="nodeType === 'actuator'">
          <div class="config-field">
            <label class="config-label">ESP-Gerät</label>
            <select
              class="config-select"
              :class="{ 'config-input--invalid': fieldError('espId') }"
              :value="localData.espId"
              @change="handleActuatorEspChange(($event.target as HTMLSelectElement).value)"
            >
              <option value="">-- ESP wählen --</option>
              <option v-for="esp in espDevices" :key="esp.id" :value="esp.id">
                {{ esp.name }}
              </option>
            </select>
            <p v-if="fieldError('espId')" class="config-hint config-hint--error">{{ fieldError('espId') }}</p>
          </div>

          <!-- Device-aware actuator selection -->
          <template v-if="localData.espId && availableActuators.length > 0">
            <div class="config-field">
              <label class="config-label">Aktor</label>
              <select
                class="config-select"
                :value="localData.gpio ?? ''"
                @change="selectActuator(($event.target as HTMLSelectElement).value)"
              >
                <option value="">-- Aktor wählen --</option>
                <option v-for="a in availableActuators" :key="a.gpio" :value="a.gpio">
                  {{ a.label }}
                </option>
              </select>
              <p v-if="localData.gpio != null" class="config-hint">
                GPIO {{ localData.gpio }} · {{ availableActuators.find(a => a.gpio === localData.gpio)?.actuatorType || '' }}
              </p>
            </div>
          </template>

          <!-- Fallback: manual GPIO input when ESP has no actuator data -->
          <template v-else-if="localData.espId">
            <div class="config-field">
              <p class="config-hint config-hint--warn">Keine Aktoren konfiguriert – manuelle Eingabe</p>
            </div>
            <div class="config-field">
              <label class="config-label">GPIO Pin</label>
              <input
                type="number"
                class="config-input"
                :value="localData.gpio"
                min="0"
                max="39"
                @input="updateField('gpio', Number(($event.target as HTMLInputElement).value))"
              />
            </div>
          </template>

          <!-- No ESP selected hint -->
          <div v-else class="config-field">
            <p class="config-hint">Wähle zuerst ein ESP-Gerät aus.</p>
          </div>

          <!-- Feld 5 (AUT-995): Wirkrichtungs-Label — informativ, backend-unabhaengig -->
          <div v-if="localData.gpio != null && selectedActuatorType" class="config-field">
            <p class="config-hint">
              <strong>Wirkrichtung:</strong>
              {{ getActuatorDirectionLabel(selectedActuatorType) }}
            </p>
          </div>

          <div class="config-field">
            <label class="config-label">Befehl</label>
            <select
              class="config-select"
              :class="{ 'config-input--invalid': fieldError('command') }"
              :value="localData.command"
              @change="updateField('command', ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="opt in commandOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <p v-if="fieldError('command')" class="config-hint config-hint--error">{{ fieldError('command') }}</p>
          </div>

          <div v-if="localData.command === 'PWM'" class="config-field">
            <label class="config-label">PWM-Wert (0-100%)</label>
            <input
              type="range"
              class="config-range"
              :value="(localData.pwmValue as number) ?? 50"
              min="0"
              max="100"
              @input="updateField('pwmValue', Number(($event.target as HTMLInputElement).value))"
            />
            <span class="config-range-value">{{ (localData.pwmValue as number) ?? 50 }}%</span>
          </div>

          <div class="config-field">
            <label class="config-label">
              Maximale Laufzeit pro Ausfuehrung (Sek.)
              <span
                v-if="isPumpActuator"
                class="config-mode-badge"
                data-testid="top-level-dose-mode"
              >Modus: {{ topLevelDoseModeLabel }}</span>
            </label>
            <input
              type="number"
              class="config-input"
              :value="isTopLevelMlDriven && derivedDurationSeconds != null ? derivedDurationSeconds : (localData.duration ?? 0)"
              min="0"
              placeholder="0 = Keine"
              :readonly="isTopLevelMlDriven"
              :aria-readonly="isTopLevelMlDriven"
              aria-label="Maximale Laufzeit in Sekunden"
              @input="!isTopLevelMlDriven && updateField('duration', Number(($event.target as HTMLInputElement).value) || undefined)"
            />
            <p v-if="isTopLevelMlDriven" class="config-hint config-hint--derived">
              Laufzeit abgeleitet (read-only) — Server: ceil(dose_ml / flow_rate_ml_s). Wirksam: ml-getrieben.
            </p>
            <p v-else class="config-hint">
              Wie lange der Aktor maximal laeuft, wenn diese Regel feuert. Nach Ablauf schaltet die Firmware sauber ab. 0 = kein Limit.
            </p>
          </div>

          <!-- Feld B3 (AUT-1134): kalibrierte Foerderrate — eigene Zeile, sichtbar auch ohne gesetzte Dosis. -->
          <div v-if="isPumpActuator" class="config-field">
            <label class="config-label">Kalibrierte Foerderrate</label>
            <p class="config-hint">
              <template v-if="selectedActuatorFlowRate != null">{{ selectedActuatorFlowRate }} ml/s</template>
              <template v-else>Nicht kalibriert — Kalibrierung im Aktor-Konfigurationspanel setzen.</template>
            </p>
          </div>

          <!-- Feld 2 (AUT-995): Dosis in ml (nur Pumpen). Server rechnet dose_ml → duration_seconds via flow_rate_ml_s. -->
          <div v-if="isPumpActuator" class="config-field">
            <label class="config-label">Dosis pro Ausfuehrung (ml)</label>
            <input
              type="number"
              class="config-input"
              :value="localData.dose_ml"
              min="0"
              step="0.1"
              placeholder="z.B. 50"
              @input="updateDoseMl(($event.target as HTMLInputElement).value)"
            />
            <!-- Feld 2b: abgeleitete Dauer live unter dem Input -->
            <p v-if="derivedDurationSeconds != null" class="config-hint">
              ≈ {{ derivedDurationSeconds }} s Laufzeit (bei {{ selectedActuatorFlowRate }} ml/s). Der Server berechnet die exakte Dauer beim Ausloesen.
            </p>
            <p v-else-if="localData.dose_ml && selectedActuatorFlowRate == null" class="config-hint config-hint--warn">
              Pumpe nicht kalibriert (flow_rate_ml_s fehlt) — Dauer kann nicht berechnet werden. Kalibrierung im Aktor-Konfigurationspanel setzen.
            </p>
            <p class="config-hint">
              Zielvolumen in Millilitern. Der Server rechnet ueber die Kalibrierung (flow_rate_ml_s) in eine Laufzeit um. Leer = keine ml-Dosierung (nur Befehl/Dauer).
            </p>
          </div>

          <!-- AUT-1303: Max. Dosis/Tag — UI am dosierfaehigen Aktor (H-1 Pumpe); Persistenz bleibt
               Regel-Spalte cross_esp_logic.max_dose_ml_per_day (kein neuer Server-Code / AUT-993). -->
          <div v-if="showMaxDoseMlPerDay" class="config-field">
            <label class="config-label">Max. Dosis/Tag (ml)</label>
            <input
              type="number"
              class="config-input"
              data-testid="max-dose-ml-per-day"
              :value="maxDoseMlPerDay"
              min="0"
              step="0.1"
              placeholder="0 = kein Limit"
              aria-label="Maximale Dosis pro Tag in Millilitern"
              @input="updateMaxDoseMlPerDay(($event.target as HTMLInputElement).value)"
            />
            <p class="config-hint">
              Maximale Gesamt-Dosis in ml pro rollierende 24&nbsp;h ueber alle Ausfuehrungen dieser Regel.
              0 oder leer = kein Limit. Gilt fuer die gesamte Regel (nicht pro Aktor).
            </p>
          </div>

          <!-- Feld B7/B4 (AUT-1134): Chemie-Dosierung — rule_metadata.dose_config (RULE-level,
               EIN Objekt pro Regel, Komponenten positionell auf Aktor-Aktionen gemappt, siehe
               logic_engine.py::_compute_chemistry_dose_ml). Konzentration NIEMALS in
               actuator_metadata — sonst Fail-Open ueberspringt die Dosis still. -->
          <div v-if="isPumpActuator" class="config-field">
            <label class="config-label">Chemie-Dosierung (optional)</label>
            <p class="config-hint">
              Berechnet die Dosis automatisch aus Ist-/Sollwert, Tankvolumen und Konzentration — ersetzt die feste ml-Dosis oben, wenn gesetzt.
            </p>
            <p class="config-hint config-hint--warn">
              Gilt fuer die GESAMTE Regel, nicht nur fuer diesen Aktor: Bei mehreren Pumpen-Aktionen (z.B. EC A + EC B) wird Komponente K1 der ersten, K2 der zweiten Pumpen-Aktion in Regel-Reihenfolge zugeordnet.
            </p>

            <div class="config-field-row">
              <div class="config-field config-field--half">
                <label class="config-label">Zielwert</label>
                <input
                  type="text"
                  inputmode="decimal"
                  class="config-input"
                  :value="doseConfig.target_value"
                  placeholder="z.B. 6.0"
                  aria-label="Dose-Zielwert pH oder EC"
                  @input="updateDoseConfig('target_value', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                />
              </div>
              <div class="config-field config-field--half">
                <label class="config-label">Tankvolumen (l)</label>
                <input
                  type="number"
                  class="config-input"
                  :value="doseConfig.volume_l"
                  min="0"
                  step="0.1"
                  placeholder="z.B. 20"
                  @input="updateDoseConfig('volume_l', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                />
              </div>
            </div>

            <div
              v-for="(component, idx) in doseComponents"
              :key="idx"
              class="config-dose-component"
            >
              <div class="config-field-row">
                <div class="config-field config-field--half">
                  <label class="config-label">
                    µS/cm-Anstieg pro ml je Liter (K{{ idx + 1 }}) — Referenz
                  </label>
                  <input
                    type="number"
                    class="config-input"
                    :value="component.concentration"
                    min="0"
                    step="1"
                    placeholder="z. B. 100"
                    readonly
                    :aria-label="`Referenz Konzentration Komponente ${idx + 1} (SSOT = Pumpe)`"
                  />
                  <p class="config-hint">
                    Read-only — SSOT ist die Dosierpumpe (Hardware-View → Kalibrierung).
                    Runtime-Fallback nur wenn Pumpe.concentration unset.
                  </p>
                </div>
                <div class="config-field config-field--half">
                  <label class="config-label">Anteil K{{ idx + 1 }}</label>
                  <input
                    type="number"
                    class="config-input"
                    :value="component.ratio_share"
                    min="0"
                    max="1"
                    step="0.1"
                    @input="updateDoseComponent(idx, 'ratio_share', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                  />
                </div>
                <button
                  type="button"
                  class="config-btn config-btn--danger config-btn--sm"
                  title="Komponente entfernen"
                  @click="removeDoseComponent(idx)"
                >
                  <Trash2 class="w-3 h-3" />
                </button>
              </div>

              <!-- AUT-1284: Vorschau-ml + gekoppelte Foerderrate/Laufzeit — read-only, kein zweiter
                   Schreibpfad. Pumpen-Zuordnung kommt positionell aus rulePumpActuators[idx]. -->
              <div class="config-dose-preview">
                <div class="config-dose-preview__row">
                  <span class="config-dose-preview__label">Vorschau K{{ idx + 1 }}</span>
                  <span v-if="componentPreviewMl(idx) != null" class="config-dose-preview__value">
                    ≈ {{ componentPreviewMl(idx)!.toFixed(2) }} ml
                  </span>
                  <span v-else class="config-dose-preview__value config-dose-preview__value--dim">—</span>
                </div>
                <p v-if="componentPreviewMl(idx) == null" class="config-hint">
                  Vorschau braucht „Max. Aenderung pro Dosis" (oder Ist-/Sollwert zur Laufzeit), Tankvolumen und Konzentration.
                </p>
                <div class="config-dose-preview__row">
                  <span class="config-dose-preview__label">Foerderrate Pumpe K{{ idx + 1 }}</span>
                  <span v-if="!componentPumpRef(idx)" class="config-dose-preview__value config-dose-preview__value--dim">
                    keine {{ idx + 1 }}. Pumpen-Aktion in der Regel
                  </span>
                  <span v-else-if="getComponentFlowRate(idx) != null" class="config-dose-preview__value">
                    {{ getComponentFlowRate(idx) }} ml/s ({{ componentPumpRef(idx)?.name || 'GPIO ' + componentPumpRef(idx)?.gpio }})
                  </span>
                  <span v-else class="config-dose-preview__value config-dose-preview__value--warn">nicht kalibriert</span>
                </div>
                <div v-if="componentPreviewMl(idx) != null && componentPumpRef(idx)" class="config-dose-preview__row">
                  <span class="config-dose-preview__label">Resultierende Laufzeit</span>
                  <span v-if="componentDerivedDurationSeconds(idx) != null" class="config-dose-preview__value">
                    ≈ {{ componentDerivedDurationSeconds(idx) }} s
                  </span>
                  <span v-else class="config-dose-preview__value config-dose-preview__value--warn">nicht kalibriert</span>
                </div>
              </div>
            </div>
            <button
              v-if="doseComponents.length < 2"
              type="button"
              class="config-btn config-btn--sm"
              @click="addDoseComponent"
            >
              + Komponente (z.B. EC A/B)
            </button>

            <div class="config-field-row">
              <div class="config-field config-field--half">
                <label class="config-label">Sicherheitsfaktor</label>
                <input
                  type="number"
                  class="config-input"
                  :value="doseConfig.safety_factor"
                  min="0"
                  step="0.05"
                  placeholder="1.0"
                  @input="updateDoseConfig('safety_factor', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                />
              </div>
              <div class="config-field config-field--half">
                <label class="config-label">Verduennung</label>
                <input
                  type="number"
                  class="config-input"
                  :value="doseConfig.dilution_value"
                  min="0"
                  step="0.1"
                  placeholder="z.B. 10 (1:10)"
                  @input="updateDoseConfig('dilution_value', parseNumericOrNull(($event.target as HTMLInputElement).value))"
                />
              </div>
            </div>

            <!-- Feld B4 (AUT-1118/AUT-1134): Amplituden-Deckel — max. Wertaenderung pro Einzeldosis. -->
            <div class="config-field">
              <label class="config-label">Max. Aenderung pro Dosis</label>
              <input
                type="number"
                class="config-input"
                :value="doseConfig.max_delta_per_dose"
                min="0"
                step="0.01"
                placeholder="z.B. 0.1 (Profi-Praxis-Deckel)"
                @input="updateDoseConfig('max_delta_per_dose', parseNumericOrNull(($event.target as HTMLInputElement).value))"
              />
              <p class="config-hint">
                Begrenzt, wie stark eine einzelne Dosis den Messwert maximal veraendern darf (iteratives Nachdosieren statt Ueberschuss). Leer = kein Deckel.
              </p>
            </div>
          </div>

          <!-- AUT-1133 (B1): Geräte-Sicherheitslimit + Mindest-Pause read-only — EINZIGE
               Editier-Stelle bleibt Hardware→Aktor (ActuatorConfigPanel.vue). -->
          <div
            v-if="nodeType === 'actuator' && localData.espId && localData.gpio != null"
            class="rule-config-panel__safety-hint rule-config-panel__safety-hint--readonly"
          >
            <div class="rule-config-panel__safety-row">
              <span class="rule-config-panel__safety-label">Geräte-Sicherheitslimit</span>
              <span class="rule-config-panel__safety-value">
                <template v-if="selectedActuatorMaxRuntimeSeconds == null">—</template>
                <template v-else-if="selectedActuatorMaxRuntimeSeconds === 0">0 s (unbegrenzt)</template>
                <template v-else>{{ selectedActuatorMaxRuntimeSeconds }} s</template>
              </span>
            </div>
            <p
              v-if="isPumpActuator && selectedActuatorMaxRuntimeSeconds === 0"
              class="config-hint config-hint--warn"
            >
              ⚠ Kein Geräte-Sicherheitslimit gesetzt (0 = unbegrenzt) — der Failsafe greift bei dieser Pumpe nicht.
            </p>

            <div class="rule-config-panel__safety-row">
              <span class="rule-config-panel__safety-label">Mindest-Pause des Aktors</span>
              <span class="rule-config-panel__safety-value">
                <template v-if="!isPumpActuator">nicht anwendbar</template>
                <template v-else-if="selectedActuatorCooldownSeconds == null">—</template>
                <template v-else-if="selectedActuatorCooldownSeconds === 0">keine</template>
                <template v-else>{{ selectedActuatorCooldownSeconds }} s</template>
              </span>
            </div>

            <p class="config-hint">
              Geräte-Ebene, gilt unabhängig vom Regel-Cooldown für alle Quellen (Regel + manuell).
              <button type="button" class="rule-config-panel__safety-edit-link" @click="openActuatorInHardwarePanel">
                Bearbeiten unter Hardware → Aktor
              </button>
            </p>
          </div>
        </template>

        <!-- ======================== NOTIFICATION CONFIG ======================== -->
        <template v-if="nodeType === 'notification'">
          <div class="config-field">
            <label class="config-label">Kanal</label>
            <select
              class="config-select"
              :value="localData.channel"
              @change="updateField('channel', ($event.target as HTMLSelectElement).value)"
            >
              <option v-for="opt in channelOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <div class="config-field">
            <label class="config-label">Ziel</label>
            <input
              type="text"
              class="config-input"
              :value="localData.target"
              placeholder="z.B. admin@example.com"
              @input="updateField('target', ($event.target as HTMLInputElement).value)"
            />
          </div>

          <div class="config-field">
            <label class="config-label">Nachricht</label>
            <textarea
              class="config-textarea"
              :value="String(localData.messageTemplate ?? '')"
              placeholder="Temperatur {value}°C überschritten!"
              rows="3"
              @input="updateField('messageTemplate', ($event.target as HTMLTextAreaElement).value)"
            ></textarea>
            <p class="config-hint">
              Variablen: {value}, {sensor_type}, {esp_id}, {timestamp}
            </p>
          </div>
        </template>

        <!-- ======================== DELAY CONFIG ======================== -->
        <template v-if="nodeType === 'delay'">
          <div class="config-field">
            <label class="config-label">Wartezeit (Sekunden)</label>
            <input
              type="number"
              class="config-input"
              :value="localData.seconds"
              min="1"
              max="86400"
              @input="updateField('seconds', Number(($event.target as HTMLInputElement).value))"
            />
            <p class="config-hint">
              {{ localData.seconds ? `= ${Math.floor((localData.seconds as number) / 60)} Min. ${(localData.seconds as number) % 60} Sek.` : '' }}
            </p>
          </div>
        </template>

        <!-- ======================== SEQUENCE CONFIG (AUT-1281) ======================== -->
        <template v-if="nodeType === 'sequence'">
          <!-- AUT-1303: gleiches Regel-Limit wie am Einzel-Pumpen-Aktor — nur wenn Sequenz Pumpen hat. -->
          <div v-if="showMaxDoseMlPerDay" class="config-field">
            <label class="config-label">Max. Dosis/Tag (ml)</label>
            <input
              type="number"
              class="config-input"
              data-testid="max-dose-ml-per-day"
              :value="maxDoseMlPerDay"
              min="0"
              step="0.1"
              placeholder="0 = kein Limit"
              aria-label="Maximale Dosis pro Tag in Millilitern"
              @input="updateMaxDoseMlPerDay(($event.target as HTMLInputElement).value)"
            />
            <p class="config-hint">
              Maximale Gesamt-Dosis in ml pro rollierende 24&nbsp;h ueber alle Ausfuehrungen dieser Regel
              (Summe aller Sequenz-Schritte). 0 oder leer = kein Limit.
            </p>
          </div>

          <div class="config-field config-field--sequence-limit">
            <!-- AUT-1281/AUT-1306: MAX. LAUFZEIT = Gesamtlimit; getrennt von Pause-Wartezeit je Schritt. -->
            <label class="config-label">MAX. LAUFZEIT — Gesamtlimit Sequenz (Sekunden)</label>
            <input
              type="number"
              class="config-input"
              :value="localData.maxDurationSeconds"
              min="1"
              max="3600"
              aria-label="Maximale Laufzeit der gesamten Sequenz in Sekunden"
              @input="updateField('maxDurationSeconds', Number(($event.target as HTMLInputElement).value))"
            />
            <p class="config-hint">
              Gesamtlimit für <strong>alle</strong> Schritte zusammen (max. 3600&nbsp;s) — nicht die Wartezeit einer einzelnen Pause.
            </p>
          </div>

          <div class="config-field">
            <label class="config-label">Schritte (ziehbar sortieren)</label>
            <p v-if="!sequenceSteps.length" class="config-hint">Noch keine Schritte — Aktor-Schritt oder Pause hinzufügen.</p>
            <VueDraggable
              v-model="sequenceSteps"
              class="config-sequence-step-list"
              handle=".config-sequence-step__handle"
              :animation="180"
              ghost-class="config-sequence-step--ghost"
              chosen-class="config-sequence-step--chosen"
              drag-class="config-sequence-step--drag"
            >
              <div
                v-for="(step, idx) in sequenceSteps"
                :key="idx"
                class="config-sequence-step"
                :class="{ 'config-sequence-step--pause': step.stepType === 'delay' }"
              >
                <div class="config-sequence-step__header">
                  <GripVertical
                    class="config-sequence-step__handle w-3.5 h-3.5"
                    role="button"
                    tabindex="0"
                    :aria-label="`Schritt ${sequenceStepNumber(idx)} verschieben`"
                  />
                  <span class="config-sequence-step__nr" aria-hidden="true">{{ sequenceStepNumber(idx) }}</span>
                  <span
                    class="config-sequence-step__type-badge"
                    :class="step.stepType === 'delay'
                      ? 'config-sequence-step__type-badge--pause'
                      : 'config-sequence-step__type-badge--actuator'"
                  >{{ sequenceStepTypeLabel(step.stepType) }}</span>
                  <select
                    class="config-select config-select--compact"
                    :value="step.stepType"
                    :aria-label="`Schritt ${sequenceStepNumber(idx)} Typ`"
                    @change="updateStep(idx, 'stepType', ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="actuator">Aktor-Schritt</option>
                    <option value="delay">Pause</option>
                  </select>
                  <button
                    class="config-btn config-btn--danger config-btn--sm"
                    title="Schritt entfernen"
                    :aria-label="`Schritt ${sequenceStepNumber(idx)} entfernen`"
                    @click="removeStep(idx)"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>

                <template v-if="step.stepType === 'actuator'">
                  <input
                    type="text"
                    class="config-input config-input--sm"
                    placeholder="Name (optional)"
                    :value="step.name ?? ''"
                    @input="updateStep(idx, 'name', ($event.target as HTMLInputElement).value)"
                  />
                  <select
                    class="config-select"
                    :value="step.espId ?? ''"
                    @change="updateStep(idx, 'espId', ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="">-- ESP wählen --</option>
                    <option v-for="d in espStore.devices" :key="espStore.getDeviceId(d)" :value="espStore.getDeviceId(d)">
                      {{ d.name || espStore.getDeviceId(d) }}
                    </option>
                  </select>
                  <select
                    class="config-select"
                    :value="step.gpio ?? 0"
                    @change="updateStep(idx, 'gpio', Number(($event.target as HTMLSelectElement).value))"
                  >
                    <option value="0">-- GPIO wählen --</option>
                    <option
                      v-for="act in (espStore.devices.find(d => espStore.getDeviceId(d) === step.espId)?.actuators ?? [])"
                      :key="act.gpio"
                      :value="act.gpio"
                    >
                      {{ act.name || `GPIO ${act.gpio}` }}
                    </option>
                  </select>
                  <select
                    class="config-select"
                    :value="step.command ?? 'ON'"
                    @change="updateStep(idx, 'command', ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="ON">EIN</option>
                    <option value="OFF">AUS</option>
                  </select>
                  <!-- AUT-1390: 3-Modus-Selektor am Sequenz-Schritt (Pumpe) — erweitert Badge-Logik AUT-1379. -->
                  <div v-if="isStepPump(step)" class="config-field">
                    <label class="config-label" :for="`step-dose-mode-select-${idx}`">
                      Dosier-Modus
                      <span
                        class="config-mode-badge"
                        data-testid="step-dose-mode"
                      >{{ stepDoseModeLabel(step) }}</span>
                    </label>
                    <select
                      :id="`step-dose-mode-select-${idx}`"
                      class="config-select"
                      data-testid="step-dose-mode-select"
                      :value="stepDoseModeValue(step)"
                      aria-label="Dosier-Modus dieses Schritts"
                      @change="updateStepDoseMode(idx, ($event.target as HTMLSelectElement).value as StepDoseMode)"
                    >
                      <option
                        v-for="opt in STEP_DOSE_MODE_OPTIONS"
                        :key="opt"
                        :value="opt"
                      >
                        {{ stepDoseModeOptionLabel(opt) }}
                      </option>
                    </select>
                    <p class="config-hint" data-testid="step-dose-mode-help">
                      {{ stepDoseModeHelp(stepDoseModeValue(step)) }}
                    </p>
                    <p
                      v-if="stepDoseModeValue(step) === 'target_optimal' && getStepFlowRate(step) == null"
                      class="config-hint config-hint--warn"
                      data-testid="step-dose-fallback-hint"
                    >
                      Foerderrate fehlt — laeuft laufzeit-getrieben bis kalibriert (Server-Fallback).
                      Setze unten eine Fallback-Laufzeit in Sekunden.
                    </p>
                    <p
                      v-else-if="stepDoseModeValue(step) === 'target_optimal'
                        && getStepFlowRate(step) != null
                        && (getStepConcentration(step) == null || (getStepConcentration(step) ?? 0) <= 0)"
                      class="config-hint config-hint--derived"
                      data-testid="step-dose-autocal-hint"
                    >
                      Konzentration noch unbekannt — misst sich beim naechsten Dosieren selbst (kein Sekunden-Fallback).
                    </p>
                  </div>

                  <div class="config-field">
                    <label class="config-label">
                      Laufzeit (s, 0 = permanent)
                    </label>
                    <input
                      type="number"
                      class="config-input config-input--sm"
                      :value="isStepMlDriven(step) && stepDerivedDurationSeconds(step) != null
                        ? stepDerivedDurationSeconds(step)
                        : (step.duration ?? 0)"
                      min="0"
                      max="3600"
                      :readonly="isStepMlDriven(step)"
                      :aria-readonly="isStepMlDriven(step)"
                      aria-label="Schritt-Laufzeit in Sekunden"
                      @input="!isStepMlDriven(step) && updateStep(idx, 'duration', Number(($event.target as HTMLInputElement).value))"
                    />
                    <p
                      v-if="isStepPump(step) && isStepMlDriven(step)"
                      class="config-hint config-hint--derived"
                      data-testid="step-derived-runtime"
                    >
                      Abgeleitet (read-only): ceil({{ step.dose_ml }} / {{ getStepFlowRate(step) }})
                      = <strong>{{ stepDerivedDurationSeconds(step) }}&nbsp;s</strong>
                      — wirksam ist die ml-Dosis (Server überschreibt Laufzeit).
                    </p>
                    <p
                      v-else-if="isStepPump(step) && stepDerivedMlFromDuration(step) != null"
                      class="config-hint config-hint--derived"
                      data-testid="step-ml-equivalent"
                    >
                      ≈ {{ stepDerivedMlFromDuration(step) }}&nbsp;ml
                      ({{ step.duration }}&nbsp;s × {{ getStepFlowRate(step) }}&nbsp;ml/s) —
                      wirksam ist die Laufzeit (FW-Auto-OFF).
                    </p>
                  </div>

                  <!-- AUT-1281 / AUT-1379 / AUT-1390: Dosis ml — bei Modus duration ausgeblendet. -->
                  <div
                    v-if="isStepPump(step) && stepDoseModeValue(step) !== 'duration'"
                    class="config-field"
                  >
                    <label class="config-label">Dosis dieses Schritts (ml)</label>
                    <input
                      type="number"
                      class="config-input config-input--sm"
                      :value="step.dose_ml"
                      min="0"
                      step="0.1"
                      placeholder="z.B. 9"
                      aria-label="Dosis dieses Schritts in Millilitern"
                      @input="updateStepDoseMl(idx, ($event.target as HTMLInputElement).value)"
                    />
                    <p
                      v-if="stepDoseModeValue(step) === 'ml' && getStepFlowRate(step) === null"
                      class="config-hint config-hint--warn"
                    >
                      Foerderrate fehlt — Dauer kann nicht berechnet werden. Kalibrierung im Aktor-Panel setzen.
                    </p>
                    <p v-else-if="stepDoseModeValue(step) === 'target_optimal'" class="config-hint">
                      Zielmenge fuer konzentrations-exakte Dosierung. Ohne Foerderrate greift die Laufzeit oben als Fallback.
                    </p>
                    <p v-else class="config-hint">
                      Feste ml-Menge — Laufzeit oben read-only, sobald Foerderrate bekannt.
                    </p>
                  </div>
                </template>

                <template v-else>
                  <input
                    type="text"
                    class="config-input config-input--sm"
                    placeholder="Name (optional, z.B. Mischzeit)"
                    :value="step.name ?? ''"
                    @input="updateStep(idx, 'name', ($event.target as HTMLInputElement).value)"
                  />
                  <div class="config-field">
                    <!-- AUT-1281/AUT-1306: Pause-Wartezeit ≠ MAX. LAUFZEIT oben. -->
                    <label class="config-label">Wartezeit dieses Schritts — Pause (Sekunden)</label>
                    <input
                      type="number"
                      class="config-input"
                      :value="step.seconds ?? 60"
                      min="1"
                      max="3600"
                      aria-label="Wartezeit dieser Pause in Sekunden"
                      @input="updateStep(idx, 'seconds', Number(($event.target as HTMLInputElement).value))"
                    />
                    <p class="config-hint">Nur diese Pause — nicht das Gesamtlimit der Sequenz.</p>
                  </div>
                </template>
              </div>
            </VueDraggable>

            <div class="config-sequence-step__actions">
              <button
                class="config-btn config-btn--sm"
                aria-label="Aktor-Schritt hinzufügen"
                @click="addStep('actuator')"
              >+ Aktor-Schritt</button>
              <button
                class="config-btn config-btn--sm"
                aria-label="Pause hinzufügen"
                @click="addStep('delay')"
              >+ Pause</button>
            </div>
          </div>
        </template>

        <!-- ======================== PLUGIN CONFIG ======================== -->
        <template v-if="nodeType === 'plugin'">
          <div class="config-field">
            <label class="config-label">Plugin</label>
            <select
              class="config-select"
              :value="localData.pluginId"
              @change="updateField('pluginId', ($event.target as HTMLSelectElement).value)"
            >
              <option value="">-- Plugin wählen --</option>
              <option
                v-for="p in availablePlugins"
                :key="p.plugin_id"
                :value="p.plugin_id"
                :disabled="!p.is_enabled"
              >
                {{ p.display_name }}{{ !p.is_enabled ? ' (deaktiviert)' : '' }}
              </option>
            </select>
          </div>

          <template v-if="localData.pluginId">
            <div class="config-field">
              <p class="config-hint">
                {{ availablePlugins.find(p => p.plugin_id === localData.pluginId)?.description || '' }}
              </p>
            </div>

            <!-- Dynamic config fields from plugin config_schema -->
            <template
              v-for="(schemaDef, key) in (availablePlugins.find(p => p.plugin_id === localData.pluginId)?.config_schema || {})"
              :key="key"
            >
              <div v-if="(schemaDef as Record<string, unknown>)?.type === 'boolean'" class="config-field">
                <label class="config-label">
                  {{ (schemaDef as Record<string, unknown>).label || key }}
                </label>
                <div class="config-toggle-group">
                  <button
                    class="config-toggle-btn"
                    :class="{ 'config-toggle-btn--active': localData[`cfg_${key}`] !== false }"
                    @click="updateField(`cfg_${key}`, true)"
                  >
                    An
                  </button>
                  <button
                    class="config-toggle-btn"
                    :class="{ 'config-toggle-btn--active': localData[`cfg_${key}`] === false }"
                    @click="updateField(`cfg_${key}`, false)"
                  >
                    Aus
                  </button>
                </div>
              </div>
              <div v-else-if="(schemaDef as Record<string, unknown>)?.type === 'number' || (schemaDef as Record<string, unknown>)?.type === 'integer'" class="config-field">
                <label class="config-label">
                  {{ (schemaDef as Record<string, unknown>).label || key }}
                </label>
                <input
                  type="number"
                  class="config-input"
                  :value="localData[`cfg_${key}`] ?? (schemaDef as Record<string, unknown>).default"
                  @input="updateField(`cfg_${key}`, Number(($event.target as HTMLInputElement).value))"
                />
              </div>
              <div v-else-if="(schemaDef as Record<string, unknown>)?.type === 'select'" class="config-field">
                <label class="config-label">
                  {{ (schemaDef as Record<string, unknown>).label || key }}
                </label>
                <select
                  class="config-select"
                  :value="(localData[`cfg_${key}`] ?? (schemaDef as Record<string, unknown>).default ?? '') as string"
                  @change="updateField(`cfg_${key}`, ($event.target as HTMLSelectElement).value)"
                >
                  <option
                    v-for="opt in ((schemaDef as Record<string, unknown>).options as string[]) || []"
                    :key="opt"
                    :value="opt"
                  >
                    {{ opt }}
                  </option>
                </select>
              </div>
              <div v-else-if="(schemaDef as Record<string, unknown>)?.type === 'string'" class="config-field">
                <label class="config-label">
                  {{ (schemaDef as Record<string, unknown>).label || key }}
                </label>
                <input
                  type="text"
                  class="config-input"
                  :value="localData[`cfg_${key}`] ?? (schemaDef as Record<string, unknown>).default ?? ''"
                  @input="updateField(`cfg_${key}`, ($event.target as HTMLInputElement).value)"
                />
              </div>
            </template>
          </template>
        </template>

        <!-- AUT-1399: Mess-Bindung nur am sensor_diff-Knoten (node-native), nie Regel-Ebene-Doppelung -->
        <template v-if="nodeType === 'sensor_diff'">
          <div class="config-field">
            <label class="config-label" for="measure-binding-label">Name auf dem Knoten</label>
            <input
              id="measure-binding-label"
              type="text"
              class="config-input"
              :value="(localData.label as string) || ''"
              placeholder="z. B. Frischwasser-Menge"
              aria-label="Name der Mess-Bindung auf dem Knoten"
              @input="updateField('label', ($event.target as HTMLInputElement).value)"
            />
            <p class="config-hint">
              Linien zu Aktoren brauchst du nicht für Anfang/Ende — das legen die
              Häkchen „Wann wird gemessen?“ fest.
            </p>
          </div>
          <MeasureBindingEditor
            :rule-metadata="measureBindingNodeMetadata"
            :refill-pump-hint="refillPumpHint"
            :single-binding="true"
            @update:rule-metadata="onMeasureBindingNodeUpdate"
          />
        </template>
      </div>

      <!-- Footer Actions -->
      <div class="config-panel__footer">
        <button class="config-action config-action--duplicate" @click="emit('duplicate-node', node!.id)">
          <Copy class="w-3.5 h-3.5" />
          Duplizieren
        </button>
        <button class="config-action config-action--delete" @click="emit('delete-node', node!.id)">
          <Trash2 class="w-3.5 h-3.5" />
          Löschen
        </button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.config-panel {
  width: 400px;
  min-width: 400px;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border-left: 1px solid var(--glass-border);
  overflow: hidden;
}

.config-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.875rem 1rem;
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.config-panel__type {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.config-panel__type-icon {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.config-panel__type-icon--sensor {
  background: rgba(96, 165, 250, 0.1);
  color: var(--color-iridescent-1);
}

.config-panel__type-icon--time {
  background: rgba(251, 191, 36, 0.1);
  color: var(--color-warning);
}

.config-panel__type-icon--logic {
  background: rgba(167, 139, 250, 0.1);
  color: var(--color-iridescent-3);
}

.config-panel__type-icon--actuator {
  background: rgba(192, 132, 252, 0.1);
  color: var(--color-iridescent-4);
}

.config-panel__type-icon--notification {
  background: rgba(52, 211, 153, 0.1);
  color: var(--color-success);
}

.config-panel__type-icon--delay {
  background: rgba(133, 133, 160, 0.1);
  color: var(--color-text-secondary);
}

.config-panel__type-icon--plugin {
  background: rgba(245, 158, 11, 0.1);
  color: var(--color-warning);
}

.config-panel__type-icon--sequence {
  background: rgba(34, 211, 238, 0.1);
  color: var(--color-real);
}

.config-panel__type-label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.config-panel__close {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.config-panel__close:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.config-panel__body {
  flex: 1;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  overflow-y: auto;
}

.config-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.config-validation-summary {
  border: 1px solid rgba(248, 113, 113, 0.35);
  background: rgba(248, 113, 113, 0.08);
  color: var(--color-error);
  border-radius: var(--radius-md);
  padding: 0.5rem 0.625rem;
  font-size: 0.75rem;
}

.config-validation-summary ul {
  margin: 0.25rem 0 0;
  padding-left: 1rem;
}

.config-field--half {
  flex: 1;
}

.config-field-row {
  display: flex;
  gap: 0.75rem;
}

.config-label {
  font-size: 0.6875rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.config-unit {
  margin-left: var(--space-1);
  font-weight: 500;
  text-transform: none;
  letter-spacing: normal;
  color: var(--color-text-muted);
}

.config-input,
.config-select,
.config-textarea {
  width: 100%;
  padding: 0.5rem 0.625rem;
  font-size: var(--text-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  outline: none;
  transition: all var(--transition-fast);
}

.config-input:focus,
.config-select:focus,
.config-textarea:focus {
  border-color: rgba(129, 140, 248, 0.4);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.06);
}

.config-input--invalid {
  border-color: var(--color-error);
}

/* AUT-246: Rule sync row + indicator */
.config-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-bottom: var(--space-1);
}

.rule-sync-indicator {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  font-size: var(--text-xxs);
  font-weight: 600;
  border-radius: var(--radius-xs);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-family: var(--font-mono);
}

.rule-sync-indicator__dot {
  font-size: 10px;
  line-height: 1;
}

.rule-sync-indicator--synced {
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.12);
}

.rule-sync-indicator--independent {
  color: var(--color-text-muted);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--glass-border);
}

.rule-sync-row {
  display: flex;
  gap: var(--space-2);
  align-items: stretch;
}

.rule-sync-row__input {
  flex: 1;
  min-width: 72px;
}

.rule-sync-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0.375rem 0.625rem;
  background: transparent;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
  min-height: 32px;
}

.rule-sync-btn:hover:not(:disabled) {
  border-color: rgba(129, 140, 248, 0.4);
  color: var(--color-text-primary);
  background: rgba(129, 140, 248, 0.06);
}

.rule-sync-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}

.config-input::placeholder,
.config-textarea::placeholder {
  color: var(--color-text-muted);
}

.config-select {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23707080' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.5rem center;
  padding-right: 1.75rem;
  cursor: pointer;
}

.config-select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.config-textarea {
  resize: vertical;
  min-height: 64px;
  font-family: inherit;
  line-height: 1.5;
}

.config-range {
  width: 100%;
  accent-color: var(--color-iridescent-2);
  cursor: pointer;
}

.config-range-value {
  font-size: 0.75rem;
  color: var(--color-iridescent-2);
  font-weight: 700;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.config-hint {
  font-size: 0.625rem;
  color: var(--color-text-muted);
  line-height: 1.4;
}

.config-hint--warn {
  color: var(--color-warning);
  font-style: italic;
}

.config-hint--error {
  color: var(--color-error);
}

/* AUT-1020/AUT-1133: Geräte-Sicherheitslimit + Mindest-Pause, read-only in actuator node config */
.rule-config-panel__safety-hint {
  display: flex;
  align-items: flex-start;
  gap: 0.375rem;
  padding: 0.5rem 0.625rem;
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--color-info, #60a5fa) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-info, #60a5fa) 30%, transparent);
  font-size: 0.625rem;
  color: var(--color-text-muted);
  line-height: 1.4;
}

.rule-config-panel__safety-hint--readonly {
  flex-direction: column;
  gap: 0.375rem;
}

.rule-config-panel__safety-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
  width: 100%;
}

.rule-config-panel__safety-label {
  color: var(--color-text-muted);
}

.rule-config-panel__safety-value {
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
}

.rule-config-panel__safety-edit-link {
  background: none;
  border: none;
  padding: 0;
  margin-left: 0.25rem;
  color: var(--color-info, #60a5fa);
  text-decoration: underline;
  font-size: inherit;
  font-family: inherit;
  cursor: pointer;
}

.config-toggle-group {
  display: flex;
  gap: 1px;
  background: var(--glass-border);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.config-toggle-btn {
  flex: 1;
  padding: 0.5rem;
  font-size: var(--text-sm);
  font-weight: 600;
  background: var(--color-bg-tertiary);
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
  letter-spacing: 0.04em;
}

.config-toggle-btn:hover:not(.config-toggle-btn--active) {
  color: var(--color-text-secondary);
}

.config-toggle-btn--active {
  background: linear-gradient(135deg, var(--color-iridescent-2), var(--color-iridescent-3));
  color: white;
}

.config-days {
  display: flex;
  gap: 4px;
}

.config-day {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.625rem;
  font-weight: 700;
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
  letter-spacing: 0.02em;
}

.config-day:hover:not(.config-day--active) {
  border-color: rgba(129, 140, 248, 0.3);
  color: var(--color-text-primary);
}

.config-day--active {
  background: linear-gradient(135deg, var(--color-iridescent-1), var(--color-iridescent-2));
  border-color: transparent;
  color: white;
  box-shadow: 0 2px 6px rgba(96, 165, 250, 0.2);
}

/* ======================== SEQUENCE STEP EDITOR (AUT-1281 / AUT-1306) ======================== */

.config-field--sequence-limit {
  padding: 0.5rem;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-bg-tertiary) 80%, transparent);
}

.config-sequence-step-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.config-sequence-step {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 0.5rem;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.config-sequence-step--pause {
  border-color: color-mix(in srgb, var(--color-warning) 35%, var(--glass-border));
}

/* VueDraggable feedback — ghost / chosen / drag (dark theme) */
.config-sequence-step--ghost {
  opacity: 0.35;
  border-style: dashed;
  border-color: var(--color-iridescent-2);
}

.config-sequence-step--chosen {
  border-color: var(--color-iridescent-2);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--color-iridescent-2) 40%, transparent);
}

.config-sequence-step--drag {
  opacity: 0.92;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
}

.config-sequence-step__header {
  display: flex;
  align-items: center;
  gap: 0.375rem;
}

.config-sequence-step__nr {
  flex-shrink: 0;
  min-width: 1rem;
  font-size: var(--text-xs);
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--color-text-muted);
  text-align: right;
}

.config-sequence-step__type-badge {
  flex-shrink: 0;
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  padding: 0.1rem 0.3rem;
  border-radius: var(--radius-sm);
}

.config-sequence-step__type-badge--actuator {
  color: var(--color-real);
  background: color-mix(in srgb, var(--color-real) 18%, transparent);
}

.config-sequence-step__type-badge--pause {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
}

.config-sequence-step__handle {
  flex-shrink: 0;
  color: var(--color-text-muted);
  cursor: grab;
}

.config-sequence-step__handle:active {
  cursor: grabbing;
}

.config-sequence-step__header .config-select--compact {
  flex: 1;
}

.config-sequence-step__actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.config-mode-badge {
  display: inline-block;
  margin-left: var(--space-2);
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-info);
  background: color-mix(in srgb, var(--color-info) 18%, transparent);
  vertical-align: middle;
}

.config-hint--derived {
  color: var(--color-text-secondary);
}

.config-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  padding: 0.4375rem 0.625rem;
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.config-btn:hover {
  border-color: rgba(129, 140, 248, 0.4);
  color: var(--color-text-primary);
  background: rgba(129, 140, 248, 0.06);
}

.config-btn--sm {
  padding: 0.25rem 0.5rem;
  font-size: 0.6875rem;
}

.config-btn--danger {
  color: var(--color-text-muted);
}

.config-btn--danger:hover {
  color: var(--color-error);
  border-color: rgba(248, 113, 113, 0.35);
  background: rgba(248, 113, 113, 0.08);
}

.config-input--sm {
  padding: 0.375rem 0.5rem;
  font-size: var(--text-xs);
}

/* AUT-1284: Wrapper je Chemie-Komponente (Eingabe-Zeile + Vorschau darunter) */
.config-dose-component {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 0.5rem;
}

/* AUT-1284: Chemie ↔ Foerderrate Vorschau — kompakte read-only Zeilen je Komponente */
.config-dose-preview {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.5rem 0.625rem;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  margin: -0.25rem 0 0.25rem;
}

.config-dose-preview__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.config-dose-preview__label {
  font-size: 0.625rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.config-dose-preview__value {
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.config-dose-preview__value--dim {
  color: var(--color-text-muted);
  font-weight: 500;
  font-style: italic;
}

.config-dose-preview__value--warn {
  color: var(--color-warning);
  font-weight: 500;
  font-style: italic;
}

.config-panel__footer {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
}

.config-action {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.375rem;
  padding: 0.4375rem;
  font-size: 0.6875rem;
  font-weight: 500;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.config-action--duplicate {
  color: var(--color-text-secondary);
}

.config-action--duplicate:hover {
  background: rgba(129, 140, 248, 0.08);
  color: var(--color-iridescent-2);
}

.config-action--delete {
  color: var(--color-text-muted);
}

.config-action--delete:hover {
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.08);
}

.config-action:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 1px;
}

.config-toggle-btn:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: -1px;
}

.config-day:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 1px;
}

.config-panel__close:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 1px;
}

/* Slide transition */
.config-slide-enter-active {
  transition: all 0.2s var(--ease-out);
}

.config-slide-leave-active {
  transition: all 0.15s ease-in;
}

.config-slide-enter-from {
  opacity: 0;
  transform: translateX(16px);
}

.config-slide-leave-to {
  opacity: 0;
  transform: translateX(8px);
}

/* AUT-1389: Plan-Abo im Sensor-Panel */
.config-plan-abo {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
  background: var(--color-bg-secondary);
}

.config-plan-abo__fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.config-hint--plan-effective,
.config-hint--plan-locked {
  color: var(--color-iridescent-2);
}

.config-input--readonly {
  opacity: 0.75;
  cursor: not-allowed;
  background: var(--color-bg-tertiary, var(--color-bg-secondary));
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .config-slide-enter-active,
  .config-slide-leave-active {
    transition-duration: 0.01ms;
  }

  .config-slide-enter-from,
  .config-slide-leave-to {
    transform: none;
  }
}
</style>
