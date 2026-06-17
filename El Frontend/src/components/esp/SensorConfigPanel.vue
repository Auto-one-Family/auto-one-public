<script setup lang="ts">
/**
 * SensorConfigPanel — Three-Zone Sensor Configuration
 *
 * Zone 1 (Basic, always visible): Name, Unit, Enabled, Subzone
 * Zone 2 (Accordion): Thresholds & Alarms, Operation & Interval, Calibration
 * Zone 3 (Accordion - Expert): Hardware (GPIO/I2C/OneWire), Live Preview
 *
 * Used inside ESPSettingsSheet as SlideOver panel (HardwareView only, Route /hardware).
 */

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Save, Gauge, Settings, Cpu, Trash2, LayoutGrid, Workflow, ExternalLink, Info, FileText, Sprout, AlertTriangle, AlertCircle } from 'lucide-vue-next'
import { sensorsApi } from '@/api/sensors'
import { espApi } from '@/api/esp'
import { useEspStore } from '@/stores/esp'
import { useUiStore } from '@/shared/stores/ui.store'
import { useToast } from '@/composables/useToast'
import { inferInterfaceType } from '@/utils/sensorDefaults'
import { roundToDecimals } from '@/utils/formatters'
import { SENSOR_TYPE_CONFIG, getSensorUnit } from '@/utils/sensorDefaults'
import { AccordionSection } from '@/shared/design/primitives'
import RangeSlider from '@/shared/design/primitives/RangeSlider.vue'
import LiveDataPreview from './LiveDataPreview.vue'
import AlertConfigSection from '@/components/devices/AlertConfigSection.vue'
import RuntimeMaintenanceSection from '@/components/devices/RuntimeMaintenanceSection.vue'
import DeviceMetadataSection from '@/components/devices/DeviceMetadataSection.vue'
import LinkedRulesSection from '@/components/devices/LinkedRulesSection.vue'
import SubzoneAssignmentSection from '@/components/devices/SubzoneAssignmentSection.vue'
import SettingsBreadcrumb from '@/components/settings/SettingsBreadcrumb.vue'
import { useDashboardStore } from '@/shared/stores/dashboard.store'
import { useLogicStore } from '@/shared/stores/logic.store'
import { usePlantsStore } from '@/shared/stores/plants.store'
import { formatRelativeTime } from '@/utils/formatters'
import { PLANT_PHASE_LABELS, getPlantEventTypeLabel } from '@/components/plants/plantLabels'
import type { Plant, PlantLifecycleEvent } from '@/types'
import { extractSensorConditions } from '@/types/logic'
import type { LogicRule } from '@/types/logic'
import { deviceContextApi } from '@/api/device-context'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useActuatorStore } from '@/shared/stores/actuator.store'
import { createLogger } from '@/utils/logger'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { useSensorStore } from '@/shared/stores/sensor.store'
import type { DeviceScope } from '@/types'
import type { DeviceMetadata } from '@/types/device-metadata'
import { parseDeviceMetadata, mergeDeviceMetadata } from '@/types/device-metadata'
import type { SensorConfigCreate } from '@/types'
import PendingConfigBanner from './PendingConfigBanner.vue'
import { useBoardLayout } from '@/composables/useBoardLayout'

const configLogger = createLogger('SensorConfigPanel')
const alertStore = useAlertCenterStore()

interface Props {
  espId: string
  gpio: number
  sensorType: string
  unit?: string
  /** Sensor config UUID from database (required for DELETE on real ESPs) */
  configId?: string
  showMetadata?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  unit: '',
  configId: undefined,
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
const router = useRouter()
const espStore = useEspStore()
const actuatorStore = useActuatorStore()
const uiStore = useUiStore()
const zoneStore = useZoneStore()
const dashboardStore = useDashboardStore()
const logicStore = useLogicStore()
const plantsStore = usePlantsStore()

// =============================================================================
// State
// =============================================================================
const loading = ref(true)
const saving = ref(false)
const sensorDbId = ref<string | null>(null)
const lastConfigSubjectId = ref<string | null>(null)
const lastConfigCorrelationId = ref<string | null>(null)

// Basic fields
const name = ref('')
const description = ref('')
const unitValue = ref('')
const enabled = ref(true)

// Subzone
const subzoneId = ref<string | null>(null)

// AUT-299: Linked temperature sensor for ATC (Automatic Temperature Compensation)
const tempSensorConfigId = ref<string | null>(null)

// Device Scope (T13-R3 WP4) — UI auf Sensor-Ebene entfernt (AUT-251),
// Werte werden weiterhin geladen/gespeichert um Backend-Kompatibilitaet zu wahren.
const localScope = ref<DeviceScope>('zone_local')
const localAssignedZones = ref<string[]>([])
const activeZoneId = ref<string | null>(null)

// Operating mode (Block C: Phase 2B)
const operatingMode = ref<'continuous' | 'on_demand' | 'scheduled' | 'paused'>('continuous')
const timeoutSeconds = ref(0)
const timeoutSecondsHuman = computed(() => {
  const s = timeoutSeconds.value
  if (!s) return null
  if (s < 60) return `${s} Sekunden`
  const m = Math.floor(s / 60)
  return m === 1 ? '1 Minute' : `${m} Minuten`
})
// schedule_config (Auftrag 5): nur bei operating_mode=scheduled relevant
const scheduleConfig = ref<{ type: string; expression: string } | null>(null)

// Sensor-Lifecycle: Freshness & Calibration (AUT-39)
const measurementFreshnessHours = ref<number | null>(null)
const calibrationIntervalDays = ref<number | null>(null)
const calibrationData = ref<Record<string, unknown> | null>(null)

const calibrationStatusSummary = computed(() => {
  const data = calibrationData.value
  if (!data || typeof data !== 'object') {
    return { calibrated: false, label: 'Nicht kalibriert — Werte unzuverlässig' }
  }
  const derived = (data.derived as Record<string, unknown> | undefined) ?? data
  const calibratedAt = (data.metadata as Record<string, unknown> | undefined)?.calibrated_at
    ?? data.calibrated_at
    ?? derived.calibrated_at
  const cellFactor = derived.cell_factor
  if (calibratedAt || cellFactor != null) {
    return {
      calibrated: true,
      label: calibratedAt
        ? `Kalibriert ${formatRelativeTime(String(calibratedAt))}`
        : 'Kalibriert',
      cellFactor: typeof cellFactor === 'number' ? cellFactor : null,
      calibratedAt: calibratedAt ? String(calibratedAt) : null,
    }
  }
  return { calibrated: false, label: 'Nicht kalibriert — Werte unzuverlässig' }
})

function openCalibrationWizard(): void {
  router.push({
    path: '/calibration',
    query: {
      espId: props.espId,
      gpio: String(props.gpio),
      sensorType: props.sensorType,
      skipSelect: '1',
    },
  })
}
const CRON_PRESETS = [
  { label: 'Jede Stunde', value: '0 * * * *', description: 'Zur vollen Stunde' },
  { label: 'Alle 6 Stunden', value: '0 */6 * * *', description: '00:00, 06:00, 12:00, 18:00' },
  { label: 'Täglich um 8:00', value: '0 8 * * *', description: 'Einmal täglich' },
  { label: 'Alle 15 Minuten', value: '*/15 * * * *', description: '00, 15, 30, 45' },
  { label: 'Alle 30 Minuten', value: '*/30 * * * *', description: '00 und 30' },
  { label: 'Wochentags 9:00', value: '0 9 * * 1-5', description: 'Mo-Fr um 9:00' },
]

// Interface-specific
const interfaceType = computed(() => inferInterfaceType(props.sensorType))
const gpioPin = ref(props.gpio)
const i2cAddress = ref('0x44')
const i2cBus = ref(0)
const measureRangeMin = ref(0)
const measureRangeMax = ref(100)
const pulsesPerLiter = ref(330)

// External ADC source (ADS1115) — only relevant for analog probes (pH/EC).
// adc_source='internal' keeps the unchanged ESP32 12-bit ADC path (default).
// adc_source='ads1115' acquires via an external 16-bit I2C ADC (gpio stays 0,
// adcI2cAddress carries the ADS1115 module address 0x48-0x4B).
const adcSource = ref<'internal' | 'ads1115'>('internal')
const adcI2cAddress = ref('0x48')
const adcChannel = ref(0)
const pgaGain = ref<'6.144' | '4.096' | '2.048' | '1.024' | '0.512' | '0.256'>('4.096')
const ADS1115_ADDRESS_OPTIONS = ['0x48', '0x49', '0x4A', '0x4B']
const PGA_GAIN_OPTIONS: Array<{ value: typeof pgaGain.value; label: string }> = [
  { value: '6.144', label: '±6.144 V' },
  { value: '4.096', label: '±4.096 V (Standard)' },
  { value: '2.048', label: '±2.048 V' },
  { value: '1.024', label: '±1.024 V' },
  { value: '0.512', label: '±0.512 V' },
  { value: '0.256', label: '±0.256 V' },
]
const useAds1115 = computed(() => interfaceType.value === 'ANALOG' && adcSource.value === 'ads1115')

// Thresholds
const alarmLow = ref(0)
const warnLow = ref(0)
const warnHigh = ref(100)
const alarmHigh = ref(100)

// Device Metadata
const metadata = ref<DeviceMetadata>({})

// =============================================================================
// Computed
// =============================================================================

const sensorConfig = computed(() => SENSOR_TYPE_CONFIG[props.sensorType])
const defaultUnit = computed(() => getSensorUnit(props.sensorType) || props.unit || '')

// AUT-299: Is this sensor a pH or EC sensor that can use ATC?
const isAtcCapable = computed(() => {
  const t = props.sensorType.toLowerCase()
  return t === 'ph' || t === 'ec'
})

// AUT-300: Sensor types that require periodic calibration (matches server CALIBRATION_REQUIRED_SENSOR_TYPES)
const CALIBRATION_REQUIRED_TYPES = new Set(['ph', 'ec', 'moisture', 'soil_moisture'])
const isCalibrationRequired = computed(() =>
  CALIBRATION_REQUIRED_TYPES.has(props.sensorType.toLowerCase())
)

// AUT-300: Sensor-type-specific calibration hint for the alert section
const calibrationHelpText = computed((): string => {
  const t = props.sensorType.toLowerCase()
  if (t === 'ph') return 'pH-Elektroden degradieren durch Alterung und Verschmutzung. Monatliche Kalibrierung empfohlen (Standardintervall: 30 Tage).'
  if (t === 'ec') return 'EC-Elektroden können durch Ablagerungen und Alterung driften. Monatliche Kalibrierung empfohlen (Standardintervall: 30 Tage).'
  return 'Feuchtesensoren können nach einigen Monaten im Substrat driften. Regelmäßige Überprüfung empfohlen (Standardintervall: 90 Tage).'
})

// AUT-686 S4: ATC status + mode warning + calibration health
const sensorStore = useSensorStore()
const calGuideVisible = ref(false)

const showModeWarning = computed(() =>
  ['ph', 'ec'].includes(props.sensorType.toLowerCase()) && operatingMode.value === 'continuous'
)

const atcStatus = computed((): 'not_applicable' | 'no_link' | 'fallback' | 'ok' => {
  if (!isAtcCapable.value) return 'not_applicable'
  if (!tempSensorConfigId.value) return 'no_link'
  const degradedTs = sensorStore.getAtcDegradedTimestamp(props.espId, props.gpio, props.sensorType)
  if (degradedTs && Date.now() - degradedTs < 10 * 60 * 1000) return 'fallback'
  return 'ok'
})

const calibrationHealthState = computed((): {
  state: 'uncalibrated' | 'healthy' | 'drifting' | 'critical'
  slopePct: number | null
  calibratedAt: string | null
} => {
  const data = calibrationData.value
  if (!data || typeof data !== 'object') return { state: 'uncalibrated', slopePct: null, calibratedAt: null }
  const result = (data.calibration_result as Record<string, unknown> | undefined) ?? data
  const slopePct = result.slope_deviation_pct as number | null | undefined
  const calibratedAt = (data.metadata as Record<string, unknown> | undefined)?.calibrated_at
    ?? data.calibrated_at ?? result.calibrated_at
  const calStr = calibratedAt ? String(calibratedAt) : null
  if (slopePct == null) return calStr ? { state: 'healthy', slopePct: null, calibratedAt: calStr } : { state: 'uncalibrated', slopePct: null, calibratedAt: null }
  if (slopePct <= 15) return { state: 'healthy', slopePct, calibratedAt: calStr }
  if (slopePct <= 50) return { state: 'drifting', slopePct, calibratedAt: calStr }
  return { state: 'critical', slopePct, calibratedAt: calStr }
})

const CALIBRATION_GUIDES: Record<string, string> = {
  ph: '1. pH-7-Pufferlösung bereitstellen → Sensor eintauchen → warten bis stabil → Wert erfassen. 2. pH-4-Pufferlösung → gleicher Ablauf. → Kalibrierung starten',
  ec: '1. 1413 µS/cm KCl-Lösung bei bekannter Temperatur → Sensor eintauchen → warten bis stabil → Wert erfassen. → Kalibrierung starten',
}

/** AUT-299: All temperature sensors across all ESPs for ATC dropdown */
const temperatureSensorOptions = computed<Array<{ value: string; label: string }>>(() => {
  const TEMP_TYPES = new Set(['temperature', 'ds18b20', 'sht31_temp', 'sht31', 'bme280_temp'])
  const options: Array<{ value: string; label: string }> = []
  for (const device of espStore.devices) {
    const espDeviceId = espStore.getDeviceId(device)
    for (const sensor of (device.sensors ?? []) as Array<{ sensor_type: string; gpio: number; name?: string | null; config_id?: string; id?: string }>) {
      const sType = String(sensor.sensor_type ?? '').toLowerCase()
      if (!TEMP_TYPES.has(sType)) continue
      const configId: string | null = sensor.config_id ?? sensor.id ?? null
      if (!configId) continue
      const sensorName = sensor.name || sType
      options.push({
        value: configId,
        label: `${sensorName} (${espDeviceId}, GPIO ${sensor.gpio})`,
      })
    }
  }
  return options
})

// =============================================================================
// AUT-252: Datasheet metadata (read-only) + Plant context
// =============================================================================

/** Hat dieser Sensor-Typ Datenblatt-Metadaten hinterlegt? */
const hasDatasheet = computed<boolean>(() => {
  const cfg = sensorConfig.value
  if (!cfg) return false
  return Boolean(
    cfg.manufacturer
    || cfg.accuracy
    || cfg.datasheetUrl
    || cfg.maintenanceYears != null
    || cfg.calibrationRequired != null
    || cfg.calibrationNote,
  )
})

/**
 * AUT-252: Pflanzen-Kontext fuer die aktuelle Subzone.
 * Liefert die Pflanze, die der Subzone des Sensors zugeordnet ist (soft-deleted ausgeschlossen).
 */
const subzonePlant = computed<Plant | null>(() => {
  const sz = subzoneId.value
  if (!sz) return null
  const found = plantsStore.plants.find(
    (p) => p.subzone_id === sz && !p.deleted_at,
  )
  return found ?? null
})

/** Letzte 3 Lifecycle-Events der zugeordneten Pflanze (chronologisch absteigend). */
const recentLifecycleEvents = computed<PlantLifecycleEvent[]>(() => {
  const plant = subzonePlant.value
  if (!plant) return []
  const events = plant.lifecycle_events ?? []
  // events kommen vom Server in der Regel absteigend; Defensiv erneut sortieren.
  return [...events]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 3)
})

