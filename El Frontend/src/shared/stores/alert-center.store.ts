/**
 * Alert Center Store (Phase 4B)
 *
 * ISA-18.2 Alert Lifecycle Management.
 * Manages active/acknowledged alerts, stats, and lifecycle actions.
 *
 * Data flow:
 * - Stats: REST API → alertStats
 * - Active alerts: REST API → activeAlerts[]
 * - Lifecycle actions: acknowledge/resolve → REST API → WS update
 * - Real-time: notification-inbox.store handles WS events for list updates
 *
 * P3 (Poll vs. WS): Tab-/KPI-Zähler (alertStats) werden per REST alle STATS_POLL_INTERVAL_MS
 * nachgezogen; die Inbox-Liste und unreadCount können per WebSocket schneller wechseln —
 * UI zeigt „Live“ + Zeit der letzten KPI-Synchronisation (statsSyncedAt), siehe Drawer.
 *
 * Cross-store: Reads from notification-inbox.store for unified view.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  notificationsApi,
  type AlertStatsDTO,
  type AlertStatus,
  type NotificationDTO,
  type NotificationSeverity,
} from '@/api/notifications'
import { toUiApiError } from '@/api/uiApiError'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useAuthStore } from '@/shared/stores/auth.store'
import { createLogger } from '@/utils/logger'

const logger = createLogger('AlertCenterStore')

/** Ergebnis von Ack / Resolve / Resolve-All — für einheitliche UI-Finalität (Toast). */
export type AlertLifecycleFailure = {
  success: false
  message: string
  requestId: string | null
}

export type AlertLifecycleResult = { success: true } | AlertLifecycleFailure

function mapAlertLifecycleError(err: unknown, fallback: string): AlertLifecycleFailure {
  const ui = toUiApiError(err, fallback)
  return { success: false, message: ui.message, requestId: ui.request_id }
}

/** Polling interval for alert stats (30s). Export für Operator-Hinweise (P3 Poll vs. WS). */
export const STATS_POLL_INTERVAL_MS = 30_000
const REALTIME_STATS_REFRESH_DEBOUNCE_MS = 600

