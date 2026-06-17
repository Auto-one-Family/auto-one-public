<script setup lang="ts">
/**
 * QuickAlertPanel — Top-5 active alerts shown as sub-panel in the FAB.
 *
 * Data source: notification-inbox.store.ts (no own fetch).
 * Actions: Ack/Resolve, Navigate (deep-link), Details (expand).
 * Mute: Calls sensorsApi.updateAlertConfig() to suppress alerts per sensor.
 * Footer: "Alle Alerts anzeigen" opens the full NotificationDrawer.
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  BellOff,
  AlertTriangle,
  Clock,
  Info,
  CheckCircle2,
  ShieldCheck,
} from 'lucide-vue-next'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import {
  useAlertCenterStore,
  type AlertLifecycleFailure,
} from '@/shared/stores/alert-center.store'
import { useQuickActionStore } from '@/shared/stores/quickAction.store'
import { useEspStore } from '@/stores/esp'
import { useToast } from '@/composables/useToast'
import { sensorsApi } from '@/api/sensors'
import { formatRelativeTime, severityToStatus } from '@/utils/formatters'
import {
  getNotificationSeverityLabel,
  getNotificationSourceLabel,
  getNotificationCategoryLabel,
} from '@/utils/labels'
import StatusBadge from '@/components/base/StatusBadge.vue'
import { buildEspContextRoute } from '@/utils/notificationNavigation'
import { formatAlertLifecycleFailureMessage } from '@/utils/alertLifecycleUi'
import AlertAuditLines from '@/components/notifications/AlertAuditLines.vue'
import type { NotificationDTO } from '@/api/notifications'

type QuickAlertFilter = 'active' | 'acknowledged' | 'all'

const MAX_ALERTS = 5
const BATCH_ACK_THRESHOLD = 3

/** Snooze duration presets in milliseconds */
const SNOOZE_PRESETS = [
  { key: '1h', label: '1 Stunde', ms: 3_600_000 },
  { key: '4h', label: '4 Stunden', ms: 14_400_000 },
  { key: '24h', label: '24 Stunden', ms: 86_400_000 },
  { key: '1w', label: '1 Woche', ms: 604_800_000 },
  { key: 'permanent', label: 'Permanent', ms: 0 },
] as const

/** Timer update interval for snooze countdown (60 seconds) */
const SNOOZE_TIMER_INTERVAL_MS = 60_000

const router = useRouter()
const inboxStore = useNotificationInboxStore()
const alertStore = useAlertCenterStore()
const quickActionStore = useQuickActionStore()
const espStore = useEspStore()

const { success, error, warning } = useToast()
const expandedId = ref<string | null>(null)
const mutingId = ref<string | null>(null)
const snoozeOpenId = ref<string | null>(null)
const statusFilter = ref<QuickAlertFilter>('active')
const isBatchAcking = ref(false)

/**
 * Map of sensor_config_id → suppression_until ISO string.
 * Loaded lazily when alerts are expanded, updated on snooze.
 */
const suppressionMap = ref<Map<string, string | null>>(new Map())
let snoozeTimerHandle: ReturnType<typeof setInterval> | null = null
const timerTick = ref(0) // reactive trigger for countdown re-computation

const severityOrder: Record<string, number> = {
  critical: 0,
  warning: 1,
  info: 2,
}

/** Filtered alerts based on status filter, sorted by severity priority */
const topAlerts = computed<NotificationDTO[]>(() => {
  let filtered = [...inboxStore.notifications]

  if (statusFilter.value === 'active') {
    filtered = filtered.filter(n => n.status === 'active')
  } else if (statusFilter.value === 'acknowledged') {
    filtered = filtered.filter(n => n.status === 'acknowledged')
  } else {
    filtered = filtered.filter(n => n.status !== 'resolved')
  }

  return filtered
    .sort((a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9))
    .slice(0, MAX_ALERTS)
})

const activeCount = computed(() =>
  inboxStore.notifications.filter(n => n.status === 'active').length
)

const showBatchAck = computed(() =>
  statusFilter.value === 'active' && activeCount.value > BATCH_ACK_THRESHOLD
)

const hasAlerts = computed(() => topAlerts.value.length > 0)


