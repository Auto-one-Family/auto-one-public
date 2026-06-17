<script setup lang="ts">
/**
 * NotificationDrawer — Slide-in inbox panel
 *
 * Uses SlideOver.vue primitive (width="lg" = 560px).
 * Features:
 * - Header: Title + Settings gear + "Alle gelesen" button
 * - Filter tabs: Alle | Kritisch | Warnungen | Infos
 * - Grouped by Heute/Gestern/Älter
 * - Lazy loading: first 50, then "Mehr laden" button
 * - ESC and click-outside close (SlideOver feature)
 */

import { ref, computed, watch } from 'vue'
import { Settings, CheckCheck, ChevronDown, ChevronUp, Filter, Bell, BellOff, Activity, SlidersHorizontal } from 'lucide-vue-next'
import SlideOver from '@/shared/design/primitives/SlideOver.vue'
import NotificationItem from '@/components/notifications/NotificationItem.vue'
import NotificationPreferences from '@/components/notifications/NotificationPreferences.vue'
import {
  useNotificationInboxStore,
  type SourceFilterValue,
} from '@/shared/stores/notification-inbox.store'
import { useAlertCenterStore, STATS_POLL_INTERVAL_MS } from '@/shared/stores/alert-center.store'
import { formatRelativeTime } from '@/utils/formatters'
import { useToast } from '@/composables/useToast'
import { formatAlertLifecycleFailureMessage } from '@/utils/alertLifecycleUi'

const inboxStore = useNotificationInboxStore()
const alertStore = useAlertCenterStore()
const toast = useToast()

const isResolvingAll = ref(false)
const advancedSourcesOpen = ref(false)
const settingsOpen = ref(false)
const sourceSearchQuery = ref('')

/** Source filter chips for the collapsed advanced section */
const sourceChips: { value: SourceFilterValue; label: string }[] = [
  { value: null, label: 'Alle Quellen' },
  { value: 'sensor_threshold', label: 'Sensor' },
  { value: 'grafana', label: 'Infrastruktur' },
  { value: 'mqtt_handler', label: 'Aktor' },
  { value: 'logic_engine', label: 'Regel' },
  { value: 'ai_anomaly_service', label: 'KI-Anomalie' },
  { value: 'freshness_reminder', label: 'Frische' },
  { value: 'calibration_reminder', label: 'Kalibrierung' },
  { value: '__system__', label: 'System' },
]

/** Filter chips by search query */
const filteredSourceChips = computed(() => {
  const q = sourceSearchQuery.value.trim().toLowerCase()
  if (!q) return sourceChips
  return sourceChips.filter(c => c.label.toLowerCase().includes(q))
})

/** Segmented control: Aktiv / Bestätigt / Erledigt */
const segmentTabs = computed(() => {
  const stats = alertStore.alertStats
  const active = stats?.active_count ?? 0
  const ack = stats?.acknowledged_count ?? 0
  return [
    { key: 'active' as const, label: 'Aktiv', count: active },
    { key: 'acknowledged' as const, label: 'Bestätigt', count: ack },
    { key: 'resolved' as const, label: 'Erledigt', count: 0 },
  ]
})

function setSegmentFilter(key: 'active' | 'acknowledged' | 'resolved'): void {
  inboxStore.lifecycleFilter = key
  void inboxStore.reloadListForFilters()
}

/** Severity sort order for display */
const SEVERITY_ORDER: Record<string, number> = { critical: 0, warning: 1, info: 2 }

/** Notifications sorted by severity desc, then created_at desc within each date group */
const sortedGroupedNotifications = computed(() =>
  inboxStore.groupedNotifications.map(group => ({
    ...group,
    items: [...group.items].sort((a, b) => {
      const sa = SEVERITY_ORDER[a.severity] ?? 3
      const sb = SEVERITY_ORDER[b.severity] ?? 3
      if (sa !== sb) return sa - sb
      return new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime()
    }),
  }))
)

/** Reload list when showSuppressed changes */
watch(() => inboxStore.showSuppressed, () => {
  void inboxStore.reloadListForFilters()
})

