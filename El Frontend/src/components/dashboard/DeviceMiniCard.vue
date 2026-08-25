<script setup lang="ts">
/**
 * DeviceMiniCard Component
 *
 * Compact device card for Level 1 (Zone Overview).
 * Shows: status dot, device name, alert chip in the header when alerts are active,
 * optional health/suppression line, and sensor/actuator rows.
 *
 * Click: Zoom to Level 2 (device detail) with DOMRect for transition origin.
 * Drag: Header element has .esp-drag-handle for VueDraggable (via ESPCardBase).
 *
 * Wraps ESPCardBase variant="mini" for consistent header rendering.
 */

import type { ESPDevice } from '@/api/esp'
import type { Component } from 'vue'
import { computed, ref } from 'vue'
import {
  Thermometer, Droplets, Droplet, Zap, Sun, Gauge, Wind, Activity, Waves, Cloud, ToggleLeft, Layers,
  ToggleRight, GitBranch, Fan, Flame, Lightbulb, Cog, Power, Bell,
} from 'lucide-vue-next'
import ESPCardBase from '@/components/esp/ESPCardBase.vue'
import { getESPStatus, type ESPStatus } from '@/composables/useESPStatus'
import { useEspStore } from '@/stores/esp'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { espHealthPresentation } from '@/domain/esp/espHealth'
import { groupSensorsByBaseType, getSensorConfig, type RawSensor } from '@/utils/sensorDefaults'
import { getActuatorTypeInfo } from '@/utils/labels'
import type { MockActuator } from '@/types'
import { actuatorDutyToDisplayPercent } from '@/utils/eventTransformer'

interface Props {
  device: ESPDevice
  isMock: boolean
}

const props = defineProps<Props>()
const espStore = useEspStore()
const alertStore = useAlertCenterStore()
const inboxStore = useNotificationInboxStore()

/** Always bind live fields from esp.store (AUT-580 L1 — avoids VueDraggable local copies going stale). */
const liveDevice = computed(() => {
  void espStore.devicesLiveTick
  const id = espStore.getDeviceId(props.device)
  return espStore.devices.find((entry) => espStore.getDeviceId(entry) === id) ?? props.device
})

const emit = defineEmits<{
  (e: 'click', payload: { deviceId: string; originRect: DOMRect }): void
  (e: 'settings', device: ESPDevice): void
  (e: 'change-zone', device: ESPDevice): void
  (e: 'monitor-nav', device: ESPDevice): void
  (e: 'device-delete', deviceId: string): void
}>()

const cardRef = ref<InstanceType<typeof ESPCardBase> | null>(null)

/** Device ID (needed locally for emit payloads) */
const deviceId = computed(() => espStore.getDeviceId(liveDevice.value))

// ── AUT-619: Active notification-alerts for this specific device ─────────
const deviceAlerts = computed(() =>
  alertStore.activeAlertsFromInbox.filter(
    n => n.metadata != null && (n.metadata as Record<string, unknown>)['esp_id'] === deviceId.value
  )
)

const deviceAlertCount = computed(() => deviceAlerts.value.length)

const deviceAlertSeverity = computed(() => {
  if (deviceAlerts.value.some(n => n.severity === 'critical')) return 'critical'
  if (deviceAlerts.value.some(n => n.severity === 'warning')) return 'warning'
  return 'info'
})

const deviceAlertChipLabel = computed(() => {
  const count = deviceAlertCount.value
  return `${count} aktive${count === 1 ? 'r' : ''} Alert${count === 1 ? '' : 's'} — Inbox öffnen`
})

function openDeviceAlerts(event: Event): void {
  event.stopPropagation()
  inboxStore.openDrawerWithActiveAlertsFocus()
}

// ── Status ───────────────────────────────────────────────────────────────
const deviceStatus = computed<ESPStatus>(() => getESPStatus(liveDevice.value))
const isDeviceOnline = computed(() => deviceStatus.value === 'online')

