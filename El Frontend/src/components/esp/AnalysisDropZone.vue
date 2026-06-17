<script setup lang="ts">
/**
 * AnalysisDropZone Component
 *
 * Drop target for sensor satellites to create Multi-Sensor Charts.
 * Accepts dragged sensors and displays them in a combined chart.
 *
 * Features:
 * - Drop zone with visual feedback
 * - Multiple sensor selection
 * - Time range selector (1h, 6h, 24h, 7d, 30d)
 * - Remove sensors from chart
 * - Integrates with MultiSensorChart component
 *
 * Phase 4: Charts & Drag-Drop
 */

import { ref, computed } from 'vue'
import { X, ChartLine, Plus } from 'lucide-vue-next'
import MultiSensorChart from '@/components/charts/MultiSensorChart.vue'
import type { ChartSensor } from '@/types'
import { createLogger } from '@/utils/logger'
import { tokens } from '@/utils/cssTokens'

const log = createLogger('AnalysisDropZone')

interface Props {
  /** Title for the drop zone */
  title?: string
  /** Maximum sensors allowed */
  maxSensors?: number
  /** ESP ID to filter sensors (optional) */
  espId?: string
  /** Compact mode for embedded display */
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Sensor-Analyse',
  maxSensors: 5,
  espId: '',
  compact: false,
})

const emit = defineEmits<{
  sensorAdded: [sensor: ChartSensor]
  sensorRemoved: [sensorId: string]
  sensorsCleared: []
}>()

// State
const isDragOver = ref(false)
const selectedSensors = ref<ChartSensor[]>([])
const timeRange = ref<'1h' | '6h' | '24h' | '7d' | '30d'>('24h')

// Chart colors palette
const chartColors = [
  tokens.mock,
  tokens.success,
  tokens.accentBright,
  tokens.real,
  tokens.warning,
]

// Time range options
const timeRangeOptions = [
  { value: '1h', label: '1h' },
  { value: '6h', label: '6h' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
  { value: '30d', label: '30d' },
] as const

// Computed
const hasReachedMax = computed(() => selectedSensors.value.length >= props.maxSensors)
const isEmpty = computed(() => selectedSensors.value.length === 0)
// Safely get className as string (handles SVG elements where className is SVGAnimatedString)
function getClassName(element: Element | null): string {
  if (!element) return ''
  const cn = element.className
  if (typeof cn === 'string') return cn.slice(0, 50)
  // SVG elements have SVGAnimatedString with baseVal property
  if (cn && typeof cn === 'object' && 'baseVal' in cn) {
    return ((cn as SVGAnimatedString).baseVal || '').slice(0, 50)
  }
  return ''
}

// Get next available color
function getNextColor(): string {
  const usedColors = selectedSensors.value.map((s) => s.color)
  return chartColors.find((c) => !usedColors.includes(c)) || chartColors[0]
}

// Drag handlers - auf Root-Element für zuverlässiges Drop-Target
function handleDragEnter(event: DragEvent) {
  // KRITISCH: stopPropagation verhindert dass Parent-Handler (ESPOrbitalLayout) interferieren
  event.stopPropagation()
  event.preventDefault()

  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  log.debug('dragenter', {
    hasReachedMax: hasReachedMax.value,
    targetTag: (event.target as Element)?.tagName,
    targetClass: getClassName(event.target as Element),
    relatedTarget: (event.relatedTarget as Element)?.tagName,
    rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height },
    clientXY: { x: event.clientX, y: event.clientY }
  })

  if (!hasReachedMax.value) {
    isDragOver.value = true
    log.debug('isDragOver = true ✓')
  }
}

function handleDragOver(event: DragEvent) {
  // KRITISCH: stopPropagation + preventDefault BEIDE nötig für korrekten Drop!
  event.stopPropagation()
  event.preventDefault()

  if (hasReachedMax.value) {
    log.debug('dragover - BLOCKED (max reached)')
    event.dataTransfer!.dropEffect = 'none'
    return
  }

  event.dataTransfer!.dropEffect = 'copy'
  isDragOver.value = true

  // Nur alle 500ms loggen um Console nicht zu fluten
  const now = Date.now()
  if (!handleDragOver._lastLog || now - handleDragOver._lastLog > 500) {
    log.debug('dragover ✓', {
      dropEffect: event.dataTransfer!.dropEffect,
      clientXY: { x: event.clientX, y: event.clientY }
    })
    handleDragOver._lastLog = now
  }
}
// Timestamp für Throttling
handleDragOver._lastLog = 0