export const useAlertCenterStore = defineStore('alert-center', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // State
  // ═══════════════════════════════════════════════════════════════════════════

  const alertStats = ref<AlertStatsDTO | null>(null)
  /** Zeitpunkt der letzten erfolgreichen KPI-/Statistik-Synchronisation (ms), für P3-Hinweise. */
  const statsSyncedAt = ref<number | null>(null)
  const isLoadingStats = ref(false)
  const activeAlerts = ref<NotificationDTO[]>([])
  const isLoadingAlerts = ref(false)
  const statusFilter = ref<AlertStatus>('active')
  const severityFilter = ref<NotificationSeverity | null>(null)
  let statsPollTimer: ReturnType<typeof setInterval> | null = null
  let statsInFlight: Promise<void> | null = null
  let realtimeStatsRefreshTimer: ReturnType<typeof setTimeout> | null = null

  // ═══════════════════════════════════════════════════════════════════════════
  // Computed
  // ═══════════════════════════════════════════════════════════════════════════

  /** Total active + acknowledged alerts (unresolved) */
  const unresolvedCount = computed(() => {
    if (!alertStats.value) return 0
    return alertStats.value.active_count + alertStats.value.acknowledged_count
  })

  /** Active critical alerts */
  const criticalCount = computed(() => alertStats.value?.critical_active ?? 0)

  /** Active warning alerts */
  const warningCount = computed(() => alertStats.value?.warning_active ?? 0)

  /** Is there any active critical alert? */
  const hasCritical = computed(() => criticalCount.value > 0)

  /** Active alerts from inbox store (derived, no extra REST call) */
  const activeAlertsFromInbox = computed(() => {
    const inboxStore = useNotificationInboxStore()
    return inboxStore.notifications.filter(
      (n) => n.status === 'active' || n.status === 'acknowledged',
    )
  })

  /** Mean Time to Acknowledge formatted */
  const mttaFormatted = computed(() => {
    const s = alertStats.value?.mean_time_to_acknowledge_s
    if (s == null) return '–'
    if (s < 60) return `${Math.round(s)}s`
    if (s < 3600) return `${Math.round(s / 60)}m`
    return `${(s / 3600).toFixed(1)}h`
  })

  /** Mean Time to Resolve formatted */
  const mttrFormatted = computed(() => {
    const s = alertStats.value?.mean_time_to_resolve_s
    if (s == null) return '–'
    if (s < 60) return `${Math.round(s)}s`
    if (s < 3600) return `${Math.round(s / 60)}m`
    return `${(s / 3600).toFixed(1)}h`
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Actions
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Fetch alert statistics from server.
   */
  async function fetchStats(options: { force?: boolean } = {}): Promise<void> {
    const authStore = useAuthStore()
    if (!authStore.isAuthenticated) {
      return
    }
    if (isLoadingStats.value) {
      if (!options.force) {
        if (statsInFlight) await statsInFlight
        return
      }
      if (statsInFlight) await statsInFlight
    }

    statsInFlight = (async () => {
      isLoadingStats.value = true
      try {
        alertStats.value = await notificationsApi.getAlertStats()
        statsSyncedAt.value = Date.now()
        logger.debug(
          `Stats loaded: ${alertStats.value.active_count} active, ` +
            `${alertStats.value.acknowledged_count} acknowledged`,
        )
      } catch (err) {
        logger.error('Failed to fetch alert stats', err)
      } finally {
        isLoadingStats.value = false
        statsInFlight = null
      }
    })()

    await statsInFlight
  }

  /**
   * Fetch active alerts list from server.
   */
  async function fetchActiveAlerts(): Promise<void> {
    if (isLoadingAlerts.value) return
    isLoadingAlerts.value = true

    try {
      const res = await notificationsApi.getActiveAlerts({
        status: statusFilter.value,
        severity: severityFilter.value ?? undefined,
        page: 1,
        page_size: 100,
      })
      activeAlerts.value = res.data
      logger.debug(`Loaded ${res.data.length} ${statusFilter.value} alerts`)
    } catch (err) {
      logger.error('Failed to fetch active alerts', err)
    } finally {
      isLoadingAlerts.value = false
    }
  }

  /**
   * Acknowledge an alert (active → acknowledged).
   */
  async function acknowledgeAlert(id: string): Promise<AlertLifecycleResult> {
    try {
      const updated = await notificationsApi.acknowledgeAlert(id)

      // Update local lists
      _updateAlertInLists(id, updated)

      // Refresh stats
      await fetchStats({ force: true })

      logger.info(`Alert acknowledged: ${id}`)
      return { success: true }
    } catch (err) {
      logger.error(`Failed to acknowledge alert ${id}`, err)
      return mapAlertLifecycleError(err, 'Alert konnte nicht bestätigt werden.')
    }
  }

  /**
   * Resolve an alert (active/acknowledged → resolved).
   */
  async function resolveAlert(id: string): Promise<AlertLifecycleResult> {
    try {
      const updated = await notificationsApi.resolveAlert(id)

      // Update local lists
      _updateAlertInLists(id, updated)

      // Remove from active alerts list
      activeAlerts.value = activeAlerts.value.filter((a) => a.id !== id)

      // Refresh stats
      await fetchStats({ force: true })

      logger.info(`Alert resolved: ${id}`)
      return { success: true }
    } catch (err) {
      logger.error(`Failed to resolve alert ${id}`, err)
      return mapAlertLifecycleError(err, 'Alert konnte nicht erledigt werden.')
    }
  }

  /**
   * Resolve all unresolved alerts (active + acknowledged) for current user.
   */
  async function resolveAllAlerts(): Promise<AlertLifecycleResult> {
    try {
      const result = await notificationsApi.resolveAllAlerts()

      const now = new Date().toISOString()
      const inboxStore = useNotificationInboxStore()
      for (const notification of inboxStore.notifications) {
        if (notification.status === 'active' || notification.status === 'acknowledged') {
          notification.status = 'resolved'
          notification.resolved_at = notification.resolved_at || now
          notification.is_read = true
          notification.read_at = notification.read_at || now
        }
      }

      activeAlerts.value = []
      if (alertStats.value) {
        alertStats.value = {
          ...alertStats.value,
          active_count: 0,
          acknowledged_count: 0,
        }
      }
      await fetchStats({ force: true })
      logger.info(`All unresolved alerts resolved (${result.resolved_count})`)
      return { success: true }
    } catch (err) {
      logger.error('Failed to resolve all alerts', err)
      return mapAlertLifecycleError(
        err,
        'Alle Alerts erledigen ist fehlgeschlagen. Bitte erneut versuchen.',
      )
    }
  }

  /**
   * Start polling for alert stats.
   */
  function startStatsPolling(): void {
    const authStore = useAuthStore()
    if (!authStore.isAuthenticated) {
      logger.debug('Alert stats polling skipped (not authenticated)')
      return
    }
    stopStatsPolling()
    fetchStats()
    statsPollTimer = setInterval(fetchStats, STATS_POLL_INTERVAL_MS)
    logger.debug('Alert stats polling started')
  }

  /**
   * Stop polling for alert stats.
   */
  function stopStatsPolling(): void {
    if (statsPollTimer) {
      clearInterval(statsPollTimer)
      statsPollTimer = null
    }
  }

  /**
   * Trigger a near-realtime stats refresh after WS notification events.
   * Debounced to avoid REST storms when multiple events arrive in a burst.
   */
  function scheduleStatsRefresh(): void {
    if (realtimeStatsRefreshTimer) {
      clearTimeout(realtimeStatsRefreshTimer)
    }
    realtimeStatsRefreshTimer = setTimeout(() => {
      void fetchStats({ force: true })
      realtimeStatsRefreshTimer = null
    }, REALTIME_STATS_REFRESH_DEBOUNCE_MS)
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Internal
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Update an alert in all local lists after API response.
   */
  function _updateAlertInLists(id: string, updated: NotificationDTO): void {
    // Update in active alerts
    const activeIdx = activeAlerts.value.findIndex((a) => a.id === id)
    if (activeIdx >= 0) {
      activeAlerts.value[activeIdx] = updated
    }

    // Update in inbox store
    const inboxStore = useNotificationInboxStore()
    inboxStore.applyAlertUpdate(updated)
  }

  return {
    // State
    alertStats,
    statsSyncedAt,
    isLoadingStats,
    activeAlerts,
    isLoadingAlerts,
    statusFilter,
    severityFilter,

    // Computed
    unresolvedCount,
    criticalCount,
    warningCount,
    hasCritical,
    activeAlertsFromInbox,
    mttaFormatted,
    mttrFormatted,

    // Actions
    fetchStats,
    fetchActiveAlerts,
    acknowledgeAlert,
    resolveAlert,
    resolveAllAlerts,
    startStatsPolling,
    stopStatsPolling,
    scheduleStatsRefresh,
  }
})