const runtimeHealthBadge = computed(() => {
  const vm = liveDevice.value.runtime_health_view
  if (!vm) return null
  const onlineLike = deviceStatus.value === 'online' || deviceStatus.value === 'stale'
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

// AUT-255: Device-level alert suppression (propagate_to_children).
interface DeviceAlertConfigShape {
  propagate_to_children?: boolean
  suppression_reason?: string | null
  suppression_until?: string | null
}

const deviceAlertConfig = computed<DeviceAlertConfigShape | null>(() => {
  const cfg = (liveDevice.value as unknown as { alert_config?: DeviceAlertConfigShape }).alert_config
  return cfg ?? null
})

const isDeviceSuppressed = computed(() => {
  return deviceAlertConfig.value?.propagate_to_children === true
})

const suppressionTooltip = computed(() => {
  if (!isDeviceSuppressed.value) return ''
  const cfg = deviceAlertConfig.value
  const reason = cfg?.suppression_reason
  const until = cfg?.suppression_until
  const parts = ['Alerts unterdrückt (Device-Suppression aktiv)']
  if (reason) parts.push(`Grund: ${reason}`)
  if (until) parts.push(`Reaktivierung: ${until}`)
  return parts.join('\n')
})

const handoverBadge = computed(() => {
  const handover = liveDevice.value.runtime_health_view?.handover
  if (!handover) return null

  const hasEpoch = handover.epoch !== null
  const hasRejects = handover.rejectTotal > 0
  if (!hasEpoch && !hasRejects) return null

  const titleLines = [
    `Startup-Rejects: ${handover.rejectStartup}`,
    `Runtime-Rejects: ${handover.rejectRuntime}`,
    `Gesamt-Rejects: ${handover.rejectTotal}`,
    `Epoche: ${handover.epoch ?? 'unbekannt'}`,
  ]

  return {
    label: hasRejects ? `Übergabe: ${handover.rejectTotal} Konflikte` : 'Übergabe aktiv',
    title: titleLines.join('\n'),
    isWarning: hasRejects,
  }
})

/** Relative time for stale/offline devices */
const lastSeenText = computed(() => {
  if (isDeviceOnline.value) return ''
  const ts = liveDevice.value.last_seen || liveDevice.value.last_heartbeat
  if (!ts) return ''
  const diffMs = Date.now() - new Date(ts).getTime()
  if (diffMs < 0) return ''
  if (diffMs < 60_000) return 'Gerade eben'
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 60) return `vor ${minutes} Min.`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `vor ${hours} Std.`
  const days = Math.floor(hours / 24)
  return `vor ${days} Tag${days > 1 ? 'en' : ''}`
})

// ── Sensor Icon Map ──────────────────────────────────────────────────────
const SENSOR_ICON_MAP: Record<string, Component> = {
  Thermometer, Droplet, Droplets, Zap, Sun, Gauge, Wind, Activity,
  Waves, Cloud, ToggleLeft, Layers, ToggleRight, GitBranch, Fan,
  Flame, Lightbulb, Cog, Power,
}

function resolveIcon(iconName: string): Component {
  return SENSOR_ICON_MAP[iconName] || Activity
}

// ── Sensor Display (via groupSensorsByBaseType) ──────────────────────────
interface SensorDisplay {
  label: string
  value: string
  unit: string
  valueColor: string
  icon: Component
}

const MAX_VISIBLE_ROWS = 20

/** Map quality to CSS color for value text */
function qualityToValueColor(quality: 'normal' | 'warning' | 'stale' | 'unknown', isOnline: boolean): string {
  if (!isOnline) return 'var(--color-text-muted)'
  if (quality === 'warning') return 'var(--color-warning)'
  if (quality === 'stale') return 'var(--color-text-muted)'
  if (quality === 'unknown') return 'var(--color-text-muted)'
  return 'var(--color-text-primary)'
}

/** Format a sensor value with type-aware decimals and German locale */
function formatValue(value: number | null, quality: 'normal' | 'warning' | 'stale' | 'unknown', sensorType: string): string {
  if (value === null || value === undefined) return '--'
  const dec = getSensorConfig(sensorType)?.decimals ?? 2
  const formatted = new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  }).format(value)
  if (quality === 'stale') return `${formatted}?`
  return formatted
}

