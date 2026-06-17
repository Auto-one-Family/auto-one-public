/**
 * Notification Inbox Store
 *
 * Persistent notification inbox with WebSocket real-time updates.
 * SEPARATE from notification.store.ts which handles transient toasts.
 *
 * Data flow:
 * - Initial load: REST API → notifications[] + unreadCount
 * - Real-time: WS notification_new → unshift to list
 * - Real-time: WS notification_updated → update item in list
 * - Real-time: WS notification_unread_count → update badge count
 *
 * Cross-store: esp.store.ts WS-Dispatcher delegates 3 events here.
 *
 * P3: inboxLiveTouchedAt = letzte Änderung an Liste/Zähler (REST oder WS) — für Abgleich mit
 * alert-center.statsSyncedAt (KPI-Polling), siehe NotificationDrawer.
 */

import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import {
  notificationsApi,
  type AlertStatus,
  type NotificationDTO,
  type NotificationSeverity,
  type NotificationListFilters,
} from '@/api/notifications'
import router from '@/router'
import { createLogger } from '@/utils/logger'
import { useAuthStore } from '@/shared/stores/auth.store'

const logger = createLogger('NotificationInboxStore')

/** Filter tabs in the drawer */
export type InboxFilter = 'all' | 'critical' | 'warning' | 'info'

/** Alert lifecycle filter (server-side list; 'all' = no status query) */
export type InboxLifecycleFilter = 'all' | AlertStatus

/** Source filter: null = all, or backend source value. "__system__" = manual|system|device_event|autoops */
export type SourceFilterValue = string | null

/** Sources grouped as "System" for filter chip */
const SYSTEM_SOURCES_SET = new Set(['manual', 'system', 'device_event', 'autoops'])

/** Severity priority for sorting (lower = higher priority, ISA-18.2: 3 levels) */
const SEVERITY_PRIORITY: Record<string, number> = {
  critical: 0,
  warning: 1,
  info: 2,
}

/** Max items to load per page */
const PAGE_SIZE = 50