/**
 * AUT-252: Empfohlene Schwellwerte aus Plant-Profil ableiten.
 * Plant-Schema hat aktuell kein `thresholds_json` Feld — wir lesen defensiv und
 * unterstuetzen es, sobald Server es liefert (kein Schema-Bruch).
 * Erwartetes Format: { [sensorType: string]: { warn_low?: number; warn_high?: number; alarm_low?: number; alarm_high?: number } }
 */
interface PlantThresholdProfile {
  warn_low?: number | null
  warn_high?: number | null
  alarm_low?: number | null
  alarm_high?: number | null
}

const plantThresholdsForSensor = computed<PlantThresholdProfile | null>(() => {
  const plant = subzonePlant.value
  if (!plant) return null
  const ext = plant as unknown as Record<string, unknown>
  const raw = ext.thresholds_json
  if (!raw || typeof raw !== 'object') return null
  const sensorTypeKey = String(props.sensorType)
  const map = raw as Record<string, unknown>
  // Try exact, lower, and upper key variants
  const candidate =
    map[sensorTypeKey]
    ?? map[sensorTypeKey.toLowerCase()]
    ?? map[sensorTypeKey.toUpperCase()]
  if (!candidate || typeof candidate !== 'object') return null
  const t = candidate as Record<string, unknown>
  const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
  return {
    warn_low: num(t.warn_low),
    warn_high: num(t.warn_high),
    alarm_low: num(t.alarm_low),
    alarm_high: num(t.alarm_high),
  }
})

const hasPlantThresholds = computed<boolean>(() => {
  const t = plantThresholdsForSensor.value
  if (!t) return false
  return [t.alarm_low, t.warn_low, t.warn_high, t.alarm_high].some(v => v != null)
})

/** Pflanzen-Phase als deutsches Label (Fallback: roher Wert). */
const plantPhaseLabel = computed<string>(() => {
  const plant = subzonePlant.value
  if (!plant) return ''
  return PLANT_PHASE_LABELS[plant.phase] ?? plant.phase
})

/** Schwellwerte aus Pflanzenprofil uebernehmen + speichern. */
const applyingPlantThresholds = ref(false)

async function applyPlantThresholds(): Promise<void> {
  const t = plantThresholdsForSensor.value
  if (!t) return
  applyingPlantThresholds.value = true
  try {
    if (t.alarm_low != null) alarmLow.value = roundToDecimals(t.alarm_low, 2)
    if (t.warn_low != null) warnLow.value = roundToDecimals(t.warn_low, 2)
    if (t.warn_high != null) warnHigh.value = roundToDecimals(t.warn_high, 2)
    if (t.alarm_high != null) alarmHigh.value = roundToDecimals(t.alarm_high, 2)
    await handleSave()
  } finally {
    applyingPlantThresholds.value = false
  }
}

const isI2C = computed(() => interfaceType.value === 'I2C')
const isOneWire = computed(() => interfaceType.value === 'ONEWIRE')
const isAnalog = computed(() => interfaceType.value === 'ANALOG')
const isDigital = computed(() => props.sensorType.toLowerCase().includes('flow'))
const contextDevice = computed(() =>
  espStore.devices.find((device) => espStore.getDeviceId(device) === props.espId),
)
const deviceHardwareType = computed(() => contextDevice.value?.hardware_type ?? null)
const {
  layout: boardLayout,
  isKnownBoard,
  i2cDefaultLabel,
  isReserved,
} = useBoardLayout(deviceHardwareType)
const contextSensor = computed(() => {
  const normalizedType = String(props.sensorType || '').toLowerCase()
  return (contextDevice.value?.sensors ?? []).find((sensor: any) =>
    Number(sensor.gpio) === props.gpio
    && String(sensor.sensor_type ?? '').toLowerCase() === normalizedType,
  ) ?? null
})
const zoneContextLabel = computed(() =>
  (contextDevice.value as any)?.zone_name
  || (contextDevice.value as any)?.zone_id
  || 'nicht zugewiesen',
)
const subzoneContextLabel = computed(() =>
  (contextSensor.value as any)?.subzone_id || subzoneId.value || null,
)

/** ADC1-only pins for analog sensors — board-aware via useBoardLayout */

/** I2C address options per sensor type */
const i2cAddressOptions = computed(() => {
  const t = props.sensorType.toLowerCase()
  if (t.includes('sht31')) return [{ value: '0x44', label: '0x44 (Default)' }, { value: '0x45', label: '0x45 (Alt)' }]
  if (t.includes('bmp280') || t.includes('bme280')) return [{ value: '0x76', label: '0x76 (Default)' }, { value: '0x77', label: '0x77 (Alt)' }]
  return [{ value: '0x44', label: '0x44' }, { value: '0x45', label: '0x45' }, { value: '0x76', label: '0x76' }, { value: '0x77', label: '0x77' }]
})

/** Storage key prefix for accordion persistence */
const accordionKey = computed(() => `sensor-${props.espId}-${props.gpio}`)

// =============================================================================
// AUT-246: Cross-References (Verlinkte Quellen) — read-only
// =============================================================================

/** Composite sensor ID used by dashboard widgets: "{espId}:{gpio}:{sensorType}" */
const sensorWidgetKey = computed(
  () => `${props.espId}:${props.gpio}:${props.sensorType}`,
)

/**
 * AUT-246: Widgets, die diesen Sensor visuell darstellen.
 * Quelle: dashboardStore.layouts[].widgets[].config.sensorId
 * Diese Widgets nutzen visuelle (read-only) Schwellwerte; KEIN Alert.
 */
interface LinkedWidgetEntry {
  layoutId: string
  layoutName: string
  widgetId: string
  widgetTitle: string
}

const linkedWidgets = computed<LinkedWidgetEntry[]>(() => {
  const key = sensorWidgetKey.value
  const result: LinkedWidgetEntry[] = []
  for (const layout of dashboardStore.layouts) {
    for (const widget of layout.widgets) {
      if (widget.config?.sensorId === key) {
        result.push({
          layoutId: layout.id,
          layoutName: layout.name || 'Unbenanntes Dashboard',
          widgetId: widget.id,
          widgetTitle: widget.config?.title || widget.type,
        })
      }
    }
  }
  return result
})