const sensorDisplays = computed((): SensorDisplay[] => {
  const sensors = liveDevice.value.sensors as RawSensor[] | undefined
  if (!sensors || sensors.length === 0) return []

  const grouped = groupSensorsByBaseType(sensors)
  const result: SensorDisplay[] = []

  for (const group of grouped) {
    for (const val of group.values) {
      if (result.length >= MAX_VISIBLE_ROWS) break
      result.push({
        label: val.label,
        value: formatValue(val.value, val.quality, val.type),
        unit: val.unit,
        valueColor: qualityToValueColor(val.quality, isDeviceOnline.value),
        icon: resolveIcon(val.icon),
      })
    }
    if (result.length >= MAX_VISIBLE_ROWS) break
  }

  return result
})

/** Total number of grouped sensor values */
const totalSensorValues = computed(() => {
  const sensors = liveDevice.value.sensors as RawSensor[] | undefined
  if (!sensors) return 0
  const grouped = groupSensorsByBaseType(sensors)
  return grouped.reduce((sum, g) => sum + g.values.length, 0)
})

interface ActuatorDisplay {
  label: string
  value: string
  valueColor: string
  icon: Component
}

function resolveActuatorBaseValue(actuator: MockActuator): string {
  const type = actuator.hardware_type ?? actuator.actuator_type
  if ((type === 'pwm' || type === 'fan') && actuator.pwm_value > 0) {
    return `${actuatorDutyToDisplayPercent(actuator.pwm_value)}%`
  }
  return actuator.state ? 'EIN' : 'AUS'
}

function resolveActuatorValue(actuator: MockActuator, status: ESPStatus): string {
  const base = resolveActuatorBaseValue(actuator)
  if (status === 'online') return base
  return `Zuletzt ${base}`
}

function resolveActuatorValueColor(actuator: MockActuator, status: ESPStatus): string {
  if (status === 'stale') return 'var(--color-warning)'
  if (status !== 'online') return 'var(--color-text-muted)'

  const type = actuator.hardware_type ?? actuator.actuator_type
  if ((type === 'pwm' || type === 'fan') && actuator.pwm_value > 0) {
    return 'var(--color-success)'
  }
  return actuator.state ? 'var(--color-success)' : 'var(--color-text-muted)'
}

function resolveActuatorIcon(type: string, hardwareType?: string | null): Component {
  const { icon } = getActuatorTypeInfo(type, hardwareType)
  return resolveIcon(icon)
}

const actuatorDisplays = computed((): ActuatorDisplay[] => {
  const actuators = (liveDevice.value.actuators as MockActuator[] | undefined) ?? []
  if (actuators.length === 0) return []

  return actuators.map((actuator) => ({
    label: actuator.name || getActuatorTypeInfo(actuator.actuator_type, actuator.hardware_type).label,
    value: resolveActuatorValue(actuator, deviceStatus.value),
    valueColor: resolveActuatorValueColor(actuator, deviceStatus.value),
    icon: resolveActuatorIcon(actuator.actuator_type, actuator.hardware_type),
  }))
})

const visibleSensorDisplays = computed(() => {
  const availableRows = Math.max(0, MAX_VISIBLE_ROWS - (actuatorDisplays.value.length > 0 ? 1 : 0))
  return sensorDisplays.value.slice(0, availableRows)
})

const visibleActuatorDisplays = computed(() => {
  const usedRows = visibleSensorDisplays.value.length
  const availableRows = Math.max(0, MAX_VISIBLE_ROWS - usedRows)
  return actuatorDisplays.value.slice(0, availableRows)
})

const extraSensorsCount = computed(() => {
  return Math.max(0, totalSensorValues.value - visibleSensorDisplays.value.length)
})

const extraActuatorsCount = computed(() => {
  return Math.max(0, actuatorDisplays.value.length - visibleActuatorDisplays.value.length)
})

const dataOverflowText = computed(() => {
  const parts: string[] = []
  if (extraSensorsCount.value > 0) parts.push(`${extraSensorsCount.value} Sensoren`)
  if (extraActuatorsCount.value > 0) parts.push(`${extraActuatorsCount.value} Aktoren`)
  if (parts.length === 0) return ''
  return `+${parts.join(' · ')} weitere`
})

