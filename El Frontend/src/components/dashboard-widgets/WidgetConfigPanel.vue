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
import { ChevronRight, Download, Plus, X } from 'lucide-vue-next'
import { useEspStore } from '@/stores/esp'
import { SlideOver } from '@/shared/design/primitives'
import { SENSOR_TYPE_CONFIG, getSensorTypeOptions } from '@/utils/sensorDefaults'
import { CHART_COLORS } from '@/utils/chartColors'
import { useSensorOptions } from '@/composables/useSensorOptions'
import { sensorsApi } from '@/api/sensors'
import type { MockActuator } from '@/types'
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
}>()

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
  return undefined
}

const isLoadingThresholds = ref(false)
const thresholdSyncMessage = ref<string | null>(null)
let syncMessageTimer: ReturnType<typeof setTimeout> | undefined

function showSyncMessage(msg: string) {
  thresholdSyncMessage.value = msg
  clearTimeout(syncMessageTimer)
  syncMessageTimer = setTimeout(() => { thresholdSyncMessage.value = null }, 3000)
}

// AUT-246: Cache for base sensor thresholds (SensorConfig.thresholds — SSoT for alerts)
// Used for divergence detection between widget visual lines and sensor base thresholds.
interface SensorBaseThresholds {
  warning_min: number | null
  warning_max: number | null
  alarm_min: number | null
  alarm_max: number | null
}
const sensorBaseThresholds = ref<SensorBaseThresholds | null>(null)
const sensorBaseLoadedFor = ref<string | null>(null)

async function fetchSensorBaseThresholds(sensorId: string): Promise<void> {
  if (sensorBaseLoadedFor.value === sensorId) return
  const configId = findSensorConfigId(sensorId)
  if (!configId) {
    sensorBaseThresholds.value = null
    sensorBaseLoadedFor.value = sensorId
    return
  }
  try {
    const cfg = await sensorsApi.getByConfigId(configId)
    sensorBaseThresholds.value = {
      warning_min: cfg?.warning_min ?? null,
      warning_max: cfg?.warning_max ?? null,
      alarm_min: cfg?.threshold_min ?? null,
      alarm_max: cfg?.threshold_max ?? null,
    }
  } catch {
    sensorBaseThresholds.value = null
  } finally {
    sensorBaseLoadedFor.value = sensorId
  }
}

watch(
  () => localConfig.value.sensorId,
  (sId) => {
    if (typeof sId === 'string' && sId) {
      void fetchSensorBaseThresholds(sId)
    } else {
      sensorBaseThresholds.value = null
      sensorBaseLoadedFor.value = null
    }
  },
  { immediate: true },
)

/**
 * AUT-246: True if any widget visual threshold differs from the sensor base threshold.
 * Used to display a yellow divergence warning so the operator knows alerts are
 * still triggered by the sensor base threshold, not the visible chart lines.
 */
