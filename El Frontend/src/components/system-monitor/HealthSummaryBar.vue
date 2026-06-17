<script setup lang="ts">
/**
 * HealthSummaryBar - Compact health problem overview in Events tab
 *
 * Shows offline devices, low heap, weak signal at a glance.
 * Expandable to show detailed table with click-outside-to-close.
 *
 * Mobile: Hidden via CSS (use Health Tab instead).
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ChevronDown, CheckCircle, AlertTriangle, AlertCircle, Info, Lightbulb, Bell, Stethoscope } from 'lucide-vue-next'
import type { FleetHealthDevice, RecentError } from '@/api/health'
import { formatRelativeTime } from '@/utils/formatters'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useDiagnosticsStore } from '@/shared/stores/diagnostics.store'
import HealthProblemChip from './HealthProblemChip.vue'

interface Props {
  devices: FleetHealthDevice[]
  isLoading: boolean
  expanded: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  'filter-device': [espId: string]
  'update:expanded': [value: boolean]
  'open-alerts': []
}>()

const alertStore = useAlertCenterStore()
const inboxStore = useNotificationInboxStore()
const diagStore = useDiagnosticsStore()

// Problem detection
const offlineDevices = computed(() =>
  props.devices.filter(d => d.status === 'offline')
)

const lowHeapDevices = computed(() =>
  props.devices.filter(d => d.status === 'online' && d.heap_free != null && d.heap_free < 20000)
)

const weakSignalDevices = computed(() =>
  props.devices.filter(d => d.status === 'online' && d.wifi_rssi != null && d.wifi_rssi < -80)
)

const hasDeviceProblems = computed(() =>
  offlineDevices.value.length > 0 ||
  lowHeapDevices.value.length > 0 ||
  weakSignalDevices.value.length > 0
)

const hasAlertProblems = computed(() => alertStore.unresolvedCount > 0)

const hasProblems = computed(() =>
  hasDeviceProblems.value || hasAlertProblems.value
)

// Status text
const statusText = computed(() => {
  const parts: string[] = []

  if (offlineDevices.value.length > 0) {
    const n = offlineDevices.value.length
    parts.push(`${n} ${n === 1 ? 'Gerät' : 'Geräte'} offline`)
  }
  if (lowHeapDevices.value.length > 0) {
    parts.push(`${lowHeapDevices.value.length} Heap kritisch`)
  }
  if (weakSignalDevices.value.length > 0) {
    parts.push(`${weakSignalDevices.value.length} Signal schwach`)
  }
  if (alertStore.criticalCount > 0) {
    parts.push(`${alertStore.criticalCount} Critical Alerts`)
  } else if (alertStore.warningCount > 0) {
    parts.push(`${alertStore.warningCount} Warning Alerts`)
  }

  if (parts.length === 0) {
    const count = props.devices.length
    return `Alle ${count} ${count === 1 ? 'Gerät' : 'Geräte'} online`
  }

  return parts.join(' · ')
})

function handleOpenAlerts() {
  emit('open-alerts')
  inboxStore.toggleDrawer()
}

// All problem devices (deduplicated)
const allProblemDevices = computed(() => {
  const seen = new Set<string>()
  const result: { device: FleetHealthDevice; type: 'offline' | 'low-heap' | 'weak-signal' }[] = []

  for (const d of offlineDevices.value) {
    if (!seen.has(d.device_id)) {
      seen.add(d.device_id)
      result.push({ device: d, type: 'offline' })
    }
  }
  for (const d of lowHeapDevices.value) {
    if (!seen.has(d.device_id)) {
      seen.add(d.device_id)
      result.push({ device: d, type: 'low-heap' })
    }
  }
  for (const d of weakSignalDevices.value) {
    if (!seen.has(d.device_id)) {
      seen.add(d.device_id)
      result.push({ device: d, type: 'weak-signal' })
    }
  }
  return result
})

// Backdrop visible state (delayed for animation)
const backdropVisible = ref(false)

function toggleExpanded() {
  const next = !props.expanded
  emit('update:expanded', next)
  if (next) {
    requestAnimationFrame(() => {
      backdropVisible.value = true
    })
  } else {
    backdropVisible.value = false
  }
}

function closeExpanded() {
  backdropVisible.value = false
  emit('update:expanded', false)
}

function handleFilterDevice(espId: string) {
  emit('filter-device', espId)
  closeExpanded()
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.expanded) {
    closeExpanded()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  // Sync backdrop if already expanded on mount
  if (props.expanded) {
    backdropVisible.value = true
  }
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})

// All recent errors from problem devices, sorted newest first
const recentErrors = computed(() => {
  const flat: Array<RecentError & { esp_id: string }> = []

  for (const item of allProblemDevices.value) {
    const device = item.device
    if (device.recent_errors) {
      for (const error of device.recent_errors) {
        flat.push({ ...error, esp_id: device.device_id })
      }
    }
  }

  flat.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
  return flat.slice(0, 10)
})

function getDeviceName(espId: string): string {
  const device = props.devices.find(d => d.device_id === espId)
  return device?.name || espId
}

function getSeverityIcon(severity: string) {
  switch (severity) {
    case 'critical':
    case 'error':
      return AlertCircle
    case 'warning':
      return AlertTriangle
    default:
      return Info
  }
}

function formatErrorTime(isoString: string): string {
  return formatRelativeTime(isoString)
}
</script>

<template>
  <!-- Backdrop for click-outside-to-close -->
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="expanded && hasProblems"
        class="health-backdrop"
        :class="{ 'health-backdrop--visible': backdropVisible }"
        @click="closeExpanded"
      />
    </Transition>
  </Teleport>

  <!-- Mobile: Health Summary hidden, use Health Tab instead -->
  <div
    v-if="!isLoading && devices.length > 0"
    class="health-summary"
    :class="{
      'health-summary--has-problems': hasProblems,
      'health-summary--all-ok': !hasProblems,
      'health-summary--expanded': expanded,
    }"
  >
    <!-- Header -->
    <div class="health-summary__header">
      <div class="health-summary__status">
        <AlertTriangle v-if="hasProblems" :size="18" class="health-summary__icon--warning" />
        <CheckCircle v-else :size="16" class="health-summary__icon--ok" />
        <span>{{ statusText }}</span>
      </div>

      <button
        v-if="hasProblems"
        class="health-summary__toggle"
        @click="toggleExpanded"
      >
        Details
        <ChevronDown :size="14" class="health-summary__chevron" />
      </button>
    </div>

    <!-- Problem Chips (collapsed state) -->
    <div v-if="hasProblems && !expanded" class="health-summary__problems">
      <HealthProblemChip
        v-for="item in allProblemDevices"
        :key="item.device.device_id"
        :device="item.device"
        :problem-type="item.type"
        @click="handleFilterDevice"
      />
      <!-- Alert Chips -->
      <button
        v-if="alertStore.criticalCount > 0"
        type="button"
        class="alert-chip alert-chip--critical"
        aria-label="Server-Inbox öffnen: Critical Alerts (nicht Echtzeit-error_event-Stream)"
        title="Öffnet die Server-Inbox — Echtzeit-Fehler siehe Tab Ereignisse (Stream)"
        @click="handleOpenAlerts"
      >
        <Bell :size="12" />
        Inbox · {{ alertStore.criticalCount }} Critical
      </button>
      <button
        v-if="alertStore.warningCount > 0"
        type="button"
        class="alert-chip alert-chip--warning"
        aria-label="Server-Inbox öffnen: Warning Alerts (nicht Echtzeit-error_event-Stream)"
        title="Öffnet die Server-Inbox — Echtzeit-Fehler siehe Tab Ereignisse (Stream)"
        @click="handleOpenAlerts"
      >
        <Bell :size="12" />
        Inbox · {{ alertStore.warningCount }} Warnings
      </button>
    </div>

    <!-- Diagnostic Status Chip (immer sichtbar wenn letzte Diagnose vorhanden) -->
    <div v-if="diagStore.lastRunAge && !hasProblems" class="health-summary__diag-row">
      <span
        :class="['diag-chip', diagStore.hasProblems ? 'diag-chip--warning' : 'diag-chip--ok']"
      >
        <Stethoscope :size="12" />
        Letzte Diagnose: {{ diagStore.lastRunAge }}
        <template v-if="!diagStore.hasProblems"> ✓</template>
      </span>
    </div>
    <div v-else-if="diagStore.lastRunAge && hasProblems" class="health-summary__diag-row">
      <span class="diag-chip diag-chip--warning">
        <Stethoscope :size="12" />
        Diagnose: {{ diagStore.lastRunAge }} (Probleme)
      </span>
    </div>

    <!-- Expanded: Error Messages -->
    <div class="health-summary__details">
      <div class="health-summary__details-inner">
        <template v-if="expanded && hasProblems">

          <!-- Problem Chips (shown in expanded too) -->
          <div class="health-summary__problems health-summary__problems--expanded">
            <HealthProblemChip
              v-for="item in allProblemDevices"
              :key="item.device.device_id"
              :device="item.device"
              :problem-type="item.type"
              @click="handleFilterDevice"
            />
          </div>

          <!-- Divider -->
          <div class="health-summary__divider">
            <span>Letzte Ereignisse zu diesen Geräten</span>
          </div>

          <!-- Error Messages List -->
          <div class="health-summary__errors">
            <div
              v-for="(error, idx) in recentErrors"
              :key="`${error.esp_id}-${idx}`"
              class="error-item"
              :class="`error-item--${error.severity}`"
            >
              <component
                :is="getSeverityIcon(error.severity)"
                :size="14"
                class="error-item__icon"
              />
              <span class="error-item__source">
                {{ getDeviceName(error.esp_id) }} · {{ formatErrorTime(error.timestamp) }}
              </span>
              <span class="error-item__message">{{ error.message }}</span>
            </div>

            <div v-if="recentErrors.length === 0" class="error-item--empty">
              Keine detaillierten Fehlermeldungen verfügbar
            </div>
          </div>

          <p class="health-summary__tip">
            <Lightbulb :size="14" />
            Klicke auf ein Gerät um alle Ereignisse anzuzeigen
          </p>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.health-summary {
  background: var(--glass-bg, rgba(255, 255, 255, 0.03));
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md);
  margin: 0.75rem 1rem;
  padding: 0.75rem 1rem;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  transition: box-shadow 0.3s ease, border-color 0.3s ease;
  position: relative;
}

.health-summary--expanded {
  z-index: var(--z-modal);
}

.health-summary--has-problems {
  border-color: rgba(248, 113, 113, 0.3);
  box-shadow:
    0 0 0 1px rgba(248, 113, 113, 0.1),
    0 0 20px rgba(248, 113, 113, 0.1);
}

.health-summary--all-ok {
  border-color: rgba(34, 197, 94, 0.2);
}

/* Header */
.health-summary__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.health-summary__status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.health-summary__icon--warning {
  color: var(--color-warning);
}

