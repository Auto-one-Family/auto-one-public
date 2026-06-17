<script setup lang="ts">
/**
 * ComponentSidebar Component
 *
 * Kombinierte Sidebar für Sensoren und Aktoren.
 * Items können per Drag-and-Drop auf ESPs gezogen werden.
 *
 * Features:
 * - Sensoren und Aktoren in einer Liste
 * - Keine Kategorieüberschriften - nur Items
 * - Lucide Icons (konsistent mit Rest der App)
 * - Globaler Drag-State via dragStateStore
 * - Responsive Design mit clamp()
 * - Verbesserte Tooltips mit vollständigem Namen + Beschreibung
 */

import { ref, computed, watch, type Component } from 'vue'
import {
  Thermometer,
  Droplet,
  Droplets,
  Zap,
  Sun,
  Cloud,
  Gauge,
  Waves,
  Layers,
  Activity,
  ToggleLeft,
  Leaf,
  Wind,
  Settings,
  Power,
} from 'lucide-vue-next'
import {
  SENSOR_TYPE_CONFIG,
  type SensorTypeConfig,
} from '@/utils/sensorDefaults'
import {
  ACTUATOR_TYPE_CONFIG,
  type ActuatorTypeConfig,
} from '@/utils/actuatorDefaults'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { createLogger } from '@/utils/logger'

const props = withDefaults(defineProps<{
  orbitalMode?: boolean
}>(), {
  orbitalMode: false,
})

const logger = createLogger('ComponentSidebar')
const dragStore = useDragStateStore()

// Reactive state for dragging
const draggingItem = ref<string | null>(null)

// Watch dragStore for cleanup when drag ends
watch([() => dragStore.isDraggingSensorType, () => dragStore.isDraggingActuatorType], ([isSensor, isActuator]) => {
  if (!isSensor && !isActuator) {
    draggingItem.value = null
  }
})

// Icon mapping
const iconComponents: Record<string, Component> = {
  Thermometer,
  Droplet,
  Droplets,
  Zap,
  Sun,
  Cloud,
  Gauge,
  Waves,
  Layers,
  Activity,
  ToggleLeft,
  Leaf,
  Wind,
  Settings,
  Power,
}

// Basis-Sensor-Typen (physische Hardware)
const BASE_SENSOR_TYPES = [
  'DS18B20',
  'SHT31',
  'BME280',
  'pH',
  'EC',
  'moisture',
  'light',
  'co2',
  'flow',
  'level',
] as const

// Kurzlabels für kompakte Darstellung
const SHORT_LABELS: Record<string, string> = {
  'DS18B20': 'Temp',
  'SHT31': 'T+H',
  'BME280': 'T+H+P',
  'pH': 'pH',
  'EC': 'EC',
  'moisture': 'Feuchte',
  'light': 'Licht',
  'co2': 'CO2',
  'flow': 'Flow',
  'level': 'Level',
}

// Interface for sidebar items
interface SidebarItem {
  id: string
  type: 'sensor' | 'actuator'
  shortLabel: string
  fullLabel: string
  description: string
  iconComponent: Component
  config: SensorTypeConfig | ActuatorTypeConfig
}

// Computed: Alle Items (Sensoren + Aktoren)
const allItems = computed<SidebarItem[]>(() => {
  const items: SidebarItem[] = []

  // Sensoren hinzufügen
  BASE_SENSOR_TYPES.forEach(type => {
    const config = SENSOR_TYPE_CONFIG[type]
    if (config) {
      items.push({
        id: `sensor-${type}`,
        type: 'sensor',
        shortLabel: SHORT_LABELS[type] || type,
        fullLabel: config.label,
        description: config.description || '',
        iconComponent: iconComponents[config.icon] || Activity,
        config,
      })
    }
  })

  // Aktoren hinzufügen
  Object.entries(ACTUATOR_TYPE_CONFIG).forEach(([type, config]) => {
    items.push({
      id: `actuator-${type}`,
      type: 'actuator',
      shortLabel: config.label,
      fullLabel: config.label,
      description: config.description,
      iconComponent: iconComponents[config.icon] || Power,
      config,
    })
  })

  return items
})

// Drag handlers
function onDragStart(event: DragEvent, item: SidebarItem) {
  if (!event.dataTransfer) return

  if (item.type === 'sensor') {
    const sensorConfig = item.config as SensorTypeConfig
    const sensorType = item.id.replace('sensor-', '')
    const dragData = {
      action: 'add-sensor' as const,
      sensorType,
      label: sensorConfig.label,
      defaultUnit: sensorConfig.unit,
      icon: sensorConfig.icon,
    }
    event.dataTransfer.setData('application/json', JSON.stringify(dragData))
    event.dataTransfer.setData('text/plain', sensorType)
    event.dataTransfer.effectAllowed = 'copy'
    logger.info('[DnD] Drag START sensor', { sensorType, label: sensorConfig.label })
    dragStore.startSensorTypeDrag(dragData)
  } else {
    const actuatorConfig = item.config as ActuatorTypeConfig
    const actuatorType = item.id.replace('actuator-', '')
    const dragData = {
      action: 'add-actuator' as const,
      actuatorType,
      label: actuatorConfig.label,
      icon: actuatorConfig.icon,
      isPwm: actuatorConfig.isPwm,
    }
    event.dataTransfer.setData('application/json', JSON.stringify(dragData))
    event.dataTransfer.setData('text/plain', actuatorType)
    event.dataTransfer.effectAllowed = 'copy'
    logger.info('[DnD] Drag START actuator', { actuatorType, label: actuatorConfig.label })
    dragStore.startActuatorTypeDrag(dragData)
  }

  draggingItem.value = item.id
}