/** P3: KPI-Tabs nutzen gepollte Server-Stats; Liste unread/WS kann schneller sein. */
const syncHintLine = computed(() => {
  const t = alertStore.statsSyncedAt
  const kpi = t != null ? `KPI-Tabs: zuletzt ${formatRelativeTime(new Date(t))}` : 'KPI-Tabs: noch nicht synchronisiert'
  return `Liste Live (WebSocket). ${kpi}.`
})

/** Liste/Zähler neuer als letzte KPI-Sync → kurzer Degrade-Hinweis (Polling-Intervall). */
const listAheadOfKpiStats = computed(() => {
  const a = alertStore.statsSyncedAt
  const b = inboxStore.inboxLiveTouchedAt
  if (a == null || b == null) return false
  return b > a + 1500
})

const kpiPollHuman = computed(() => {
  const s = Math.round(STATS_POLL_INTERVAL_MS / 1000)
  return `${s}s`
})

function handleClose(): void {
  inboxStore.isDrawerOpen = false
}

function handleMarkRead(id: string): void {
  inboxStore.markAsRead(id)
}

async function handleResolveAll(): Promise<void> {
  if (isResolvingAll.value || alertStore.unresolvedCount === 0) return
  isResolvingAll.value = true
  try {
    const res = await alertStore.resolveAllAlerts()
    if (!res.success) {
      toast.show({
        type: 'error',
        message: formatAlertLifecycleFailureMessage(res),
        dedupeKey: 'resolve-all-alerts-failed',
      })
      return
    }
    await inboxStore.loadInitial()
  } finally {
    isResolvingAll.value = false
  }
}

async function handleAcknowledge(id: string): Promise<void> {
  const res = await alertStore.acknowledgeAlert(id)
  if (!res.success) {
    toast.show({
      type: 'error',
      message: formatAlertLifecycleFailureMessage(res),
      dedupeKey: `ack-alert-${id}`,
    })
  }
}

async function handleResolve(id: string): Promise<void> {
  const res = await alertStore.resolveAlert(id)
  if (!res.success) {
    toast.show({
      type: 'error',
      message: formatAlertLifecycleFailureMessage(res),
      dedupeKey: `resolve-alert-${id}`,
    })
  }
}

</script>