function handleDragLeave(event: DragEvent) {
  // KRITISCH: stopPropagation für konsistentes Event-Handling
  event.stopPropagation()

  // Nur zurücksetzen wenn wir das Root-Element verlassen, nicht bei Child-Elementen
  const target = event.currentTarget as HTMLElement
  const related = event.relatedTarget as HTMLElement | null

  log.debug('dragleave RAW', {
    targetTag: (event.target as Element)?.tagName,
    relatedTargetTag: related?.tagName,
    relatedTargetClass: getClassName(related),
    containsRelated: related ? target.contains(related) : 'null'
  })

  if (!related || !target.contains(related)) {
    isDragOver.value = false
    log.debug('dragleave - isDragOver = false (left element)')
  } else {
    log.debug('dragleave - IGNORED (moved to child element)')
  }
}

function handleDrop(event: DragEvent) {
  // KRITISCH: stopPropagation verhindert dass ESPOrbitalLayout das Event abfängt
  event.stopPropagation()
  event.preventDefault()

  log.debug('DROP EVENT FIRED! 🎯', {
    hasData: !!event.dataTransfer?.getData('application/json'),
    types: event.dataTransfer?.types,
    clientXY: { x: event.clientX, y: event.clientY }
  })

  isDragOver.value = false

  if (hasReachedMax.value) {
    log.debug('DROP REJECTED - max sensors reached')
    return
  }

  const data = event.dataTransfer?.getData('application/json')
  if (!data) {
    log.debug('DROP REJECTED - no JSON data in dataTransfer')
    return
  }

  try {
    const dragData = JSON.parse(data)
    log.debug('Parsed drag data', dragData)

    // ISSUE-002 fix: Vollständige Validierung der drag data
    // Prüfe alle erforderlichen Felder bevor sie verwendet werden
    if (
      dragData.type !== 'sensor' ||
      typeof dragData.espId !== 'string' || !dragData.espId ||
      typeof dragData.gpio !== 'number' || isNaN(dragData.gpio) ||
      typeof dragData.sensorType !== 'string' || !dragData.sensorType
    ) {
      log.debug('DROP REJECTED - invalid drag data', {
        type: dragData.type,
        espId: dragData.espId,
        gpio: dragData.gpio,
        sensorType: dragData.sensorType,
      })
      return
    }

    // Check if sensor already exists (include sensorType for multi-value sensors like SHT31)
    const sensorId = `${dragData.espId}_${dragData.gpio}_${dragData.sensorType}`
    if (selectedSensors.value.some((s) => s.id === sensorId)) {
      log.debug('DROP REJECTED - sensor already in chart', { sensorId })
      return
    }

    // Add sensor to chart with validated data and defaults for optional fields
    const newSensor: ChartSensor = {
      id: sensorId,
      espId: dragData.espId,
      gpio: dragData.gpio,
      sensorType: dragData.sensorType,
      name: dragData.name || `Sensor GPIO ${dragData.gpio}`,
      unit: dragData.unit || '',
      color: getNextColor(),
    }
    selectedSensors.value.push(newSensor)
    emit('sensorAdded', newSensor)
    log.debug('✅ SENSOR ADDED TO CHART', { newSensor, totalSensors: selectedSensors.value.length })
  } catch (error) {
    log.debug('DROP ERROR - failed to parse', { error })
  }
}

// Remove sensor from chart
function removeSensor(sensorId: string) {
  selectedSensors.value = selectedSensors.value.filter((s) => s.id !== sensorId)
  emit('sensorRemoved', sensorId)
}

// Clear all sensors
function clearAll() {
  selectedSensors.value = []
  emit('sensorsCleared')
}
</script>

