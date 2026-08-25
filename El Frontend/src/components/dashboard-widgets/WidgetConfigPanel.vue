<script setup lang="ts">
/**
 * WidgetConfigPanel — SlideOver panel for configuring dashboard widgets
 *
 * 3-Zone Progressive Disclosure Layout:
 *   Zone 1 (KERN): Title, Zone-Filter, Sensor/Actuator, Time Range — always visible
 *   Zone 2 (DARSTELLUNG): Y-Axis, Color, Thresholds — accordion, collapsed by default
 *   Zone 3 (ERWEITERT): Statistics options — accordion, collapsed by default
 */
import { ref, computed, watch } from 'vue'
import { ChevronRight, Download, Plus, Trash2, X } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { SlideOver } from '@/shared/design/primitives'
import { SENSOR_TYPE_CONFIG, getSensorTypeOptions, getSensorDisplayName, formatSensorType } from '@/utils/sensorDefaults'
import { CHART_COLORS } from '@/utils/chartColors'
import { useSensorOptions } from '@/composables/useSensorOptions'
import { parseSensorId } from '@/composables/useSensorId'
import { sensorsApi } from '@/api/sensors'
import type { MockActuator, MockSensor } from '@/types'
import {
  collectStoreSensors,
  isConfigId,
  resolveStoredSensorConfigId,
} from '@/utils/sensorConfigLookup'
import { getWidgetCapabilities } from '@/types/widgetRegistry'

interface Props {
  open: boolean
  widgetId: string
  widgetType: string
  config: Record<string, any>
  /** Zone ID for pre-filtering sensor options in zone-scoped dashboards (PA-02c) */
  zoneId?: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  'update:config': [config: Record<string, any>]
  remove: []
}>()

/** Sensor-Kachel: Entfernen nur hier (kein Delete-Icon auf der Kachel) */
const showRemoveAction = computed(() => props.widgetType === 'sensor-tile')

const espStore = useEspStore()

// Local config copy for editing
const localConfig = ref<Record<string, any>>({})

watch(() => props.config, (cfg) => {
  localConfig.value = { ...cfg }
}, { immediate: true, deep: true })

// AUT-247: Widget capability resolution via registry — replaces 10+
// `computed(() => [...].includes(widgetType))` with one declarative lookup.
// New widget types add a row to WIDGET_REGISTRY in src/types/widgetRegistry.ts.
const caps = computed(() => getWidgetCapabilities(props.widgetType))

// AUT-1107: Display-mode picker (numeric/gauge/sparkline/historic) — sensor-tile only.
// The four modes and their German labels mirror SensorTile.vue MODE_OPTIONS.
const hasDisplayModePicker = computed(() => caps.value.hasDisplayModePicker)

const SENSOR_TILE_DISPLAY_MODES = [
  { value: 'numeric', label: 'Zahl' },
  { value: 'gauge', label: 'Gauge' },
  { value: 'sparkline', label: 'Live-Kurve' },
  { value: 'historic', label: 'Verlauf' },
] as const

const hasSensorField = computed(() => caps.value.hasSensorPicker)
const hasActuatorField = computed(() => caps.value.hasActuatorPicker)
/** Short time range chips (1h/6h/24h/7d/30d) */
const hasShortTimeRange = computed(() => caps.value.hasShortTimeRange)
/** Long time range chips (7d/30d/90d/season) */
const hasLongTimeRange = computed(() => caps.value.hasLongTimeRange)
const hasYRange = computed(() => caps.value.hasYRange)
const hasColor = computed(() => caps.value.hasColor)

// AUT-231: Comparison-Boxplot / Correlation-Scatter capability flags
const hasSensorTypeField = computed(() => caps.value.hasSensorType)
const hasGroupByField = computed(() => caps.value.hasGroupBy)
const hasAnonymizeField = computed(() => caps.value.hasAnonymize)
const hasCorrelationConfig = computed(() => caps.value.hasCorrelationConfig)

// AUT-239 Fix 2: Multi-Sensor list (max 6 sensors)
const hasMultiSensorField = computed(() => caps.value.hasMultiSensorList)
const MIN_MULTI_SENSOR_COUNT = 1
const MAX_MULTI_SENSOR_COUNT = 6

const multiSensorList = computed<string[]>(() => {
  const raw = localConfig.value.dataSources
  if (typeof raw !== 'string' || !raw) return []
  return raw.split(',').map((s) => s.trim()).filter(Boolean)
})

const isMultiSensorMaxReached = computed(
  () => multiSensorList.value.length >= MAX_MULTI_SENSOR_COUNT,
)

const showAddSensorPicker = ref(false)

function commitMultiSensorList(list: string[]): void {
  updateField('dataSources', list.join(','))
}

function addMultiSensor(sensorId: string): void {
  if (!sensorId) return
  const list = multiSensorList.value.slice()
  if (list.includes(sensorId)) {
    showAddSensorPicker.value = false
    return
  }
  if (list.length >= MAX_MULTI_SENSOR_COUNT) return
  list.push(sensorId)
  commitMultiSensorList(list)
  showAddSensorPicker.value = false
}

function removeMultiSensor(sensorId: string): void {
  const list = multiSensorList.value.slice()
  const idx = list.indexOf(sensorId)
  if (idx === -1) return
  if (list.length <= MIN_MULTI_SENSOR_COUNT) return
  list.splice(idx, 1)
  commitMultiSensorList(list)
}

function getSensorOptionLabel(sensorId: string): string {
  for (const group of groupedSensorOptions.value) {
    for (const subgroup of group.subgroups) {
      const opt = subgroup.options.find((o) => o.value === sensorId)
      if (opt) return opt.label
    }
  }
  return sensorId
}

const sensorTypeOptions = getSensorTypeOptions()

/** Threshold fields — sensor widgets that have warn/alarm low/high inputs */
const hasThresholdFields = computed(() => caps.value.hasThresholds)