<template>
  <SlideOver
    :open="inboxStore.isDrawerOpen"
    title="Benachrichtigungen"
    subtitle="Server-Inbox (Ack/Resolve). Echtzeit-Fehler (error_event) nur als Toast — nicht diese Liste."
    width="lg"
    @close="handleClose"
  >
    <!-- Custom header actions (injected via default slot, header area) -->
    <template #default>
      <div class="drawer__panel-root" data-testid="notification-drawer-panel">
      <!-- Header Actions Row -->
      <div class="drawer__header-actions">
      <!-- Segmented Control: Aktiv / Bestätigt / Erledigt -->
      <div class="drawer__primary-toolbar">
        <div
          class="drawer__segment-control"
          role="tablist"
          aria-label="Alert-Status-Filter"
        >
          <button
            v-for="seg in segmentTabs"
            :key="seg.key"
            type="button"
            role="tab"
            :aria-selected="inboxStore.lifecycleFilter === seg.key"
            :data-testid="`notification-segment-${seg.key}`"
            :class="[
              'drawer__segment',
              { 'drawer__segment--active': inboxStore.lifecycleFilter === seg.key },
            ]"
            @click="setSegmentFilter(seg.key)"
          >
            {{ seg.label }}
            <!-- AUT-628: Aktiv-Tab badge colored by highest severity of active alerts -->
            <span
              v-if="seg.count > 0"
              :class="[
                'drawer__segment-badge',
                seg.key === 'active' && alertStore.hasCritical
                  ? 'drawer__segment-badge--critical'
                  : seg.key === 'active' && alertStore.warningCount > 0
                    ? 'drawer__segment-badge--warning'
                    : '',
              ]"
              aria-hidden="true"
            >{{ seg.count }}</span>
          </button>
        </div>
        <!-- Settings: suppressed-toggle hinter diesem Icon -->
        <div class="drawer__settings-wrap">
          <button
            type="button"
            class="drawer__settings-btn"
            :aria-expanded="settingsOpen"
            :title="settingsOpen ? 'Einstellungen schließen' : 'Erweiterte Einstellungen'"
            data-testid="notification-settings-toggle"
            @click="settingsOpen = !settingsOpen"
          >
            <SlidersHorizontal :size="14" aria-hidden="true" />
          </button>
          <div v-if="settingsOpen" class="drawer__settings-popover">
            <label class="drawer__suppressed-label">
              <input
                v-model="inboxStore.showSuppressed"
                type="checkbox"
                class="drawer__suppressed-checkbox"
                data-testid="notification-show-suppressed"
              />
              <BellOff :size="12" aria-hidden="true" class="drawer__suppressed-icon" />
              Auch unterdrückte Alerts anzeigen
            </label>
          </div>
        </div>
      </div>

      <div class="drawer__actions-row">
          <button
            type="button"
            class="drawer__action-btn"
            title="Alle aktiven Alerts erledigen"
            data-testid="notification-resolve-all"
            :disabled="alertStore.unresolvedCount === 0 || isResolvingAll"
            @click="handleResolveAll"
          >
            <CheckCheck class="drawer__action-icon" />
            <span class="drawer__action-label">
              {{ isResolvingAll ? 'Erledige...' : 'Alle erledigen' }}
            </span>
          </button>
          <button
            type="button"
            class="drawer__action-btn"
            title="Einstellungen"
            aria-label="Benachrichtigungseinstellungen öffnen"
            data-testid="notification-preferences-button"
            @click="inboxStore.openPreferences()"
          >
            <Settings class="drawer__action-icon" />
          </button>
        </div>
      </div>

      <!-- Quelle filtern: collapsed by default, search + chips -->
      <div class="drawer__advanced">
        <button
          type="button"
          class="drawer__advanced-toggle"
          :aria-expanded="advancedSourcesOpen"
          aria-controls="notification-advanced-sources"
          data-testid="notification-advanced-toggle"
          @click="advancedSourcesOpen = !advancedSourcesOpen"
        >
          <Filter class="drawer__advanced-icon" />
          <span class="drawer__advanced-label">Quelle filtern</span>
          <span
            v-if="inboxStore.sourceFilter !== null"
            class="drawer__advanced-badge"
            aria-hidden="true"
          >
            1
          </span>
          <component
            :is="advancedSourcesOpen ? ChevronUp : ChevronDown"
            class="drawer__advanced-chevron"
          />
        </button>
        <div
          v-show="advancedSourcesOpen"
          id="notification-advanced-sources"
        >
          <div class="drawer__source-search">
            <input
              v-model="sourceSearchQuery"
              type="search"
              class="drawer__source-input"
              placeholder="Quelle suchen…"
              aria-label="Quell-Filter suchen"
            />
          </div>
          <div class="drawer__source-chips">
            <button
              v-for="chip in filteredSourceChips"
              :key="chip.value ?? 'all'"
              type="button"
              :class="[
                'drawer__source-chip',
                { 'drawer__source-chip--active': inboxStore.sourceFilter === chip.value },
              ]"
              @click="inboxStore.setSourceFilter(chip.value)"
            >
              {{ chip.label }}
            </button>
          </div>
        </div>
      </div>

      <!-- P3: Poll vs. WebSocket — Operator-Hinweis -->
      <p
        class="drawer__sync-hint"
        data-testid="notification-drawer-sync-hint"
        role="status"
      >
        <Activity class="drawer__sync-hint-icon" :size="12" aria-hidden="true" />
        <span class="drawer__sync-hint-text">{{ syncHintLine }}</span>
        <span v-if="listAheadOfKpiStats" class="drawer__sync-hint-lag">
          Tab-Zähler können bis zu {{ kpiPollHuman }} hinter der Liste liegen.
        </span>
      </p>

      <!-- Notification List -->
      <div class="drawer__list">
        <!-- Loading State -->
        <div v-if="inboxStore.isLoading && inboxStore.notifications.length === 0" class="drawer__loading">
          <span class="drawer__loading-text">Lade Benachrichtigungen...</span>
        </div>

        <!-- Empty State -->
        <div
          v-else-if="inboxStore.groupedNotifications.length === 0"
          class="drawer__empty"
          data-testid="notification-drawer-empty"
        >
          <Bell class="drawer__empty-icon" aria-hidden="true" />
          <!-- AUT-610: lifecycle-aware empty state text, never shown alongside alert list -->
          <span class="drawer__empty-text">
            {{ inboxStore.lifecycleFilter === 'active' ? 'Keine aktiven Alarme'
              : inboxStore.lifecycleFilter === 'acknowledged' ? 'Keine bestätigten Alarme'
              : inboxStore.lifecycleFilter === 'resolved' ? 'Keine erledigten Alarme'
              : 'Keine Benachrichtigungen' }}
          </span>
          <span class="drawer__empty-sub">
            {{ inboxStore.sourceFilter
              ? 'Kein Ergebnis für diesen Quell-Filter'
              : 'Hier erscheinen zukünftige Alarme und Ereignisse' }}
          </span>
        </div>

        <!-- Grouped Notifications (sorted: severity desc, then created_at desc) -->
        <template v-else>
          <div
            v-for="group in sortedGroupedNotifications"
            :key="group.label"
            class="drawer__group"
          >
            <div class="drawer__group-label">{{ group.label }}</div>
            <NotificationItem
              v-for="n in group.items"
              :key="n.id"
              :notification="n"
              @mark-read="handleMarkRead"
              @acknowledge="handleAcknowledge"
              @resolve="handleResolve"
            />
          </div>

          <!-- Load More Button -->
          <div v-if="inboxStore.hasMore" class="drawer__load-more">
            <button
              type="button"
              class="drawer__load-more-btn"
              data-testid="notification-load-more"
              :disabled="inboxStore.isLoading"
              @click="inboxStore.loadMore()"
            >
              {{ inboxStore.isLoading ? 'Lade...' : 'Mehr laden' }}
            </button>
          </div>
        </template>
      </div>

      </div>
    </template>
  </SlideOver>

  <!-- Preferences Panel -->
  <NotificationPreferences />