async function handleAck(id: string): Promise<void> {
  const res = await alertStore.acknowledgeAlert(id)
  if (!res.success) {
    error(formatAlertLifecycleFailureMessage(res), { dedupeKey: `qa-ack-${id}` })
  }
}

async function handleResolve(id: string): Promise<void> {
  const res = await alertStore.resolveAlert(id)
  if (!res.success) {
    error(formatAlertLifecycleFailureMessage(res), { dedupeKey: `qa-resolve-${id}` })
  }
}

async function handleBatchAcknowledge(): Promise<void> {
  const activeAlerts = inboxStore.notifications.filter(n => n.status === 'active')
  if (activeAlerts.length === 0) return

  isBatchAcking.value = true
  try {
    let okCount = 0
    let lastFail: AlertLifecycleFailure | null = null

    for (const alert of activeAlerts) {
      const res = await alertStore.acknowledgeAlert(alert.id)
      if (res.success) {
        okCount++
      } else {
        lastFail = res
      }
    }

    if (okCount === activeAlerts.length) {
      success(`${activeAlerts.length} Alerts bestätigt`)
    } else if (okCount === 0 && lastFail) {
      error(formatAlertLifecycleFailureMessage(lastFail), { dedupeKey: 'qa-batch-ack-all-fail' })
    } else if (lastFail) {
      warning(
        `${okCount} von ${activeAlerts.length} Alerts bestätigt. ` +
          formatAlertLifecycleFailureMessage(lastFail),
        { dedupeKey: 'qa-batch-ack-partial' },
      )
    } else {
      error('Fehler beim Bestätigen', { dedupeKey: 'qa-batch-ack-unknown' })
    }
  } finally {
    isBatchAcking.value = false
  }
}

function handleNavigate(notification: NotificationDTO): void {
  const target = buildEspContextRoute(notification, espStore.devices)
  if (!target) return
  void router.push(target)
  quickActionStore.closeMenu()
}

function handleOpenEventDetails(notification: NotificationDTO): void {
  if (!notification.correlation_id) return
  void router.push({
    path: '/system-monitor',
    query: {
      tab: 'events',
      correlation: notification.correlation_id,
    },
  })
  quickActionStore.closeMenu()
}

function toggleExpand(id: string): void {
  expandedId.value = expandedId.value === id ? null : id
}