<template>
  <div
    :class="[
      'analysis-drop-zone',
      {
        'analysis-drop-zone--compact': compact,
        'analysis-drop-zone--drag-over': isDragOver
      }
    ]"
    data-no-drag="true"
    @dragover="handleDragOver"
    @dragenter="handleDragEnter"
    @dragleave="handleDragLeave"
    @drop="handleDrop"
  >
    <!-- Header (hidden in compact mode when empty) -->
    <div v-if="!compact || !isEmpty" class="analysis-drop-zone__header">
      <div class="analysis-drop-zone__title">
        <ChartLine :class="compact ? 'w-4 h-4' : 'w-5 h-5'" />
        <span>{{ title }}</span>
      </div>

      <!-- Time Range Selector -->
      <div v-if="!isEmpty" class="analysis-drop-zone__controls">
        <div class="analysis-drop-zone__time-range">
          <button
            v-for="option in timeRangeOptions"
            :key="option.value"
            :class="[
              'analysis-drop-zone__time-btn',
              { 'analysis-drop-zone__time-btn--active': timeRange === option.value },
            ]"
            @click="timeRange = option.value"
          >
            {{ option.label }}
          </button>
        </div>

      </div>
    </div>

    <!-- Drop Zone (when empty) - Events sind auf Root-Element -->
    <div
      v-if="isEmpty"
      :class="[
        'analysis-drop-zone__empty',
        { 'analysis-drop-zone__empty--drag-over': isDragOver },
        { 'analysis-drop-zone__empty--compact': compact },
      ]"
    >
      <Plus :class="compact ? 'w-5 h-5' : 'w-8 h-8'" />
      <p>{{ compact ? 'Sensoren hierher ziehen' : 'Sensoren hierher ziehen' }}</p>
      <p v-if="!compact" class="text-sm text-muted">Max. {{ maxSensors }} Sensoren</p>
    </div>

    <!-- Chart Content -->
    <template v-else>
      <!-- Sensor Legend -->
      <div class="analysis-drop-zone__legend">
        <div
          v-for="sensor in selectedSensors"
          :key="sensor.id"
          class="analysis-drop-zone__legend-item"
        >
          <span
            class="analysis-drop-zone__legend-color"
            :style="{ backgroundColor: sensor.color }"
          />
          <span class="analysis-drop-zone__legend-name">{{ sensor.name }}</span>
          <span class="analysis-drop-zone__legend-unit">({{ sensor.unit }})</span>
          <button
            class="analysis-drop-zone__legend-remove"
            @click="removeSensor(sensor.id)"
            title="Entfernen"
          >
            <X class="w-3 h-3" />
          </button>
        </div>

        <!-- Add more indicator - NUR während Drag sichtbar -->
        <div
          v-if="!hasReachedMax && isDragOver"
          class="analysis-drop-zone__add-more analysis-drop-zone__add-more--drag-over"
        >
          <Plus class="w-4 h-4" />
        </div>
      </div>

      <!-- Chart -->
      <MultiSensorChart
        :sensors="selectedSensors"
        :time-range="timeRange"
        :height="compact ? 160 : 300"
      />

      <!-- Actions -->
      <div class="analysis-drop-zone__actions">
        <button class="analysis-drop-zone__clear-btn" @click="clearAll">
          Alle entfernen
        </button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.analysis-drop-zone {
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
  /* Drop zone, not drag source - default cursor indicates this isn't draggable */
  cursor: default;
}

/* Visuelles Feedback auf Root-Element beim Drag-Over */
.analysis-drop-zone--drag-over {
  border-color: var(--color-success);
  box-shadow: 0 0 12px rgba(16, 185, 129, 0.3),
              inset 0 0 20px rgba(16, 185, 129, 0.05);
  background: rgba(16, 185, 129, 0.05);
}

.analysis-drop-zone__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.analysis-drop-zone__title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.analysis-drop-zone__controls {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.analysis-drop-zone__time-range {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  color: var(--color-text-muted);
}

.analysis-drop-zone__time-btn {
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-xs);
  font-size: 0.75rem;
  font-weight: 500;
  background: transparent;
  border: 1px solid transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.analysis-drop-zone__time-btn:hover {
  background: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.analysis-drop-zone__time-btn--active {
  background: var(--color-iridescent-1);
  color: white;
  border-color: var(--color-iridescent-1);
}

.analysis-drop-zone__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  padding: 3rem 2rem;
  border: 2px dashed var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.analysis-drop-zone__empty--drag-over {
  border-color: var(--color-success);
  border-style: solid;
  background: rgba(16, 185, 129, 0.15);
  color: var(--color-success);
  transform: scale(1.02);
  box-shadow: 0 0 20px rgba(16, 185, 129, 0.2),
              inset 0 0 30px rgba(16, 185, 129, 0.05);
}

.analysis-drop-zone__empty--drag-over svg {
  animation: pulse-scale 1s ease-in-out infinite;
}

@keyframes pulse-scale {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.15); }
}

