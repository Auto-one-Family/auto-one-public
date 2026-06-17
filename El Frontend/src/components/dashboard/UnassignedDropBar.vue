<script setup lang="ts">
/**
 * UnassignedDropBar Component
 *
 * Redesigned: Always-visible bottom tray for unassigned ESP devices.
 * - Shows device cards in a horizontal scrolling row (always visible when devices exist)
 * - Collapses to thin strip only when empty
 * - Drop target for removing devices from zones
 * - Status indicator, sensor count, and hardware badge per device
 */

import { ref, computed, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { VueDraggable } from 'vue-draggable-plus'
import {
  Inbox,
  ChevronUp,
  ChevronDown,
  Loader2,
  ArrowUpRight
} from 'lucide-vue-next'
import { Badge } from '@/shared/design/primitives'
import { useZoneDragDrop } from '@/composables/useZoneDragDrop'
import { useEspStore } from '@/stores/esp'
import { useDragStateStore } from '@/shared/stores/dragState.store'
import { espApi, type ESPDevice } from '@/api/esp'
import { createLogger } from '@/utils/logger'
import { formatRelativeTime } from '@/utils/formatters'
import { groupSensorsByBaseType, type RawSensor } from '@/utils/sensorDefaults'

const log = createLogger('UnassignedDropBar')

const espStore = useEspStore()
const dragStore = useDragStateStore()
const { handleRemoveFromZone, isProcessing, processingDeviceId } = useZoneDragDrop()

// State
const isCollapsed = ref(false)
const isDragOver = ref(false)
const dragOverCount = ref(0)
const localDevices = ref<ESPDevice[]>([])

// Unassigned devices (from store — single source of truth)
const unassignedDevices = computed(() => espStore.unassignedDevices)

// Sync local devices with store
watch(unassignedDevices, (newDevices) => {
  localDevices.value = [...newDevices]
}, { immediate: true, deep: true })

// Device count
const deviceCount = computed(() => unassignedDevices.value.length)

// Check if device is mock
function isMock(device: ESPDevice): boolean {
  const deviceId = device.device_id || device.esp_id || ''
  return espApi.isMockEsp(deviceId)
}

// Get device ID
function getDeviceId(device: ESPDevice): string {
  return device.device_id || device.esp_id || ''
}

// Get status color class
function getStatusClass(device: ESPDevice): string {
  if (device.status === 'online' || device.connected === true) return 'status--online'
  if (device.status === 'offline') return 'status--offline'
  if (device.status === 'error') return 'status--error'
  return 'status--unknown'
}

/** Compact 1-line sensor summary: "22°C  45%" */
function getSensorSummary(device: ESPDevice): string {
  const sensors = (device.sensors as RawSensor[] | undefined) || []
  if (sensors.length === 0) return ''
  const grouped = groupSensorsByBaseType(sensors)
  const parts: string[] = []
  for (const group of grouped) {
    for (const val of group.values) {
      if (val.value === null) continue
      const formatted = Number.isInteger(val.value) ? String(val.value) : val.value.toFixed(1)
      parts.push(`${formatted}${val.unit}`)
      if (parts.length >= 3) break
    }
    if (parts.length >= 3) break
  }
  return parts.join('  ')
}

// Toggle collapsed state
function toggleCollapsed() {
  isCollapsed.value = !isCollapsed.value
}

// Drag & Drop handlers
function handleDragEnter(event: DragEvent) {
  event.preventDefault()
  dragOverCount.value++
  isDragOver.value = true
}

function handleDragLeave(event: DragEvent) {
  event.preventDefault()
  dragOverCount.value--
  if (dragOverCount.value <= 0) {
    dragOverCount.value = 0
    isDragOver.value = false
  }
}

function handleDragOver(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move'
  }
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  dragOverCount.value = 0
  isDragOver.value = false
}

// Handle device added via VueDraggable
async function handleDragAdd(event: any) {
  const device = event?.added?.element as ESPDevice | undefined
  if (!device) {
    // Not an add event (could be a move or remove) — ignore
    return
  }

  const deviceId = getDeviceId(device)
  if (!deviceId) {
    log.warn('handleDragAdd: Device has no ID')
    return
  }

  // Only unassign if device has a zone (was dragged FROM a zone)
  if (device.zone_id) {
    log.debug('Unassigning device from zone', { deviceId, zoneId: device.zone_id })
    await handleRemoveFromZone(device)
  }
}

function handleDragStart() {
  dragStore.startEspCardDrag()
}

function handleDragEnd() {
  dragStore.endEspCardDrag()
}
</script>