</template>

<style scoped>
.drawer__panel-root {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* Header Actions */
.drawer__header-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding-bottom: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
  margin-bottom: var(--space-3);
}

.drawer__primary-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.drawer__status-tabs--inline {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  padding-bottom: 0;
  border-bottom: none;
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
}

/* Segmented Control — AUT-561 */
.drawer__segment-control {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 2px;
  flex: 1;
  background: var(--color-bg-primary);
  padding: 2px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.drawer__segment {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  min-width: 80px;
  min-height: 44px;
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.drawer__segment:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.03);
}

.drawer__segment--active {
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.drawer__segment-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  color: var(--color-text-primary);
  background: var(--color-bg-quaternary);
  border-radius: var(--radius-full);
}

.drawer__segment--active .drawer__segment-badge {
  background: var(--color-accent-dim);
  color: var(--color-accent-bright);
}

/* AUT-628: Severity-colored badge on the Aktiv tab */
.drawer__segment-badge--critical {
  background: color-mix(in srgb, var(--color-error) 20%, transparent);
  color: var(--color-error);
}

.drawer__segment-badge--warning {
  background: color-mix(in srgb, var(--color-warning) 20%, transparent);
  color: var(--color-warning);
}

/* Settings popover — suppressed toggle */
.drawer__settings-wrap {
  position: relative;
  flex-shrink: 0;
}

.drawer__settings-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: var(--color-text-muted);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.drawer__settings-btn:hover,
.drawer__settings-btn[aria-expanded="true"] {
  color: var(--color-text-secondary);
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border);
}

.drawer__settings-popover {
  position: absolute;
  top: calc(100% + var(--space-1));
  right: 0;
  z-index: var(--z-dropdown);
  min-width: 220px;
  padding: var(--space-3);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  box-shadow: var(--elevation-floating);
}