/** Fallback text when no sensor data */
const sensorFallback = computed(() => {
  if (sensorDisplays.value.length > 0) return ''
  const sensors = liveDevice.value.sensors as RawSensor[] | undefined
  if (Array.isArray(sensors)) {
    const grouped = groupSensorsByBaseType(sensors)
    const count = grouped.reduce((sum, g) => sum + g.values.length, 0)
    if (count > 0) return `${count} Sensoren`
  } else if ((liveDevice.value.sensor_count ?? 0) > 0) {
    return `${liveDevice.value.sensor_count} Sensoren`
  }
  return ''
})

const hasStatusLineContent = computed(() =>
  isDeviceSuppressed.value
  || Boolean(runtimeHealthBadge.value?.showBadge)
  || Boolean(handoverBadge.value)
  || Boolean(lastSeenText.value),
)

/** Subzone label (if assigned) */
const subzoneName = computed(() => liveDevice.value.subzone_name || '')

// ── Click / Action Handlers ──────────────────────────────────────────────
function handleClick() {
  const el = cardRef.value?.$el as HTMLElement | undefined
  const rect = el?.getBoundingClientRect()
  if (rect) {
    emit('click', { deviceId: deviceId.value, originRect: rect })
  }
}

function handleSettings() {
  emit('settings', liveDevice.value)
}

function handleChangeZone() {
  emit('change-zone', liveDevice.value)
}

function handleMonitorNav() {
  emit('monitor-nav', liveDevice.value)
}

function handleDeviceDelete() {
  if (!deviceId.value) return
  emit('device-delete', deviceId.value)
}
</script>

<template>
  <ESPCardBase
    ref="cardRef"
    :esp="liveDevice"
    variant="mini"
    :class="[
      'device-mini-card',
      {
        'device-mini-card--stale': !isDeviceOnline,
        'device-mini-card--mock': isMock,
        'device-mini-card--real': !isMock,
      },
    ]"
    @click="handleClick"
    @keydown.enter.prevent="handleClick"
    @settings="handleSettings"
    @change-zone="handleChangeZone"
    @monitor-nav="handleMonitorNav"
    @delete="handleDeviceDelete"
  >
    <template #badge>
      <button
        v-if="deviceAlertCount > 0"
        type="button"
        :class="[
          'device-mini-card__alert-badge',
          deviceAlertSeverity === 'critical'
            ? 'device-mini-card__alert-badge--critical'
            : 'device-mini-card__alert-badge--warning',
        ]"
        data-testid="device-alert-chip"
        :title="deviceAlertChipLabel"
        :aria-label="deviceAlertChipLabel"
        @click.stop="openDeviceAlerts"
        @pointerdown.stop
        @mousedown.stop
      >
        <Bell class="device-mini-card__alert-badge-icon" aria-hidden="true" />
        {{ deviceAlertCount > 9 ? '9+' : deviceAlertCount }}
      </button>
    </template>

    <!-- Card content: status line, subzone, sensors -->
    <template #default>
      <!-- Status line: health / suppression / last seen (alert chip lives in header) -->
      <div v-if="hasStatusLineContent" class="device-mini-card__status-line">
        <span
          v-if="isDeviceSuppressed"
          class="device-mini-card__suppression-pill"
          :title="suppressionTooltip"
        >
          🔕 Alerts pausiert
        </span>
        <span
          v-if="runtimeHealthBadge?.showBadge"
          class="device-mini-card__status-chip device-mini-card__status-chip--stale device-mini-card__status-chip--health"
          :title="runtimeHealthTooltip"
        >
          <span class="device-mini-card__status-chip-label">{{ runtimeHealthBadge.badgeLabel }}</span>
          <!-- Primäre Ursache als Sublabel (AUT-124) -->
          <span
            v-if="runtimeHealthBadge.primaryReasonLabel"
            class="device-mini-card__health-reason"
          >{{ runtimeHealthBadge.primaryReasonLabel }}</span>
        </span>
        <span
          v-if="handoverBadge"
          class="device-mini-card__status-chip"
          :class="handoverBadge.isWarning ? 'device-mini-card__status-chip--handover-warning' : 'device-mini-card__status-chip--handover'"
          :title="handoverBadge.title"
        >
          {{ handoverBadge.label }}
        </span>
        <span v-if="lastSeenText" class="device-mini-card__last-seen">· {{ lastSeenText }}</span>
      </div>

      <!-- Subzone indicator -->
      <div v-if="subzoneName" class="device-mini-card__subzone">
        {{ subzoneName }}
      </div>

      <!-- Sensor + actuator values (stabile Hoehe, max 4 Zeilen) -->
      <div
        v-if="visibleSensorDisplays.length > 0 || visibleActuatorDisplays.length > 0"
        class="device-mini-card__sensors"
      >
        <div v-if="visibleSensorDisplays.length > 0" class="device-mini-card__section-title">
          Sensoren
        </div>
        <div
          v-for="(sensor, idx) in visibleSensorDisplays"
          :key="idx"
          class="device-mini-card__sensor"
        >
          <component :is="sensor.icon" class="device-mini-card__sensor-icon" />
          <span class="device-mini-card__sensor-name" :title="sensor.label">{{ sensor.label }}</span>
          <span class="device-mini-card__sensor-value" :style="{ color: sensor.valueColor }">{{ sensor.value }}</span>
          <span class="device-mini-card__sensor-unit">{{ sensor.unit }}</span>
        </div>

        <div
          v-if="visibleActuatorDisplays.length > 0"
          class="device-mini-card__section-title device-mini-card__section-title--actuator"
        >
          Aktoren
        </div>
        <div
          v-for="(actuator, idx) in visibleActuatorDisplays"
          :key="`act-${idx}`"
          class="device-mini-card__sensor device-mini-card__sensor--actuator"
        >
          <component :is="actuator.icon" class="device-mini-card__sensor-icon device-mini-card__sensor-icon--actuator" />
          <span class="device-mini-card__sensor-name" :title="actuator.label">{{ actuator.label }}</span>
          <span class="device-mini-card__sensor-value" :style="{ color: actuator.valueColor }">{{ actuator.value }}</span>
        </div>

        <div v-if="dataOverflowText" class="device-mini-card__sensors-overflow">
          {{ dataOverflowText }}
        </div>
      </div>

      <!-- Fallback: keeps card height stable -->
      <div v-else class="device-mini-card__values">
        <span v-if="sensorFallback">{{ sensorFallback }}</span>
        <span v-else>Keine Sensoren oder Aktoren</span>
      </div>

    </template>
  </ESPCardBase>
