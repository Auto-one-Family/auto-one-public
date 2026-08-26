<script setup lang="ts">
/**
 * AddWidgetDialog — 3-step dialog for adding a widget to a zone dashboard.
 *
 * Steps: 1. Widget type → 2. Zone → 3. Sensor
 * Used from the FAB in Monitor context. Creates zone dashboard if none exists.
 */

import { ref, computed, watch, type Component } from 'vue'
import { useDashboardStore, type WidgetType } from '@/shared/stores/dashboard.store'
import { useZoneStore } from '@/shared/stores/zone.store'
import { useEspStore } from '@/stores/esp'
import { useSensorOptions } from '@/composables/useSensorOptions'
import { B2_CATALOG_WIDGET_TYPE_META, useDashboardWidgets, WIDGET_ICON_MAP } from '@/composables/useDashboardWidgets'
import { useToast } from '@/composables/useToast'
import BaseModal from '@/shared/design/primitives/BaseModal.vue'
import { BarChart3 } from 'lucide-vue-next'

interface Props {
  open: boolean
  defaultZoneId?: string
  defaultWidgetType?: string
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
  added: [widgetConfig: { type: WidgetType; layoutId: string; widgetId: string; requiresConfig: boolean }]
}>()

const dashStore = useDashboardStore()
const zoneStore = useZoneStore()
const espStore = useEspStore()
const toast = useToast()
const { WIDGET_DEFAULT_CONFIGS } = useDashboardWidgets({
  showConfigButton: false,
  showWidgetHeader: false,
})
const WIDGET_TYPE_META = B2_CATALOG_WIDGET_TYPE_META

/**
 * Widget types that require additional configuration after placement
 * (typically multi-source widgets). Toast hint nudges the user to open the config panel.
 */
const REQUIRES_POST_CONFIG = new Set<WidgetType>([
  'comparison-boxplot', 'correlation-scatter', 'fertigation-pair',
])

// ── State ──────────────────────────────────────────────────────────────────

const selectedWidgetType = ref<string>(props.defaultWidgetType || '')
const selectedZoneId = ref<string>(props.defaultZoneId || '')
const selectedSensorId = ref<string>('')

// Zone-filtered sensor options
const filterZoneRef = computed(() => selectedZoneId.value || undefined)
const { groupedSensorOptions } = useSensorOptions(filterZoneRef)

