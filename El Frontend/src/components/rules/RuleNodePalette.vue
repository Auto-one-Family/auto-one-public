<script setup lang="ts">
/**
 * RuleNodePalette
 *
 * Left sidebar for the rules editor with draggable node types.
 * Grouped into: Conditions (sensors, time), Logic (AND/OR), Actions (actuator, notification, delay).
 * Drag items onto the canvas to create nodes.
 */

import { ref } from 'vue'
import {
  Thermometer,
  Clock,
  GitMerge,
  Power,
  Bell,
  Timer,
  ChevronDown,
  Search,
  Droplets,
  Gauge,
  Sun,
  Wind,
  Waves,
  Leaf,
  Zap,
  Puzzle,
  Stethoscope,
  Snowflake,
  Flame,
  ArrowLeftRight,
  Cpu,
  ListOrdered,
  ShieldOff,
} from 'lucide-vue-next'
import type { Component } from 'vue'

export interface PaletteItem {
  type: string
  label: string
  description: string
  icon: Component
  category: 'condition' | 'logic' | 'action' | 'template'
  defaults?: Record<string, unknown>
  /** AUT-248: True for hysteresis-based blocks that run directly on the ESP. */
  offlineCapable?: boolean
}

const searchQuery = ref('')

const categories = [
  {
    id: 'sensor',
    label: 'Reagiere auf einen Messwert',
    collapsed: ref(false),
    items: [
      {
        type: 'sensor',
        label: 'Feuchtigkeit',
        description: 'Luftfeuchtigkeit Bedingung',
        icon: Droplets,
        category: 'condition' as const,
        defaults: { sensorType: 'SHT31', operator: '<', value: 40, conditionCategory: 'humidity' },
      },
      {
        type: 'sensor',
        label: 'pH-Wert',
        description: 'pH-Sensor Bedingung',
        icon: Gauge,
        category: 'condition' as const,
        defaults: { sensorType: 'pH', operator: 'between', value: 6, min: 5.5, max: 7.0, conditionCategory: 'ph' },
      },
      {
        type: 'sensor',
        label: 'EC-Wert',
        description: 'Leitfähigkeit Bedingung',
        icon: Zap,
        category: 'condition' as const,
        defaults: { sensorType: 'EC', operator: 'between', value: 1.2, min: 0.8, max: 2.0, conditionCategory: 'ec' },
      },
      {
        type: 'sensor',
        label: 'CO2',
        description: 'CO2-Konzentration Bedingung',
        icon: Wind,
        category: 'condition' as const,
        defaults: { sensorType: 'co2', operator: '>', value: 1000, conditionCategory: 'co2' },
      },
      {
        type: 'sensor',
        label: 'Licht',
        description: 'Lichtsensor Bedingung',
        icon: Sun,
        category: 'condition' as const,
        defaults: { sensorType: 'light', operator: '<', value: 500, conditionCategory: 'light' },
      },
      {
        type: 'sensor',
        label: 'Bodenfeuchte',
        description: 'Bodenfeuchtigkeit Bedingung',
        icon: Waves,
        category: 'condition' as const,
        defaults: { sensorType: 'moisture', operator: '<', value: 30, conditionCategory: 'moisture' },
      },
      {
        type: 'sensor',
        label: 'Füllstand',
        description: 'Tank-/Behälter-Füllstand',
        icon: Leaf,
        category: 'condition' as const,
        defaults: { sensorType: 'level', operator: '<', value: 20, conditionCategory: 'level' },
      },
      {
        // AUT-1399: umgewidmet — einziger Mess-Bindungs-Baustein (kein zweiter Palette-Eintrag)
        type: 'sensor_diff',
        label: 'Mess-Bindung',
        description: 'Misst während die Regel läuft (kein Auslöser)',
        icon: ArrowLeftRight,
        category: 'condition' as const,
        defaults: {
          label: '',
          formulaId: 'difference',
          sensorEspId: '',
          sensorGpio: null,
          sensorType: '',
          sensorBEspId: '',
          sensorBGpio: null,
          sensorBType: '',
          hooks: ['on_start', 'on_complete'],
          outputTarget: 'execution_metadata',
          formulaParams: {},
        },
      },
    ],
  },
  {
    id: 'time',
    label: 'Reagiere zu einer Uhrzeit',
    collapsed: ref(false),
    items: [
      {
        type: 'time',
        label: 'Zeitfenster',
        description: 'Tageszeitbasierte Bedingung',
        icon: Clock,
        category: 'condition' as const,
        defaults: { startHour: 8, startMinute: 0, endHour: 18, endMinute: 0 },
      },
    ],
  },
  {
    id: 'template',
    label: 'Halte einen Bereich stabil',
    collapsed: ref(false),
    items: [
      {
        type: 'sensor',
        label: 'Kühlung (Hysterese)',
        description: 'Lüfter/Kühlung: Ein über Schwellwert, Aus unter Schwellwert',
        icon: Snowflake,
        category: 'template' as const,
        offlineCapable: true,
        defaults: {
          sensorType: 'sht31_temp',
          operator: 'hysteresis',
          isHysteresis: true,
          activateAbove: 28,
          deactivateBelow: 24,
          conditionCategory: 'temperature',
        },
      },
      {
        type: 'sensor',
        label: 'Befeuchtung (Hysterese)',
        description: 'Befeuchter: Ein unter Schwellwert, Aus über Schwellwert',
        icon: Flame,
        category: 'template' as const,
        offlineCapable: true,
        defaults: {
          sensorType: 'sht31_humidity',
          operator: 'hysteresis',
          isHysteresis: true,
          activateBelow: 45,
          deactivateAbove: 55,
          conditionCategory: 'humidity',
        },
      },
    ],
  },
  {
    id: 'advanced',
    label: 'Erweitert',
    collapsed: ref(true),
    items: [
      {
        type: 'logic',
        label: 'UND',
        description: 'Alle Bedingungen müssen zutreffen',
        icon: GitMerge,
        category: 'logic' as const,
        defaults: { operator: 'AND' },
      },
      {
        type: 'logic',
        label: 'ODER',
        description: 'Mindestens eine Bedingung muss zutreffen',
        icon: GitMerge,
        category: 'logic' as const,
        defaults: { operator: 'OR' },
      },
      {
        type: 'sensor',
        label: 'Sensor (Erweitert)',
        description: 'Beliebiger Sensor-Schwellwert — für Fortgeschrittene',
        icon: Thermometer,
        category: 'condition' as const,
        defaults: { sensorType: 'DS18B20', operator: '>', value: 25 },
      },
      {
        type: 'diagnostics_status',
        label: 'Diagnose-Status',
        description: 'Bedingung basierend auf System-Diagnose',
        icon: Stethoscope,
        category: 'condition' as const,
        defaults: { checkName: 'mqtt', expectedStatus: 'critical', operator: '==' },
      },
      {
        type: 'not_running',
        label: 'Nicht laufend (Interlock)',
        description: 'AND: nur feuern wenn Peer-Aktor/Sequenz idle ist',
        icon: ShieldOff,
        category: 'condition' as const,
        defaults: { target: 'actuator', espId: '', gpio: null, ruleId: '' },
      },
    ],
  },
  {
    id: 'action',
    label: 'Aktionen',
    collapsed: ref(false),
    items: [
      {
        type: 'actuator',
        label: 'Aktor steuern',
        description: 'Aktor ein-/ausschalten oder PWM setzen',
        icon: Power,
        category: 'action' as const,
        defaults: { command: 'ON' },
      },
      {
        type: 'notification',
        label: 'Benachrichtigung',
        description: 'Email, Webhook oder WebSocket Nachricht',
        icon: Bell,
        category: 'action' as const,
        defaults: { channel: 'websocket', target: '', messageTemplate: '' },
      },
      {
        type: 'delay',
        label: 'Verzögerung',
        description: 'Aktion nach Wartezeit ausführen',
        icon: Timer,
        category: 'action' as const,
        defaults: { seconds: 60 },
      },
      {
        type: 'plugin',
        label: 'Plugin ausführen',
        description: 'AutoOps-Plugin als Aktion triggern',
        icon: Puzzle,
        category: 'action' as const,
        defaults: { pluginId: '', config: {} },
      },
      {
        type: 'run_diagnostic',
        label: 'Diagnose starten',
        description: 'System-Diagnose als Aktion auslösen',
        icon: Stethoscope,
        category: 'action' as const,
        defaults: { checkName: '' },
      },
      {
        type: 'sequence',
        label: 'Sequenz',
        description: 'Mehrere Aktionen nacheinander ausführen (Aktor, Verzögerung)',
        icon: ListOrdered,
        category: 'action' as const,
        defaults: { steps: [] },
      },
    ],
  },
]