</template>

<style scoped>
/* ── Root overrides on ESPCardBase for mini card styling ── */
.device-mini-card {
  background: var(--glass-bg-l2);
  padding: var(--space-3);
  cursor: pointer;
  transition:
    background var(--transition-fast),
    border-color var(--transition-fast),
    transform var(--transition-fast),
    box-shadow var(--transition-fast);
  min-width: 180px;
  /* Content-driven height; empty cards collapse to ~120px naturally */
  max-width: 100%;
  position: relative;
  overflow: hidden;
  will-change: transform;
}

.device-mini-card.esp-card-base {
  border-left-width: 1px;
  border-left-color: var(--glass-border);
}

/* Shimmer sweep on hover */
.device-mini-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 50%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.03),
    transparent
  );
  pointer-events: none;
  transition: none;
}

.device-mini-card:hover::before {
  animation: shimmer 0.8s ease-out forwards;
}

.device-mini-card:hover {
  background: var(--color-bg-quaternary);
  border-color: var(--glass-border-hover);
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
  filter: brightness(1.05);
}


/* Tactile touch feedback */
.device-mini-card:active {
  transform: scale(0.99);
  transition-duration: 60ms;
}

/* Mock / Real glow border — analog to esp-info-compact--mock/--real */
.device-mini-card--mock {
  border-left: 3px solid var(--color-mock);
  box-shadow:
    var(--glass-shadow-l2),
    0 0 16px color-mix(in srgb, var(--color-mock) 15%, transparent);
}

.device-mini-card--mock:hover {
  box-shadow:
    0 6px 18px rgba(0, 0, 0, 0.35),
    0 0 22px color-mix(in srgb, var(--color-mock) 22%, transparent);
}

.device-mini-card--real {
  border-left: 3px solid var(--color-real);
  box-shadow:
    var(--glass-shadow-l2),
    0 0 16px color-mix(in srgb, var(--color-real) 13%, transparent);
}

.device-mini-card--real:hover {
  box-shadow:
    0 6px 18px rgba(0, 0, 0, 0.35),
    0 0 22px color-mix(in srgb, var(--color-real) 18%, transparent);
}