/** Widgets that support zoneFilter (AlarmListWidget, ESPHealthWidget, ActuatorRuntimeWidget) */
const hasZoneFilterField = computed(() => caps.value.hasZoneFilter)

const hasStatisticsOptions = computed(() => caps.value.hasStatisticsOptions)

const isFertigationPair = computed(() => caps.value.isFertigationPair)

// Zone 3 is visible only for statistics or fertigation-pair widgets
const hasZone3 = computed(() =>
  hasStatisticsOptions.value || isFertigationPair.value
)

// Zone filter for sensor selection — defaults to dashboard zoneId (PA-02c)
const selectedSensorZone = ref<string | undefined>(props.zoneId)

// Sync zone filter when dashboard zoneId changes
watch(() => props.zoneId, (v) => { selectedSensorZone.value = v })

// Centralized sensor options (deduplicated, zone-grouped)
const { groupedSensorOptions } = useSensorOptions(selectedSensorZone)

// Available zones (derived from grouped sensor options)
const availableZones = computed(() => {
  const seen = new Set<string>()
  const list: { id: string; name: string }[] = []
  for (const d of espStore.devices) {
    if (d.zone_id && !seen.has(d.zone_id)) {
      seen.add(d.zone_id)
      list.push({ id: d.zone_id, name: d.zone_name || d.zone_id })
    }
  }
  return list.sort((a, b) => (a.name || a.id).localeCompare(b.name || b.id))
})

// Available actuators
const availableActuators = computed(() => {
  const items: { id: string; label: string }[] = []
  for (const device of espStore.devices) {
    const deviceId = espStore.getDeviceId(device)
    for (const a of (device.actuators as MockActuator[]) || []) {
      items.push({
        id: `${deviceId}:${a.gpio}`,
        label: `${a.name || a.actuator_type} (${deviceId})`,
      })
    }
  }
  return items
})

// Find sensor type from grouped options for Y-range hints
function findSensorType(sensorId: string): string | null {
  for (const group of groupedSensorOptions.value) {
    for (const subgroup of group.subgroups) {
      const opt = subgroup.options.find(o => o.value === sensorId)
      if (opt) return opt.sensorType
    }
  }
  return null
}

/** Upgrade legacy 2-part sensorId (esp:gpio) to 3-part when unambiguous. */
function normalizeLegacySensorId(sensorId: string): string {
  const parsed = parseSensorId(sensorId)
  if (!parsed.isValid || parsed.sensorType) return sensorId
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === parsed.espId)
  if (!device) return sensorId
  const matches = ((device.sensors as MockSensor[]) || []).filter(s => s.gpio === parsed.gpio)
  if (matches.length === 1) {
    return `${parsed.espId}:${parsed.gpio}:${matches[0].sensor_type}`
  }
  return sensorId
}

const sensorOptionValues = computed(() => {
  const values = new Set<string>()
  for (const group of groupedSensorOptions.value) {
    for (const subgroup of group.subgroups) {
      for (const opt of subgroup.options) values.add(opt.value)
    }
  }
  return values
})

const resolvedSensorSelectId = computed(() => {
  const raw = localConfig.value.sensorId
  if (typeof raw !== 'string' || !raw) return ''
  const normalized = normalizeLegacySensorId(raw)
  if (normalized !== raw && sensorOptionValues.value.has(normalized)) {
    return normalized
  }
  return raw
})

/** Shown when the configured sensor is not in the current option list (zone filter / timing). */
const orphanSensorOption = computed(() => {
  const id = resolvedSensorSelectId.value
  if (!id || sensorOptionValues.value.has(id)) return null
  const parsed = parseSensorId(id)
  if (!parsed.isValid || !parsed.espId || parsed.gpio == null) {
    return { value: id, label: id }
  }
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === parsed.espId)
  const sensor = device
    ? ((device.sensors as MockSensor[]) || []).find(
        s => s.gpio === parsed.gpio && (!parsed.sensorType || s.sensor_type === parsed.sensorType)
      )
    : null
  const espName = device?.name?.trim() || parsed.espId
  const sensorLabel = sensor
    ? getSensorDisplayName({ sensor_type: sensor.sensor_type || parsed.sensorType || '', name: sensor.name })
    : (parsed.sensorType ? formatSensorType(parsed.sensorType) : `GPIO ${parsed.gpio}`)
  return { value: id, label: `${espName} · ${sensorLabel}` }
})

watch(
  () => [localConfig.value.sensorId, sensorOptionValues.value.size] as const,
  () => {
    const raw = localConfig.value.sensorId
    if (typeof raw !== 'string' || !raw) return
    const normalized = normalizeLegacySensorId(raw)
    if (normalized !== raw && sensorOptionValues.value.has(normalized)) {
      localConfig.value = { ...localConfig.value, sensorId: normalized }
    }
  },
  { immediate: true },
)

// Current sensor type config for Y-range hints
const sensorTypeConfig = computed(() => {
  if (!localConfig.value.sensorId) return null
  const type = findSensorType(localConfig.value.sensorId)
  if (!type) return null
  return SENSOR_TYPE_CONFIG[type] || null
})

function updateField(field: string, value: any) {
  localConfig.value = { ...localConfig.value, [field]: value }
  emit('update:config', localConfig.value)
}

function normalizeFertigationConfigId(field: 'inflowSensorId' | 'runoffSensorId'): void {
  const raw = localConfig.value[field]
  if (typeof raw !== 'string' || !raw || isConfigId(raw)) return
  const resolved = resolveStoredSensorConfigId(raw, collectStoreSensors(espStore.devices))
  if (resolved && resolved !== raw) updateField(field, resolved)
}

watch(
  () => [isFertigationPair.value, localConfig.value.inflowSensorId, localConfig.value.runoffSensorId, espStore.devices.length] as const,
  ([fertigation]) => {
    if (!fertigation) return
    normalizeFertigationConfigId('inflowSensorId')
    normalizeFertigationConfigId('runoffSensorId')
  },
  { immediate: true },
)