function formatMeasurementAgeAtAlert(secondsRaw: unknown): string {
  if (typeof secondsRaw !== 'number' || Number.isNaN(secondsRaw) || secondsRaw < 0) {
    return 'Unbekannt'
  }
  const totalSeconds = Math.floor(secondsRaw)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)

  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m`
  return `${totalSeconds}s`
}

function toggleSnoozeDropdown(notificationId: string): void {
  snoozeOpenId.value = snoozeOpenId.value === notificationId ? null : notificationId
}

async function handleSnooze(
  notification: NotificationDTO,
  preset: typeof SNOOZE_PRESETS[number],
): Promise<void> {
  const meta = notification.metadata || {}
  const sensorId = meta.sensor_config_id as string | undefined

  if (!sensorId) {
    error('Sensor-ID nicht verfügbar — Snooze nicht möglich')
    return
  }

  mutingId.value = notification.id
  snoozeOpenId.value = null
  try {
    if (preset.key === 'permanent') {
      await sensorsApi.updateAlertConfig(sensorId, {
        alerts_enabled: false,
        suppression_reason: 'custom',
        suppression_note: 'Permanent stummgeschaltet via Quick Alert Panel',
      })
      suppressionMap.value.set(sensorId, null)
      success('Sensor-Alerts permanent stummgeschaltet')
    } else {
      const until = new Date(Date.now() + preset.ms).toISOString()
      await sensorsApi.updateAlertConfig(sensorId, {
        alerts_enabled: false,
        suppression_until: until,
        suppression_reason: 'custom',
        suppression_note: `Snooze ${preset.label} via Quick Alert Panel`,
      })
      suppressionMap.value.set(sensorId, until)
      success(`Sensor-Alerts für ${preset.label} stummgeschaltet`)
    }
    await handleAck(notification.id)
  } catch (e) {
    error(e instanceof Error ? e.message : 'Fehler beim Stummschalten')
  } finally {
    mutingId.value = null
  }
}

/** Load suppression_until for a sensor from the alert-config API */
async function loadSuppressionInfo(sensorId: string): Promise<void> {
  if (suppressionMap.value.has(sensorId)) return
  try {
    const config = await sensorsApi.getAlertConfig(sensorId)
    const until = (config.alert_config?.suppression_until as string) ?? null
    suppressionMap.value.set(sensorId, until)
  } catch {
    // Silent fail — timer just won't show
  }
}

/** Get the suppression_until for a notification's sensor (if available) */
function getSuppressionUntil(notification: NotificationDTO): string | null {
  const sensorId = (notification.metadata?.sensor_config_id as string) ?? ''
  return suppressionMap.value.get(sensorId) ?? null
}

/**
 * Format remaining snooze time as human-readable string.
 * Uses timerTick for reactivity (re-computed every 60s).
 */
function formatTimeRemaining(until: string): string {
  // Access timerTick to create reactive dependency
  void timerTick.value
  const remaining = new Date(until).getTime() - Date.now()
  if (remaining <= 0) return 'Läuft ab...'

  const hours = Math.floor(remaining / 3_600_000)
  const minutes = Math.floor((remaining % 3_600_000) / 60_000)

  if (hours > 24) return `${Math.floor(hours / 24)}d ${hours % 24}h`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}

function handleExpandAndLoad(id: string, notification: NotificationDTO): void {
  toggleExpand(id)
  // Lazy-load suppression info when expanding
  if (expandedId.value === id) {
    const sensorId = (notification.metadata?.sensor_config_id as string) ?? ''
    if (sensorId) {
      loadSuppressionInfo(sensorId)
    }
  }
}

// Lifecycle: start/stop timer for snooze countdowns
onMounted(() => {
  snoozeTimerHandle = setInterval(() => {
    timerTick.value++
  }, SNOOZE_TIMER_INTERVAL_MS)
})

onUnmounted(() => {
  if (snoozeTimerHandle) {
    clearInterval(snoozeTimerHandle)
    snoozeTimerHandle = null
  }
})

function handleBack(): void {
  quickActionStore.setActivePanel('menu')
}

function handleShowAll(): void {
  quickActionStore.closeMenu()
  inboxStore.openDrawerWithActiveAlertsFocus()
}
</script>

<template>
  <div
    class="qa-alert-panel"
    role="region"
    aria-label="Quick Alerts"
    data-testid="quick-alert-panel"
  >
    <!-- Header -->
    <div class="qa-alert-panel__header">
      <button
        class="qa-alert-panel__back"
        aria-label="Zurück"
        data-testid="quick-alert-back"
        @click="handleBack"
      >
        <ArrowLeft class="qa-alert-panel__back-icon" />
      </button>
      <span class="qa-alert-panel__title">Alerts</span>
      <span v-if="activeCount > 0" class="qa-alert-panel__count">
        {{ activeCount > 99 ? '99+' : activeCount }}
      </span>
    </div>

    <!-- Status Filter Chips -->
    <div class="qa-alert-panel__filters">
      <button
        :class="['qa-alert-panel__filter', { 'qa-alert-panel__filter--active': statusFilter === 'active' }]"
        data-testid="quick-alert-filter-active"
        @click="statusFilter = 'active'"
      >
        Aktiv
      </button>
      <button
        :class="['qa-alert-panel__filter', { 'qa-alert-panel__filter--active': statusFilter === 'acknowledged' }]"
        data-testid="quick-alert-filter-acknowledged"
        @click="statusFilter = 'acknowledged'"
      >
        Bestätigt
      </button>
      <button
        :class="['qa-alert-panel__filter', { 'qa-alert-panel__filter--active': statusFilter === 'all' }]"
        data-testid="quick-alert-filter-all"
        @click="statusFilter = 'all'"
      >
        Alle
      </button>

      <!-- Batch Acknowledge -->
      <button
        v-if="showBatchAck"
        class="qa-alert-panel__batch-ack"
        data-testid="quick-alert-batch-ack"
        :disabled="isBatchAcking"
        title="Alle aktiven Alerts bestätigen"
        @click.stop="handleBatchAcknowledge"
      >
        <ShieldCheck class="qa-alert-panel__batch-icon" />
        {{ isBatchAcking ? '...' : 'Alle' }}
      </button>
    </div>

    <!-- Alert List -->
    <div v-if="hasAlerts" class="qa-alert-panel__list" data-testid="quick-alert-list">
      <div
        v-for="alert in topAlerts"
        :key="alert.id"
        class="alert-item"
        :data-testid="`quick-alert-row-${alert.id}`"
        :class="{ 'alert-item--expanded': expandedId === alert.id }"
      >
        <!-- Main Row -->
        <div class="alert-item__row">
          <StatusBadge :level="severityToStatus(alert.severity)" compact />
          <div class="alert-item__content">
            <span class="alert-item__title">{{ alert.title }}</span>
            <span class="alert-item__meta">
              <span v-if="alert.metadata?.zone_name" class="alert-item__zone">
                {{ alert.metadata.zone_name }}
              </span>
              <span class="alert-item__time">{{ formatRelativeTime(alert.created_at) }}</span>
            </span>
          </div>
          <div class="alert-item__actions">
            <button
              v-if="alert.status === 'active'"
              class="alert-item__action alert-item__action--ack"
              :data-testid="`quick-alert-ack-${alert.id}`"
              title="Bestätigen (Acknowledge)"
              @click.stop="handleAck(alert.id)"
            >
              <ShieldCheck class="alert-item__action-icon" />
            </button>
            <button
              v-if="alert.status === 'active' || alert.status === 'acknowledged'"
              class="alert-item__action alert-item__action--resolve"
              :data-testid="`quick-alert-resolve-${alert.id}`"
              title="Erledigen (Resolve)"
              @click.stop="handleResolve(alert.id)"
            >
              <CheckCheck class="alert-item__action-icon" />
            </button>
            <button
              v-if="alert.metadata?.esp_id"
              class="alert-item__action"
              title="Zum Gerät anzeigen"
              @click.stop="handleNavigate(alert)"
            >
              <ExternalLink class="alert-item__action-icon" />
            </button>
            <button
              class="alert-item__action"
              title="Details"
              @click.stop="handleExpandAndLoad(alert.id, alert)"
            >
              <ChevronDown v-if="expandedId !== alert.id" class="alert-item__action-icon" />
              <ChevronUp v-else class="alert-item__action-icon" />
            </button>
          </div>
        </div>

        <!-- Expanded Details -->
        <Transition name="alert-expand">
          <div v-if="expandedId === alert.id" class="alert-item__details">
            <div v-if="alert.body" class="alert-item__body">{{ alert.body }}</div>
            <div class="alert-item__detail-grid">
              <AlertAuditLines
                :acknowledged-at="alert.acknowledged_at"
                :acknowledged-by="alert.acknowledged_by"
                :resolved-at="alert.resolved_at"
              />
              <div v-if="alert.severity" class="alert-item__detail">
                <component
                  :is="alert.severity === 'critical' || alert.severity === 'warning' ? AlertTriangle : Info"
                  class="alert-item__detail-icon"
                />
                <span class="alert-item__detail-label">{{ getNotificationSeverityLabel(alert.severity) }}</span>
              </div>
              <div v-if="alert.source" class="alert-item__detail">
                <span class="alert-item__detail-text">Quelle: {{ getNotificationSourceLabel(alert.source) }}</span>
              </div>
              <div v-if="alert.category" class="alert-item__detail">
                <span class="alert-item__detail-text">Kategorie: {{ getNotificationCategoryLabel(alert.category) }}</span>
              </div>
              <div v-if="alert.metadata?.esp_id" class="alert-item__detail">
                <span class="alert-item__detail-text">ESP: {{ alert.metadata.esp_id }}</span>
              </div>
              <div v-if="alert.correlation_id" class="alert-item__detail">
                <span class="alert-item__detail-text">Korrelation: {{ alert.correlation_id }}</span>
              </div>
              <div
                v-if="typeof alert.metadata?.measurement_age_seconds === 'number' && alert.metadata?.operating_mode !== 'continuous'"
                class="alert-item__detail"
              >
                <span class="alert-item__detail-text">
                  Messwertalter beim Alert: {{ formatMeasurementAgeAtAlert(alert.metadata?.measurement_age_seconds) }}
                </span>
              </div>
            </div>
            <button
              v-if="alert.correlation_id"
              class="alert-item__action alert-item__action--details-link"
              title="Im Ereignis-Monitor anzeigen"
              @click.stop="handleOpenEventDetails(alert)"
            >
              <ExternalLink class="alert-item__action-icon" />
              Ereignis-Details
            </button>
            <!-- Snooze Timer: show remaining suppression time -->
            <div
              v-if="getSuppressionUntil(alert)"
              class="alert-item__snooze-timer"
            >
              <Clock class="alert-item__snooze-timer-icon" />
              <span>Snooze: {{ formatTimeRemaining(getSuppressionUntil(alert)!) }}</span>
            </div>
            <!-- Snooze: suppress sensor alerts with timed presets -->
            <div class="alert-item__snooze-wrapper">
              <button
                class="alert-item__mute"
                :class="{ 'alert-item__mute--active': alert.metadata?.sensor_config_id }"
                :disabled="!alert.metadata?.sensor_config_id || mutingId === alert.id"
                :title="alert.metadata?.sensor_config_id ? 'Sensor-Alerts stummschalten' : 'Sensor-ID nicht verfügbar'"
                @click.stop="toggleSnoozeDropdown(alert.id)"
              >
                <BellOff class="alert-item__mute-icon" />
                <span>{{ mutingId === alert.id ? 'Wird stummgeschaltet...' : 'Stummschalten' }}</span>
                <ChevronDown v-if="snoozeOpenId !== alert.id" class="alert-item__mute-icon" />
                <ChevronUp v-else class="alert-item__mute-icon" />
              </button>
              <!-- Snooze Dropdown -->
              <Transition name="alert-expand">
                <div v-if="snoozeOpenId === alert.id" class="alert-item__snooze-dropdown">
                  <button
                    v-for="preset in SNOOZE_PRESETS"
                    :key="preset.key"
                    class="alert-item__snooze-option"
                    @click.stop="handleSnooze(alert, preset)"
                  >
                    {{ preset.label }}
                  </button>
                </div>
              </Transition>
            </div>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="qa-alert-panel__empty" data-testid="quick-alert-empty">
      <CheckCircle2 class="qa-alert-panel__empty-icon" />
      <span>Keine aktiven Alerts</span>
    </div>

    <!-- Footer -->
    <button
      class="qa-alert-panel__footer"
      data-testid="quick-alert-show-all"
      @click="handleShowAll"
    >
      Alle Alerts anzeigen &rarr;
    </button>
  </div>
</template>

<style scoped>
/* ═══════════════════════════════════════════════════════════════════════════
   QUICK ALERT PANEL — Sub-panel inside the FAB
   ═══════════════════════════════════════════════════════════════════════════ */

.qa-alert-panel {
  position: absolute;
  bottom: calc(100% + var(--space-2));
  right: 0;
  width: 320px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-md);
  background: rgba(20, 20, 30, 0.9);
  -webkit-backdrop-filter: blur(16px);
  backdrop-filter: blur(16px);
  border: 1px solid var(--glass-border);
  box-shadow: var(--elevation-floating);
  transform-origin: bottom right;
  overflow: hidden;
}

/* ── Header ── */

.qa-alert-panel__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.qa-alert-panel__back {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qa-alert-panel__back:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
}

.qa-alert-panel__back-icon {
  width: 14px;
  height: 14px;
}

.qa-alert-panel__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-primary);
  flex: 1;
}

.qa-alert-panel__count {
  font-size: var(--text-xs);
  font-weight: 700;
  color: white;
  background: var(--color-error);
  border-radius: var(--radius-full);
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

/* ── Status Filter Chips ── */

.qa-alert-panel__filters {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.qa-alert-panel__filter {
  padding: 2px var(--space-2);
  font-size: var(--text-xxs);
  font-weight: 500;
  color: var(--color-text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.qa-alert-panel__filter:hover {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
}

.qa-alert-panel__filter--active {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border);
}

.qa-alert-panel__batch-ack {
  display: flex;
  align-items: center;
  gap: 3px;
  margin-left: auto;
  padding: 2px var(--space-2);
  font-size: var(--text-xxs);
  font-weight: 600;
  color: var(--color-warning);
  background: transparent;
  border: 1px solid rgba(251, 191, 36, 0.2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.qa-alert-panel__batch-ack:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.08);
  border-color: rgba(251, 191, 36, 0.3);
}

.qa-alert-panel__batch-ack:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.qa-alert-panel__batch-icon {
  width: 11px;
  height: 11px;
}

/* ── Alert List ── */

.qa-alert-panel__list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-1);
}

/* ── Alert Item ── */

.alert-item {
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.alert-item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.alert-item__row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2);
}

.alert-item__dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: var(--radius-full);
  margin-top: 5px;
}

.alert-item__dot--critical {
  background: var(--color-error);
  box-shadow: 0 0 6px rgba(248, 113, 113, 0.5);
}

.alert-item__dot--warning {
  background: var(--color-warning);
  box-shadow: 0 0 4px rgba(251, 191, 36, 0.4);
}

.alert-item__dot--info {
  background: var(--color-info);
}

.alert-item__content {
  flex: 1;
  min-width: 0;
}

.alert-item__title {
  display: block;
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.alert-item__meta {
  display: flex;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: 2px;
}

.alert-item__zone {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 100px;
}

.alert-item__actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
}

.alert-item__action {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--radius-sm);
  border: none;
  background: transparent;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.alert-item__action:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.08);
}

.alert-item__action--ack {
  color: var(--color-warning);
}

.alert-item__action--ack:hover {
  background: rgba(251, 191, 36, 0.12);
}

.alert-item__action--resolve {
  color: var(--color-success);
}

.alert-item__action--resolve:hover {
  background: rgba(52, 211, 153, 0.12);
}

.alert-item__action--details-link {
  width: auto;
  padding: 0 var(--space-2);
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.alert-item__action-icon {
  width: 13px;
  height: 13px;
}

/* ── Expanded Details ── */

.alert-item__details {
  padding: 0 var(--space-2) var(--space-2) calc(var(--space-2) + 8px + var(--space-2));
}

.alert-item__body {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.4;
  margin-bottom: var(--space-2);
}

.alert-item__detail-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1) var(--space-3);
  margin-bottom: var(--space-2);
}

.alert-item__detail {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xxs);
  color: var(--color-text-muted);
}

.alert-item__detail-icon {
  width: 11px;
  height: 11px;
}

.alert-item__detail-label {
  text-transform: capitalize;
}

.alert-item__detail-text {
  font-family: var(--font-mono);
}

.alert-item__mute {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: transparent;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
  cursor: not-allowed;
  opacity: 0.4;
  transition: all var(--transition-fast);
}

.alert-item__mute--active {
  cursor: pointer;
  opacity: 1;
}

.alert-item__mute--active:hover {
  border-color: var(--color-warning);
  color: var(--color-warning);
  background: rgba(251, 191, 36, 0.08);
}

.alert-item__mute-icon {
  width: 12px;
  height: 12px;
}

/* ── Snooze Timer ── */

.alert-item__snooze-timer {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.2);
  color: var(--color-warning);
  font-size: var(--text-xs);
  margin-bottom: var(--space-1);
}

.alert-item__snooze-timer-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

/* ── Snooze Dropdown ── */

.alert-item__snooze-wrapper {
  position: relative;
}

.alert-item__snooze-dropdown {
  display: flex;
  flex-direction: column;
  margin-top: var(--space-1);
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
  background: rgba(20, 20, 30, 0.95);
  overflow: hidden;
}

.alert-item__snooze-option {
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  text-align: left;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.alert-item__snooze-option:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-primary);
}

.alert-item__snooze-option:not(:last-child) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
}

.alert-item__snooze-option:last-child {
  color: var(--color-text-muted);
  font-style: italic;
}

/* ── Empty State ── */

.qa-alert-panel__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-6) var(--space-4);
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.qa-alert-panel__empty-icon {
  width: 24px;
  height: 24px;
  color: var(--color-success);
  opacity: 0.6;
}

/* ── Footer ── */

.qa-alert-panel__footer {
  display: block;
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  border-top: 1px solid var(--glass-border);
  background: transparent;
  color: var(--color-iridescent-1);
  font-size: var(--text-xs);
  font-weight: 500;
  text-align: center;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.qa-alert-panel__footer:hover {
  background: rgba(255, 255, 255, 0.04);
  color: var(--color-iridescent-2);
}

/* ── Expand Transition ── */

.alert-expand-enter-active {
  transition: all var(--duration-fast) var(--ease-out);
}

.alert-expand-leave-active {
  transition: all var(--duration-fast) var(--ease-in-out);
}

.alert-expand-enter-from,
.alert-expand-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
