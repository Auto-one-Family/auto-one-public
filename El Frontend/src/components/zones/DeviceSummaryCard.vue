<script setup lang="ts">
/**
 * DeviceSummaryCard Component (~240x140px)
 *
 * Level 2 (Zone Detail): Medium device card showing:
 * - Name, status dot, mock/real badge (via ESPCardBase)
 * - Top-2 live sensor values (fallback to count)
 * - Health-bar at bottom edge
 * - Quick-action buttons (heartbeat mock-only, settings)
 * - Value-flash animation on sensor data change
 *
 * Wraps ESPCardBase variant="summary" for consistent header rendering.
 */

import { computed, ref, watch, onUnmounted } from 'vue'
import type { ESPDevice } from '@/api/esp'
import ESPCardBase from '@/components/esp/ESPCardBase.vue'
import { getESPStatus } from '@/composables/useESPStatus'
import { espHealthPresentation } from '@/domain/esp/espHealth'
import {
  Heart,
  Settings2,
} from 'lucide-vue-next'
import StatusBadge from '@/components/base/StatusBadge.vue'

interface Props {
  device: ESPDevice
  isMock: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'click', payload: { deviceId: string; originRect: DOMRect }): void
  (e: 'heartbeat', deviceId: string): void
  (e: 'settings', device: ESPDevice): void
}>()

const cardRef = ref<InstanceType<typeof ESPCardBase> | null>(null)

/** Value-flash trigger: toggled when sensor data changes */
const valueFlashing = ref(false)

/** Device ID (needed locally for emit payloads) */
const deviceId = computed(() => {
  const d = props.device
  return d.device_id || (d as any).esp_id || ''
})

/** Top-2 live sensor values */
interface LiveSensor {
  value: string
  unit: string
}

const liveSensors = computed((): LiveSensor[] => {
  const sensors = props.device.sensors as any[] | undefined
  if (!sensors || sensors.length === 0) return []

  const result: LiveSensor[] = []
  for (const sensor of sensors) {
    if (result.length >= 2) break
    if (sensor.raw_value != null) {
      result.push({
        value: String(sensor.raw_value),
        unit: sensor.unit || '',
      })
    }
  }
  return result
})

/** Fallback counts when no sensor data */
const sensorCount = computed(() => {
  const sensors = props.device.sensors as any[] | undefined
  return sensors?.length ?? props.device.sensor_count ?? 0
})

const actuatorCount = computed(() => {
  const actuators = props.device.actuators as any[] | undefined
  return actuators?.length ?? props.device.actuator_count ?? 0
})

const runtimeHealthBadge = computed(() => {
  const vm = props.device.runtime_health_view
  if (!vm) return null
  const status = getESPStatus(props.device)
  const onlineLike = status === 'online' || status === 'stale'
  return espHealthPresentation(vm, onlineLike)
})
const runtimeHealthTooltip = computed(() => {
  const badge = runtimeHealthBadge.value
  if (!badge) return ''
  const hasPrefixedCause = badge.tooltipLines.some(
    line => /^Ursache:/i.test(line) || /^Weitere Ursache:/i.test(line),
  )
  const normalizedLines = hasPrefixedCause
    ? badge.tooltipLines
    : badge.tooltipLines.map((line, index) => `${index === 0 ? 'Ursache' : 'Weitere Ursache'}: ${line}`)
  const recommendedAction = badge.recommendedAction ?? (
    badge.showBadge
      ? 'System-Monitor und Geräte-Details prüfen, dann bei anhaltender Meldung eskalieren.'
      : null
  )
  return [
    ...normalizedLines,
    recommendedAction ? `Nächster Schritt: ${recommendedAction}` : null,
  ].filter((line): line is string => Boolean(line)).join('\n')
})

/** Connection indicator (0-100) for bottom bar (not runtime-health severity). */
const healthPercent = computed(() => {
  if (props.device.status === 'online' || props.device.connected === true) return 100
  if (props.isMock) {
    const state = (props.device as any).system_state
    if (state === 'SAFE_MODE') return 60
    if (state === 'ERROR') return 20
  }
  if (props.device.status === 'error') return 20
  return 40
})