function isAutoGeneratedTitle(title: string | undefined | null): boolean {
  if (!title) return true
  const knownLabels = new Set(
    Object.values(SENSOR_TYPE_CONFIG).map(c => c.label)
  )
  const knownTypes = new Set(Object.keys(SENSOR_TYPE_CONFIG))
  return knownLabels.has(title) || knownTypes.has(title)
}

function handleSensorChange(sensorId: string) {
  const sType = findSensorType(sensorId)
  const updates: Record<string, any> = { sensorId }

  if (sType) {
    const cfg = SENSOR_TYPE_CONFIG[sType]
    if (cfg) {
      updates.yMin = cfg.min
      updates.yMax = cfg.max
      if (isAutoGeneratedTitle(localConfig.value.title)) {
        updates.title = cfg.label
      }
    } else {
      updates.yMin = null
      updates.yMax = null
      if (isAutoGeneratedTitle(localConfig.value.title)) {
        updates.title = sType
      }
    }
  }

  localConfig.value = { ...localConfig.value, ...updates }
  emit('update:config', localConfig.value)
}

function handleActuatorChange(actuatorId: string) {
  updateField('actuatorId', actuatorId)
}

// --- Alert-Config Threshold Sync (P8-A3) ---

/** Find the config_id (UUID) for the currently selected sensor */
function findSensorConfigId(sensorId: string): string | undefined {
  for (const group of groupedSensorOptions.value) {
    for (const subgroup of group.subgroups) {
      const opt = subgroup.options.find(o => o.value === sensorId)
      if (opt?.configId) return opt.configId
    }
  }
  const parsed = parseSensorId(sensorId)
  if (!parsed.isValid || !parsed.espId || parsed.gpio == null) return undefined
  const device = espStore.devices.find(d => espStore.getDeviceId(d) === parsed.espId)
  const sensor = device
    ? ((device.sensors as MockSensor[]) || []).find(
        s => s.gpio === parsed.gpio && (!parsed.sensorType || s.sensor_type === parsed.sensorType)
      )
    : null
  return sensor?.config_id ?? (sensor as { id?: string } | undefined)?.id
}

const isLoadingThresholds = ref(false)
const thresholdSyncMessage = ref<string | null>(null)
let syncMessageTimer: ReturnType<typeof setTimeout> | undefined

function showSyncMessage(msg: string) {
  thresholdSyncMessage.value = msg
  clearTimeout(syncMessageTimer)
  syncMessageTimer = setTimeout(() => { thresholdSyncMessage.value = null }, 3000)
}

// AUT-246 / AUT-911/912: Effective alert threshold for the selected sensor.
// "Effective" = per-sensor override (alert_config.custom_thresholds) when any
// value is set, otherwise the sensor base thresholds (SensorConfig.thresholds).
// This mirrors the server's AlertSuppressionService.get_effective_thresholds
// (whole-config fallback) — i.e. the threshold that actually triggers alerts.
// Drives (a) the divergence warning and (b) the one-shot "übernehmen" button.
interface EffectiveThresholds {
  warnLow: number | null
  warnHigh: number | null
  alarmLow: number | null
  alarmHigh: number | null
  source: 'override' | 'base'
}
const sensorEffectiveThresholds = ref<EffectiveThresholds | null>(null)
const effectiveLoadedFor = ref<string | null>(null)

async function fetchEffectiveThresholds(sensorId: string): Promise<void> {
  if (effectiveLoadedFor.value === sensorId) return
  const configId = findSensorConfigId(sensorId)
  if (!configId) {
    sensorEffectiveThresholds.value = null
    effectiveLoadedFor.value = sensorId
    return
  }
  isLoadingThresholds.value = true
  try {
    // Base (warning_min/max + threshold_min/max) and override (custom_thresholds)
    // resolved together so the effective set matches server alert evaluation.
    const [base, alert] = await Promise.all([
      sensorsApi.getByConfigId(configId),
      sensorsApi.getAlertConfig(configId),
    ])
    const custom = (alert?.alert_config as Record<string, any> | undefined)?.custom_thresholds as
      | { warning_min?: number | null; warning_max?: number | null; critical_min?: number | null; critical_max?: number | null }
      | undefined
    const hasOverride = !!custom && (
      custom.warning_min != null || custom.warning_max != null
      || custom.critical_min != null || custom.critical_max != null
    )
    sensorEffectiveThresholds.value = hasOverride
      ? {
          warnLow: custom!.warning_min ?? null,
          warnHigh: custom!.warning_max ?? null,
          alarmLow: custom!.critical_min ?? null,
          alarmHigh: custom!.critical_max ?? null,
          source: 'override',
        }
      : {
          warnLow: base?.warning_min ?? null,
          warnHigh: base?.warning_max ?? null,
          alarmLow: base?.threshold_min ?? null,
          alarmHigh: base?.threshold_max ?? null,
          source: 'base',
        }
  } catch {
    sensorEffectiveThresholds.value = null
  } finally {
    effectiveLoadedFor.value = sensorId
    isLoadingThresholds.value = false
  }
}

watch(
  () => localConfig.value.sensorId,
  async (sId) => {
    if (typeof sId === 'string' && sId) {
      await fetchEffectiveThresholds(normalizeLegacySensorId(sId))
      autoFillIfEmpty()
    } else {
      sensorEffectiveThresholds.value = null
      effectiveLoadedFor.value = null
    }
  },
  { immediate: true },
)

/** AUT-1054 TM-3: visible hint when the sync button stays disabled (no effective threshold loaded). */
const thresholdSyncUnavailableHint = computed(() => {
  if (!localConfig.value.showThresholds || !localConfig.value.sensorId) return null
  if (isLoadingThresholds.value || sensorEffectiveThresholds.value) return null
  if (effectiveLoadedFor.value !== normalizeLegacySensorId(localConfig.value.sensorId)) return null
  const configId = findSensorConfigId(normalizeLegacySensorId(localConfig.value.sensorId))
  if (!configId) {
    return 'Sensor-Konfiguration (UUID) nicht gefunden — Alert-Schwellen können nicht geladen werden.'
  }
  return 'Keine Alert-Schwelle für diesen Sensor konfiguriert. Zuerst in den Sensor-Einstellungen setzen.'
})