<template>
  <div
    :class="[
      'unassigned-tray',
      {
        'unassigned-tray--collapsed': isCollapsed,
        'unassigned-tray--drag-active': dragStore.isAnyDragActive,
        'unassigned-tray--drag-over': isDragOver,
        'unassigned-tray--empty': deviceCount === 0
      }
    ]"
    @dragenter="handleDragEnter"
    @dragleave="handleDragLeave"
    @dragover="handleDragOver"
    @drop="handleDrop"
  >
    <!-- Drag Over Glow -->
    <div v-if="isDragOver" class="unassigned-tray__glow" />

    <!-- Header Strip -->
    <button
      class="unassigned-tray__header"
      @click="toggleCollapsed"
    >
      <div class="unassigned-tray__header-left">
        <Inbox class="unassigned-tray__icon" />
        <span class="unassigned-tray__label">
          {{ isDragOver ? 'Zum Entfernen aus Zone ablegen' : 'Nicht zugewiesen' }}
        </span>
        <span v-if="deviceCount > 0" class="unassigned-tray__count">
          {{ deviceCount }}
        </span>
      </div>
      <component
        :is="isCollapsed ? ChevronUp : ChevronDown"
        class="unassigned-tray__toggle"
      />
    </button>

    <!-- Device Cards Row (visible by default when devices exist) -->
    <Transition name="tray-slide">
      <div
        v-if="!isCollapsed && (deviceCount > 0 || isDragOver)"
        class="unassigned-tray__body"
      >
        <VueDraggable
          v-model="localDevices"
          class="unassigned-tray__cards"
          group="esp-devices"
          :animation="150"
          ghost-class="unassigned-card--ghost"
          :force-fallback="true"
          :fallback-on-body="true"
          :delay-on-touch-only="true"
          :delay="300"
          :fallback-tolerance="5"
          :touch-start-threshold="3"
          @change="handleDragAdd"
          @start="handleDragStart"
          @end="handleDragEnd"
        >
          <!-- Device Card -->
          <div
            v-for="device in localDevices"
            :key="getDeviceId(device)"
            class="unassigned-card"
            :data-device-id="getDeviceId(device)"
          >
            <!-- Status Dot -->
            <span :class="['unassigned-card__status', getStatusClass(device)]" />

            <!-- Device Info -->
            <div class="unassigned-card__info">
              <div class="unassigned-card__row-top">
                <Badge v-if="isMock(device)" variant="mock" size="xs">
                  MOCK
                </Badge>
                <span class="unassigned-card__name">
                  {{ device.name || getDeviceId(device) }}
                </span>
                <Loader2
                  v-if="isProcessing && processingDeviceId === getDeviceId(device)"
                  class="w-3 h-3 animate-spin"
                  style="color: var(--color-iridescent-1)"
                />
              </div>
              <div class="unassigned-card__row-meta">
                <span v-if="device.last_seen" class="unassigned-card__meta-item unassigned-card__meta-item--time">
                  {{ formatRelativeTime(device.last_seen) }}
                </span>
              </div>
              <div v-if="getSensorSummary(device)" class="unassigned-card__row-sensors">
                {{ getSensorSummary(device) }}
              </div>
            </div>

            <!-- Settings Link -->
            <RouterLink
              :to="`/?openSettings=${getDeviceId(device)}`"
              class="unassigned-card__link"
              title="Einstellungen öffnen"
            >
              <ArrowUpRight class="w-3.5 h-3.5" />
            </RouterLink>
          </div>

          <!-- Drop Hint (when empty or dragging) -->
          <div v-if="deviceCount === 0 && isDragOver" class="unassigned-tray__drop-hint">
            <Inbox class="w-5 h-5" />
            <span>Hier ablegen</span>
          </div>
        </VueDraggable>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   UNASSIGNED TRAY — Industrial Bottom Strip
   Token-aligned, drag-aware, auto-hide when empty
   ═══════════════════════════════════════════════════════════════════════════ */

.unassigned-tray {
  position: fixed;
  bottom: 0;
  left: var(--sidebar-width);
  right: 0;
  z-index: var(--z-tray);
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--glass-border);
  transition: all var(--transition-base);
}

/* Global drag active: Expand tray to be a larger drop target */
.unassigned-tray--drag-active {
  padding-top: var(--space-2);
  min-height: 120px;
}

.unassigned-tray--drag-active .unassigned-tray__body {
  padding-top: var(--space-2);
}

.unassigned-tray--drag-over {
  border-top-color: var(--color-warning);
  background: color-mix(in srgb, var(--color-bg-secondary), var(--color-warning) 5%);
}