.health-summary__icon--ok {
  color: var(--color-success);
}

.health-summary--has-problems .health-summary__status {
  color: var(--color-text-primary);
}

.health-summary--all-ok .health-summary__status {
  color: var(--color-success);
}

/* Problem Chips */
.health-summary__problems {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
}

/* Diagnose-Chip Zeile (immer sichtbar wenn letzte Diagnose) */
.health-summary__diag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

/* Alert Chips */
.alert-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
  font-family: inherit;
}

.alert-chip--critical {
  color: var(--color-error);
  background: rgba(248, 113, 113, 0.1);
  border-color: rgba(248, 113, 113, 0.2);
}

.alert-chip--critical:hover {
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.3);
}

.alert-chip--warning {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
  border-color: rgba(251, 191, 36, 0.2);
}

.alert-chip--warning:hover {
  background: rgba(251, 191, 36, 0.15);
  border-color: rgba(251, 191, 36, 0.3);
}

/* Diagnostic Chip */
.diag-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  border-radius: var(--radius-sm);
  font-size: 0.75rem;
  font-weight: 600;
  border: 1px solid transparent;
}

.diag-chip--ok {
  color: var(--color-success);
  background: rgba(52, 211, 153, 0.1);
  border-color: rgba(52, 211, 153, 0.2);
}