const thresholdsDiverge = computed<boolean>(() => {
  if (!localConfig.value.showThresholds) return false
  const eff = sensorEffectiveThresholds.value
  if (!eff) return false
  const checks: Array<[number | null, number | null | undefined]> = [
    [eff.warnLow, localConfig.value.warnLow],
    [eff.warnHigh, localConfig.value.warnHigh],
    [eff.alarmLow, localConfig.value.alarmLow],
    [eff.alarmHigh, localConfig.value.alarmHigh],
  ]
  for (const [b, w] of checks) {
    const bVal = b == null ? null : Number(b)
    const wVal = w == null ? null : Number(w)
    if (bVal == null && wVal == null) continue
    if (bVal == null || wVal == null) return true
    if (Math.abs(bVal - wVal) > 1e-6) return true
  }
  return false
})

/**
 * AUT-246: Copy the sensor's effective alert threshold (override → base fallback)
 * into the widget config. One-shot click — no auto-sync, widget lines stay editable.
 */
function loadThresholdsFromEffective(): void {
  const eff = sensorEffectiveThresholds.value
  if (!eff) {
    showSyncMessage('Alert-Schwelle nicht geladen')
    return
  }
  if (eff.warnLow == null && eff.warnHigh == null && eff.alarmLow == null && eff.alarmHigh == null) {
    showSyncMessage('Keine Alert-Schwelle für diesen Sensor konfiguriert')
    return
  }
  const updates: Record<string, any> = { ...localConfig.value, showThresholds: true }
  if (eff.warnLow != null) updates.warnLow = eff.warnLow
  if (eff.warnHigh != null) updates.warnHigh = eff.warnHigh
  if (eff.alarmLow != null) updates.alarmLow = eff.alarmLow
  if (eff.alarmHigh != null) updates.alarmHigh = eff.alarmHigh
  localConfig.value = updates
  emit('update:config', localConfig.value)
  showSyncMessage(eff.source === 'override' ? 'Aus Alert-Override übernommen' : 'Aus Sensor-Schwelle übernommen')
}

/**
 * AUT-1105: Silently pre-fill display-line fields with the effective alert threshold
 * when ALL four fields are unset (first open / never configured by the operator).
 * Unlike loadThresholdsFromEffective(), this shows no toast and does not force
 * showThresholds=true — it is a pure default-state initialisation.
 * Randfall: sensor with no configured threshold → all four effective values are null
 * → fields stay empty, matching the existing behaviour of the manual button.
 */
function autoFillIfEmpty(): void {
  if (!caps.value.hasThresholds) return
  const eff = sensorEffectiveThresholds.value
  if (!eff) return
  // Skip when the operator has already set at least one display-line field
  const hasAnyLocal =
    localConfig.value.alarmLow != null ||
    localConfig.value.warnLow != null ||
    localConfig.value.warnHigh != null ||
    localConfig.value.alarmHigh != null
  if (hasAnyLocal) return
  // Randfall: sensor has no configured alert threshold → leave fields empty
  if (eff.alarmLow == null && eff.warnLow == null && eff.warnHigh == null && eff.alarmHigh == null) return
  const updates: Record<string, any> = { ...localConfig.value }
  if (eff.alarmLow != null) updates.alarmLow = eff.alarmLow
  if (eff.warnLow != null) updates.warnLow = eff.warnLow
  if (eff.warnHigh != null) updates.warnHigh = eff.warnHigh
  if (eff.alarmHigh != null) updates.alarmHigh = eff.alarmHigh
  localConfig.value = updates
  emit('update:config', localConfig.value)
}

const widgetTypeLabels: Record<string, string> = {
  'sensor-tile': 'Sensor-Kachel',
  'line-chart': 'Linien-Chart',
  'gauge': 'Gauge',
  'sensor-card': 'Sensor-Karte',
  'historical': 'Historische Zeitreihe',
  'actuator-card': 'Aktor-Status',
  'actuator-runtime': 'Aktor-Laufzeit',
  'esp-health': 'ESP-Health',
  'alarm-list': 'Alarm-Liste',
  'multi-sensor': 'Multi-Sensor-Chart',
  'statistics': 'Statistik',
  'fertigation-pair': 'Fertigation-Paar',
  'comparison-boxplot': 'Boxplot',
  'correlation-scatter': 'Korrelation',
}
</script>