/**
 * AUT-246: Regeln, die diesen Sensor als Trigger verwenden.
 * Quelle: logicStore.rules[].conditions[] mit type='sensor'|'sensor_threshold'|'hysteresis'
 * Vergleich: esp_id + gpio + sensor_type (sensor_type optional bei hysteresis).
 */
interface LinkedRuleEntry {
  ruleId: string
  ruleName: string
  enabled: boolean
}

const linkedRules = computed<LinkedRuleEntry[]>(() => {
  const result: LinkedRuleEntry[] = []
  const sensorType = String(props.sensorType || '').toLowerCase()
  for (const rule of logicStore.rules as LogicRule[]) {
    const sensorConds = extractSensorConditions(rule.conditions)
    const matches = sensorConds.some((sc) => {
      if (sc.esp_id !== props.espId) return false
      if (Number(sc.gpio) !== props.gpio) return false
      const condType = String(sc.sensor_type || '').toLowerCase()
      // sensor_type may be empty for hysteresis; fall back to gpio match only.
      return condType === '' || condType === sensorType
    })
    if (matches) {
      result.push({
        ruleId: rule.id,
        ruleName: rule.name,
        enabled: rule.enabled,
      })
    }
  }
  return result
})

// ── AUT-623: Active alerts for this sensor (config_id primary, esp_id+gpio fallback) ──
const sensorActiveAlerts = computed(() => {
  const meta = (n: { metadata: unknown }): Record<string, unknown> =>
    (n.metadata as Record<string, unknown>) ?? {}
  return alertStore.activeAlertsFromInbox.filter(n => {
    const m = meta(n)
    if (props.configId && m['config_id'] === props.configId) return true
    return m['esp_id'] === props.espId && Number(m['gpio']) === props.gpio
  })
})

const sensorHasActiveAlert = computed(() => sensorActiveAlerts.value.length > 0)

const sensorAlertIcon = computed(() => {
  if (!sensorHasActiveAlert.value) return null
  return sensorActiveAlerts.value.some(n => n.severity === 'critical') ? AlertCircle : AlertTriangle
})

/** True when any active alert for this sensor was triggered by the logic engine */
const hasRuleTriggeredAlert = computed(() =>
  sensorActiveAlerts.value.some(n => n.source === 'logic_engine')
)

function navigateToWidget(entry: LinkedWidgetEntry): void {
  router.push({ name: 'editor-dashboard', params: { dashboardId: entry.layoutId } })
}

function navigateToRule(entry: LinkedRuleEntry): void {
  router.push({ name: 'logic-rule', params: { ruleId: entry.ruleId } })
}

// =============================================================================
// Load existing config
// =============================================================================
onMounted(async () => {

  // Load sensor config from server (Real + Mock — Single Source of Truth).
  // Primary: config_id (UUID) — always unambiguous, even for 2x SHT31 on different I2C addresses.
  // Fallback: gpio + sensorType (legacy, works for single-sensor-per-GPIO).
  try {
    const config = props.configId
      ? await sensorsApi.getByConfigId(props.configId)
      : await sensorsApi.get(props.espId, props.gpio, props.sensorType)
    if (config) {
      sensorDbId.value = config.id ? String(config.id) : null
      name.value = config.name || ''
      const configExt = config as unknown as Record<string, unknown>
      description.value = (configExt.description as string) || ''
      unitValue.value = (configExt.unit as string) || defaultUnit.value
      enabled.value = config.enabled !== false
      const i2cVal = config.i2c_address
      i2cAddress.value = i2cVal != null ? `0x${Number(i2cVal).toString(16)}` : '0x44'
      i2cBus.value = (configExt.i2c_bus as number) ?? 0
      pulsesPerLiter.value = (configExt.pulses_per_liter as number) ?? 330

      // External ADC source (ADS1115) — hydrate for analog probes
      adcSource.value = (configExt.adc_source as 'internal' | 'ads1115') ?? 'internal'
      const adcCh = configExt.adc_channel
      adcChannel.value = adcCh != null ? Number(adcCh) : 0
      // For ADS1115 the i2c_address carries the module address (0x48-0x4B)
      if (adcSource.value === 'ads1115' && i2cVal != null) {
        adcI2cAddress.value = `0x${Number(i2cVal).toString(16).toUpperCase()}`
      }
      const loadedPga = configExt.pga_gain as string | undefined
      if (loadedPga && PGA_GAIN_OPTIONS.some((o) => o.value === loadedPga)) {
        pgaGain.value = loadedPga as typeof pgaGain.value
      }

      // Subzone (C1: backend returns subzone_id in GET response)
      subzoneId.value = config.subzone_id ?? null

      // Operating mode (Block C: backend returns operating_mode, timeout_seconds)
      operatingMode.value = (config.operating_mode as 'continuous' | 'on_demand' | 'scheduled' | 'paused') || 'continuous'
      timeoutSeconds.value = config.timeout_seconds ?? 0

      // schedule_config (Auftrag 5: backend returns schedule_config)
      const sc = configExt.schedule_config as { type?: string; expression?: string } | null | undefined
      scheduleConfig.value =
        sc?.expression && sc?.type === 'cron'
          ? { type: 'cron', expression: sc.expression }
          : null

      // Sensor-Lifecycle: Freshness & Calibration (AUT-39)
      measurementFreshnessHours.value = (configExt.measurement_freshness_hours as number) ?? null
      calibrationIntervalDays.value = (configExt.calibration_interval_days as number) ?? null
      calibrationData.value = (config.calibration as Record<string, unknown> | null) ?? null

      if (config.threshold_min != null) alarmLow.value = roundToDecimals(config.threshold_min, 2)
      if (config.warning_min != null) warnLow.value = roundToDecimals(config.warning_min, 2)
      if (config.warning_max != null) warnHigh.value = roundToDecimals(config.warning_max, 2)
      if (config.threshold_max != null) alarmHigh.value = roundToDecimals(config.threshold_max, 2)

      metadata.value = parseDeviceMetadata(config.metadata)

      // Device Scope (T13-R3 WP4)
      localScope.value = (configExt.device_scope as DeviceScope) ?? 'zone_local'
      localAssignedZones.value = (configExt.assigned_zones as string[]) ?? []

      // AUT-299: ATC linked temperature sensor
      tempSensorConfigId.value = (configExt.temp_sensor_config_id as string | null) ?? null
    }
  } catch {
    // No config in DB — use defaults or Mock fallback (C2)
    if (isMockEsp.value) {
      const device = espStore.devices.find(d => espStore.getDeviceId(d) === props.espId)
      const sensor = device?.sensors
        ? (device.sensors as any[]).find(
            (s) =>
              s.gpio === props.gpio &&
              (!props.sensorType || s.sensor_type === props.sensorType)
          )
        : null

      if (sensor) {
        name.value = sensor.name ?? ''
        unitValue.value = sensor.unit ?? defaultUnit.value
        subzoneId.value = sensor.subzone_id ?? null
        operatingMode.value = (sensor as any).operating_mode || 'continuous'
        timeoutSeconds.value = (sensor as any).timeout_seconds ?? 0
        const sc = (sensor as any).schedule_config
        scheduleConfig.value =
          sc?.expression && sc?.type === 'cron'
            ? { type: 'cron', expression: sc.expression }
            : null
        measurementFreshnessHours.value = (sensor as any).measurement_freshness_hours ?? null
        calibrationIntervalDays.value = (sensor as any).calibration_interval_days ?? null
      } else {
        unitValue.value = defaultUnit.value
      }
    } else {
      unitValue.value = defaultUnit.value
      operatingMode.value = 'continuous'
      timeoutSeconds.value = 0
      scheduleConfig.value = null
    }

    if (sensorConfig.value) {
      const { min, max } = sensorConfig.value
      const range = max - min
      alarmLow.value = roundToDecimals(min, 2)
      warnLow.value = roundToDecimals(min + range * 0.1, 2)
      warnHigh.value = roundToDecimals(max - range * 0.1, 2)
      alarmHigh.value = roundToDecimals(max, 2)
    }
  }
  loading.value = false

  // Load active zone context (T13-R3 WP4)
  if (sensorDbId.value && localScope.value !== 'zone_local') {
    try {
      const ctx = await deviceContextApi.getContext('sensor', sensorDbId.value)
      activeZoneId.value = ctx.active_zone_id ?? null
    } catch {
      // No context set yet — that's fine
    }
  }

  // Ensure zone entities are loaded for the scope section
  if (zoneStore.zoneEntities.length === 0) {
    zoneStore.fetchZoneEntities().catch(() => {})
  }

  // AUT-246: Ensure logic rules are loaded for the cross-reference list
  if (logicStore.rules.length === 0) {
    logicStore.fetchRules().catch(() => {})
  }

  // AUT-252: Plants fuer Subzone-Pflanzen-Kontext laden
  if (plantsStore.plants.length === 0) {
    plantsStore.fetchPlants().catch(() => {})
  }
})

function setCronExpression(expression: string) {
  scheduleConfig.value = expression.trim()
    ? { type: 'cron', expression: expression.trim() }
    : null
}

// =============================================================================
// Delete
// =============================================================================
const deleting = ref(false)
const isMockEsp = computed(() => espApi.isMockEsp(props.espId))