/* Status-dot puls ring on online devices */
:deep(.esp-card-base__status-dot)::after {
  content: '';
  position: absolute;
  inset: -3px;
  border-radius: var(--radius-full);
  border: 1px solid currentColor;
  opacity: 0;
  pointer-events: none;
}

.device-mini-card:not(.device-mini-card--stale) :deep(.esp-card-base__status-dot)::after {
  animation: status-ring-pulse 2.4s ease-out infinite;
}

@keyframes status-ring-pulse {
  0% { opacity: 0.6; transform: scale(1); }
  60% { opacity: 0; transform: scale(2.2); }
  100% { opacity: 0; transform: scale(2.2); }
}


/* ── Grip handle (always visible for discoverability) ── */
:deep(.esp-drag-handle) {
  cursor: grab;
  min-height: 44px; /* Touch-friendly target size */
  min-width: 44px;
}

:deep(.esp-drag-handle):active {
  cursor: grabbing;
}

/* Long-press visual feedback (VueDraggable chosen-class applies after 300ms delay) */
.zone-item--chosen.device-mini-card,
.device-mini-card.sortable-chosen {
  transform: scale(1.02);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3), 0 0 0 2px var(--color-iridescent-1);
  transition: transform 150ms ease-out, box-shadow 150ms ease-out;
}

:deep(.esp-drag-handle)::before {
  content: '⠿';
  font-size: var(--text-xs);
  line-height: 1;
  color: var(--color-text-muted);
  opacity: 0.25;
  transition: opacity var(--transition-fast);
  flex-shrink: 0;
}

.device-mini-card:hover :deep(.esp-drag-handle)::before,
.device-mini-card:focus-within :deep(.esp-drag-handle)::before {
  opacity: 0.5;
}

/* Touch devices: grip always visible */
@media (hover: none) {
  :deep(.esp-drag-handle)::before {
    opacity: 0.5;
  }
}

/* ── ESPCardBase inner overrides for mini sizing ── */

/* Status dot: 8px per orbital design spec */
:deep(.esp-card-base__status-dot) {
  width: 8px;
  height: 8px;
}

/* Status dot glow on hover */
.device-mini-card:hover :deep(.esp-card-base__status-dot) {
  box-shadow: 0 0 8px currentColor;
}

/* Smaller name text — desktop compact; touch via coarse/hover-none below */
:deep(.esp-card-base__name) {
  font-size: var(--text-sm);
  font-weight: 500;
}

/* Match original badge styling */
:deep(.esp-card-base__badge) {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
}

/* (Settings button moved to action row) */

/* ── Status line ── */
.device-mini-card__status-line {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 20px;
}

.device-mini-card__status-chip {
  display: inline-flex;
  align-items: center;
  border-radius: var(--radius-full);
  border: 1px solid var(--glass-border);
  padding: 1px var(--space-2);
  font-size: var(--text-xxs);
  line-height: 1.2;
  font-weight: 600;
  white-space: nowrap;
}

.device-mini-card__status-chip--online {
  color: var(--color-success);
  border-color: color-mix(in srgb, var(--color-success) 40%, transparent);
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
}

.device-mini-card__status-chip--stale,
.device-mini-card__status-chip--safemode {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 40%, transparent);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
}

/* AUT-124: Health chip with primary reason sublabel */
.device-mini-card__status-chip--health {
  gap: var(--space-1);
  max-width: 100%;
  overflow: hidden;
}

.device-mini-card__status-chip-label {
  flex-shrink: 0;
}