<template>
  <SlideOver
    :open="open"
    :title="`${widgetTypeLabels[widgetType] || widgetType} konfigurieren`"
    width="md"
    @close="emit('close')"
  >
    <div class="widget-config-panel">

      <!-- ═══════════════════════════════════════════════════════
           ZONE 1: KERN — always visible, max 5 fields
           ═══════════════════════════════════════════════════════ -->

      <!-- Title -->
      <div class="widget-config-panel__field">
        <label class="widget-config-panel__label">Titel</label>
        <input
          type="text"
          class="widget-config-panel__input"
          :value="localConfig.title || ''"
          placeholder="Widget-Titel..."
          @input="updateField('title', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <!-- Zone Filter for Sensor Selection -->
      <div v-if="hasSensorField" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Zone</label>
        <select
          class="widget-config-panel__select"
          :value="selectedSensorZone || ''"
          @change="selectedSensorZone = ($event.target as HTMLSelectElement).value || undefined"
        >
          <option value="">Alle Zonen</option>
          <option
            v-for="z in availableZones"
            :key="z.id"
            :value="z.id"
          >{{ z.name }}</option>
        </select>
      </div>

      <!-- Zone Filter (AlarmListWidget, ESPHealthWidget, ActuatorRuntimeWidget) -->
      <div v-if="hasZoneFilterField" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Zone-Filter</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.zoneFilter ?? ''"
          @change="updateField('zoneFilter', ($event.target as HTMLSelectElement).value || null)"
          aria-label="Anzeige für Zone"
        >
          <option value="">Alle Zonen</option>
          <option
            v-for="z in availableZones"
            :key="z.id"
            :value="z.id"
          >{{ z.name }}</option>
        </select>
      </div>

      <!-- Sensor Selection (grouped by Zone / Subzone) -->
      <div v-if="hasSensorField" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Sensor</label>
        <select
          class="widget-config-panel__select"
          :value="resolvedSensorSelectId || ''"
          @change="handleSensorChange(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>— Sensor wählen —</option>
          <option
            v-if="orphanSensorOption"
            :value="orphanSensorOption.value"
          >{{ orphanSensorOption.label }} (konfiguriert)</option>
          <template v-for="zoneGroup in groupedSensorOptions" :key="zoneGroup.zoneId ?? '__unassigned'">
            <template v-for="subgroup in zoneGroup.subgroups" :key="`${zoneGroup.zoneId}_${subgroup.subzoneId ?? '__nosub'}`">
              <optgroup :label="subgroup.label ? `${zoneGroup.label} / ${subgroup.label}` : zoneGroup.label">
                <option
                  v-for="opt in subgroup.options"
                  :key="opt.value"
                  :value="opt.value"
                >{{ opt.label }}</option>
              </optgroup>
            </template>
          </template>
        </select>
      </div>

      <!-- Actuator Selection -->
      <div v-if="hasActuatorField" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Aktor</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.actuatorId || ''"
          @change="handleActuatorChange(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>— Aktor wählen —</option>
          <option
            v-for="a in availableActuators"
            :key="a.id"
            :value="a.id"
          >{{ a.label }}</option>
        </select>
      </div>

      <!-- ═══ Fertigation-Pair Config ═══ -->

      <!-- Inflow Sensor Selection -->
      <div v-if="isFertigationPair" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Inflow-Sensor</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.inflowSensorId || ''"
          @change="updateField('inflowSensorId', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">— keiner —</option>
          <template v-for="zoneGroup in groupedSensorOptions" :key="zoneGroup.zoneId ?? '__unassigned'">
            <template v-for="subgroup in zoneGroup.subgroups" :key="`${zoneGroup.zoneId}_${subgroup.subzoneId ?? '__nosub'}`">
              <optgroup :label="subgroup.label ? `${zoneGroup.label} / ${subgroup.label}` : zoneGroup.label">
                <option
                  v-for="opt in subgroup.options.filter((o) => o.configId)"
                  :key="opt.configId"
                  :value="opt.configId"
                >{{ opt.label }}</option>
              </optgroup>
            </template>
          </template>
        </select>
      </div>

      <!-- Runoff Sensor Selection -->
      <div v-if="isFertigationPair" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Runoff-Sensor</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.runoffSensorId || ''"
          @change="updateField('runoffSensorId', ($event.target as HTMLSelectElement).value)"
        >
          <option value="">— keiner —</option>
          <template v-for="zoneGroup in groupedSensorOptions" :key="zoneGroup.zoneId ?? '__unassigned'">
            <template v-for="subgroup in zoneGroup.subgroups" :key="`${zoneGroup.zoneId}_${subgroup.subzoneId ?? '__nosub'}`">
              <optgroup :label="subgroup.label ? `${zoneGroup.label} / ${subgroup.label}` : zoneGroup.label">
                <option
                  v-for="opt in subgroup.options.filter((o) => o.configId)"
                  :key="opt.configId"
                  :value="opt.configId"
                >{{ opt.label }}</option>
              </optgroup>
            </template>
          </template>
        </select>
      </div>

      <!-- Sensor Type (EC / pH) -->
      <div v-if="isFertigationPair" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Sensortyp</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.sensorType || 'ec'"
          @change="updateField('sensorType', ($event.target as HTMLSelectElement).value)"
        >
          <option value="ec">EC (Leitfähigkeit)</option>
          <option value="ph">pH</option>
        </select>
      </div>

      <!-- AUT-1107: Display Mode (sensor-tile only) -->
      <div v-if="hasDisplayModePicker" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Anzeigeart</label>
        <div class="widget-config-panel__chips">
          <button
            v-for="mode in SENSOR_TILE_DISPLAY_MODES"
            :key="mode.value"
            :class="['widget-config-panel__chip', { 'widget-config-panel__chip--active': localConfig.displayMode === mode.value }]"
            @click="updateField('displayMode', mode.value)"
          >{{ mode.label }}</button>
        </div>
      </div>

      <!-- Time Range — Short (Historical, Statistics, Fertigation-Pair) -->
      <div v-if="hasShortTimeRange" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Zeitraum</label>
        <div class="widget-config-panel__chips">
          <button
            v-for="range in ['1h', '6h', '24h', '7d', '30d']"
            :key="range"
            :class="['widget-config-panel__chip', { 'widget-config-panel__chip--active': localConfig.timeRange === range }]"
            @click="updateField('timeRange', range)"
          >{{ range }}</button>
        </div>
      </div>

      <!-- Time Range — Long (Boxplot, Correlation-Scatter) -->
      <div v-if="hasLongTimeRange" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Zeitraum</label>
        <div class="widget-config-panel__chips">
          <button
            v-for="range in ['7d', '30d', '90d', 'season']"
            :key="range"
            :class="['widget-config-panel__chip', { 'widget-config-panel__chip--active': localConfig.timeRange === range }]"
            @click="updateField('timeRange', range)"
          >{{ range }}</button>
        </div>
      </div>

      <!-- AUT-231: Sensor-Type (Boxplot, Correlation-Scatter) -->
      <div v-if="hasSensorTypeField" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Sensortyp</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.sensor_type || ''"
          @change="updateField('sensor_type', ($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>— Sensortyp wählen —</option>
          <option
            v-for="opt in sensorTypeOptions"
            :key="opt.value"
            :value="opt.value"
          >{{ opt.label }}</option>
        </select>
      </div>

      <!-- AUT-231: Group-By (Boxplot) -->
      <div v-if="hasGroupByField" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Gruppieren nach</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.group_by || 'zone_id'"
          @change="updateField('group_by', ($event.target as HTMLSelectElement).value)"
        >
          <option value="zone_id">Zone</option>
          <option value="subzone_id">Subzone</option>
          <option value="plant_id">Pflanze</option>
        </select>
      </div>

      <!-- AUT-231: Anonymize Labels (Boxplot) -->
      <div v-if="hasAnonymizeField" class="widget-config-panel__field">
        <label class="widget-config-panel__label-row">
          <span>Labels anonymisieren</span>
          <input
            type="checkbox"
            :checked="localConfig.anonymize_labels ?? false"
            @change="updateField('anonymize_labels', ($event.target as HTMLInputElement).checked)"
          />
        </label>
      </div>

      <!-- AUT-231: Correlation-Scatter Config -->
      <template v-if="hasCorrelationConfig">
        <div class="widget-config-panel__field">
          <label class="widget-config-panel__label">X-Sensortyp</label>
          <select
            class="widget-config-panel__select"
            :value="localConfig.x_sensor_type || ''"
            @change="updateField('x_sensor_type', ($event.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>— Sensortyp wählen —</option>
            <option
              v-for="opt in sensorTypeOptions"
              :key="opt.value"
              :value="opt.value"
            >{{ opt.label }}</option>
          </select>
        </div>
        <div class="widget-config-panel__field">
          <label class="widget-config-panel__label">Y-Metadata-Key</label>
          <input
            type="text"
            class="widget-config-panel__input"
            :value="localConfig.y_metadata_key || ''"
            placeholder="z.B. yield_kg"
            @input="updateField('y_metadata_key', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <div class="widget-config-panel__field">
          <label class="widget-config-panel__label-row">
            <span>Regressionslinie anzeigen</span>
            <input
              type="checkbox"
              :checked="localConfig.show_regression_line ?? false"
              @change="updateField('show_regression_line', ($event.target as HTMLInputElement).checked)"
            />
          </label>
        </div>
      </template>

      <!-- AUT-239 Fix 2: Multi-Sensor list -->
      <div v-if="hasMultiSensorField" class="widget-config-panel__field">
        <label class="widget-config-panel__label">
          Sensoren
          <span class="widget-config-panel__hint">
            ({{ multiSensorList.length }} / {{ MAX_MULTI_SENSOR_COUNT }})
          </span>
        </label>
        <ul class="widget-config-panel__sensor-list">
          <li
            v-for="sId in multiSensorList"
            :key="sId"
            class="widget-config-panel__sensor-item"
          >
            <span class="widget-config-panel__sensor-label">{{ getSensorOptionLabel(sId) }}</span>
            <button
              type="button"
              class="widget-config-panel__sensor-remove"
              :disabled="multiSensorList.length <= MIN_MULTI_SENSOR_COUNT"
              :aria-label="`Sensor ${getSensorOptionLabel(sId)} entfernen`"
              @click="removeMultiSensor(sId)"
            >
              <X :size="14" />
            </button>
          </li>
        </ul>
        <div v-if="showAddSensorPicker && !isMultiSensorMaxReached" class="widget-config-panel__sensor-picker">
          <select
            class="widget-config-panel__select"
            :value="''"
            @change="addMultiSensor(($event.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>— Sensor wählen —</option>
            <template v-for="zoneGroup in groupedSensorOptions" :key="zoneGroup.zoneId ?? '__unassigned'">
              <template v-for="subgroup in zoneGroup.subgroups" :key="`${zoneGroup.zoneId}_${subgroup.subzoneId ?? '__nosub'}`">
                <optgroup :label="subgroup.label ? `${zoneGroup.label} / ${subgroup.label}` : zoneGroup.label">
                  <option
                    v-for="opt in subgroup.options"
                    :key="opt.value"
                    :value="opt.value"
                    :disabled="multiSensorList.includes(opt.value)"
                  >{{ opt.label }}</option>
                </optgroup>
              </template>
            </template>
          </select>
        </div>
        <button
          v-if="!isMultiSensorMaxReached"
          type="button"
          class="widget-config-panel__sensor-add"
          @click="showAddSensorPicker = !showAddSensorPicker"
        >
          <Plus :size="14" />
          <span>Sensor hinzufügen</span>
        </button>
        <p v-else class="widget-config-panel__sensor-max-warning">
          Maximum von {{ MAX_MULTI_SENSOR_COUNT }} Sensoren erreicht
        </p>
      </div>

      <!-- ═══════════════════════════════════════════════════════
           ZONE 2: DARSTELLUNG — accordion, collapsed by default
           ═══════════════════════════════════════════════════════ -->

      <details class="config-section">
        <summary class="config-section__header">
          <ChevronRight :size="16" class="config-section__chevron" />
          <span>Darstellung</span>
        </summary>
        <div class="config-section__body">

          <!-- Y-Axis Range (Charts) -->
          <div v-if="hasYRange" class="widget-config-panel__field">
            <label class="widget-config-panel__label">
              Y-Achse
              <span v-if="sensorTypeConfig" class="widget-config-panel__hint">
                ({{ sensorTypeConfig.label }}: {{ sensorTypeConfig.min }}–{{ sensorTypeConfig.max }} {{ sensorTypeConfig.unit }})
              </span>
            </label>
            <div class="widget-config-panel__range-row">
              <input
                type="number"
                class="widget-config-panel__input widget-config-panel__input--small"
                :value="localConfig.yMin ?? ''"
                placeholder="Min (auto)"
                @input="updateField('yMin', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : undefined)"
              />
              <span class="widget-config-panel__range-sep">–</span>
              <input
                type="number"
                class="widget-config-panel__input widget-config-panel__input--small"
                :value="localConfig.yMax ?? ''"
                placeholder="Max (auto)"
                @input="updateField('yMax', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : undefined)"
              />
            </div>
          </div>

          <!-- Color -->
          <div v-if="hasColor" class="widget-config-panel__field">
            <label class="widget-config-panel__label">Farbe</label>
            <div class="widget-config-panel__color-row">
              <button
                v-for="c in CHART_COLORS"
                :key="c"
                :class="['widget-config-panel__color-swatch', { 'widget-config-panel__color-swatch--active': localConfig.color === c }]"
                :style="{ background: c }"
                @click="updateField('color', c)"
              />
            </div>
          </div>

          <!-- Thresholds toggle -->
          <div v-if="hasThresholdFields" class="widget-config-panel__field">
            <label class="widget-config-panel__label-row">
              <span>Schwellenwerte anzeigen</span>
              <input
                type="checkbox"
                :checked="localConfig.showThresholds ?? false"
                @change="updateField('showThresholds', ($event.target as HTMLInputElement).checked)"
              />
            </label>
          </div>

          <!-- AUT-246 / AUT-911/912: Single sync button — copies the effective alert
               threshold (override → base fallback) of the selected sensor. -->
          <div v-if="hasThresholdFields && localConfig.showThresholds && localConfig.sensorId" class="widget-config-panel__field widget-config-panel__sync-row">
            <button
              type="button"
              class="widget-config-panel__sync-btn"
              :disabled="isLoadingThresholds || !sensorEffectiveThresholds"
              :title="thresholdSyncUnavailableHint || undefined"
              @click="loadThresholdsFromEffective"
            >
              <Download :size="14" />
              <span>{{ isLoadingThresholds ? 'Laden…' : 'Aus Alert-Schwelle übernehmen' }}</span>
            </button>
            <p
              v-if="thresholdSyncUnavailableHint"
              class="widget-config-panel__hint"
            >
              {{ thresholdSyncUnavailableHint }}
            </p>
            <Transition name="sync-msg">
              <span v-if="thresholdSyncMessage" class="widget-config-panel__sync-msg">
                {{ thresholdSyncMessage }}
              </span>
            </Transition>
          </div>

          <!-- AUT-246: Divergence warning — widget lines differ from the effective alert threshold -->
          <p
            v-if="thresholdsDiverge"
            class="widget-config-panel__divergence-warning"
            data-testid="widget-threshold-divergence-warning"
          >
            Diese Anzeige-Linien weichen von der Alert-Schwelle des Sensors ab. Alerts werden weiter durch die Alert-Schwelle getriggert.
          </p>

          <!-- Anzeige-Linien (nur visuell) — AUT-246: Labels + Disclaimer -->
          <div v-if="hasThresholdFields && localConfig.showThresholds" class="widget-config-panel__field">
            <label class="widget-config-panel__label">Anzeige-Linien (nur visuell)</label>
            <p class="widget-config-panel__threshold-info">
              Diese Werte steuern nur die Chart-Darstellung. Sensor-Alerts werden durch die <strong>Alert-Schwelle des Sensors</strong> getriggert (Sensor-Einstellungen).
            </p>
            <div class="widget-config-panel__threshold-grid">
              <div class="widget-config-panel__threshold-row">
                <span class="widget-config-panel__threshold-label widget-config-panel__threshold-label--alarm">Anzeige-Linie Alarm Low</span>
                <input
                  type="number"
                  class="widget-config-panel__input widget-config-panel__input--small"
                  :value="localConfig.alarmLow ?? ''"
                  placeholder="—"
                  @input="updateField('alarmLow', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : undefined)"
                />
              </div>
              <div class="widget-config-panel__threshold-row">
                <span class="widget-config-panel__threshold-label widget-config-panel__threshold-label--warn">Anzeige-Linie Warn Low</span>
                <input
                  type="number"
                  class="widget-config-panel__input widget-config-panel__input--small"
                  :value="localConfig.warnLow ?? ''"
                  placeholder="—"
                  @input="updateField('warnLow', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : undefined)"
                />
              </div>
              <div class="widget-config-panel__threshold-row">
                <span class="widget-config-panel__threshold-label widget-config-panel__threshold-label--warn">Anzeige-Linie Warn High</span>
                <input
                  type="number"
                  class="widget-config-panel__input widget-config-panel__input--small"
                  :value="localConfig.warnHigh ?? ''"
                  placeholder="—"
                  @input="updateField('warnHigh', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : undefined)"
                />
              </div>
              <div class="widget-config-panel__threshold-row">
                <span class="widget-config-panel__threshold-label widget-config-panel__threshold-label--alarm">Anzeige-Linie Alarm High</span>
                <input
                  type="number"
                  class="widget-config-panel__input widget-config-panel__input--small"
                  :value="localConfig.alarmHigh ?? ''"
                  placeholder="—"
                  @input="updateField('alarmHigh', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : undefined)"
                />
              </div>
            </div>
          </div>

        </div>
      </details>

      <!-- ═══════════════════════════════════════════════════════
           ZONE 3: ERWEITERT — accordion, collapsed by default
           ═══════════════════════════════════════════════════════ -->

      <details v-if="hasZone3" class="config-section">
        <summary class="config-section__header">
          <ChevronRight :size="16" class="config-section__chevron" />
          <span>Erweitert</span>
        </summary>
        <div class="config-section__body">

          <!-- Fertigation-Pair: Schwellen -->
          <template v-if="isFertigationPair">
            <div class="widget-config-panel__field">
              <label class="widget-config-panel__label">Warning-Schwelle (Differenz)</label>
              <input
                type="number"
                step="0.1"
                class="widget-config-panel__input widget-config-panel__input--small"
                :value="localConfig.diffWarningThreshold ?? 0.5"
                @input="updateField('diffWarningThreshold', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : 0.5)"
              />
            </div>
            <div class="widget-config-panel__field">
              <label class="widget-config-panel__label">Critical-Schwelle (Differenz)</label>
              <input
                type="number"
                step="0.1"
                class="widget-config-panel__input widget-config-panel__input--small"
                :value="localConfig.diffCriticalThreshold ?? 0.8"
                @input="updateField('diffCriticalThreshold', ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : 0.8)"
              />
            </div>
          </template>

          <!-- Statistics: Standard deviation -->
          <div class="widget-config-panel__field">
            <label class="widget-config-panel__label-row">
              <span>Standardabweichung anzeigen</span>
              <input
                type="checkbox"
                :checked="localConfig.showStdDev ?? true"
                @change="updateField('showStdDev', ($event.target as HTMLInputElement).checked)"
              />
            </label>
          </div>

          <!-- Statistics: Data quality -->
          <div class="widget-config-panel__field">
            <label class="widget-config-panel__label-row">
              <span>Datenqualitaet anzeigen</span>
              <input
                type="checkbox"
                :checked="localConfig.showQuality ?? false"
                @change="updateField('showQuality', ($event.target as HTMLInputElement).checked)"
              />
            </label>
          </div>

        </div>
      </details>

      <div v-if="showRemoveAction" class="widget-config-panel__danger-zone">
        <button
          type="button"
          class="widget-config-panel__remove-btn"
          aria-label="Widget entfernen"
          @click="emit('remove')"
        >
          <Trash2 :size="14" aria-hidden="true" />
          Widget entfernen
        </button>
      </div>

    </div>
  </SlideOver>