async function confirmAndDelete() {
  const confirmed = await uiStore.confirm({
    title: 'Sensor entfernen',
    message: 'Der Sensor wird unwiderruflich aus diesem Gerät entfernt. Historische Daten bleiben erhalten.',
    variant: 'danger',
    confirmText: 'Entfernen',
  })
  if (!confirmed) return

  deleting.value = true
  try {
    if (props.configId) {
      // Unified path: Mock AND Real ESPs use the same DELETE /sensors/{esp_id}/{config_id}
      // This endpoint handles simulation job cleanup, dual-storage sync, and MQTT config publish
      await sensorsApi.delete(props.espId, props.configId)
    } else if (espApi.isMockEsp(props.espId)) {
      // Fallback for Mock-ESPs without config_id (e.g. freshly added sensors not yet in DB)
      await espStore.removeSensor(props.espId, props.gpio)
    } else {
      toast.error('Sensor-Config-ID fehlt — Löschung nicht möglich')
      return
    }
    if (isMockEsp.value) {
      toast.success('[Simulation] Sensor entfernt', {
        dedupeKey: `sensor-delete:${props.espId}:${props.gpio}:${props.sensorType}`,
      })
    } else {
      toast.info('Löschauftrag akzeptiert - warte auf Geräte-Rückmeldung', {
        dedupeKey: `sensor-delete:${props.espId}:${props.gpio}:${props.sensorType}`,
      })
    }
    emit('deleted')
  } catch {
    toast.error('Sensor konnte nicht entfernt werden')
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
    // Block A: Real AND Mock — persist via Backend (Single Source of Truth: subzone_configs)
    const config: Record<string, unknown> = {
      esp_id: props.espId,
      gpio: props.gpio,
      sensor_type: props.sensorType,
      name: name.value || null,
      description: description.value || null,
      unit: unitValue.value || null,
      enabled: enabled.value,
      interface_type: interfaceType.value,
      threshold_min: alarmLow.value,
      threshold_max: alarmHigh.value,
      warning_min: warnLow.value,
      warning_max: warnHigh.value,
      operating_mode: operatingMode.value,
      timeout_seconds: timeoutSeconds.value,
      measurement_freshness_hours: measurementFreshnessHours.value,
      calibration_interval_days: calibrationIntervalDays.value,
    }

    // schedule_config (Auftrag 5): nur bei scheduled senden
    if (operatingMode.value === 'scheduled' && scheduleConfig.value?.expression) {
      config.schedule_config = { type: 'cron', expression: scheduleConfig.value.expression }
    } else if (operatingMode.value !== 'scheduled') {
      config.schedule_config = null
    }

    if (isI2C.value) {
      const parsed = i2cAddress.value != null
        ? parseInt(String(i2cAddress.value).replace(/^0x/i, ''), 16)
        : null
      config.i2c_address = Number.isNaN(parsed) ? null : parsed
      config.i2c_bus = i2cBus.value
    }

    if (isDigital.value) {
      config.pulses_per_liter = pulsesPerLiter.value
    }

    if (isAnalog.value) {
      config.measure_range_min = measureRangeMin.value
      config.measure_range_max = measureRangeMax.value

      // External ADC source (ADS1115). The internal ADC stays the default and
      // the analog path is fully unchanged; ads1115 only swaps the RAW source.
      config.adc_source = adcSource.value
      if (adcSource.value === 'ads1115') {
        // For ADS1115 the module address travels in i2c_address (gpio stays 0).
        const adcParsed = parseInt(String(adcI2cAddress.value).replace(/^0x/i, ''), 16)
        config.i2c_address = Number.isNaN(adcParsed) ? null : adcParsed
        config.adc_channel = adcChannel.value
        config.pga_gain = pgaGain.value
      } else {
        config.adc_channel = null
        config.pga_gain = null
      }
    }

    // Block B1: Normalize "Keine Subzone" — never send "__none__" to API
    const rawSubzone = subzoneId.value
    config.subzone_id =
      rawSubzone === '__none__' || rawSubzone == null || rawSubzone === ''
        ? null
        : rawSubzone

    // Device Scope (T13-R3 WP4)
    config.device_scope = localScope.value
    config.assigned_zones = localScope.value === 'zone_local' ? [] : localAssignedZones.value

    // AUT-299: ATC temperature sensor link (null = remove link)
    config.temp_sensor_config_id = tempSensorConfigId.value ?? null

    config.metadata = mergeDeviceMetadata(null, metadata.value)

    const result = await sensorsApi.createOrUpdate(props.espId, props.gpio, config as unknown as SensorConfigCreate)
    if (result?.id) {
      sensorDbId.value = String(result.id)
    }
    if (isMockEsp.value) {
      toast.success('[Simulation] Sensor-Konfiguration gespeichert')
      emit('saved')
    } else {
      const response = result as unknown as Record<string, unknown>
      const correlationId = typeof response.correlation_id === 'string' ? response.correlation_id : undefined
      const requestId = typeof response.request_id === 'string' ? response.request_id : undefined
      const handles = [correlationId ? `Korrelation: ${correlationId}` : '', requestId ? `Request-ID: ${requestId}` : '']
        .filter(Boolean)
        .join(' | ')
      const scope = `sensor:${props.gpio}:${props.sensorType}`
      const summary = `Sensor-Konfiguration ${props.sensorType} an GPIO ${props.gpio}`
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
        toast.success('Sensor-Konfiguration wurde vom Gerät bestätigt')
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
</script>

<template>
  <div class="sensor-config" :class="{ 'sensor-config--loading': loading }">
    <div v-if="loading" class="sensor-config__loading">Lade Konfiguration...</div>

    <template v-else>
      <!-- Settings-Kontextpfad: Zone -> Subzone -> ESP -> GPIO (AUT-251) -->
      <SettingsBreadcrumb
        :zone="zoneContextLabel"
        :subzone="subzoneContextLabel"
        :esp-id="espId"
        :gpio="gpio"
      />

      <!-- AUT-623: Active alert indicator (only shown when alert exists for this sensor) -->
      <div v-if="sensorHasActiveAlert" class="sensor-config__alert-notice">
        <component :is="sensorAlertIcon" class="sensor-config__alert-notice-icon" aria-hidden="true" />
        <span>Aktiver Alarm für diesen Sensor</span>
      </div>

      <section v-if="isMockEsp" class="sensor-config__simulation-badge" aria-label="Simulation Hinweis">
        [Simulation] Mock-ESP - Aktionen werden simuliert.
      </section>
      <!-- ═══ ZONE 1: BASIC (always visible) ══════════════════════════════ -->
      <section class="sensor-config__section">
        <h3 class="sensor-config__section-title">Grundeinstellungen</h3>

        <!-- Zone: read-only, vom Geraet vererbt (Subzone wird unten als Dropdown gepflegt) -->
        <!-- AUT-251: Zone gehoert zum Geraet, NICHT zum Sensor — "im Geraet aendern" oeffnet ESP-Settings -->
        <div class="sensor-config__zone-header">
          <span class="sensor-config__zone-label">Geraet:</span>
          <span class="sensor-config__zone-value">{{ contextDevice?.name || espId }}</span>
          <span class="sensor-config__zone-hint">(vom Geraet vererbt)</span>
        </div>
        <div class="sensor-config__zone-header">
          <span class="sensor-config__zone-label">Zone:</span>
          <span class="sensor-config__zone-value">{{ contextDevice?.zone_name || contextDevice?.zone_id || 'Keine Zone' }}</span>
          <button
            type="button"
            class="sensor-config__zone-link"
            aria-label="Zone im Geraet aendern"
            @click="requestOpenEspSettings"
          >
            im Geraet aendern
          </button>
        </div>

        <div class="sensor-config__field">
          <label class="sensor-config__label">Name</label>
          <input
            v-model="name"
            type="text"
            class="sensor-config__input"
            placeholder="z.B. pH Becken Ost"
          />
        </div>

        <div class="sensor-config__field">
          <label class="sensor-config__label">Beschreibung</label>
          <input
            v-model="description"
            type="text"
            class="sensor-config__input"
            placeholder="Optional"
          />
        </div>

        <div class="sensor-config__row">
          <div class="sensor-config__field sensor-config__field--half">
            <label class="sensor-config__label">Einheit</label>
            <input v-model="unitValue" type="text" class="sensor-config__input" />
          </div>
          <div class="sensor-config__field sensor-config__field--half">
            <label class="sensor-config__label">Sensor-Typ</label>
            <input :value="sensorConfig?.label ?? sensorType" type="text" class="sensor-config__input" disabled :title="sensorType" />
          </div>
        </div>

        <div class="sensor-config__field sensor-config__field--toggle">
          <label class="sensor-config__label">Aktiv</label>
          <button
            :class="['sensor-config__toggle', { 'sensor-config__toggle--on': enabled }]"
            @click="enabled = !enabled"
          >
            <span class="sensor-config__toggle-dot" />
          </button>
        </div>

        <!-- Subzone assignment (with create-new option) -->
        <div class="sensor-config__field">
          <SubzoneAssignmentSection
            v-model="subzoneId"
            :esp-id="espId"
            :gpio="gpio"
            :zone-id="espStore.devices.find(d => espStore.getDeviceId(d) === espId)?.zone_id ?? null"
          />
        </div>

        <!-- Betriebsmodus (Block C) -->
        <div class="sensor-config__field">
          <label class="sensor-config__label">Betriebsmodus</label>
          <select v-model="operatingMode" class="sensor-config__select">
            <option value="continuous">Dauerbetrieb</option>
            <option value="on_demand">Bei Bedarf</option>
            <option value="scheduled">Zeitgesteuert</option>
            <option value="paused">Pausiert</option>
          </select>
        </div>

        <!-- AUT-686 S4: pH/EC Dauerbetrieb-Warning (informativ, kein Hard-Block) -->
        <div v-if="showModeWarning" class="sensor-config__mode-warning" role="note">
          <AlertTriangle class="sensor-config__mode-warning-icon" :size="14" aria-hidden="true" />
          Dauerbetrieb beschleunigt den Verschleiß der Referenzelektrode (DFRobot SEN0169-V2, SEN0231). "Bei Bedarf" verlängert die Elektrodenlebensdauer erheblich.
        </div>

        <!-- Stale-Timeout (nur bei Dauerbetrieb) -->
        <div v-if="operatingMode === 'continuous'" class="sensor-config__field">
          <label class="sensor-config__label">Alarm bei fehlendem Signal nach</label>
          <div class="sensor-config__input-row">
            <input
              v-model.number="timeoutSeconds"
              type="number"
              min="0"
              max="86400"
              class="sensor-config__input"
            />
            <span v-if="timeoutSecondsHuman" class="sensor-config__input-hint">{{ timeoutSecondsHuman }}</span>
          </div>
          <span class="sensor-config__helper">0 = Alarm deaktiviert — Wird kein Messwert empfangen, zeigt das Dashboard eine Warnung.</span>
        </div>

        <!-- schedule_config (Auftrag 5: nur bei Zeitgesteuert) -->
        <div v-if="operatingMode === 'scheduled'" class="sensor-config__field sensor-config__schedule">
          <label class="sensor-config__label">Zeitplan (Cron)</label>
          <span class="sensor-config__helper">Server-gesteuerte Messung nach Zeitplan</span>
          <div class="sensor-config__schedule-presets">
            <button
              v-for="preset in CRON_PRESETS"
              :key="preset.value"
              type="button"
              class="sensor-config__preset-btn"
              :class="{ 'sensor-config__preset-btn--active': scheduleConfig?.expression === preset.value }"
              :title="preset.description"
              @click="setCronExpression(preset.value)"
            >
              {{ preset.label }}
            </button>
          </div>
          <input
            :value="scheduleConfig?.expression ?? ''"
            type="text"
            class="sensor-config__input sensor-config__input--mono"
            placeholder="z.B. 0 */6 * * *"
            @input="setCronExpression(($event.target as HTMLInputElement).value)"
          />
          <span class="sensor-config__helper">Format: Minute Stunde Tag Monat Wochentag</span>
        </div>

        <!-- Sensor-Lifecycle: Freshness (AUT-39) — calibration interval moved to Kalibrierungsbereich -->
        <div class="sensor-config__field">
          <label class="sensor-config__label">Veraltungsgrenze (Stunden)</label>
          <input
            v-model.number="measurementFreshnessHours"
            type="number"
            min="0"
            step="1"
            class="sensor-config__input"
            placeholder="leer = kein Limit"
          />
          <span class="sensor-config__helper">Nach dieser Zeit gilt ein Messwert als veraltet</span>
        </div>
        <!-- AUT-299: ATC Temperaturkompensation (nur für pH und EC) -->
        <div v-if="isAtcCapable" class="sensor-config__field">
          <label class="sensor-config__label">Temperaturkompensation — Quelle</label>
          <select v-model="tempSensorConfigId" class="sensor-config__select">
            <option :value="null">Keiner (Standardwert 25 °C)</option>
            <option
              v-for="opt in temperatureSensorOptions"
              :key="opt.value"
              :value="opt.value"
            >
              {{ opt.label }}
            </option>
          </select>
          <!-- AUT-686 S4: ATC status indicator -->
          <div class="sensor-config__atc-status">
            <span v-if="atcStatus === 'no_link'" class="sensor-config__atc-badge sensor-config__atc-badge--gray">
              Kein Sensor verknüpft — 25 °C Standardwert aktiv
            </span>
            <span v-else-if="atcStatus === 'fallback'" class="sensor-config__atc-badge sensor-config__atc-badge--warning">
              <AlertTriangle :size="12" aria-hidden="true" />
              ATC-Fallback — Temperatursensor antwortet nicht
            </span>
            <span v-else class="sensor-config__atc-badge sensor-config__atc-badge--ok">
              Temperaturkompensation aktiv
            </span>
          </div>
        </div>
      </section>

      <!-- ═══ ZONE 2: ADVANCED (Accordion sections) ═══════════════════════ -->

      <!--
        AUT-246: Schwellwerte & Alerts — vereinigtes Akkordeon
        Vereint die früheren zwei Akkordeons:
          1) "Sensor-Schwellwerte (Basis)" → SSoT für Sensor-Threshold-Alerts
             (Speichert in SensorConfig.thresholds via createOrUpdate)
          2) "Alert-Konfiguration"        → Override/Suppression (ISA-18.2)
             (Speichert in SensorConfig.alert_config via PATCH /sensors/{id}/alert-config)
        Inhalt 1:1 erhalten — nur visuelle Restrukturierung mit Sub-Sektionen.
        Zusätzlich: Read-only Cross-Reference auf Widgets + Regeln (verlinkte Quellen).
      -->
      <AccordionSection
        title="Schwellwerte & Alerts"
        :storage-key="`${accordionKey}-thresholds-alerts`"
        :icon="Gauge"
      >
        <!-- ─── Sub-Sektion 1: Sensor-Schwelle (Basis) ───────────────── -->
        <div class="sensor-config__sub-section">
          <div class="sensor-config__sub-header">
            <h4 class="sensor-config__sub-title">Sensor-Schwelle (Basis)</h4>
            <span class="sensor-config__source-tag">DB: sensor_config</span>
          </div>
          <p class="sensor-config__sub-hint">
            <Info class="sensor-config__sub-hint-icon" aria-hidden="true" />
            Diese Schwelle löst direkte Sensor-Alerts beim Datenempfang aus.
          </p>

          <RangeSlider
            :min="sensorConfig?.min ?? 0"
            :max="sensorConfig?.max ?? 100"
            :alarm-low="alarmLow"
            :warn-low="warnLow"
            :warn-high="warnHigh"
            :alarm-high="alarmHigh"
            :unit="unitValue"
            :step="0.1"
            @update:alarm-low="alarmLow = $event"
            @update:warn-low="warnLow = $event"
            @update:warn-high="warnHigh = $event"
            @update:alarm-high="alarmHigh = $event"
          />

          <div class="sensor-config__threshold-inputs">
            <div class="sensor-config__field sensor-config__field--quarter">
              <label class="sensor-config__label sensor-config__label--alarm">Alarm &#8595;</label>
              <input v-model.number="alarmLow" type="number" step="0.1" class="sensor-config__input sensor-config__input--sm" />
            </div>
            <div class="sensor-config__field sensor-config__field--quarter">
              <label class="sensor-config__label sensor-config__label--warn">Warn &#8595;</label>
              <input v-model.number="warnLow" type="number" step="0.1" class="sensor-config__input sensor-config__input--sm" />
            </div>
            <div class="sensor-config__field sensor-config__field--quarter">
              <label class="sensor-config__label sensor-config__label--warn">Warn &#8593;</label>
              <input v-model.number="warnHigh" type="number" step="0.1" class="sensor-config__input sensor-config__input--sm" />
            </div>
            <div class="sensor-config__field sensor-config__field--quarter">
              <label class="sensor-config__label sensor-config__label--alarm">Alarm &#8593;</label>
              <input v-model.number="alarmHigh" type="number" step="0.1" class="sensor-config__input sensor-config__input--sm" />
            </div>
          </div>
        </div>

        <!-- ─── Sub-Sektion 2: Alert-Override ────────────────────────── -->
        <div v-if="sensorDbId" class="sensor-config__sub-section">
          <div class="sensor-config__sub-header">
            <h4 class="sensor-config__sub-title">Alert-Override</h4>
            <span class="sensor-config__source-tag">DB: alert_config</span>
          </div>
          <p class="sensor-config__sub-hint">
            <Info class="sensor-config__sub-hint-icon" aria-hidden="true" />
            Override gilt zusätzlich zur Basis-Schwelle (ISA-18.2 Suppression-Hierarchie).
          </p>

          <AlertConfigSection
            :entity-id="sensorDbId"
            entity-type="sensor"
            :fetch-fn="sensorsApi.getAlertConfig"
            :update-fn="sensorsApi.updateAlertConfig"
          />
        </div>

        <!-- ─── Sub-Sektion 3: Verlinkte Quellen (Cross-Reference) ───── -->
        <div class="sensor-config__sub-section">
          <div class="sensor-config__sub-header">
            <h4 class="sensor-config__sub-title">Verlinkte Quellen</h4>
            <span class="sensor-config__source-tag sensor-config__source-tag--readonly">read-only</span>
          </div>

          <ul class="sensor-config__cross-ref-list">
            <li class="sensor-config__cross-ref-item">
              <LayoutGrid class="sensor-config__cross-ref-icon" aria-hidden="true" />
              <span class="sensor-config__cross-ref-count">{{ linkedWidgets.length }}</span>
              <span class="sensor-config__cross-ref-text">
                {{ linkedWidgets.length === 1 ? 'Widget nutzt' : 'Widgets nutzen' }} visuelle Schwellen
              </span>
            </li>
            <li
              v-for="entry in linkedWidgets"
              :key="`widget-${entry.layoutId}-${entry.widgetId}`"
              class="sensor-config__cross-ref-link-item"
            >
              <button
                type="button"
                class="sensor-config__cross-ref-link"
                @click="navigateToWidget(entry)"
              >
                <span class="sensor-config__cross-ref-link-name">{{ entry.widgetTitle }}</span>
                <span class="sensor-config__cross-ref-link-meta">in {{ entry.layoutName }}</span>
                <ExternalLink class="sensor-config__cross-ref-nav-icon" aria-hidden="true" />
              </button>
            </li>

            <li class="sensor-config__cross-ref-item">
              <Workflow class="sensor-config__cross-ref-icon" aria-hidden="true" />
              <span class="sensor-config__cross-ref-count">{{ linkedRules.length }}</span>
              <span class="sensor-config__cross-ref-text">
                {{ linkedRules.length === 1 ? 'Regel nutzt' : 'Regeln nutzen' }} diesen Sensor als Trigger
              </span>
            </li>
            <li
              v-for="entry in linkedRules"
              :key="`rule-${entry.ruleId}`"
              class="sensor-config__cross-ref-link-item"
            >
              <button
                type="button"
                class="sensor-config__cross-ref-link"
                @click="navigateToRule(entry)"
              >
                <span class="sensor-config__cross-ref-link-name">{{ entry.ruleName }}</span>
                <span
                  :class="[
                    'sensor-config__cross-ref-state',
                    entry.enabled ? 'sensor-config__cross-ref-state--on' : 'sensor-config__cross-ref-state--off',
                  ]"
                >{{ entry.enabled ? 'Aktiv' : 'Inaktiv' }}</span>
                <ExternalLink class="sensor-config__cross-ref-nav-icon" aria-hidden="true" />
              </button>
            </li>
          </ul>
        </div>

        <!-- ─── Sub-Sektion 4: Kalibrierungs-Alerts (AUT-300) ──────────── -->
        <div v-if="isCalibrationRequired" class="sensor-config__sub-section sensor-config__sub-section--calibration">
          <div class="sensor-config__sub-header">
            <h4 class="sensor-config__sub-title">Kalibrierungs-Alerts</h4>
            <span class="sensor-config__source-tag">DB: sensor_config</span>
          </div>
          <p class="sensor-config__sub-hint">
            <Info class="sensor-config__sub-hint-icon" aria-hidden="true" />
            {{ calibrationHelpText }}
          </p>

          <div class="sensor-config__field">
            <label class="sensor-config__label">Kalibrierungs-Erinnerung (Tage)</label>
            <input
              v-model.number="calibrationIntervalDays"
              type="number"
              min="1"
              max="365"
              step="1"
              class="sensor-config__input"
              placeholder="leer = deaktiviert"
            />
            <span class="sensor-config__helper">
              Nach diesem Intervall erscheint eine Erinnerung im Benachrichtigungssystem.
              Leer lassen = keine automatische Erinnerung.
            </span>
          </div>

          <!-- AUT-686 S4: Kalibrierungsstatus für ph/ec/moisture/soil_moisture -->
          <div class="sensor-config__calibration-status">
            <!-- Status Badge -->
            <div class="sensor-config__calibration-status-row">
              <span class="sensor-config__label">Kalibrierungsstatus</span>
              <span
                :class="[
                  'sensor-config__cal-badge',
                  `sensor-config__cal-badge--${calibrationHealthState.state}`
                ]"
              >
                <template v-if="calibrationHealthState.state === 'uncalibrated'">Nicht kalibriert</template>
                <template v-else-if="calibrationHealthState.state === 'healthy'">
                  Elektrode in gutem Zustand
                  <template v-if="calibrationHealthState.calibratedAt"> — {{ calibrationStatusSummary.label }}</template>
                </template>
                <template v-else-if="calibrationHealthState.state === 'drifting'">
                  Kalibrierung empfohlen — Slope weicht {{ Math.round(calibrationHealthState.slopePct ?? 0) }}% ab
                </template>
                <template v-else>
                  Elektrodenwechsel prüfen — Slope {{ Math.round(calibrationHealthState.slopePct ?? 0) }}% außerhalb Nernst-Ideal
                </template>
              </span>
            </div>
            <!-- Detail message -->
            <p v-if="calibrationHealthState.state === 'uncalibrated' && ['ph','ec'].includes(sensorType.toLowerCase())" class="sensor-config__cal-hint">
              Unkalibriert bedeutet Default-Berechnung (kann bis ±2 pH / ±200 µS/cm abweichen).
            </p>
            <p v-else-if="calibrationHealthState.state === 'drifting'" class="sensor-config__cal-hint">
              Elektrode zeigt frühe Drift-Zeichen. Kalibrierung mit frischen Pufferlösungen empfohlen.
            </p>
            <p v-else-if="calibrationHealthState.state === 'critical'" class="sensor-config__cal-hint">
              Slope deutlich außerhalb Nernst-Ideal (±59.16 mV/pH). Elektrode möglicherweise erschöpft oder verschmutzt.
            </p>
            <!-- Collapsible guide (nur ph/ec) -->
            <div v-if="CALIBRATION_GUIDES[sensorType.toLowerCase()]" class="sensor-config__cal-guide">
              <button
                type="button"
                class="sensor-config__cal-guide-toggle"
                @click="calGuideVisible = !calGuideVisible"
              >
                {{ calGuideVisible ? 'Anleitung verbergen ▲' : 'Kalibrierungs-Kurzanleitung anzeigen ▼' }}
              </button>
              <p v-if="calGuideVisible" class="sensor-config__cal-guide-text">
                {{ CALIBRATION_GUIDES[sensorType.toLowerCase()] }}
              </p>
            </div>
            <!-- Calibration button (ph + ec + moisture) -->
            <button
              type="button"
              class="sensor-config__calibrate-btn"
              @click="openCalibrationWizard"
            >
              Kalibrierung starten
            </button>
          </div>
        </div>
      </AccordionSection>

      <!-- ═══ ZONE 3: EXPERT (Hardware + Preview) ═════════════════════════ -->

      <!-- Hardware / Interface -->
      <AccordionSection
        title="Hardware & Interface"
        :storage-key="`${accordionKey}-hardware`"
        :icon="Cpu"
      >
        <div class="sensor-config__interface-badge-row">
          Interface:
          <span class="sensor-config__interface-badge">{{ interfaceType }}</span>
        </div>

        <div v-if="!isKnownBoard" class="sensor-config__info-box sensor-config__info-box--warning">
          Board-Typ unbekannt — manuelle Pin-Pruefung noetig. GPIO-Defaults koennen abweichen.
        </div>
        <div v-else-if="boardLayout" class="sensor-config__info-box">
          Board: {{ boardLayout.label }}
          <span v-if="isReserved(gpioPin)" class="sensor-config__reserved-badge">GPIO reserviert</span>
        </div>

        <!-- ANALOG: GPIO (ADC1 only) + Range -->
        <template v-if="isAnalog">
          <div class="sensor-config__field">
            <label class="sensor-config__label">GPIO Pin (nur ADC1)</label>
            <input :value="`GPIO ${props.gpio}`" disabled class="sensor-config__input sensor-config__input--disabled" />
            <span class="sensor-config__helper">GPIO kann nach Sensor-Anlage nicht geändert werden</span>
          </div>
          <div class="sensor-config__row">
            <div class="sensor-config__field sensor-config__field--half">
              <label class="sensor-config__label">Messbereich Min</label>
              <input v-model.number="measureRangeMin" type="number" class="sensor-config__input" />
            </div>
            <div class="sensor-config__field sensor-config__field--half">
              <label class="sensor-config__label">Messbereich Max</label>
              <input v-model.number="measureRangeMax" type="number" class="sensor-config__input" />
            </div>
          </div>

          <!-- ADC-Quelle: interner ESP32-ADC (Standard) oder externer ADS1115 -->
          <div class="sensor-config__field">
            <label class="sensor-config__label" for="adc-source-select">ADC-Quelle</label>
            <select
              id="adc-source-select"
              v-model="adcSource"
              class="sensor-config__select"
              aria-label="ADC-Quelle waehlen"
            >
              <option value="internal">Intern (ESP32 12-bit)</option>
              <option value="ads1115">ADS1115 (extern, 16-bit I2C)</option>
            </select>
            <span class="sensor-config__helper">
              ADS1115 nutzt einen externen 16-bit-I2C-ADC fuer pH/EC. Die Kalibrierung
              bleibt identisch &mdash; nur die Erfassung wechselt die Quelle.
            </span>
          </div>

          <template v-if="useAds1115">
            <div class="sensor-config__info-box">
              ADS1115 am I2C-Bus &mdash; der ESP32-ADC-Pin wird nicht genutzt (gpio=0).
              Versorgung und Kalibrierung muessen mit derselben Spannung erfolgen.
            </div>
            <div class="sensor-config__row">
              <div class="sensor-config__field sensor-config__field--half">
                <label class="sensor-config__label">ADS1115-Adresse</label>
                <select v-model="adcI2cAddress" class="sensor-config__select" aria-label="ADS1115 I2C-Adresse">
                  <option v-for="addr in ADS1115_ADDRESS_OPTIONS" :key="addr" :value="addr">
                    {{ addr }}
                  </option>
                </select>
              </div>
              <div class="sensor-config__field sensor-config__field--half">
                <label class="sensor-config__label">Kanal</label>
                <select v-model.number="adcChannel" class="sensor-config__select" aria-label="ADS1115 Kanal">
                  <option :value="0">AIN0</option>
                  <option :value="1">AIN1</option>
                  <option :value="2">AIN2</option>
                  <option :value="3">AIN3</option>
                </select>
              </div>
            </div>
            <div class="sensor-config__field">
              <label class="sensor-config__label">PGA-Verstaerkung (Messbereich)</label>
              <select v-model="pgaGain" class="sensor-config__select" aria-label="ADS1115 PGA-Verstaerkung">
                <option v-for="opt in PGA_GAIN_OPTIONS" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </select>
              <span class="sensor-config__helper">
                Kleiner Bereich = hoehere Aufloesung. Eingangsspannung darf den Bereich nicht ueberschreiten.
              </span>
            </div>
          </template>
        </template>

        <!-- I2C: Address + Bus (NO GPIO!) -->
        <template v-else-if="isI2C">
          <div class="sensor-config__info-box">
            I2C-Sensoren teilen sich den Bus &mdash; kein GPIO-Pin noetig.
            <template v-if="i2cDefaultLabel">
              Standard: {{ i2cDefaultLabel }}.
            </template>
          </div>
          <div class="sensor-config__field">
            <label class="sensor-config__label">I2C-Adresse</label>
            <select v-model="i2cAddress" class="sensor-config__select">
              <option v-for="opt in i2cAddressOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
          <div class="sensor-config__field">
            <label class="sensor-config__label">I2C-Bus</label>
            <select v-model.number="i2cBus" class="sensor-config__select">
              <option :value="0">
                Bus 0 &mdash; Wire<template v-if="i2cDefaultLabel"> ({{ i2cDefaultLabel }})</template>
              </option>
              <option :value="1">Bus 1 &mdash; Wire1 (konfigurierbar)</option>
            </select>
          </div>
        </template>

        <!-- OneWire: GPIO + Address -->
        <template v-else-if="isOneWire">
          <div class="sensor-config__field">
            <label class="sensor-config__label">GPIO Pin</label>
            <input :value="`GPIO ${props.gpio}`" disabled class="sensor-config__input sensor-config__input--disabled" />
            <span class="sensor-config__helper">GPIO kann nach Sensor-Anlage nicht geändert werden</span>
          </div>
          <div class="sensor-config__info-box">
            OneWire-Sensoren werden automatisch erkannt. Mehrere DS18B20 koennen denselben GPIO teilen.
          </div>
        </template>

        <!-- Digital: GPIO + Pulses -->
        <template v-else-if="isDigital">
          <div class="sensor-config__field">
            <label class="sensor-config__label">GPIO Pin</label>
            <input :value="`GPIO ${props.gpio}`" disabled class="sensor-config__input sensor-config__input--disabled" />
            <span class="sensor-config__helper">GPIO kann nach Sensor-Anlage nicht geändert werden</span>
          </div>
          <div class="sensor-config__field">
            <label class="sensor-config__label">Impulse pro Liter</label>
            <input v-model.number="pulsesPerLiter" type="number" class="sensor-config__input" min="1" />
            <span class="sensor-config__helper">Kalibrierungsfaktor des Durchfluss-Sensors</span>
          </div>
        </template>
      </AccordionSection>

      <!-- AUT-252: Sensor-Datenblatt (read-only, aus SENSOR_TYPE_CONFIG) -->
      <AccordionSection
        title="Sensor-Datenblatt"
        :storage-key="`${accordionKey}-datasheet`"
        :icon="FileText"
      >
        <div v-if="hasDatasheet && sensorConfig" class="sensor-config__datasheet">
          <div class="sensor-config__datasheet-row">
            <span class="sensor-config__datasheet-label">Typ</span>
            <span class="sensor-config__datasheet-value">{{ sensorConfig.label }} ({{ sensorType }})</span>
          </div>
          <div v-if="sensorConfig.manufacturer" class="sensor-config__datasheet-row">
            <span class="sensor-config__datasheet-label">Hersteller</span>
            <span class="sensor-config__datasheet-value">{{ sensorConfig.manufacturer }}</span>
          </div>
          <div v-if="sensorConfig.accuracy" class="sensor-config__datasheet-row">
            <span class="sensor-config__datasheet-label">Genauigkeit</span>
            <span class="sensor-config__datasheet-value">{{ sensorConfig.accuracy }}</span>
          </div>
          <div v-if="sensorConfig.calibrationRequired != null" class="sensor-config__datasheet-row">
            <span class="sensor-config__datasheet-label">Kalibrierung</span>
            <span class="sensor-config__datasheet-value">
              {{ sensorConfig.calibrationRequired ? 'Periodisch erforderlich' : 'Werks-kalibriert' }}
              <span v-if="sensorConfig.calibrationNote" class="sensor-config__datasheet-note">
                — {{ sensorConfig.calibrationNote }}
              </span>
            </span>
          </div>
          <div v-if="sensorConfig.maintenanceYears != null" class="sensor-config__datasheet-row">
            <span class="sensor-config__datasheet-label">Wartungsintervall</span>
            <span class="sensor-config__datasheet-value">
              {{ sensorConfig.maintenanceYears }} {{ sensorConfig.maintenanceYears === 1 ? 'Jahr' : 'Jahre' }}
            </span>
          </div>
          <div v-if="sensorConfig.datasheetUrl" class="sensor-config__datasheet-row">
            <span class="sensor-config__datasheet-label">Datenblatt</span>
            <a
              class="sensor-config__datasheet-link"
              :href="sensorConfig.datasheetUrl"
              target="_blank"
              rel="noopener noreferrer"
            >
              Hersteller-Dokumentation
              <ExternalLink class="sensor-config__datasheet-link-icon" aria-hidden="true" />
            </a>
          </div>
        </div>
        <div v-else class="sensor-config__datasheet-empty">
          <Info class="sensor-config__datasheet-empty-icon" aria-hidden="true" />
          <div>
            <p class="sensor-config__datasheet-empty-title">Datenblatt nicht hinterlegt</p>
            <p class="sensor-config__datasheet-empty-hint">
              Hersteller- und Genauigkeitsdaten werden zentral in der Komponenten-Bibliothek gepflegt.
            </p>
          </div>
        </div>
      </AccordionSection>

      <!-- Live Preview -->
      <AccordionSection
        title="Live-Vorschau"
        :storage-key="`${accordionKey}-preview`"
        :icon="Settings"
      >
        <div class="sensor-config__preview">
          <LiveDataPreview :esp-id="espId" :gpio="gpio" :sensor-type="sensorType" :unit="unitValue || defaultUnit" />
        </div>
      </AccordionSection>

      <!-- AUT-252: Pflanzen-Kontext (nur wenn Subzone eine Pflanze hat) -->
      <AccordionSection
        v-if="subzonePlant"
        title="Pflanzen-Kontext"
        :storage-key="`${accordionKey}-plant-context`"
        :icon="Sprout"
      >
        <div class="sensor-config__plant-context">
          <!-- Stammdaten -->
          <div class="sensor-config__plant-header">
            <div class="sensor-config__plant-genotype">{{ subzonePlant.genotype }}</div>
            <span class="sensor-config__plant-phase">{{ plantPhaseLabel }}</span>
          </div>
          <div v-if="subzonePlant.qr_code" class="sensor-config__plant-qr">
            QR-Label: <span class="sensor-config__plant-qr-code">{{ subzonePlant.qr_code }}</span>
          </div>

          <!-- Empfohlene Schwellwerte -->
          <div class="sensor-config__plant-thresholds">
            <h4 class="sensor-config__plant-section-title">Empfohlene Schwellwerte</h4>
            <div v-if="hasPlantThresholds && plantThresholdsForSensor" class="sensor-config__plant-thresholds-grid">
              <div v-if="plantThresholdsForSensor.alarm_low != null" class="sensor-config__plant-threshold">
                <span class="sensor-config__plant-threshold-label sensor-config__label--alarm">Alarm &#8595;</span>
                <span class="sensor-config__plant-threshold-value">{{ plantThresholdsForSensor.alarm_low }} {{ unitValue || defaultUnit }}</span>
              </div>
              <div v-if="plantThresholdsForSensor.warn_low != null" class="sensor-config__plant-threshold">
                <span class="sensor-config__plant-threshold-label sensor-config__label--warn">Warn &#8595;</span>
                <span class="sensor-config__plant-threshold-value">{{ plantThresholdsForSensor.warn_low }} {{ unitValue || defaultUnit }}</span>
              </div>
              <div v-if="plantThresholdsForSensor.warn_high != null" class="sensor-config__plant-threshold">
                <span class="sensor-config__plant-threshold-label sensor-config__label--warn">Warn &#8593;</span>
                <span class="sensor-config__plant-threshold-value">{{ plantThresholdsForSensor.warn_high }} {{ unitValue || defaultUnit }}</span>
              </div>
              <div v-if="plantThresholdsForSensor.alarm_high != null" class="sensor-config__plant-threshold">
                <span class="sensor-config__plant-threshold-label sensor-config__label--alarm">Alarm &#8593;</span>
                <span class="sensor-config__plant-threshold-value">{{ plantThresholdsForSensor.alarm_high }} {{ unitValue || defaultUnit }}</span>
              </div>
            </div>
            <p v-else class="sensor-config__plant-hint">
              <Info class="sensor-config__sub-hint-icon" aria-hidden="true" />
              Fuer dieses Pflanzenprofil sind keine sensor-typ-spezifischen Schwellwerte hinterlegt. Werte werden manuell gepflegt.
            </p>

            <button
              v-if="hasPlantThresholds"
              type="button"
              class="sensor-config__plant-apply-btn"
              :disabled="applyingPlantThresholds || saving"
              @click="applyPlantThresholds"
            >
              <Save class="w-4 h-4" />
              {{ applyingPlantThresholds ? 'Übernehme...' : 'Aus Pflanzenprofil übernehmen' }}
            </button>
          </div>

          <!-- Letzte Lifecycle-Events -->
          <div v-if="recentLifecycleEvents.length > 0" class="sensor-config__plant-events">
            <h4 class="sensor-config__plant-section-title">Letzte Ereignisse</h4>
            <ul class="sensor-config__plant-events-list">
              <li
                v-for="evt in recentLifecycleEvents"
                :key="evt.id"
                class="sensor-config__plant-event"
              >
                <span class="sensor-config__plant-event-type">{{ getPlantEventTypeLabel(evt.event_type) }}</span>
                <span class="sensor-config__plant-event-time">{{ formatRelativeTime(evt.created_at) }}</span>
                <p v-if="evt.note" class="sensor-config__plant-event-note">{{ evt.note }}</p>
              </li>
            </ul>
          </div>
        </div>
      </AccordionSection>

      <!-- AUT-246: "Alert-Konfiguration" Akkordeon entfernt — Inhalt jetzt
           als Sub-Sektion innerhalb von "Schwellwerte & Alerts" oben. -->

      <!-- ═══ RUNTIME & MAINTENANCE (Phase 4A.8) ══════════════════════ -->
      <AccordionSection
        v-if="sensorDbId"
        title="Laufzeit & Wartung"
        :storage-key="`${accordionKey}-runtime`"
      >
        <RuntimeMaintenanceSection
          :entity-id="sensorDbId"
          entity-type="sensor"
          :fetch-fn="sensorsApi.getRuntime"
          :update-fn="sensorsApi.updateRuntime"
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

      <!-- ═══ LINKED RULES ════════════════════════════════════════════════ -->
      <!-- AUT-623: AlertTriangle icon when a rule has triggered an active alert for this sensor -->
      <AccordionSection
        title="Verknüpfte Regeln"
        :storage-key="`${accordionKey}-linked-rules`"
        :icon="hasRuleTriggeredAlert ? AlertTriangle : undefined"
      >
        <LinkedRulesSection
          :esp-id="espId"
          :gpio="gpio"
          device-type="sensor"
        />
      </AccordionSection>

      <!-- AUT-251: Zone-Zuordnung wird ausschliesslich auf Geraete-Ebene gepflegt
           (HardwareView -> ESPSettingsSheet). Sensoren erben die Zone vom Geraet
           und besitzen nur eine eigene Subzone (siehe Dropdown oben). -->

      <!-- ═══ PENDING CONFIG STATUS (AUT-64) ═══════════════════════════════ -->
      <PendingConfigBanner
        :subject-id="lastConfigSubjectId"
        :correlation-id="lastConfigCorrelationId"
        @retry="handleSave"
      />

      <!-- ═══ ACTIONS ══════════════════════════════════════════════════════ -->
      <div class="sensor-config__actions">
        <button
          class="sensor-config__save"
          :disabled="saving || loading"
          @click="handleSave"
        >
          <Save class="w-4 h-4" />
          {{ saving ? 'Speichert...' : 'Speichern' }}
        </button>
        <button
          class="sensor-config__delete"
          :disabled="deleting || loading"
          @click="confirmAndDelete"
        >
          <Trash2 class="w-4 h-4" />
          Sensor entfernen
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sensor-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* AUT-623: Accordion icon color for rule-triggered alerts (AlertTriangle in warning color) */
:deep(.accordion__icon) {
  color: var(--color-warning);
  width: 14px;
  height: 14px;
}

