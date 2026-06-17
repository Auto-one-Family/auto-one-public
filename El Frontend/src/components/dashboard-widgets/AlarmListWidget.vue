<script setup lang="ts">
/**
 * AlarmListWidget — Active alarms and warnings for dashboard
 *
 * Data source: alert-center.store (activeAlertsFromInbox) — persistierte Notifications
 * aus der API. Gleiche Quelle wie QuickAlertPanel und NotificationDrawer.
 *
 * Zeigt Alerts mit status active/acknowledged (optional resolved).
 * Chronologische Liste (neueste zuerst), sortiert nach Severity.
 * Min-size: 4x4
 *
 * @see Alert-Basis 1 — AlarmListWidget auf Notification-API umstellen
 */
import { computed } from 'vue'
import { useAlertCenterStore } from '@/shared/stores/alert-center.store'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useEspStore } from '@/stores/esp'
import { Bell, AlertTriangle, AlertCircle } from 'lucide-vue-next'
import { formatRelativeTime } from '@/utils/formatters'
import type { NotificationDTO } from '@/api/notifications'

interface Props {
  maxItems?: number
  showResolved?: boolean
  zoneFilter?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  maxItems: 20,
  showResolved: false,
  zoneFilter: null,
})

const alertCenterStore = useAlertCenterStore()
const inboxStore = useNotificationInboxStore()
const espStore = useEspStore()

/** Severity order: critical first, then warning, then info */
const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  warning: 1,
  info: 2,
}

/** Filtered and sorted alerts from notification API (persistierte Notifications) */
const alarms = computed<NotificationDTO[]>(() => {
  let items = alertCenterStore.activeAlertsFromInbox

  if (props.showResolved) {
    items = inboxStore.notifications.filter(
      (n) =>
        n.status === 'active' ||
        n.status === 'acknowledged' ||
        n.status === 'resolved',
    )
  }

  if (props.zoneFilter) {
    items = items.filter((n) => {
      const meta = n.metadata || {}
      const zoneId = meta.zone_id as string | undefined
      if (zoneId) return zoneId === props.zoneFilter
      const espId = meta.esp_id as string | undefined
      if (espId) {
        const device = espStore.devices.find((d) => espStore.getDeviceId(d) === espId)
        return device?.zone_id === props.zoneFilter
      }
      return false
    })
  }

  const sorted = [...items].sort((a, b) => {
    const orderA = SEVERITY_ORDER[a.severity] ?? 9
    const orderB = SEVERITY_ORDER[b.severity] ?? 9
    if (orderA !== orderB) return orderA - orderB
    const tA = a.created_at ? new Date(a.created_at).getTime() : 0
    const tB = b.created_at ? new Date(b.created_at).getTime() : 0
    return tB - tA
  })

  return sorted.slice(0, props.maxItems)
})

const alarmCount = computed(() =>
  alarms.value.filter((a) => a.severity === 'critical').length,
)

function severityDisplay(severity: string): 'alarm' | 'warning' {
  return severity === 'critical' ? 'alarm' : 'warning'
}

/** "Zum Alert" — öffnet NotificationDrawer für Ack/Resolve */
function openNotificationDrawer(): void {
  inboxStore.isDrawerOpen = true
}
</script>