function onDragEnd() {
  logger.info('[DnD] Drag END')
  dragStore.endDrag()
  draggingItem.value = null
}

</script>

<template>
  <aside :class="['component-sidebar', { 'component-sidebar--orbital': props.orbitalMode }]">
    <div class="component-sidebar__content">
      <div class="component-sidebar__header">
        <span class="component-sidebar__title">Komponenten</span>
        <span class="component-sidebar__hint">Auf ESP ziehen</span>
      </div>

      <div class="component-sidebar__items">
        <div
          v-for="item in allItems"
          :key="item.id"
          class="component-item"
          :class="[
            `component-item--${item.type}`,
            { 'component-item--dragging': draggingItem === item.id }
          ]"
          draggable="true"
          @dragstart="onDragStart($event, item)"
          @dragend="onDragEnd"
          :title="`${item.fullLabel}\n${item.description}`"
        >
          <component
            :is="item.iconComponent"
            class="component-item__icon"
            :size="18"
            :stroke-width="1.5"
          />
          <span class="component-item__label">{{ item.shortLabel }}</span>
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.component-sidebar {
  position: relative;
  width: clamp(88px, 6.5rem, 128px);
  min-width: clamp(88px, 6.5rem, 128px);
  flex-shrink: 0;
  background: var(--color-bg-secondary);
  border-left: 1px solid var(--glass-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Scroll indicator — gradient fade at bottom when content overflows */
.component-sidebar::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 24px;
  background: linear-gradient(to bottom, transparent, var(--color-bg-secondary));
  pointer-events: none;
  z-index: var(--z-dropdown);
}

.component-sidebar__content {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 0.5rem;
  gap: 0.5rem;
  overflow-y: auto;
}

.component-sidebar__header {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.125rem;
  padding-bottom: 0.375rem;
  border-bottom: 1px solid var(--glass-border);
}

.component-sidebar__title {
  font-size: 0.65rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-secondary);
}

.component-sidebar__hint {
  font-size: 0.55rem;
  color: var(--color-text-muted);
  opacity: 0.7;
}

.component-sidebar__items {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
  overflow-y: auto;
}

/* Component Item */
.component-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0.375rem 0.25rem;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: grab;
  transition: all 0.15s ease;
  user-select: none;
}

.component-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

/* Sensor-spezifische Farben */
.component-item--sensor:hover {
  background: rgba(167, 139, 250, 0.12);
  border-color: var(--color-iridescent-1);
}

.component-item--sensor .component-item__icon {
  color: var(--color-iridescent-1);
}

.component-item--sensor:hover .component-item__icon {
  color: var(--color-iridescent-2);
}

/* Aktor-spezifische Farben */
.component-item--actuator:hover {
  background: rgba(59, 130, 246, 0.12);
  border-color: var(--color-accent-blue);
}

.component-item--actuator .component-item__icon {
  color: var(--color-accent-blue);
}

.component-item--actuator:hover .component-item__icon {
  color: var(--color-accent-cyan);
}

/* Dragging State */
.component-item:active,
.component-item--dragging {
  cursor: grabbing;
  opacity: 0.7;
}

.component-item--sensor.component-item--dragging {
  border-color: var(--color-iridescent-2);
  box-shadow: 0 0 12px rgba(167, 139, 250, 0.4);
}

.component-item--actuator.component-item--dragging {
  border-color: var(--color-accent-cyan);
  box-shadow: 0 0 12px rgba(59, 130, 246, 0.4);
}

.component-item__icon {
  transition: color 0.15s ease;
}

.component-item__label {
  font-size: 0.55rem;
  font-weight: 500;
  color: var(--color-text-muted);
  text-align: center;
  margin-top: 0.125rem;
  line-height: 1.2;
}

/* Scrollbar Styling */
.component-sidebar__items::-webkit-scrollbar {
  width: 3px;
}

.component-sidebar__items::-webkit-scrollbar-track {
  background: transparent;
}

.component-sidebar__items::-webkit-scrollbar-thumb {
  background: var(--glass-border);
  border-radius: var(--radius-xs);
}

.component-sidebar__items::-webkit-scrollbar-thumb:hover {
  background: var(--color-iridescent-1);
}

/* === Orbital Mode: Horizontal Top-Drawer (S7) === */
.component-sidebar--orbital {
  position: fixed;
  top: 1rem;
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-modal);
  width: auto;
  min-width: 0;
  max-width: calc(100vw - 2rem);
  border-left: none;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-floating);
  backdrop-filter: blur(var(--glass-blur-l2));
  overflow: hidden;
  flex-shrink: initial;
}

.component-sidebar--orbital::after {
  display: none;
}

.component-sidebar--orbital .component-sidebar__content {
  flex-direction: row;
  align-items: center;
  height: auto;
  padding: 0.375rem 0.5rem;
  gap: 0.375rem;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}

.component-sidebar--orbital .component-sidebar__content::-webkit-scrollbar {
  display: none;
}

.component-sidebar--orbital .component-sidebar__header {
  flex-direction: column;
  align-items: center;
  padding-bottom: 0;
  padding-right: 0.5rem;
  border-bottom: none;
  border-right: 1px solid var(--glass-border);
  margin-right: 0.125rem;
  gap: 0;
}

.component-sidebar--orbital .component-sidebar__items {
  flex-direction: row;
  gap: 0.25rem;
  flex: 0 0 auto;
  overflow-y: visible;
  scrollbar-width: none;
}

.component-sidebar--orbital .component-item {
  min-width: 52px;
  flex-shrink: 0;
  padding: 0.375rem 0.5rem;
}
</style>