</template>

<style scoped>
.widget-config-panel {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
}

.widget-config-panel__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.widget-config-panel__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
}

.widget-config-panel__hint {
  font-weight: 400;
  text-transform: none;
  letter-spacing: normal;
  color: var(--color-text-muted);
}

.widget-config-panel__label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.widget-config-panel__input {
  padding: var(--space-2);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.widget-config-panel__input--small {
  width: 100px;
}

.widget-config-panel__select {
  padding: var(--space-2);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.widget-config-panel__range-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.widget-config-panel__range-sep {
  color: var(--color-text-muted);
}

.widget-config-panel__chips {
  display: flex;
  gap: var(--space-1);
}

.widget-config-panel__chip {
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-quaternary);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.widget-config-panel__chip:hover {
  border-color: var(--color-accent);
  color: var(--color-text-primary);
}

.widget-config-panel__chip--active {
  background: rgba(59, 130, 246, 0.15);
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
}

.widget-config-panel__color-row {
  display: flex;
  gap: var(--space-2);
}

.widget-config-panel__color-swatch {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: 2px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.widget-config-panel__color-swatch:hover {
  transform: scale(1.15);
}

.widget-config-panel__color-swatch--active {
  border-color: var(--color-text-primary);
  box-shadow: 0 0 0 2px var(--color-bg-primary);
}

.widget-config-panel__threshold-grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.widget-config-panel__threshold-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.widget-config-panel__threshold-label {
  font-size: var(--text-xs);
  width: 80px;
  flex-shrink: 0;
}

.widget-config-panel__threshold-label--alarm {
  color: var(--color-error);
}

.widget-config-panel__threshold-label--warn {
  color: var(--color-warning);
}

/* ═══ Alert-Config Threshold Sync (P8-A3) ═══ */

.widget-config-panel__sync-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px solid var(--color-accent);
  border-radius: var(--radius-sm);
  color: var(--color-accent-bright);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 32px;
}

.widget-config-panel__sync-btn:hover:not(:disabled) {
  border-color: var(--color-accent-bright);
  color: var(--color-accent-bright);
}

.widget-config-panel__threshold-info {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-2);
}

/* AUT-246: Divergence warning + sync row */
.widget-config-panel__divergence-warning {
  margin: 0;
  padding: var(--space-2) var(--space-3);
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.25);
  border-radius: var(--radius-sm);
  color: var(--color-warning);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.widget-config-panel__sync-row {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

/* AUT-239 Fix 2: Multi-Sensor list */
.widget-config-panel__sensor-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.widget-config-panel__sensor-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  background: var(--color-bg-quaternary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  min-height: 32px;
}

.widget-config-panel__sensor-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.widget-config-panel__sensor-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: color var(--transition-fast);
  min-width: 24px;
  min-height: 24px;
}

.widget-config-panel__sensor-remove:hover:not(:disabled) {
  color: var(--color-error);
}

.widget-config-panel__sensor-remove:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.widget-config-panel__sensor-picker {
  margin-top: var(--space-1);
}

.widget-config-panel__sensor-add {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  background: transparent;
  border: 1px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 32px;
  align-self: flex-start;
}

.widget-config-panel__sensor-add:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
}