function onDragStart(event: DragEvent, item: PaletteItem) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData(
    'application/rulenode',
    JSON.stringify({
      type: item.type,
      label: item.label,
      defaults: item.defaults || {},
    })
  )
  event.dataTransfer.effectAllowed = 'move'
}

function matchesSearch(item: PaletteItem): boolean {
  if (!searchQuery.value) return true
  const q = searchQuery.value.toLowerCase()
  return (
    item.label.toLowerCase().includes(q) ||
    item.description.toLowerCase().includes(q) ||
    item.type.toLowerCase().includes(q)
  )
}
</script>

<template>
  <div class="palette">
    <div class="palette__header">
      <h3 class="palette__title">Bausteine</h3>
    </div>

    <!-- Search -->
    <div class="palette__search">
      <Search class="palette__search-icon" />
      <input
        v-model="searchQuery"
        type="text"
        placeholder="Suchen..."
        class="palette__search-input"
      />
    </div>

    <!-- Categories -->
    <div class="palette__categories">
      <div
        v-for="category in categories"
        :key="category.id"
        class="palette__category"
      >
        <button
          class="palette__category-header"
          :class="{ 'palette__category-header--esp': category.id === 'template' }"
          @click="category.collapsed.value = !category.collapsed.value"
        >
          <span class="palette__category-label">
            <Cpu
              v-if="category.id === 'template'"
              class="palette__category-icon"
              aria-hidden="true"
            />
            {{ category.label }}
          </span>
          <ChevronDown
            class="palette__category-chevron"
            :class="{ 'palette__category-chevron--collapsed': category.collapsed.value }"
          />
        </button>

        <Transition name="palette-collapse">
          <div v-show="!category.collapsed.value" class="palette__items">
            <template v-for="item in category.items" :key="item.label">
              <div
                v-if="matchesSearch(item)"
                class="palette__item"
                :class="[
                  `palette__item--${item.category}`,
                  { 'palette__item--offline-capable': (item as PaletteItem).offlineCapable },
                ]"
                draggable="true"
                :title="(item as PaletteItem).offlineCapable
                  ? 'Offline-fähig: Diese Bedingung wird direkt auf dem ESP-Chip ausgewertet — funktioniert auch wenn der Server nicht erreichbar ist. Limit: 20 solcher Regeln pro ESP.'
                  : item.description"
                @dragstart="onDragStart($event, item)"
              >
                <div class="palette__item-icon">
                  <component :is="item.icon" class="w-4 h-4" />
                </div>
                <div class="palette__item-text">
                  <span class="palette__item-label">
                    {{ item.label }}
                    <span
                      v-if="(item as PaletteItem).offlineCapable"
                      class="palette__item-badge"
                      aria-label="Offline-fähig auf ESP"
                    >
                      <Cpu class="palette__item-badge-icon" aria-hidden="true" />
                      ESP
                    </span>
                  </span>
                  <span class="palette__item-desc">{{ item.description }}</span>
                </div>
              </div>
            </template>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Hint -->
    <div class="palette__hint">
      Bausteine auf die Arbeitsfläche ziehen
    </div>
  </div>