/** Health-bar gradient color */
const healthColor = computed(() => {
  if (healthPercent.value >= 80) return 'var(--color-success)'
  if (healthPercent.value >= 50) return 'var(--color-warning)'
  return 'var(--color-error)'
})

/** Watch sensor data for value-flash animation */
let flashTimer: ReturnType<typeof setTimeout> | null = null
watch(
  () => {
    const sensors = props.device.sensors as any[] | undefined
    if (!sensors) return ''
    return sensors.map(s => s.raw_value).join(',')
  },
  (newVal, oldVal) => {
    if (oldVal && newVal !== oldVal) {
      valueFlashing.value = true
      if (flashTimer) clearTimeout(flashTimer)
      flashTimer = setTimeout(() => { valueFlashing.value = false }, 600)
    }
  }
)

onUnmounted(() => {
  if (flashTimer) clearTimeout(flashTimer)
})

function handleClick(event: Event) {
  if ((event.target as HTMLElement).closest('.device-summary-card__actions')) return
  const el = cardRef.value?.$el as HTMLElement | undefined
  const rect = el?.getBoundingClientRect()
  if (rect) {
    emit('click', { deviceId: deviceId.value, originRect: rect })
  }
}

function handleHeartbeat(event: MouseEvent) {
  event.stopPropagation()
  emit('heartbeat', deviceId.value)
}

function handleSettings(event: MouseEvent) {
  event.stopPropagation()
  emit('settings', props.device)
}
</script>

<template>
  <ESPCardBase
    ref="cardRef"
    :esp="device"
    variant="summary"
    class="device-summary-card"
    :class="{ 'device-summary-card--flashing': valueFlashing }"
    :data-device-id="deviceId"
    @click="handleClick"
    @keydown.enter="handleClick"
  >
    <!-- Content: live sensor values OR fallback counts + actions -->
    <template #default="{ lastSeenText }">
      <div class="device-summary-card__status-line">
        <StatusBadge
          v-if="runtimeHealthBadge?.showBadge"
          level="warning"
          :label-override="runtimeHealthBadge!.badgeLabel"
          :title="runtimeHealthTooltip"
        />
      </div>

      <!-- Live sensor values -->
      <div v-if="liveSensors.length > 0" class="device-summary-card__live-data">
        <div
          v-for="(sensor, idx) in liveSensors"
          :key="idx"
          class="device-summary-card__live-value"
        >
          <span class="device-summary-card__live-number">{{ sensor.value }}</span>
          <span class="device-summary-card__live-unit">{{ sensor.unit }}</span>
        </div>
        <div class="device-summary-card__live-meta">
          {{ lastSeenText }}
        </div>
      </div>

      <!-- Fallback: sensor/actuator counts -->
      <div v-else class="device-summary-card__meta">
        <span>{{ sensorCount }} Sensor{{ sensorCount !== 1 ? 'en' : '' }}</span>
        <span class="device-summary-card__meta-sep">·</span>
        <span>{{ actuatorCount }} Aktor{{ actuatorCount !== 1 ? 'en' : '' }}</span>
        <span class="device-summary-card__meta-sep">·</span>
        <span>{{ lastSeenText }}</span>
      </div>

      <!-- Quick actions -->
      <div class="device-summary-card__actions">
        <button
          v-if="isMock"
          class="device-summary-card__action-btn"
          title="Heartbeat auslösen"
          @click="handleHeartbeat"
        >
          <Heart class="w-3 h-3" />
        </button>
        <button
          class="device-summary-card__action-btn"
          title="Einstellungen"
          @click="handleSettings"
        >
          <Settings2 class="w-3 h-3" />
        </button>
      </div>
    </template>

    <!-- Health bar at bottom edge -->
    <template #footer>
      <div class="device-summary-card__health-bar" title="Verbindungsindikator">
        <div
          class="device-summary-card__health-fill"
          :style="{
            width: healthPercent + '%',
            backgroundColor: healthColor,
          }"
        />
      </div>
    </template>
  </ESPCardBase>