/* AUT-623: Active alert notice below breadcrumb (only visible when alert exists for this sensor) */
.sensor-config__alert-notice {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-3);
  margin-bottom: var(--space-1);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
}

.sensor-config__alert-notice-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.sensor-config--loading {
  opacity: 0.6;
}

.sensor-config__loading {
  padding: var(--space-8);
  text-align: center;
  color: var(--color-text-muted);
}

/* ═══════════════════════════════════════════════════════════════════════════
   SECTIONS (Zone 1)
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-config__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--glass-border);
}

.sensor-config__simulation-badge {
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(167, 139, 250, 0.35);
  background: rgba(167, 139, 250, 0.1);
  color: var(--color-mock);
  font-size: var(--text-xs);
  font-weight: 600;
}

.sensor-config__section-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  margin: 0;
}

.sensor-config__context-anchor {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
}

.sensor-config__context-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.sensor-config__context-item {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.sensor-config__context-item--mono {
  font-family: var(--font-mono);
}

/* Zone-Header (read-only, vom Geraet vererbt) — AUT-251 */
.sensor-config__zone-header {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
}

.sensor-config__zone-label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-muted);
}

.sensor-config__zone-value {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.sensor-config__zone-hint {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  font-style: italic;
}

.sensor-config__zone-link {
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

.sensor-config__zone-link:hover {
  color: var(--color-text-primary);
  border-color: var(--color-iridescent-1);
  background: var(--color-bg-tertiary);
}

.sensor-config__zone-link:focus-visible {
  outline: 2px solid var(--color-iridescent-1);
  outline-offset: 2px;
}

/* ═══════════════════════════════════════════════════════════════════════════
   FIELDS
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-config__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.sensor-config__field--half { flex: 1; }
.sensor-config__field--quarter { flex: 1; min-width: 0; }

.sensor-config__field--toggle {
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
}

.sensor-config__row {
  display: flex;
  gap: var(--space-3);
}

.sensor-config__label {
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.sensor-config__label--alarm { color: var(--color-status-alarm); }
.sensor-config__label--warn { color: var(--color-status-warning); }

.sensor-config__input {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-family: var(--font-body);
  transition: border-color var(--transition-fast);
}

.sensor-config__input:focus {
  outline: none;
  border-color: var(--color-accent);
}

.sensor-config__input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sensor-config__input--sm {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-sm);
  font-family: var(--font-mono);
}

.sensor-config__input--mono {
  font-family: var(--font-mono);
}

/* schedule_config (Auftrag 5) */
.sensor-config__schedule {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sensor-config__schedule-presets {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.sensor-config__preset-btn {
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.sensor-config__preset-btn:hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.sensor-config__preset-btn--active {
  background: var(--color-accent-dim);
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
}

.sensor-config__select {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-base);
  cursor: pointer;
}

.sensor-config__select:focus {
  outline: none;
  border-color: var(--color-accent);
}

.sensor-config__helper {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.sensor-config__input-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.sensor-config__input-row .sensor-config__input {
  flex: 1;
}

.sensor-config__input-hint {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  white-space: nowrap;
  flex-shrink: 0;
}

/* PKG-04: EC calibration status (read-only) */
.sensor-config__calibration-status {
  margin-top: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  background: rgba(52, 211, 153, 0.06);
  border: 1px solid rgba(52, 211, 153, 0.2);
}

.sensor-config__calibration-status-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  font-size: var(--text-xs);
  padding: var(--space-1) 0;
}

.sensor-config__calibration-status-row + .sensor-config__calibration-status-row {
  border-top: 1px solid rgba(52, 211, 153, 0.1);
}

.sensor-config__calibration-status-row .sensor-config__label {
  flex-shrink: 0;
  min-width: 9rem;
  color: var(--color-text-secondary);
}

.sensor-config__calibration-status-value {
  font-variant-numeric: tabular-nums;
  color: var(--color-success);
  font-size: var(--text-xs);
}

.sensor-config__calibrate-btn {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.sensor-config__calibrate-btn:hover {
  border-color: var(--color-iridescent-1);
}

.sensor-config__info-box {
  padding: var(--space-2) var(--space-3);
  background: rgba(96, 165, 250, 0.06);
  border: 1px solid rgba(96, 165, 250, 0.15);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--color-info);
  line-height: var(--leading-normal);
}

.sensor-config__info-box--warning {
  background: rgba(251, 191, 36, 0.08);
  border-color: rgba(251, 191, 36, 0.25);
  color: var(--color-warning);
}

.sensor-config__reserved-badge {
  margin-left: var(--space-2);
  padding: 0 var(--space-1);
  border-radius: var(--radius-sm);
  background: rgba(239, 68, 68, 0.15);
  color: var(--color-danger);
  font-size: var(--text-xs);
  font-weight: 600;
}

.sensor-config__interface-badge-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: 600;
}

.sensor-config__interface-badge {
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
.sensor-config__toggle {
  position: relative;
  width: 40px;
  height: 22px;
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-full);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.sensor-config__toggle--on {
  background: var(--color-status-good);
  border-color: transparent;
}

.sensor-config__toggle-dot {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: white;
  border-radius: 50%;
  transition: transform var(--transition-fast);
}

.sensor-config__toggle--on .sensor-config__toggle-dot {
  transform: translateX(18px);
}

/* Threshold inputs */
.sensor-config__threshold-inputs {
  display: flex;
  gap: var(--space-2);
}

/* AUT-246: Sub-Sektionen innerhalb des "Schwellwerte & Alerts"-Akkordeons */
.sensor-config__sub-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-tertiary);
}

.sensor-config__sub-section + .sensor-config__sub-section {
  margin-top: var(--space-3);
}

/* AUT-300: Calibration alert sub-section — subtle left accent */
.sensor-config__sub-section--calibration {
  border-left: 3px solid rgba(251, 191, 36, 0.35);
  padding-left: var(--space-3);
}

.sensor-config__sub-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.sensor-config__sub-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.sensor-config__source-tag {
  font-size: var(--text-xxs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  padding: 1px var(--space-1);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xs);
  background: var(--color-bg-secondary);
}

.sensor-config__source-tag--readonly {
  color: var(--color-text-muted);
  font-style: italic;
}

.sensor-config__sub-hint {
  display: flex;
  align-items: flex-start;
  gap: var(--space-1);
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: var(--leading-normal);
}

.sensor-config__sub-hint-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-info);
}