</template>

<style scoped>
.palette {
  width: 248px;
  min-width: 248px;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--glass-border);
  overflow: hidden;
}

.palette__header {
  padding: 0.875rem 1rem 0.625rem;
}

.palette__title {
  font-size: 0.6875rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--color-text-muted);
}

.palette__search {
  position: relative;
  padding: 0 0.75rem 0.75rem;
}

.palette__search-icon {
  position: absolute;
  left: 1.25rem;
  top: 50%;
  transform: translateY(-50%);
  width: 13px;
  height: 13px;
  color: var(--color-text-muted);
  pointer-events: none;
}

.palette__search-input {
  width: 100%;
  padding: 0.4375rem 0.5rem 0.4375rem 2rem;
  font-size: var(--text-sm);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  outline: none;
  transition: all var(--transition-fast);
}

.palette__search-input::placeholder {
  color: var(--color-text-muted);
}

.palette__search-input:focus {
  border-color: rgba(129, 140, 248, 0.4);
  box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.08);
}

.palette__categories {
  flex: 1;
  overflow-y: auto;
  padding: 0 0.5rem;
}

.palette__category {
  margin-bottom: 0.125rem;
}

.palette__category-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 0.4375rem 0.5rem;
  font-size: 0.625rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--color-text-muted);
  background: none;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.palette__category-header:hover {
  color: var(--color-text-secondary);
}

.palette__category-chevron {
  width: 12px;
  height: 12px;
  transition: transform var(--transition-base);
}

.palette__category-chevron--collapsed {
  transform: rotate(-90deg);
}

.palette__items {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding-bottom: 0.5rem;
  min-height: 0;
}