<template>
  <div class="alarm-widget">
    <!-- Alarm Count Badge -->
    <div v-if="alarmCount > 0" class="alarm-widget__badge-bar">
      <span class="alarm-widget__badge">{{ alarmCount }} aktive Alarme</span>
    </div>

    <!-- Alarm List -->
    <div v-if="alarms.length > 0" class="alarm-widget__list">
      <button
        v-for="alarm in alarms"
        :key="alarm.id"
        type="button"
        :class="[
          'alarm-widget__item',
          `alarm-widget__item--${severityDisplay(alarm.severity)}`,
          alarm.status === 'resolved' ? 'alarm-widget__item--resolved' : '',
        ]"
        @click="openNotificationDrawer"
      >
        <component
          :is="
            alarm.severity === 'critical' ? AlertCircle : AlertTriangle
          "
          class="alarm-widget__icon w-3.5 h-3.5"
        />
        <div class="alarm-widget__content">
          <div class="alarm-widget__header">
            <span class="alarm-widget__sensor">{{ alarm.title }}</span>
            <span class="alarm-widget__time">{{
              formatRelativeTime(alarm.created_at)
            }}</span>
          </div>
          <div v-if="alarm.body" class="alarm-widget__detail">
            <span class="alarm-widget__value">{{ alarm.body }}</span>
          </div>
          <div
            v-else-if="alarm.metadata?.value != null"
            class="alarm-widget__detail"
          >
            <span class="alarm-widget__value">
              {{ alarm.metadata.value }}
              {{ alarm.metadata.unit ?? '' }}
            </span>
            <span
              v-if="alarm.metadata?.zone_name"
              class="alarm-widget__zone"
            >
              {{ alarm.metadata.zone_name }}
            </span>
          </div>
        </div>
      </button>
    </div>

    <!-- Empty State -->
    <div v-else class="alarm-widget__empty">
      <Bell class="w-6 h-6" style="opacity: 0.3" />
      <span>Keine aktiven Alerts</span>
      <span class="alarm-widget__empty-sub"
        >Alle Alerts werden hier angezeigt</span
      >
      <button
        type="button"
        class="alarm-widget__link"
        @click="openNotificationDrawer"
      >
        Benachrichtigungen öffnen
      </button>
    </div>
  </div>
</template>

<style scoped>
.alarm-widget {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.alarm-widget__badge-bar {
  display: flex;
  padding: var(--space-1) var(--space-2);
  flex-shrink: 0;
}

.alarm-widget__badge {
  font-size: var(--text-xs);
  font-weight: 700;
  color: var(--color-error);
  background: var(--color-zone-alarm, rgba(248, 113, 113, 0.1));
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-sm);
}

.alarm-widget__list {
  flex: 1;
  overflow-y: auto;
  padding: 0 var(--space-1);
}

.alarm-widget__item {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-2);
  border-radius: var(--radius-sm);
  margin-bottom: 2px;
  border-left: 2px solid transparent;
  width: 100%;
  text-align: left;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font: inherit;
  transition: background 0.15s;
}

.alarm-widget__item:hover {
  background: rgba(255, 255, 255, 0.03);
}

.alarm-widget__item--alarm {
  border-left-color: var(--color-error);
  background: rgba(248, 113, 113, 0.04);
}

.alarm-widget__item--alarm .alarm-widget__icon {
  color: var(--color-error);
}

.alarm-widget__item--warning {
  border-left-color: var(--color-warning);
  background: rgba(251, 191, 36, 0.04);
}

.alarm-widget__item--warning .alarm-widget__icon {
  color: var(--color-warning);
}

.alarm-widget__item--resolved {
  opacity: 0.5;
}

.alarm-widget__item--resolved .alarm-widget__sensor,
.alarm-widget__item--resolved .alarm-widget__value {
  text-decoration: line-through;
}

.alarm-widget__content {
  flex: 1;
  min-width: 0;
}

.alarm-widget__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-1);
}

.alarm-widget__sensor {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.alarm-widget__time {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.alarm-widget__detail {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-1);
}

.alarm-widget__value {
  font-size: var(--text-xs);
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
}

.alarm-widget__zone {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  background: var(--color-bg-quaternary);
  padding: var(--space-1) var(--space-1);
  border-radius: var(--radius-sm);
}

.alarm-widget__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  height: 100%;
  color: var(--color-text-muted);
  font-size: var(--text-sm);
}

.alarm-widget__empty-sub {
  font-size: var(--text-xs);
  opacity: 0.6;
}

.alarm-widget__link {
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-iridescent-2);
  background: none;
  border: none;
  cursor: pointer;
  text-decoration: underline;
  padding: 0;
}

.alarm-widget__link:hover {
  color: var(--color-iridescent-1);
}

.alarm-widget__icon {
  flex-shrink: 0;
  margin-top: 1px;
}
</style>