.analysis-drop-zone__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
  position: relative;
  z-index: var(--z-dropdown);
}

.analysis-drop-zone__legend-item {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.25rem 0.5rem;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
}

.analysis-drop-zone__legend-color {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 50%;
  flex-shrink: 0;
}

.analysis-drop-zone__legend-name {
  color: var(--color-text-primary);
  font-weight: 500;
}

.analysis-drop-zone__legend-unit {
  color: var(--color-text-muted);
}

.analysis-drop-zone__legend-remove {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0.125rem;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.analysis-drop-zone__legend-remove:hover {
  background: rgba(248, 113, 113, 0.2);
  color: var(--color-error);
}

.analysis-drop-zone__add-more {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border: 2px dashed var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.analysis-drop-zone__add-more:hover,
.analysis-drop-zone__add-more--drag-over {
  border-color: var(--color-iridescent-1);
  color: var(--color-iridescent-1);
  background: rgba(167, 139, 250, 0.1);
}

.analysis-drop-zone__actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.25rem;
  padding-top: 0.5rem;
  border-top: 1px solid var(--glass-border);
}

.analysis-drop-zone__clear-btn {
  min-height: 2rem;
  padding: 0.375rem 0.875rem;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--glass-border);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all 0.15s;
}

.analysis-drop-zone__clear-btn:hover {
  border-color: var(--color-error);
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.1);
}

.text-muted {
  color: var(--color-text-muted);
}

/* =============================================================================
   Compact Mode Styles (for ESP Card embedded view)
   Optimized for narrow center column in horizontal ESP layout
   ============================================================================= */
.analysis-drop-zone--compact {
  padding: 0.625rem;
  gap: 0.625rem;
  border-radius: var(--radius-md);
}

.analysis-drop-zone--compact .analysis-drop-zone__header {
  gap: 0.5rem;
  min-height: 1.75rem;
}

.analysis-drop-zone--compact .analysis-drop-zone__title {
  font-size: 0.8rem;
  gap: 0.375rem;
}

.analysis-drop-zone--compact .analysis-drop-zone__controls {
  gap: 0.375rem;
  flex-wrap: wrap;
  width: 100%;
  justify-content: space-between;
  padding-top: 0.25rem;
  padding-bottom: 0;
  margin-bottom: 0;
}

.analysis-drop-zone--compact .analysis-drop-zone__time-range {
  gap: 0.125rem;
}

.analysis-drop-zone--compact .analysis-drop-zone__time-btn {
  padding: 0.1875rem 0.375rem;
  font-size: 0.6875rem;
  min-width: 1.5rem;
}

.analysis-drop-zone__empty--compact {
  padding: 1.25rem 0.75rem;
  gap: 0.375rem;
  font-size: 0.75rem;
}

/* Legend - horizontal wrap with better spacing */
.analysis-drop-zone--compact .analysis-drop-zone__legend {
  gap: 0.375rem;
  flex-wrap: wrap;
  padding: 0;
  margin-top: 0.125rem;
}

.analysis-drop-zone--compact .analysis-drop-zone__legend-item {
  padding: 0.3125rem 0.5rem;
  font-size: 0.6875rem;
  border-radius: var(--radius-sm);
  gap: 0.25rem;
}

.analysis-drop-zone--compact .analysis-drop-zone__legend-color {
  width: 0.625rem;
  height: 0.625rem;
}

.analysis-drop-zone--compact .analysis-drop-zone__legend-name {
  max-width: 5rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.analysis-drop-zone--compact .analysis-drop-zone__legend-unit {
  font-size: 0.625rem;
}

.analysis-drop-zone--compact .analysis-drop-zone__legend-remove {
  margin-left: 0.125rem;
}

/* Actions - compact clear button */
.analysis-drop-zone--compact .analysis-drop-zone__actions {
  margin-top: 0.25rem;
  padding-top: 0.375rem;
  border-top: none;
  justify-content: stretch;
}

.analysis-drop-zone--compact .analysis-drop-zone__clear-btn {
  width: 100%;
  min-height: 2.125rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.6875rem;
  border-radius: var(--radius-md);
  text-align: center;
}

/* Add-more indicator during drag */
.analysis-drop-zone--compact .analysis-drop-zone__add-more {
  width: 1.625rem;
  height: 1.625rem;
  border-width: 1.5px;
}
</style>