.diag-chip--warning {
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.1);
  border-color: rgba(251, 191, 36, 0.2);
}

/* Toggle Button - larger for better clickability */
.health-summary__toggle {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.5rem 0.875rem;
  border-radius: var(--radius-md);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--glass-border, rgba(255, 255, 255, 0.08));
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
}

.health-summary__toggle:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
  border-color: rgba(255, 255, 255, 0.15);
}

.health-summary--expanded .health-summary__toggle {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

.health-summary__chevron {
  transition: transform 0.2s ease;
}

.health-summary--expanded .health-summary__chevron {
  transform: rotate(180deg);
}

/* Expand/Collapse animation via grid */
.health-summary__details {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.3s ease;
}

.health-summary--expanded .health-summary__details {
  grid-template-rows: 1fr;
}

.health-summary__details-inner {
  overflow: hidden;
}

/* Expanded chips */
.health-summary__problems--expanded {
  margin-top: 0.75rem;
}

/* Divider */
.health-summary__divider {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin: 1rem 0 0.75rem;
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.health-summary__divider::before,
.health-summary__divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--glass-border, rgba(255, 255, 255, 0.08));
}

/* Error Messages List */
.health-summary__errors {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.error-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border-radius: var(--radius-sm);
  font-size: 0.8125rem;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid transparent;
  border-left: 2px solid transparent;
  transition: background 0.15s ease;
}

.error-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

.error-item--critical,
.error-item--error {
  border-left-color: var(--color-error);
}

.error-item--critical .error-item__icon,
.error-item--error .error-item__icon {
  color: var(--color-error);
}

.error-item--warning {
  border-left-color: var(--color-warning);
}

.error-item--warning .error-item__icon {
  color: var(--color-warning);
}

.error-item--info {
  border-left-color: var(--color-info);
}

.error-item--info .error-item__icon {
  color: var(--color-info);
}

.error-item__icon {
  flex-shrink: 0;
}

.error-item__source {
  color: var(--color-text-secondary);
  font-size: 0.75rem;
  white-space: nowrap;
  flex-shrink: 0;
}

.error-item__message {
  color: var(--color-text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error-item--empty {
  padding: 0.75rem;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 0.8125rem;
}

/* Tip */
.health-summary__tip {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 0.75rem 0 0;
  padding: 0.625rem 0.75rem;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.02);
  font-size: 0.75rem;
  color: var(--color-text-muted);
}

/* Backdrop */
.health-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0);
  z-index: var(--z-modal-backdrop);
  transition: background 0.2s ease;
}

.health-backdrop--visible {
  background: rgba(0, 0, 0, 0.4);
}

/* Fade Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Mobile: Hidden */
@media (max-width: 768px) {
  .health-summary {
    display: none;
  }
}
</style>