/* Cross-Reference list (Verlinkte Quellen) */
.sensor-config__cross-ref-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.sensor-config__cross-ref-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.sensor-config__cross-ref-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.sensor-config__cross-ref-count {
  font-weight: 600;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  min-width: 20px;
}

.sensor-config__cross-ref-text {
  flex: 1;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.sensor-config__cross-ref-link-item {
  padding-left: var(--space-5);
}

.sensor-config__cross-ref-link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-xs);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  text-align: left;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.sensor-config__cross-ref-link:hover {
  background: var(--color-bg-secondary);
  border-color: var(--glass-border);
  color: var(--color-text-primary);
}

.sensor-config__cross-ref-link-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}

.sensor-config__cross-ref-link-meta {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  font-style: italic;
}

.sensor-config__cross-ref-state {
  font-size: var(--text-xxs);
  font-weight: 600;
  padding: 1px var(--space-1);
  border-radius: var(--radius-xs);
  text-transform: uppercase;
}

.sensor-config__cross-ref-state--on {
  background: rgba(52, 211, 153, 0.12);
  color: var(--color-success);
}

.sensor-config__cross-ref-state--off {
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-muted);
  border: 1px solid var(--glass-border);
}

.sensor-config__cross-ref-nav-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: var(--color-text-muted);
}