</template>

<style scoped>
/* ── Root overrides on ESPCardBase for glassmorphism ── */
.device-summary-card {
  background: var(--glass-bg);
  backdrop-filter: blur(12px);
  padding: var(--space-4);
  padding-bottom: calc(var(--space-4) + 3px); /* room for health-bar */
  cursor: pointer;
  transition:
    transform var(--transition-base),
    box-shadow var(--transition-base),
    border-color var(--transition-base),
    border-left-width var(--transition-fast),
    backdrop-filter var(--transition-base);
  position: relative;
  overflow: hidden;
  min-width: 200px;
}

/* Noise overlay */
.device-summary-card::after {
  content: '';
  position: absolute;
  inset: 0;
  opacity: 0.015;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
  pointer-events: none;
}

.device-summary-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--elevation-floating);
  border-color: var(--glass-border-hover);
  border-left-width: 4px;
  backdrop-filter: blur(16px);
}

/* Value-flash animation */
.device-summary-card--flashing .device-summary-card__live-data {
  animation: value-flash 0.6s ease-out;
}

/* Tactile press */
.device-summary-card:active {
  transform: scale(0.98);
  transition-duration: 60ms;
}

/* ── ESPCardBase inner overrides ── */

/* Hide status line (we show lastSeenText in content area instead) */
:deep(.esp-card-base__status-line) {
  display: none;
}

/* Match original header spacing */
:deep(.esp-card-base__header) {
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

/* Match original name styling */
:deep(.esp-card-base__name) {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

/* Match original badge styling */
:deep(.esp-card-base__badge) {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
}

/* Status dot glow on hover */
.device-summary-card:hover :deep(.esp-card-base__status-dot) {
  box-shadow: 0 0 10px currentColor;
}

/* Footer: absolute health-bar positioning */
:deep(.esp-card-base__footer) {
  border-top: none;
  padding-top: 0;
  margin-top: 0;
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
}

/* ── Live sensor data display ── */
.device-summary-card__live-data {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  flex-wrap: wrap;
  border-radius: var(--radius-sm);
  padding: 2px 0;
}

.device-summary-card__status-line {
  min-height: 20px;
  display: flex;
  align-items: center;
  margin-bottom: var(--space-1);
}

.device-summary-card__status-chip {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-full);
  border: 1px solid color-mix(in srgb, var(--color-warning) 40%, transparent);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  color: var(--color-warning);
  padding: 1px var(--space-2);
  font-size: var(--text-xxs);
  line-height: 1.2;
  font-weight: 600;
  white-space: nowrap;
}

.device-summary-card__live-value {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.device-summary-card__live-number {
  font-family: var(--font-mono);
  font-size: var(--text-xl);
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.device-summary-card__live-unit {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-left: 1px;
}

.device-summary-card__live-meta {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-left: auto;
}

/* ── Fallback meta (counts) ── */
.device-summary-card__meta {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  flex-wrap: wrap;
}

.device-summary-card__meta-sep {
  color: var(--color-text-muted);
}

/* ── Action buttons ── */
.device-summary-card__actions {
  display: flex;
  gap: var(--space-1);
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--glass-border);
  opacity: 0.5;
  transition: opacity var(--transition-base);
}

.device-summary-card:hover .device-summary-card__actions {
  opacity: 1;
}

.device-summary-card__action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.device-summary-card__action-btn:hover {
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  background: var(--glass-bg-light);
}

/* ── Health bar (bottom edge) ── */
.device-summary-card__health-bar {
  height: 3px;
  background: rgba(255, 255, 255, 0.03);
}

.device-summary-card__health-fill {
  height: 100%;
  transition: width var(--transition-slow), background-color var(--transition-slow);
  border-radius: 0 var(--radius-xs) 0 0;
}
</style>