export const useNotificationInboxStore = defineStore('notification-inbox', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // State
  // ═══════════════════════════════════════════════════════════════════════════

  const notifications = ref<NotificationDTO[]>([])
  const unreadCount = ref(0)
  const highestSeverity = ref<NotificationSeverity | null>(null)
  const isDrawerOpen = ref(false)
  const isPreferencesOpen = ref(false)
  const activeFilter = ref<InboxFilter>('all')
  const lifecycleFilter = ref<InboxLifecycleFilter>('active')
  const sourceFilter = ref<SourceFilterValue>(null)
  /** When true, GET /notifications includes suppressed-channel audit notifications */
  const showSuppressed = ref(false)
  const isLoading = ref(false)
  const hasMore = ref(true)
  const currentPage = ref(1)
  const totalItems = ref(0)
  /** Letzte lokale Änderung an Inbox-Liste oder unreadCount (ms) — P3 Live vs. KPI-Poll. */
  const inboxLiveTouchedAt = ref<number | null>(null)

  function touchInboxLive(): void {
    inboxLiveTouchedAt.value = Date.now()
  }

  function isCurrentUserEvent(data: Record<string, unknown>): boolean {
    const eventUserIdRaw = data.user_id as string | number | undefined
    const eventUserId = eventUserIdRaw != null ? String(eventUserIdRaw) : null
    if (eventUserId == null) return true
    const authStore = useAuthStore()
    if (!authStore.user?.id) return true
    return String(authStore.user.id) === eventUserId
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Computed
  // ═══════════════════════════════════════════════════════════════════════════

  /** Group notifications by date (Heute / Gestern / Älter) — list is server-filtered */
  const groupedNotifications = computed(() => {
    const groups: { label: string; items: NotificationDTO[] }[] = []
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const yesterday = new Date(today)
    yesterday.setDate(yesterday.getDate() - 1)

    const todayItems: NotificationDTO[] = []
    const yesterdayItems: NotificationDTO[] = []
    const olderItems: NotificationDTO[] = []

    for (const n of notifications.value) {
      const date = n.created_at ? new Date(n.created_at) : new Date(0)
      if (date >= today) {
        todayItems.push(n)
      } else if (date >= yesterday) {
        yesterdayItems.push(n)
      } else {
        olderItems.push(n)
      }
    }

    if (todayItems.length > 0) groups.push({ label: 'Heute', items: todayItems })
    if (yesterdayItems.length > 0) groups.push({ label: 'Gestern', items: yesterdayItems })
    if (olderItems.length > 0) groups.push({ label: 'Älter', items: olderItems })

    return groups
  })

  /** Badge display string */
  const badgeText = computed(() => {
    if (unreadCount.value <= 0) return ''
    if (unreadCount.value > 99) return '99+'
    return String(unreadCount.value)
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Actions
  // ═══════════════════════════════════════════════════════════════════════════

  // ═══════════════════════════════════════════════════════════════════════════
  // List fetching (server-side filters — AUT-196)
  // ═══════════════════════════════════════════════════════════════════════════

  function buildListFilters(page: number): NotificationListFilters {
    const f: NotificationListFilters = { page, page_size: PAGE_SIZE }
    if (activeFilter.value !== 'all') {
      f.severity = activeFilter.value as NotificationSeverity
    }
    if (lifecycleFilter.value !== 'all') {
      f.status = lifecycleFilter.value
    }
    if (sourceFilter.value === '__system__') {
      f.source_bucket = 'system'
    } else if (sourceFilter.value) {
      f.source = sourceFilter.value as NotificationDTO['source']
    }
    if (showSuppressed.value) {
      f.show_suppressed = true
    }
    return f
  }

  function notificationMatchesCurrentFilters(n: NotificationDTO): boolean {
    if (activeFilter.value !== 'all' && n.severity !== activeFilter.value) return false
    if (lifecycleFilter.value !== 'all' && n.status !== lifecycleFilter.value) return false
    if (sourceFilter.value === '__system__') {
      if (!n.source || !SYSTEM_SOURCES_SET.has(n.source)) return false
    } else if (sourceFilter.value && n.source !== sourceFilter.value) return false
    if (!showSuppressed.value && n.channel === 'suppressed') return false
    return true
  }

  /** When true, opening the drawer does not reset lifecycle filter (AlertStatusBar deep-focus). */
  const skipLifecycleResetOnOpen = ref(false)

  /** Verhindert doppeltes reload beim ersten Öffnen über ?notifications=alerts (vor loadInitial). */
  const suppressNextDrawerReload = ref(false)

  /**
   * Unfiltered first page for QuickAlertPanel / global inbox cache when drawer is closed.
   * Drawer list uses server filters; closing the drawer must not leave a truncated slice in memory.
   */
  async function reloadUnfilteredFirstPageForAmbient(): Promise<void> {
    if (isLoading.value) return
    isLoading.value = true
    try {
      const ambientFilters: NotificationListFilters = { page: 1, page_size: PAGE_SIZE }
      if (showSuppressed.value) {
        ambientFilters.show_suppressed = true
      }
      const [listRes, countRes] = await Promise.all([
        notificationsApi.list(ambientFilters),
        notificationsApi.getUnreadCount(),
      ])
      notifications.value = listRes.data
      totalItems.value = listRes.pagination.total_items
      currentPage.value = 1
      hasMore.value = listRes.data.length < listRes.pagination.total_items
      unreadCount.value = countRes.unread_count
      highestSeverity.value = countRes.highest_severity
    } catch (err) {
      logger.error('Failed to reload ambient notifications', err)
    } finally {
      isLoading.value = false
    }
  }

  function mergeNotificationsRouteQuery(value: 'alerts'): void {
    const q = { ...router.currentRoute.value.query }
    if (q.notifications === value) return
    q.notifications = value
    void router.replace({ query: q })
  }

  function stripNotificationsRouteQuery(): void {
    const q = { ...router.currentRoute.value.query }
    if (q.notifications === undefined) return
    delete q.notifications
    void router.replace({ query: q })
  }

  watch(isDrawerOpen, (isOpen, wasOpen) => {
    if (isOpen) {
      const prevLifecycle = lifecycleFilter.value
      if (!skipLifecycleResetOnOpen.value) {
        lifecycleFilter.value = 'all'
      }
      skipLifecycleResetOnOpen.value = false
      if (suppressNextDrawerReload.value) {
        suppressNextDrawerReload.value = false
        return
      }
      if (prevLifecycle === lifecycleFilter.value) {
        void reloadListForFilters()
      }
    } else if (wasOpen) {
      stripNotificationsRouteQuery()
      void reloadUnfilteredFirstPageForAmbient()
    }
  })

  watch([activeFilter, lifecycleFilter, sourceFilter, showSuppressed], () => {
    if (!isDrawerOpen.value) return
    void reloadListForFilters()
  })

  /**
   * Reload first page with current inbox filters (+ badge counters).
   */
  async function reloadListForFilters(): Promise<void> {
    if (isLoading.value) return
    isLoading.value = true

    try {
      const filters = buildListFilters(1)
      const [listRes, countRes] = await Promise.all([
        notificationsApi.list(filters),
        notificationsApi.getUnreadCount(),
      ])

      notifications.value = listRes.data
      totalItems.value = listRes.pagination.total_items
      currentPage.value = 1
      hasMore.value = listRes.data.length < listRes.pagination.total_items

      unreadCount.value = countRes.unread_count
      highestSeverity.value = countRes.highest_severity

      touchInboxLive()
      logger.info(
        `Reloaded ${listRes.data.length} notifications (filtered), ${countRes.unread_count} unread`,
      )
    } catch (err) {
      logger.error('Failed to reload notifications', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * App-Start: Route ?notifications=alerts → Lifecycle + Drawer, ohne Reload bis loadInitial().
   */
  function bootstrapInboxFromRoute(): void {
    const raw = router.currentRoute.value.query.notifications
    const v = Array.isArray(raw) ? raw[0] : raw
    if (v !== 'alerts') return
    skipLifecycleResetOnOpen.value = true
    lifecycleFilter.value = 'active'
    activeFilter.value = 'all'
    sourceFilter.value = null
    suppressNextDrawerReload.value = true
    isDrawerOpen.value = true
  }

  /**
   * Initial load: Fetch first page of notifications + unread count.
   * Called from App.vue on startup (store not yet subscribed to drawer watch for reload).
   */
  async function loadInitial(): Promise<void> {
    await reloadListForFilters()
  }

  /**
   * AlertStatusBar / Deep-Link: Fokus auf aktive Alerts.
   * Setzt optional `?notifications=alerts` für Bookmark/Share (AUT-196 Paket E).
   */
  function openDrawerWithActiveAlertsFocus(options?: { syncRoute?: boolean }): void {
    skipLifecycleResetOnOpen.value = true
    lifecycleFilter.value = 'active'
    activeFilter.value = 'all'
    sourceFilter.value = null
    isDrawerOpen.value = true
    if (options?.syncRoute !== false) {
      mergeNotificationsRouteQuery('alerts')
    }
  }

  /** Route bereits mit ?notifications=alerts — z. B. Client-Navigation ohne zweite replace. */
  function applyNotificationsRouteDeepLink(): void {
    const raw = router.currentRoute.value.query.notifications
    const v = Array.isArray(raw) ? raw[0] : raw
    if (v !== 'alerts') return
    openDrawerWithActiveAlertsFocus({ syncRoute: false })
  }

  /**
   * Load next page (lazy loading) with the same filters.
   */
  async function loadMore(): Promise<void> {
    if (isLoading.value || !hasMore.value) return
    isLoading.value = true

    try {
      const nextPage = currentPage.value + 1
      const res = await notificationsApi.list(buildListFilters(nextPage))
      notifications.value.push(...res.data)
      currentPage.value = nextPage
      hasMore.value = notifications.value.length < res.pagination.total_items
      touchInboxLive()

      logger.debug(`Loaded page ${nextPage}, total items: ${notifications.value.length}`)
    } catch (err) {
      logger.error('Failed to load more notifications', err)
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Mark a single notification as read.
   */
  async function markAsRead(id: string): Promise<void> {
    try {
      await notificationsApi.markRead(id)

      // Optimistic update
      const idx = notifications.value.findIndex((n) => n.id === id)
      if (idx >= 0 && !notifications.value[idx].is_read) {
        notifications.value[idx].is_read = true
        notifications.value[idx].read_at = new Date().toISOString()
        // Count will be updated via WS notification_unread_count
      }
    } catch (err) {
      logger.error(`Failed to mark notification ${id} as read`, err)
    }
  }

  /**
   * Mark all notifications as read.
   */
  async function markAllAsRead(): Promise<void> {
    try {
      await notificationsApi.markAllRead()

      // Optimistic update
      const now = new Date().toISOString()
      for (const n of notifications.value) {
        if (!n.is_read) {
          n.is_read = true
          n.read_at = now
        }
      }
      // Count will be updated via WS notification_unread_count
    } catch (err) {
      logger.error('Failed to mark all as read', err)
    }
  }

  /**
   * Toggle drawer open/closed.
   */
  function toggleDrawer(): void {
    isDrawerOpen.value = !isDrawerOpen.value
  }

  /**
   * Open preferences panel.
   */
  function openPreferences(): void {
    isPreferencesOpen.value = true
  }

  /**
   * Close preferences panel.
   */
  function closePreferences(): void {
    isPreferencesOpen.value = false
  }

  /**
   * Set source filter (null = all, backend source value, or "__system__" for manual|system|device_event|autoops).
   */
  function setSourceFilter(source: SourceFilterValue): void {
    sourceFilter.value = source
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // WebSocket Handlers (called from esp.store.ts dispatcher)
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Handle notification_new WS event.
   * Adds new notification at the top of the list.
   */
  function handleWSNotificationNew(data: Record<string, unknown>): void {
    if (!isCurrentUserEvent(data)) return

    const notification: NotificationDTO = {
      id: data.id as string,
      user_id: data.user_id as number,
      channel: (data.channel as string) || 'websocket',
      severity: data.severity as NotificationSeverity,
      category: data.category as string as NotificationDTO['category'],
      title: data.title as string,
      body: (data.body as string) || null,
      metadata: (data.metadata as Record<string, unknown>) || {},
      source: data.source as string as NotificationDTO['source'],
      is_read: (data.is_read as boolean) || false,
      is_archived: false,
      digest_sent: false,
      parent_notification_id: (data.parent_notification_id as string) || null,
      fingerprint: (data.fingerprint as string) || null,
      created_at: (data.created_at as string) || new Date().toISOString(),
      updated_at: null,
      read_at: null,
      // Phase 4B: Alert lifecycle fields
      status: (data.status as AlertStatus) || 'active',
      acknowledged_at: (data.acknowledged_at as string) || null,
      acknowledged_by: (data.acknowledged_by as number) || null,
      resolved_at: (data.resolved_at as string) || null,
      correlation_id: (data.correlation_id as string) || null,
    }

    // Deduplicate: don't add if already in list
    if (notifications.value.some((n) => n.id === notification.id)) return

    if (!notificationMatchesCurrentFilters(notification)) {
      unreadCount.value++
      if (
        !highestSeverity.value ||
        SEVERITY_PRIORITY[notification.severity] <
          SEVERITY_PRIORITY[highestSeverity.value]
      ) {
        highestSeverity.value = notification.severity
      }
      logger.debug(`WS notification_new skipped list insert (filter): ${notification.title}`)
      return
    }

    notifications.value.unshift(notification)
    unreadCount.value++
    totalItems.value++
    touchInboxLive()

    // Update highest severity
    if (
      !highestSeverity.value ||
      SEVERITY_PRIORITY[notification.severity] <
        SEVERITY_PRIORITY[highestSeverity.value]
    ) {
      highestSeverity.value = notification.severity
    }

    // Browser notification for critical
    if (notification.severity === 'critical') {
      showBrowserNotification(notification)
    }

    logger.debug(`WS notification_new: ${notification.title}`)
  }

  /**
   * Handle notification_updated WS event.
   * Updates existing notification (e.g., after mark-as-read).
   */
  function handleWSNotificationUpdated(data: Record<string, unknown>): void {
    if (!isCurrentUserEvent(data)) return

    const id = data.id as string
    const idx = notifications.value.findIndex((n) => n.id === id)
    if (idx < 0) return

    if (data.is_read !== undefined) {
      notifications.value[idx].is_read = data.is_read as boolean
    }
    if (data.is_archived !== undefined) {
      notifications.value[idx].is_archived = data.is_archived as boolean
    }
    if (data.read_at !== undefined) {
      notifications.value[idx].read_at = data.read_at as string | null
    }
    if (data.metadata !== undefined) {
      notifications.value[idx].metadata = (data.metadata as Record<string, unknown>) || {}
    }
    if (data.title !== undefined) {
      notifications.value[idx].title = data.title as string
    }
    if (data.body !== undefined) {
      notifications.value[idx].body = (data.body as string) || null
    }
    if (data.source !== undefined) {
      notifications.value[idx].source = data.source as NotificationDTO['source']
    }
    if (data.category !== undefined) {
      notifications.value[idx].category = data.category as NotificationDTO['category']
    }
    if (data.updated_at !== undefined) {
      notifications.value[idx].updated_at = data.updated_at as string | null
    }
    // Phase 4B: Alert lifecycle fields
    if (data.status !== undefined) {
      notifications.value[idx].status = data.status as AlertStatus
    }
    if (data.acknowledged_at !== undefined) {
      notifications.value[idx].acknowledged_at = data.acknowledged_at as string | null
    }
    if (data.acknowledged_by !== undefined) {
      notifications.value[idx].acknowledged_by = data.acknowledged_by as number | null
    }
    if (data.resolved_at !== undefined) {
      notifications.value[idx].resolved_at = data.resolved_at as string | null
    }

    touchInboxLive()
    logger.debug(`WS notification_updated: ${id}`)
  }

  /**
   * Handle notification_unread_count WS event.
   * Authoritative badge count from server.
   */
  function handleWSUnreadCount(data: Record<string, unknown>): void {
    if (!isCurrentUserEvent(data)) return

    unreadCount.value = (data.unread_count as number) || 0
    highestSeverity.value = (data.highest_severity as NotificationSeverity) || null
    touchInboxLive()

    logger.debug(`WS unread count: ${unreadCount.value}`)
  }

  /**
   * Single write boundary for alert lifecycle updates coming from other stores.
   * Returns false when the notification is unknown in the current inbox page.
   */
  function applyAlertUpdate(updated: NotificationDTO): boolean {
    const idx = notifications.value.findIndex((n) => n.id === updated.id)
    if (idx < 0) return false
    notifications.value[idx] = updated
    touchInboxLive()
    return true
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Browser Notifications
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * Show browser push notification for critical alerts.
   * Requests permission on first call.
   */
  function showBrowserNotification(notification: NotificationDTO): void {
    if (!('Notification' in window)) return

    if (Notification.permission === 'granted') {
      new Notification(`[CRITICAL] ${notification.title}`, {
        body: notification.body || '',
        icon: '/favicon.ico',
        tag: notification.id,
      })
    } else if (Notification.permission !== 'denied') {
      Notification.requestPermission().then((permission) => {
        if (permission === 'granted') {
          new Notification(`[CRITICAL] ${notification.title}`, {
            body: notification.body || '',
            icon: '/favicon.ico',
            tag: notification.id,
          })
        }
      })
    }
  }

  return {
    // State
    notifications,
    unreadCount,
    highestSeverity,
    isDrawerOpen,
    isPreferencesOpen,
    activeFilter,
    lifecycleFilter,
    sourceFilter,
    showSuppressed,
    setSourceFilter,
    isLoading,
    hasMore,
    inboxLiveTouchedAt,

    // Computed
    groupedNotifications,
    badgeText,

    // Actions
    loadInitial,
    reloadListForFilters,
    loadMore,
    markAsRead,
    markAllAsRead,
    toggleDrawer,
    openDrawerWithActiveAlertsFocus,
    applyNotificationsRouteDeepLink,
    bootstrapInboxFromRoute,
    openPreferences,
    closePreferences,

    // WS Handlers (for esp.store.ts dispatcher)
    handleWSNotificationNew,
    handleWSNotificationUpdated,
    handleWSUnreadCount,
    applyAlertUpdate,
  }
})