.drawer__actions-row {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-1);
}

.drawer__advanced {
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
  padding-bottom: var(--space-3);
}

.drawer__advanced-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-1) 0;
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
}

.drawer__advanced-toggle:hover {
  color: var(--color-text-primary);
}

.drawer__advanced-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.drawer__advanced-chevron {
  width: 12px;
  height: 12px;
  color: var(--color-text-muted);
}

.drawer__advanced-label {
  flex: 1;
}

.drawer__advanced-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 var(--space-1);
  font-size: var(--text-xxs);
  font-weight: 600;
  color: var(--color-iridescent-2);
  background: rgba(129, 140, 248, 0.16);
  border-radius: var(--radius-full);
}

/* Filter Tabs */
.drawer__tabs {
  display: flex;
  gap: 1px;
  background: var(--color-bg-primary);
  padding: 2px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--glass-border);
}

.drawer__tab {
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  border-radius: var(--radius-xs);
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.drawer__tab:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.03);
}

.drawer__tab--active {
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

/* Action Buttons */
.drawer__actions-row .drawer__action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.drawer__action-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
}

.drawer__action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.drawer__action-icon {
  width: 14px;
  height: 14px;
  pointer-events: none;
}

.drawer__action-label {
  white-space: nowrap;
}

/* Source search input — AUT-561 */
.drawer__source-search {
  margin-bottom: var(--space-2);
}

.drawer__source-input {
  width: 100%;
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  outline: none;
  transition: border-color var(--transition-fast);
}

.drawer__source-input:focus {
  border-color: var(--color-accent);
}

.drawer__source-input::placeholder {
  color: var(--color-text-muted);
}

/* Suppressed label (now inside settings popover) */
.drawer__settings-popover .drawer__suppressed-label {
  padding: 0;
}

.drawer__suppressed-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  cursor: pointer;
  user-select: none;
}

.drawer__suppressed-checkbox {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  accent-color: var(--color-warning);
}

.drawer__suppressed-icon {
  color: var(--color-warning);
  flex-shrink: 0;
}

.drawer__suppressed-hint {
  font-size: 10px;
  color: var(--color-text-muted);
  padding-left: 26px;
}

/* P3: Poll vs. WebSocket — Operator-Hinweis */
.drawer__sync-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
  font-size: 10px;
  line-height: 1.4;
  color: var(--color-text-muted);
  margin: 0 0 var(--space-3);
}

.drawer__sync-hint-icon {
  flex-shrink: 0;
  color: var(--color-info);
  opacity: 0.9;
}

.drawer__sync-hint-text {
  flex: 1;
  min-width: min(100%, 12rem);
}

.drawer__sync-hint-lag {
  flex-basis: 100%;
  color: var(--color-warning);
  font-weight: 500;
}

/* Source Filter Chips */
.drawer__source-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  padding-bottom: var(--space-3);
  margin-bottom: var(--space-3);
  border-bottom: 1px solid var(--glass-border);
}

.drawer__source-chip {
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

.drawer__source-chip:hover {
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
}

.drawer__source-chip--active {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  border-color: var(--glass-border);
}

/* Notification List */
.drawer__list {
  margin: 0 calc(-1 * var(--space-6));
}

/* Group */
.drawer__group-label {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--glass-border);
  position: sticky;
  top: 0;
  z-index: var(--z-dropdown);
}

/* Loading State */
.drawer__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-8);
}

.drawer__loading-text {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* Empty State */
.drawer__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.drawer__empty-icon {
  width: 32px;
  height: 32px;
  color: var(--color-text-muted);
  opacity: 0.45;
  flex-shrink: 0;
}

.drawer__empty-text {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
}

.drawer__empty-sub {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  max-width: 240px;
}

/* Load More */
.drawer__load-more {
  display: flex;
  justify-content: center;
  padding: var(--space-4);
}

.drawer__load-more-btn {
  padding: var(--space-2) var(--space-4);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-text-secondary);
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.drawer__load-more-btn:hover:not(:disabled) {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.06);
  border-color: var(--glass-border-hover);
}

.drawer__load-more-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

</style>