.palette__item {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  padding: 0.5rem;
  border-radius: var(--radius-md);
  cursor: grab;
  transition: all var(--transition-fast);
  border: 1px solid transparent;
  user-select: none;
  position: relative;
}

.palette__item:hover {
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border);
}

.palette__item:active {
  cursor: grabbing;
  opacity: 0.8;
  transform: scale(0.97);
  border-color: var(--color-iridescent-2);
  background: rgba(129, 140, 248, 0.05);
}

.palette__item-icon {
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.palette__item:hover .palette__item-icon {
  transform: scale(1.05);
}

/* Category-specific icon colors */
.palette__item--condition .palette__item-icon {
  background: rgba(96, 165, 250, 0.1);
  color: var(--color-iridescent-1);
}

.palette__item--condition:hover .palette__item-icon {
  background: rgba(96, 165, 250, 0.18);
}

.palette__item--logic .palette__item-icon {
  background: rgba(167, 139, 250, 0.1);
  color: var(--color-iridescent-3);
}

.palette__item--logic:hover .palette__item-icon {
  background: rgba(167, 139, 250, 0.18);
}

.palette__item--action .palette__item-icon {
  background: rgba(192, 132, 252, 0.1);
  color: var(--color-iridescent-4);
}

.palette__item--action:hover .palette__item-icon {
  background: rgba(192, 132, 252, 0.18);
}

.palette__item--template .palette__item-icon {
  background: rgba(251, 191, 36, 0.1);
  color: var(--color-warning);
}

.palette__item--template:hover .palette__item-icon {
  background: rgba(251, 191, 36, 0.18);
}

.palette__item--template {
  border-left: 2px solid rgba(251, 191, 36, 0.3);
}

.palette__item-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 1px;
}

.palette__item-label {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.palette__item-desc {
  font-size: 0.625rem;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.palette__hint {
  padding: 0.625rem 1rem;
  font-size: 0.625rem;
  color: var(--color-text-muted);
  text-align: center;
  border-top: 1px solid var(--glass-border);
  letter-spacing: 0.02em;
  line-height: 1.4;
}

/* Collapse transition using grid-template-rows for smooth animation */
.palette-collapse-enter-active,
.palette-collapse-leave-active {
  display: grid;
  grid-template-rows: 1fr;
  transition: grid-template-rows var(--duration-base) var(--ease-out),
              opacity var(--duration-base) var(--ease-out);
}

.palette-collapse-enter-from,
.palette-collapse-leave-to {
  grid-template-rows: 0fr;
  opacity: 0;
}

.palette-collapse-enter-active > *,
.palette-collapse-leave-active > * {
  overflow: hidden;
  min-height: 0;
}

/* Focus-visible for palette items */
.palette__item:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: -1px;
}

.palette__category-header:focus-visible {
  outline: 2px solid var(--color-iridescent-2);
  outline-offset: 1px;
}

.palette__search-input:focus-visible {
  outline: none;
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .palette__item:active {
    transform: none;
  }

  .palette__item:hover .palette__item-icon {
    transform: none;
  }

  .palette-collapse-enter-active,
  .palette-collapse-leave-active {
    transition-duration: 0.01ms;
  }
}

/* ======================== AUT-248: OFFLINE-CAPABLE MARKERS ======================== */

.palette__category-header--esp .palette__category-label {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--color-status-good);
}

.palette__category-icon {
  width: 11px;
  height: 11px;
}

/* Hysteresis blocks: orange tint + microchip indicator */
.palette__item--offline-capable {
  background: color-mix(in srgb, var(--color-warning) 8%, transparent);
  border-color: color-mix(in srgb, var(--color-warning) 20%, transparent) !important;
  border-left: 2px solid var(--color-warning) !important;
}

.palette__item--offline-capable:hover {
  background: color-mix(in srgb, var(--color-warning) 14%, transparent);
  border-color: color-mix(in srgb, var(--color-warning) 35%, transparent) !important;
}

.palette__item--offline-capable .palette__item-icon {
  background: color-mix(in srgb, var(--color-warning) 16%, transparent);
  color: var(--color-warning);
}

.palette__item-label {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}

.palette__item-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px 4px;
  font-size: 0.5625rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border-radius: var(--radius-xs);
  background: color-mix(in srgb, var(--color-status-good) 18%, transparent);
  color: var(--color-status-good);
  border: 1px solid color-mix(in srgb, var(--color-status-good) 35%, transparent);
}

.palette__item-badge-icon {
  width: 9px;
  height: 9px;
}
</style>