/* ═══════════════════════════════════════════════════════════════════════════
   CALIBRATION
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-config__cal-current {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
}

.sensor-config__cal-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.sensor-config__cal-value {
  font-family: var(--font-mono);
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--color-text-primary);
}

.sensor-config__cal-start {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--color-accent-dim);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-accent-bright);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.sensor-config__cal-start:hover {
  background: rgba(59, 130, 246, 0.2);
}

.sensor-config__cal-step {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
}

.sensor-config__cal-step h4 {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}

.sensor-config__cal-step p {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

.sensor-config__cal-step--complete {
  border-color: var(--color-status-good);
  background: rgba(34, 197, 94, 0.04);
}

.sensor-config__cal-raw {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.sensor-config__cal-result {
  display: flex;
  gap: var(--space-4);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.sensor-config__cal-btn {
  padding: var(--space-2) var(--space-3);
  background: var(--color-accent);
  border: none;
  border-radius: var(--radius-sm);
  color: white;
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.sensor-config__cal-btn:hover {
  filter: brightness(1.1);
}

.sensor-config__cal-btn--save {
  background: var(--color-status-good);
}

.sensor-config__cal-btn--reset {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--color-text-secondary);
}

.sensor-config__cal-btn--abort {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  background: transparent;
  border: 1px solid var(--color-text-muted);
  color: var(--color-text-secondary);
}

.sensor-config__cal-btn--abort:hover {
  border-color: var(--color-error);
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.08);
}

.sensor-config__cal-actions {
  display: flex;
  gap: var(--space-2);
}

/* ═══════════════════════════════════════════════════════════════════════════
   LIVE PREVIEW
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-config__preview {
  height: 180px;
}

/* ═══════════════════════════════════════════════════════════════════════════
   ACTIONS
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-config__actions {
  padding-top: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sensor-config__save {
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

.sensor-config__save:hover:not(:disabled) {
  filter: brightness(1.1);
}

.sensor-config__save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sensor-config__delete {
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

.sensor-config__delete:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.1);
}

.sensor-config__delete:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ═══════════════════════════════════════════════════════════════════════════
   AUT-252: Sensor-Datenblatt (read-only)
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-config__datasheet {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sensor-config__datasheet-row {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  padding: var(--space-2) 0;
  border-bottom: 1px solid var(--glass-border);
}

.sensor-config__datasheet-row:last-child {
  border-bottom: none;
}

.sensor-config__datasheet-label {
  flex: 0 0 140px;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-weight: 500;
}

.sensor-config__datasheet-value {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.sensor-config__datasheet-note {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

.sensor-config__datasheet-link {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  color: var(--color-accent-bright);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.sensor-config__datasheet-link:hover {
  color: var(--color-iridescent-2);
  text-decoration: underline;
}

.sensor-config__datasheet-link-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.sensor-config__datasheet-empty {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
}

.sensor-config__datasheet-empty-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--color-info);
}

.sensor-config__datasheet-empty-title {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.sensor-config__datasheet-empty-hint {
  margin: var(--space-1) 0 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: var(--leading-normal);
}

/* ═══════════════════════════════════════════════════════════════════════════
   AUT-252: Pflanzen-Kontext
   ═══════════════════════════════════════════════════════════════════════════ */