// Available zones from espStore devices + zoneStore entities
const availableZones = computed(() => {
  const zoneMap = new Map<string, string>()

  // From Zone entities (includes empty zones)
  for (const z of zoneStore.activeZones) {
    zoneMap.set(z.zone_id, z.name)
  }

  // From devices (fallback for zones not yet in zoneStore)
  for (const device of espStore.devices) {
    if (device.zone_id && !zoneMap.has(device.zone_id)) {
      zoneMap.set(device.zone_id, device.zone_name || device.zone_id)
    }
  }

  return [...zoneMap.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

// Check if selected widget type needs a sensor
const needsSensor = computed(() => {
  const sensorTypes = new Set([
    'sensor-tile', 'gauge', 'historical', 'multi-sensor', 'statistics',
  ])
  return sensorTypes.has(selectedWidgetType.value)
})

function handleTypeSelect(type: string): void {
  selectedWidgetType.value = type
}

// Form validity
const isValid = computed(() => {
  if (!selectedWidgetType.value) return false
  if (!selectedZoneId.value) return false
  if (needsSensor.value && !selectedSensorId.value) return false
  return true
})

// ── Reset on open/close ──────────────────────────────────────────────────

watch(() => props.open, (isOpen) => {
  if (isOpen) {
    selectedWidgetType.value = props.defaultWidgetType || ''
    selectedZoneId.value = props.defaultZoneId || ''
    selectedSensorId.value = ''
  }
})

// Reset sensor when zone changes
watch(selectedZoneId, () => {
  selectedSensorId.value = ''
})

// ── Icon resolver ────────────────────────────────────────────────────────

function getWidgetIcon(meta: typeof WIDGET_TYPE_META[number]): Component {
  // AUT-901: resolve via shared WIDGET_ICON_MAP using the serializable iconName
  // (replaces the fragile meta.icon.name reverse-lookup that broke for 5 types).
  return WIDGET_ICON_MAP[meta.iconName] || BarChart3
}

// ── Submit ────────────────────────────────────────────────────────────────

function handleAdd() {
  if (!isValid.value) return

  const zoneId = selectedZoneId.value
  const zoneName = availableZones.value.find(z => z.id === zoneId)?.name || zoneId

  // Find or create zone dashboard
  let zoneDashboards = dashStore.zoneDashboards(zoneId)
  let layoutId: string

  if (zoneDashboards.length > 0) {
    layoutId = zoneDashboards[0].id
  } else {
    toast.error(`Kein Dashboard für Zone „${zoneName}" — erstellen Sie zuerst eines im Editor.`)
    return
  }

  // Build widget config
  const widgetType = selectedWidgetType.value as WidgetType
  const meta = WIDGET_TYPE_META.find(m => m.type === widgetType)
  const defaultConfig = WIDGET_DEFAULT_CONFIGS[widgetType] || {}

  const widgetConfig: Record<string, unknown> = {
    ...defaultConfig,
    zoneId,
  }

  if (needsSensor.value && selectedSensorId.value) {
    if (widgetType === 'multi-sensor') {
      // multi-sensor widget reads from config.dataSources (comma-separated sensor IDs);
      // further measurement points are added via the widget's chip picker.
      widgetConfig.dataSources = selectedSensorId.value
    } else {
      widgetConfig.sensorId = selectedSensorId.value
    }
  }

  const widget = dashStore.addWidget(layoutId, {
    type: widgetType,
    x: 0,
    y: 0,
    w: meta?.w ?? 3,
    h: meta?.h ?? 2,
    config: widgetConfig as any,
  })

  if (widget) {
    const requiresConfig = REQUIRES_POST_CONFIG.has(widgetType)
    toast.success(requiresConfig ? 'Widget hinzugefügt — bitte konfigurieren' : 'Widget hinzugefuegt')
    emit('added', {
      type: widgetType,
      layoutId,
      widgetId: widget.id,
      requiresConfig,
    })
  } else {
    toast.error('Widget konnte nicht hinzugefuegt werden')
  }

  emit('update:open', false)
  emit('close')
}
</script>

<template>
  <BaseModal
    :open="open"
    title="Widget hinzufuegen"
    max-width="max-w-lg"
    @update:open="emit('update:open', $event)"
    @close="emit('close')"
  >
    <div class="add-widget-dialog">
      <!-- Step 1: Widget Type -->
      <div class="add-widget-dialog__section">
        <label class="add-widget-dialog__label">1. Widget-Typ waehlen</label>

        <div class="add-widget-dialog__type-grid">
          <button
            v-for="meta in WIDGET_TYPE_META"
            :key="meta.type"
            class="add-widget-dialog__type-btn"
            :class="{
              'add-widget-dialog__type-btn--active': selectedWidgetType === meta.type,
            }"
            :title="meta.description"
            @click="handleTypeSelect(meta.type)"
          >
            <component :is="getWidgetIcon(meta)" class="add-widget-dialog__type-icon" />
            <span class="add-widget-dialog__type-label">{{ meta.label }}</span>
          </button>
        </div>
      </div>

      <!-- Step 2: Zone -->
      <div class="add-widget-dialog__section">
        <label class="add-widget-dialog__label" for="aw-zone">2. Zone waehlen</label>
        <select
          id="aw-zone"
          v-model="selectedZoneId"
          class="add-widget-dialog__select"
        >
          <option value="" disabled>Zone auswaehlen...</option>
          <option v-for="zone in availableZones" :key="zone.id" :value="zone.id">
            {{ zone.name }}
          </option>
        </select>
      </div>

      <!-- Step 3: Sensor (conditional) -->
      <div v-if="needsSensor && selectedZoneId" class="add-widget-dialog__section">
        <label class="add-widget-dialog__label" for="aw-sensor">3. Sensor waehlen</label>
        <select
          id="aw-sensor"
          v-model="selectedSensorId"
          class="add-widget-dialog__select"
        >
          <option value="" disabled>Sensor auswaehlen...</option>
          <template v-for="group in groupedSensorOptions" :key="group.zoneId ?? 'unassigned'">
            <template v-for="subgroup in group.subgroups" :key="subgroup.subzoneId ?? 'none'">
              <optgroup
                :label="subgroup.label ? `${group.label} / ${subgroup.label}` : group.label"
              >
                <option v-for="opt in subgroup.options" :key="opt.value" :value="opt.value">
                  {{ opt.label }}
                </option>
              </optgroup>
            </template>
          </template>
        </select>
      </div>
    </div>

    <template #footer>
      <div class="add-widget-dialog__footer">
        <button
          class="add-widget-dialog__btn add-widget-dialog__btn--cancel"
          @click="emit('update:open', false); emit('close')"
        >
          Abbrechen
        </button>
        <button
          class="add-widget-dialog__btn add-widget-dialog__btn--add"
          :disabled="!isValid"
          @click="handleAdd"
        >
          Hinzufuegen
        </button>
      </div>
    </template>
  </BaseModal>
</template>

<style scoped>
.add-widget-dialog {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.add-widget-dialog__section {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.add-widget-dialog__label {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
}

/* ── Type Grid ── */

.add-widget-dialog__type-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-2);
}

.add-widget-dialog__type-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-1);
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 44px;
}

.add-widget-dialog__type-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
  color: var(--color-text-primary);
}

.add-widget-dialog__type-btn--active {
  background: rgba(96, 165, 250, 0.12);
  border-color: rgba(96, 165, 250, 0.4);
  color: var(--color-accent);
}

.add-widget-dialog__type-icon {
  width: 18px;
  height: 18px;
}

.add-widget-dialog__type-label {
  font-size: var(--text-xxs);
  font-weight: 500;
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

/* ── Select ── */

.add-widget-dialog__select {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  min-height: 44px;
  cursor: pointer;
  transition: border-color var(--transition-fast);
}

.add-widget-dialog__select:hover {
  border-color: rgba(255, 255, 255, 0.2);
}

.add-widget-dialog__select:focus {
  outline: none;
  border-color: var(--color-accent);
}

.add-widget-dialog__select option {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

/* ── Footer ── */

.add-widget-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-3);
}

.add-widget-dialog__btn {
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  min-height: 44px;
  border: none;
}

.add-widget-dialog__btn--cancel {
  background: transparent;
  color: var(--color-text-secondary);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.add-widget-dialog__btn--cancel:hover {
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text-primary);
}

.add-widget-dialog__btn--add {
  background: var(--color-accent);
  color: white;
}

.add-widget-dialog__btn--add:hover:not(:disabled) {
  filter: brightness(1.1);
}

.add-widget-dialog__btn--add:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

@media (prefers-reduced-motion: reduce) {
  .add-widget-dialog__type-btn,
  .add-widget-dialog__select,
  .add-widget-dialog__btn {
    transition: none;
  }
}
</style>