.device-mini-card__health-reason {
  font-weight: 500;
  font-size: var(--text-xxs);
  opacity: 0.85;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

.device-mini-card__health-reason::before {
  content: '· ';
  opacity: 0.6;
}

.device-mini-card__status-chip--error {
  color: var(--color-error);
  border-color: color-mix(in srgb, var(--color-error) 40%, transparent);
  background: color-mix(in srgb, var(--color-error) 12%, transparent);
}

.device-mini-card__status-chip--offline,
.device-mini-card__status-chip--unknown {
  color: var(--color-text-muted);
  border-color: var(--glass-border);
  background: color-mix(in srgb, var(--color-bg-quaternary) 60%, transparent);
}

.device-mini-card__status-chip--handover {
  color: var(--color-info);
  border-color: color-mix(in srgb, var(--color-info) 40%, transparent);
  background: color-mix(in srgb, var(--color-info) 10%, transparent);
}

.device-mini-card__status-chip--handover-warning {
  color: var(--color-warning);
  border-color: color-mix(in srgb, var(--color-warning) 40%, transparent);
  background: color-mix(in srgb, var(--color-warning) 14%, transparent);
}

/* AUT-619: Notification-alert badge (Bell icon + count, visually distinct from status dot) */
.device-mini-card__alert-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 44px;
  min-height: 44px;
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  font: inherit;
  font-size: var(--text-xxs);
  font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
  cursor: pointer;
  transition: background var(--transition-fast), border-color var(--transition-fast);
}

.device-mini-card__alert-badge:focus-visible {
  outline: 2px solid var(--color-iridescent-1);
  outline-offset: 2px;
}

.device-mini-card__alert-badge--critical {
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 35%, transparent);
}

.device-mini-card__alert-badge--critical:hover {
  background: color-mix(in srgb, var(--color-error) 22%, transparent);
  border-color: color-mix(in srgb, var(--color-error) 50%, transparent);
}

.device-mini-card__alert-badge--warning {
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 35%, transparent);
}

.device-mini-card__alert-badge--warning:hover {
  background: color-mix(in srgb, var(--color-warning) 22%, transparent);
  border-color: color-mix(in srgb, var(--color-warning) 50%, transparent);
}

.device-mini-card__alert-badge-icon {
  width: 10px;
  height: 10px;
  flex-shrink: 0;
}

/* AUT-255: Device-level alert suppression pill */
.device-mini-card__suppression-pill {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 1px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xxs);
  font-weight: 500;
  color: var(--color-warning);
  background: color-mix(in srgb, var(--color-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent);
  white-space: nowrap;
  flex-shrink: 0;
}

.device-mini-card__last-seen {
  color: var(--color-text-muted);
  font-size: var(--text-xxs);
}


/* ── Subzone indicator ── */
.device-mini-card__subzone {
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.7;
  margin-bottom: 2px;
}

/* ── Sensor values with icons and spark-bars ── */
.device-mini-card__sensors {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  justify-content: flex-start;
}

.device-mini-card__section-title {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: var(--tracking-wide);
  font-weight: 600;
  padding-top: 2px;
}

.device-mini-card__section-title--actuator {
  margin-top: 2px;
  border-top: 1px dashed var(--glass-border);
  padding-top: var(--space-1);
}

.device-mini-card__sensor {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.device-mini-card__sensor-icon {
  width: 11px;
  height: 11px;
  flex-shrink: 0;
  color: var(--color-text-secondary);
  opacity: 0.85;
}

.device-mini-card__sensor--actuator .device-mini-card__sensor-name {
  color: var(--color-text-primary);
}

.device-mini-card__sensor-icon--actuator {
  color: var(--color-accent-bright);
  opacity: 0.8;
}

.device-mini-card__sensor-name {
  flex: 1;
  min-width: 0;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-mini-card__sensor-value {
  font-family: var(--font-mono);
  font-size: var(--text-base);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
  min-width: 0;
  flex-shrink: 0;
}

.device-mini-card__sensor-unit {
  font-family: var(--font-mono);
  font-size: var(--text-xxs);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.device-mini-card__sensors-overflow {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  padding-left: var(--space-4);
}

/* ── Stale/offline state: parent opacity dims all content uniformly ── */
.device-mini-card--stale {
  opacity: 0.65;
}

/* Fallback text — compact empty state */
.device-mini-card__values {
  display: flex;
  align-items: center;
  min-height: 48px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

/* Mobile: allow full width */
@media (max-width: 640px) {
  .device-mini-card {
    max-width: none;
  }
}

/* Touch density: tokens.css @media (pointer: coarse) + hover:none (Pi touchscreen) */
@media (pointer: coarse), (hover: none) {
  :deep(.esp-card-base__name) {
    font-size: var(--text-base);
  }

  .device-mini-card__sensor-icon {
    width: 14px;
    height: 14px;
  }
}
</style>