.widget-config-panel__sensor-add:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.widget-config-panel__sensor-max-warning {
  margin: 0;
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-error);
  align-self: flex-start;
}

.widget-config-panel__sync-btn:disabled {
  opacity: 0.5;
  cursor: wait;
}

.widget-config-panel__sync-msg {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-style: italic;
}

.sync-msg-enter-active {
  transition: opacity 200ms ease;
}

.sync-msg-leave-active {
  transition: opacity 600ms ease;
}

.sync-msg-enter-from,
.sync-msg-leave-to {
  opacity: 0;
}

/* ═══ Accordion (Zone 2 + Zone 3) ═══ */

.config-section {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.config-section__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-tertiary);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  user-select: none;
  list-style: none;
  min-height: 44px;
}

.config-section__header::-webkit-details-marker {
  display: none;
}

.config-section__header::marker {
  display: none;
  content: '';
}

.config-section__header:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-quaternary);
}

.config-section__chevron {
  flex-shrink: 0;
  transition: transform 200ms ease;
  color: var(--color-text-muted);
}

details[open] > .config-section__header .config-section__chevron {
  transform: rotate(90deg);
}

.config-section__body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-3);
  animation: configSlideDown 200ms ease;
}

@keyframes configSlideDown {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.widget-config-panel__danger-zone {
  margin-top: var(--space-2);
  padding-top: var(--space-4);
  border-top: 1px solid var(--glass-border);
}

.widget-config-panel__remove-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 44px;
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-status-alarm);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-status-alarm);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.widget-config-panel__remove-btn:hover {
  background: color-mix(in srgb, var(--color-status-alarm) 12%, transparent);
}
</style>