const thresholdsDiverge = computed<boolean>(() => {
  if (!localConfig.value.showThresholds) return false
  const base = sensorBaseThresholds.value
  if (!base) return false
  const checks: Array<[number | null, number | null | undefined]> = [
    [base.warning_min, localConfig.value.warnLow],
    [base.warning_max, localConfig.value.warnHigh],
    [base.alarm_min, localConfig.value.alarmLow],
    [base.alarm_max, localConfig.value.alarmHigh],
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
 * AUT-246: Copy sensor base thresholds (SensorConfig.thresholds) into widget config.
 * One-shot click — no auto-sync. Operator can keep widget thresholds independent.
 */
function loadThresholdsFromSensorBase(): void {
  const base = sensorBaseThresholds.value
  if (!base) {
    showSyncMessage('Sensor-Schwellwerte nicht geladen')
    return
  }
  if (
    base.warning_min == null
    && base.warning_max == null
    && base.alarm_min == null
    && base.alarm_max == null
  ) {
    showSyncMessage('Keine Sensor-Schwellwerte konfiguriert')
    return
  }
  const updates: Record<string, any> = { ...localConfig.value, showThresholds: true }
  if (base.warning_min != null) updates.warnLow = base.warning_min
  if (base.warning_max != null) updates.warnHigh = base.warning_max
  if (base.alarm_min != null) updates.alarmLow = base.alarm_min
  if (base.alarm_max != null) updates.alarmHigh = base.alarm_max
  localConfig.value = updates
  emit('update:config', localConfig.value)
  showSyncMessage('Aus Sensor-Schwelle übernommen')
}

async function loadThresholdsFromAlertConfig(): Promise<void> {
  const sensorId = localConfig.value.sensorId
  if (!sensorId) {
    showSyncMessage('Kein Sensor ausgewählt')
    return
  }

  const configId = findSensorConfigId(sensorId)
  if (!configId) {
    showSyncMessage('Sensor hat keine Config-ID')
    return
  }

  isLoadingThresholds.value = true
  try {
    const response = await sensorsApi.getAlertConfig(configId)
    const thresholds = (response.alert_config as Record<string, any>)?.custom_thresholds as
      | { warning_min?: number | null; warning_max?: number | null; critical_min?: number | null; critical_max?: number | null }
      | undefined

    if (!thresholds || (thresholds.warning_min == null && thresholds.warning_max == null && thresholds.critical_min == null && thresholds.critical_max == null)) {
      showSyncMessage('Keine Schwellwerte für diesen Sensor konfiguriert')
      return
    }

    const updates: Record<string, any> = { ...localConfig.value, showThresholds: true }
    if (thresholds.warning_min != null) updates.warnLow = thresholds.warning_min
    if (thresholds.warning_max != null) updates.warnHigh = thresholds.warning_max
    if (thresholds.critical_min != null) updates.alarmLow = thresholds.critical_min
    if (thresholds.critical_max != null) updates.alarmHigh = thresholds.critical_max

    localConfig.value = updates
    emit('update:config', localConfig.value)
    showSyncMessage('Schwellen geladen')
  } catch {
    showSyncMessage('Laden fehlgeschlagen')
  } finally {
    isLoadingThresholds.value = false
  }
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
    width="sm"
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
          :value="localConfig.sensorId || ''"
          @change="handleSensorChange(($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>— Sensor wählen —</option>
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
          <option value="" disabled>— Inflow-Sensor wählen —</option>
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

      <!-- Runoff Sensor Selection -->
      <div v-if="isFertigationPair" class="widget-config-panel__field">
        <label class="widget-config-panel__label">Runoff-Sensor</label>
        <select
          class="widget-config-panel__select"
          :value="localConfig.runoffSensorId || ''"
          @change="updateField('runoffSensorId', ($event.target as HTMLSelectElement).value)"
        >
          <option value="" disabled>— Runoff-Sensor wählen —</option>
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

          <!-- AUT-246: Sync buttons — operator chooses which source to copy -->
          <div v-if="hasThresholdFields && localConfig.showThresholds && localConfig.sensorId" class="widget-config-panel__field widget-config-panel__sync-row">
            <button
              type="button"
              class="widget-config-panel__sync-btn"
              :disabled="!sensorBaseThresholds"
              @click="loadThresholdsFromSensorBase"
            >
              <Download :size="14" />
              <span>Aus Sensor-Schwelle übernehmen</span>
            </button>
            <button
              type="button"
              class="widget-config-panel__sync-btn widget-config-panel__sync-btn--secondary"
              :disabled="isLoadingThresholds"
              @click="loadThresholdsFromAlertConfig"
            >
              <Download :size="14" />
              <span>{{ isLoadingThresholds ? 'Laden…' : 'Aus Alert-Override laden' }}</span>
            </button>
            <Transition name="sync-msg">
              <span v-if="thresholdSyncMessage" class="widget-config-panel__sync-msg">
                {{ thresholdSyncMessage }}
              </span>
            </Transition>
          </div>

          <!-- AUT-246: Divergence warning — widget lines differ from sensor base threshold -->
          <p
            v-if="thresholdsDiverge"
            class="widget-config-panel__divergence-warning"
            data-testid="widget-threshold-divergence-warning"
          >
            Diese Anzeige-Linien weichen von der Sensor-Schwelle ab. Alerts werden weiter durch die Sensor-Schwelle getriggert.
          </p>

          <!-- Anzeige-Linien (nur visuell) — AUT-246: Labels + Disclaimer -->
          <div v-if="hasThresholdFields && localConfig.showThresholds" class="widget-config-panel__field">
            <label class="widget-config-panel__label">Anzeige-Linien (nur visuell)</label>
            <p class="widget-config-panel__threshold-info">
              Diese Werte steuern nur die Chart-Darstellung. Sensor-Alerts werden durch <strong>SensorConfig.thresholds</strong> getriggert (Sensor-Settings).
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

.widget-config-panel__sync-btn--secondary {
  border-color: var(--glass-border);
  color: var(--color-text-secondary);
}

.widget-config-panel__sync-btn--secondary:hover:not(:disabled) {
  border-color: var(--color-accent);
  color: var(--color-accent-bright);
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
</style>