.sensor-config__plant-context {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.sensor-config__plant-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.sensor-config__plant-genotype {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text-primary);
}

.sensor-config__plant-phase {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-accent-dim);
  color: var(--color-accent-bright);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.sensor-config__plant-qr {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.sensor-config__plant-qr-code {
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
}

.sensor-config__plant-section-title {
  margin: 0 0 var(--space-2) 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.sensor-config__plant-thresholds {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sensor-config__plant-thresholds-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-2);
}

.sensor-config__plant-threshold {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
}

.sensor-config__plant-threshold-label {
  font-size: var(--text-xxs);
  font-weight: 500;
}

.sensor-config__plant-threshold-value {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

.sensor-config__plant-hint {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  margin: 0;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: var(--leading-normal);
}

.sensor-config__plant-apply-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-accent-dim);
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-accent-bright);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.sensor-config__plant-apply-btn:hover:not(:disabled) {
  background: rgba(96, 165, 250, 0.2);
}

.sensor-config__plant-apply-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.sensor-config__plant-events-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.sensor-config__plant-event {
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-left: 2px solid var(--color-accent-dim);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sensor-config__plant-event-type {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
}

.sensor-config__plant-event-time {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  font-style: italic;
}

.sensor-config__plant-event-note {
  margin: var(--space-1) 0 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-normal);
}

/* AUT-686 S4: Mode warning + ATC status + Calibration health */
.sensor-config__mode-warning {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-normal);
}

.sensor-config__mode-warning-icon {
  flex-shrink: 0;
  margin-top: 1px;
  color: var(--color-warning);
}

.sensor-config__atc-status {
  margin-top: var(--space-1);
}

.sensor-config__atc-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
}

.sensor-config__atc-badge--gray {
  color: var(--color-text-muted);
  background: color-mix(in srgb, var(--color-text-muted) 10%, transparent);
}

.sensor-config__atc-badge--warning {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
}

.sensor-config__atc-badge--ok {
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.sensor-config__cal-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
}

.sensor-config__cal-badge--uncalibrated {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
}

.sensor-config__cal-badge--healthy {
  color: var(--color-success);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.sensor-config__cal-badge--drifting {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
}

.sensor-config__cal-badge--critical {
  color: var(--color-danger);
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
}

.sensor-config__cal-hint {
  margin: var(--space-1) 0 0 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-normal);
}

.sensor-config__cal-guide {
  margin-top: var(--space-2);
}

.sensor-config__cal-guide-toggle {
  background: none;
  border: none;
  padding: 0;
  font-size: var(--text-xs);
  color: var(--color-accent);
  cursor: pointer;
  text-decoration: underline;
}

.sensor-config__cal-guide-text {
  margin-top: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-normal);
  background: color-mix(in srgb, var(--color-text-muted) 8%, transparent);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
}

.sensor-config__input--disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