/* Glow effect on drag */
.unassigned-tray__glow {
  position: absolute;
  top: -2px;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(
    90deg,
    transparent,
    var(--color-warning),
    var(--color-iridescent-2),
    var(--color-warning),
    transparent
  );
  background-size: 300% 100%;
  animation: glow-sweep 2s ease-in-out infinite;
}

/* ── Header ── */
.unassigned-tray__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-2) var(--space-4);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background-color var(--transition-fast);
}

.unassigned-tray__header:hover {
  background: rgba(255, 255, 255, 0.02);
}

.unassigned-tray__header-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.unassigned-tray__icon {
  width: 16px;
  height: 16px;
  color: var(--color-text-muted);
}

.unassigned-tray--drag-over .unassigned-tray__icon {
  color: var(--color-warning);
}

.unassigned-tray__label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  letter-spacing: var(--tracking-wide);
  text-transform: uppercase;
}

.unassigned-tray--drag-over .unassigned-tray__label {
  color: var(--color-warning);
}

.unassigned-tray__count {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 var(--space-1);
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--color-bg-primary);
  background: var(--color-warning);
  border-radius: var(--radius-full);
  animation: breathe-badge 3s ease-in-out infinite;
}

@keyframes breathe-badge {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}

.unassigned-tray__toggle {
  width: 16px;
  height: 16px;
  color: var(--color-text-muted);
  opacity: 0.6;
}

/* ── Body (Device Cards Row) ── */
.unassigned-tray__body {
  padding: 0 var(--space-3) var(--space-2);
}

.unassigned-tray__cards {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  padding: var(--space-1) 0;
  scrollbar-width: thin;
  scrollbar-color: var(--glass-border) transparent;
}

.unassigned-tray__cards::-webkit-scrollbar {
  height: 4px;
}

.unassigned-tray__cards::-webkit-scrollbar-track {
  background: transparent;
}

.unassigned-tray__cards::-webkit-scrollbar-thumb {
  background: var(--glass-border);
  border-radius: var(--radius-xs);
}

/* ── Device Card ── */
.unassigned-card {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  min-width: 200px;
  max-width: 280px;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: grab;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.unassigned-card:hover {
  border-color: var(--color-accent-bright);
  background: color-mix(in srgb, var(--color-bg-tertiary), var(--color-accent-bright) 3%);
  transform: translateY(-1px);
  box-shadow: var(--elevation-raised);
}

.unassigned-card:active {
  cursor: grabbing;
  transform: none;
}

.unassigned-card--ghost {
  opacity: 0.4;
  transform: scale(1.05);
}

.unassigned-card--ghost > * {
  border-style: dashed !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2) !important;
}

/* Status Dot */
.unassigned-card__status {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
}

.status--online {
  background: var(--color-success);
  box-shadow: 0 0 4px var(--color-success);
}

.status--offline {
  background: var(--color-text-muted);
  opacity: 0.5;
}

.status--error {
  background: var(--color-error);
  box-shadow: 0 0 4px var(--color-error);
}

.status--unknown {
  background: var(--color-text-muted);
  opacity: 0.3;
}

/* Card Info */
.unassigned-card__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.unassigned-card__row-top {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.unassigned-card__name {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
}

.unassigned-card__row-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.unassigned-card__meta-item {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.unassigned-card__meta-item--time {
  opacity: 0.7;
}

.unassigned-card__row-sensors {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Settings Link */
.unassigned-card__link {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-xs);
  color: var(--color-text-muted);
  opacity: 0;
  transition: all var(--transition-fast);
  flex-shrink: 0;
}

.unassigned-card:hover .unassigned-card__link {
  opacity: 1;
}

.unassigned-card__link:hover {
  color: var(--color-accent-bright);
  background: rgba(96, 165, 250, 0.1);
}

/* Drop Hint */
.unassigned-tray__drop-hint {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-6);
  color: var(--color-warning);
  font-size: var(--text-sm);
  font-weight: 500;
  border: 1px dashed var(--color-warning);
  border-radius: var(--radius-sm);
  opacity: 0.8;
}

/* ── Transitions ── */
.tray-slide-enter-active {
  transition: all var(--duration-base) var(--ease-out);
}

.tray-slide-leave-active {
  transition: all var(--duration-fast) var(--ease-in-out);
}

.tray-slide-enter-from,
.tray-slide-leave-to {
  opacity: 0;
  max-height: 0;
  padding: 0 var(--space-3);
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .unassigned-tray {
    left: 0;
  }

  .unassigned-card {
    min-width: 160px;
  }
}
</style>
