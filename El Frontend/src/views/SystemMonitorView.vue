<script setup lang="ts">
/**
 * SystemMonitorView - Live Event Monitor
 *
 * SERVER-CENTRIC ARCHITECTURE:
 * - God-Kaiser Server ist Single Source of Truth
 * - Server liefert bereits menschenverständliche Messages
 * - Server liefert bereits berechnete Severities
 * - Frontend ist "Dumb Display Layer" - zeigt nur an
 *
 * Features:
 * - Live WebSocket Events von God-Kaiser Server
 * - Deutsche Fehlermeldungen VOM SERVER (100+ Mappings)
 * - Filter nach ESP, Level, Zeitraum, Event-Type
 * - URL-Sync für Deep-Linking
 * - Event-Details mit Server-Troubleshooting
 *
 * @see El Servador/god_kaiser_server/src/core/esp32_error_mapping.py - 100+ Error Mappings
 */

import { ref, computed, onMounted, onUnmounted, watch, nextTick, defineAsyncComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWebSocket } from '@/composables/useWebSocket'
import { useAuthStore } from '@/shared/stores/auth.store'
import { useEspStore } from '@/stores/esp'
import { useNotificationInboxStore } from '@/shared/stores/notification-inbox.store'
import { useOpsLifecycleStore } from '@/shared/stores/ops-lifecycle.store'
import { detectCategory } from '@/utils/errorCodeTranslator'
import { auditApi, type AuditLog, type AuditStatistics, type StatisticsTimeRange, type DataSource, type UnifiedEventFromAPI } from '@/api/audit'
import type { UnifiedEvent } from '@/types/websocket-events'
import type { EventOrGroup, GroupingOptions } from '@/types/event-grouping'
import { groupEventsByTimeWindow } from '@/utils/eventGrouper'
import { transformEventMessage } from '@/utils/eventTransformer'
import {
  buildContractIntegritySignal,
  extractCorrelationId,
  extractEspId,
  extractRequestId,
  getDataSourceForEventType,
  inferFallbackSeverity,
  validateContractEvent,
  WS_EVENT_TYPES,
} from '@/utils/contractEventMapper'
import type { WebSocketMessage } from '@/services/websocket'
import { X, CheckCircle, AlertTriangle } from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'

const logger = createLogger('SystemMonitor')

// Sub-Components (always rendered)
import MonitorTabs, { type TabId } from '@/components/system-monitor/MonitorTabs.vue'
import HealthSummaryBar from '@/components/system-monitor/HealthSummaryBar.vue'
import RestRequestIdDevBar from '@/components/system-monitor/RestRequestIdDevBar.vue'

// Tab Content Components — lazy-loaded to reduce initial module request burst.
// Only the active tab triggers its import, preventing ERR_INSUFFICIENT_RESOURCES.
const EventsTab = defineAsyncComponent(() => import('@/components/system-monitor/EventsTab.vue'))
const ServerLogsTab = defineAsyncComponent(() => import('@/components/system-monitor/ServerLogsTab.vue'))
const DatabaseTab = defineAsyncComponent(() => import('@/components/system-monitor/DatabaseTab.vue'))
const MqttTrafficTab = defineAsyncComponent(() => import('@/components/system-monitor/MqttTrafficTab.vue'))
const HealthTab = defineAsyncComponent(() => import('@/components/system-monitor/HealthTab.vue'))
const DiagnoseTab = defineAsyncComponent(() => import('@/components/system-monitor/DiagnoseTab.vue'))
const ReportsTab = defineAsyncComponent(() => import('@/components/system-monitor/ReportsTab.vue'))
const HierarchyTab = defineAsyncComponent(() => import('@/components/system-monitor/HierarchyTab.vue'))
const CleanupPanel = defineAsyncComponent(() => import('@/components/system-monitor/CleanupPanel.vue'))
const EventDetailsPanel = defineAsyncComponent(() => import('@/components/system-monitor/EventDetailsPanel.vue'))

// ============================================================================
// Constants
// ============================================================================

// Safety limit — Virtual Scrolling handles rendering performance
const MAX_EVENTS = 5000

// All event types we subscribe to (from Server WebSocket broadcasts)
// WICHTIG: Diese Liste muss ALLE event_types aus dem Server enthalten!
// Server-Referenz: El Servador/.../event_aggregator_service.py category_map
const ALL_EVENT_TYPES = WS_EVENT_TYPES

// ============================================================================
// State
// ============================================================================

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const espStore = useEspStore()
const inboxStore = useNotificationInboxStore()
const opsLifecycleStore = useOpsLifecycleStore()
const selectedEvent = ref<UnifiedEvent | null>(null)

// Live-Pause State (persisted in localStorage)
const PAUSE_STORAGE_KEY = 'systemMonitor.isPaused'
const isPaused = ref(localStorage.getItem(PAUSE_STORAGE_KEY) === 'true')

// Watch for changes and persist to localStorage
watch(isPaused, (newValue) => {
  localStorage.setItem(PAUSE_STORAGE_KEY, String(newValue))
})

const unifiedEvents = ref<UnifiedEvent[]>([])
const maxEventsWarningShown = ref(false)
const isLoading = ref(false)
const showStats = ref(false)

// Mobile state
const isMobile = ref(false)

// Health Summary Bar state
import { getFleetHealth, type FleetHealthDevice } from '@/api/health'
const healthDevices = ref<FleetHealthDevice[]>([])
const isHealthLoading = ref(false)
const healthExpanded = ref(false)

// Event Loading State
const eventLoadHours = ref<number | null>(null) // null = load ALL events (default)
const isLoadingMore = ref(false)
const currentLimitPerSource = ref(2000) // Track current limit for incremental "Load More"

// Total available events across all selected sources (from aggregated API)
const totalAvailableEvents = ref(0)

// Pagination State (Cursor-based for Infinite Scroll)
const paginationCursor = ref<string | null>(null)  // oldest_timestamp from last response
const hasMoreEvents = ref(true)  // Whether more events are available

// Data Source Selection (for CLIENT-SIDE filtering only - all sources loaded at mount)
// Default: ALLE Datenquellen für vollständige Event-Sicht
const selectedDataSources = ref<DataSource[]>(['audit_log', 'sensor_data', 'esp_health', 'actuators'])

// Audit Statistics & Admin Features
const statistics = ref<AuditStatistics | null>(null)
const showCleanupPanel = ref(false)

// Statistics Time Range Setting (persisted in localStorage)
const STORAGE_KEY = 'systemMonitor.statisticsTimeRange'
const statisticsTimeRange = ref<StatisticsTimeRange>(
  (localStorage.getItem(STORAGE_KEY) as StatisticsTimeRange) || '24h'
)

// Watch for changes and persist to localStorage
watch(statisticsTimeRange, (newValue) => {
  localStorage.setItem(STORAGE_KEY, newValue)
})

// Time range labels for display
const TIME_RANGE_LABELS: Record<StatisticsTimeRange, string> = {
  '24h': '24H',
  '7d': '7D',
  '30d': '30D',
  'all': 'Gesamt',
}

// Time range selector modal
const showTimeRangeSelector = ref(false)

// Filter state
const activeTab = ref<TabId>('events')
const filterEspId = ref<string>('')
const filterCorrelationId = ref<string>('')
const filterLevels = ref<Set<string>>(new Set(['info', 'warning', 'error', 'critical']))
const filterTimeRange = ref<'all' | '1h' | '6h' | '24h' | '7d' | '30d' | 'custom'>('all')

/** Default + deep-link presets for the event stream data-source chips */
const DEFAULT_MONITOR_DATA_SOURCES: DataSource[] = ['audit_log', 'sensor_data', 'esp_health', 'actuators']
const ALERT_FOCUS_DATA_SOURCES: DataSource[] = ['audit_log', 'esp_health']

/** URL ?level= accepts German or English tokens (comma-separated) */
const LEVEL_QUERY_MAP: Record<string, string> = {
  kritisch: 'critical',
  critical: 'critical',
  warnung: 'warning',
  warning: 'warning',
  fehler: 'error',
  error: 'error',
  info: 'info',
}

function applyLevelQueryParam(raw: unknown): void {
  const q = Array.isArray(raw) ? raw[0] : raw
  if (q === undefined || q === null || String(q).trim() === '') {
    filterLevels.value = new Set(['info', 'warning', 'error', 'critical'])
    return
  }
  const parts = String(q)
    .split(',')
    .map(s => s.trim().toLowerCase())
    .filter(Boolean)
  const next = new Set<string>()
  for (const p of parts) {
    const mapped = LEVEL_QUERY_MAP[p]
    if (mapped) next.add(mapped)
  }
  if (next.size > 0) {
    filterLevels.value = next
  }
}

// Custom Date Range for 'custom' timeRange
const customStartDate = ref<string | undefined>(undefined)
const customEndDate = ref<string | undefined>(undefined)

// Restored events highlighting (from backup restore)
const restoredEventIds = ref<Set<string>>(new Set())

// Server-Logs Zeitfenster (Feature 1.2) + Request-ID (Phase 4)
const logsStartTime = ref<string | undefined>()
const logsEndTime = ref<string | undefined>()
const logsRequestId = ref<string | undefined>()

// Grouping state (Phase 5.2)
const groupingEnabled = ref(localStorage.getItem('systemMonitor.groupingEnabled') === 'true')
const groupingOptions = computed<GroupingOptions>(() => ({
  enabled: groupingEnabled.value,
  windowMs: 5000,
  minGroupSize: 2,
}))

const groupedEvents = computed<EventOrGroup[]>(() => {
  return groupEventsByTimeWindow(filteredEvents.value, groupingOptions.value)
})

function handleGroupingToggle(value: boolean) {
  groupingEnabled.value = value
  localStorage.setItem('systemMonitor.groupingEnabled', String(value))
}

function enforceMaxEvents(reason: string): void {
  if (unifiedEvents.value.length <= MAX_EVENTS) {
    maxEventsWarningShown.value = false
    return
  }

  if (!maxEventsWarningShown.value) {
    logger.warn(`Event count exceeds MAX_EVENTS (${MAX_EVENTS}) ${reason}`)
    maxEventsWarningShown.value = true
  }

  unifiedEvents.value = unifiedEvents.value.slice(0, MAX_EVENTS)
}

// Toast notification state
const toastMessage = ref<string | null>(null)
const toastType = ref<'success' | 'error' | 'info'>('success')

// ============================================================================
// Composables
// ============================================================================

const { on } = useWebSocket({ autoConnect: true })
const wsUnsubscribers: (() => void)[] = []

// ============================================================================
// Computed
// ============================================================================

const filteredEvents = computed(() => {
  let events = unifiedEvents.value

  const correlationTrimmed = filterCorrelationId.value.trim()
  const correlationFocus = correlationTrimmed.length > 0

  if (correlationFocus) {
    const correlationLower = correlationTrimmed.toLowerCase()
    events = events.filter(e =>
      (e.correlation_id ?? '').toLowerCase().includes(correlationLower),
    )
    if (activeTab.value === 'mqtt') {
      events = events.filter(e => e.source === 'mqtt' || e.source === 'esp')
    } else if (activeTab.value === 'logs') {
      events = events.filter(e => e.source === 'server')
    }
    return events
  }

  // ⭐ Filter by selected data sources (KATEGORISCH - ALLE Events filtern!)
  // Anders als severity/esp_id: DataSource-Änderung kann Events AUSSCHLIESSEN
  // die vorher inkludiert waren (z.B. User deselektiert "sensor_data")
  // Daher kein _sourceType Skip - alle Events müssen gegen aktuelle Auswahl geprüft werden
  events = events.filter(e => {
    // Events without dataSource are always shown (legacy/system events)
    if (!e.dataSource) return true
    return selectedDataSources.value.includes(e.dataSource)
  })

  // Filter by tab
  if (activeTab.value === 'mqtt') {
    events = events.filter(e => e.source === 'mqtt' || e.source === 'esp')
  } else if (activeTab.value === 'logs') {
    events = events.filter(e => e.source === 'server')
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // HYBRID-FILTER (Phase 4): Server-Events skippen, WebSocket-Events filtern
  // Server hat bereits nach severity/esp_ids gefiltert (Phase 3)
  // ═══════════════════════════════════════════════════════════════════════════

  // Filter by ESP ID (KATEGORISCH - ALLE Events filtern!)
  // Anders als ursprünglich angenommen: ESP-ID ist kategorisch, nicht additiv.
  // Wenn User von "Alle ESPs" zu "ESP_A" wechselt, müssen alte Events von
  // anderen ESPs ausgeschlossen werden. Daher KEIN _sourceType Skip.
  if (filterEspId.value) {
    const espFilter = filterEspId.value.toLowerCase()
    events = events.filter(e => {
      return e.esp_id?.toLowerCase().includes(espFilter)
    })
  }

  // Filter by severity level (KATEGORISCH - ALLE Events filtern!)
  // User kann Level ENTFERNEN (z.B. "Info" deaktivieren)
  // Alte Server-Events mit diesem Level müssen dann auch verschwinden
  events = events.filter(e => {
    if (!e.severity) return true  // Events ohne severity immer zeigen
    return filterLevels.value.has(e.severity)
  })

  // Event-Type-Filter ENTFERNT - DataSource-Filter ist ausreichend (Phase 5)

  // Filter by time range
  if (filterTimeRange.value !== 'all') {
    const now = Date.now()

    if (filterTimeRange.value === 'custom' && customStartDate.value && customEndDate.value) {
      // Custom date range: filter between start and end dates
      const startTime = new Date(customStartDate.value).getTime()
      const endTime = new Date(customEndDate.value).setHours(23, 59, 59, 999) // End of day
      events = events.filter(e => {
        const eventTime = new Date(e.timestamp).getTime()
        return eventTime >= startTime && eventTime <= endTime
      })
    } else {
      // Preset time ranges (relative to now)
      const ranges: Record<string, number> = {
        '1h': 60 * 60 * 1000,
        '6h': 6 * 60 * 60 * 1000,
        '24h': 24 * 60 * 60 * 1000,
        '7d': 7 * 24 * 60 * 60 * 1000,
        '30d': 30 * 24 * 60 * 60 * 1000,
      }
      const cutoff = now - (ranges[filterTimeRange.value] || 0)
      events = events.filter(e => new Date(e.timestamp).getTime() > cutoff)
    }
  }

  return events
})

/**
 * AUT-196 Paket C: All events matching the correlation deep-link, regardless of
 * other active filters (tab/severity/esp/timeRange/dataSources). Used to detect
 * whether other filters are hiding correlation-relevant events.
 */
const allCorrelationEvents = computed(() => {
  const correlationTrimmed = filterCorrelationId.value.trim()
  if (correlationTrimmed.length === 0) return [] as UnifiedEvent[]
  const correlationLower = correlationTrimmed.toLowerCase()
  return unifiedEvents.value.filter(e =>
    (e.correlation_id ?? '').toLowerCase().includes(correlationLower),
  )
})

/**
 * AUT-196 Paket C: Show banner only when a correlation deep-link is active AND
 * other filters (tab) currently hide some correlation events.
 */
const correlationFilterMismatchCount = computed(() => {
  if (!isCorrelationDeepLink.value) return 0
  return Math.max(0, allCorrelationEvents.value.length - filteredEvents.value.length)
})

const eventCounts = computed(() => {
  let events = 0
  let logs = 0
  let mqtt = 0
  for (const e of unifiedEvents.value) {
    if (e.severity === 'error' || e.severity === 'critical') events++
    if (e.source === 'server') logs++
    if (e.source === 'mqtt' || e.source === 'esp') mqtt++
  }
  return { events, logs, mqtt }
})

const opsBannerEntries = computed(() =>
  opsLifecycleStore.runningHighRiskEntries.slice(0, 5),
)

const OPS_STATUS_LABELS: Record<string, string> = {
  initiated: 'Initiiert',
  running: 'Läuft',
  partial: 'Teilweise',
  success: 'Erfolgreich',
  failed: 'Fehlgeschlagen',
}

const uniqueEspIds = computed(() => {
  const ids = new Set<string>()
  for (const e of unifiedEvents.value) {
    if (e.esp_id) ids.add(e.esp_id)
  }
  return [...ids].sort()
})

// NOTE: ESP counts were moved to Dashboard - kept for potential future use
// const totalEspCount = computed(() => espStore.deviceCount)
// const onlineEspCount = computed(() => espStore.onlineDevices.length)

// hasMoreEvents is now a ref, updated from pagination.has_more in API response
// See: paginationCursor, hasMoreEvents refs in "Event Loading State" section

// ============================================================================
// Methods - Event Transformation
// ============================================================================

function handleWebSocketMessage(message: WebSocketMessage) {
  if (message.type === 'events_restored') {
    void handleEventsRestored(message)
  }

  if (isPaused.value) return

  // ⭐ CHANGED: Don't filter here - add dataSource and let filteredEvents handle it
  const event = transformToUnifiedEvent(message)
  unifiedEvents.value.unshift(event)

  // Safety-Limit: Warnung nur einmal bis wieder unterhalb des Limits.
  enforceMaxEvents('after WebSocket message')
}

/**
 * Handle events_restored WebSocket message from backup restore
 *
 * This is triggered when events are restored from a backup.
 * We reload the historical events and show a toast notification.
 */
async function handleEventsRestored(message: WebSocketMessage) {
  const data = message.data as {
    backup_id: string
    restored_count: number
    event_ids: string[]
    message: string
  }

  logger.info('Events restored', data)

  // Show success toast
  showToast(`✅ ${data.message}`, 'success')

  // Store restored event IDs for highlighting
  data.event_ids.forEach(id => {
    restoredEventIds.value.add(`audit_${id}`)
  })

  // Clear highlight after 10 seconds
  setTimeout(() => {
    data.event_ids.forEach(id => {
      restoredEventIds.value.delete(`audit_${id}`)
    })
  }, 10000)

  // Reload historical events and statistics
  await Promise.all([
    loadHistoricalEvents(),
    loadStatistics(),
  ])
}

/**
 * Show a toast notification
 */
function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
  toastMessage.value = message
  toastType.value = type

  // Auto-hide after 6 seconds
  setTimeout(() => {
    toastMessage.value = null
  }, 6000)
}

/**
 * Hide the toast notification
 */
function hideToast() {
  toastMessage.value = null
}

function transformToUnifiedEvent(wsMessage: WebSocketMessage): UnifiedEvent {
  const data = wsMessage.data as Record<string, unknown>
  const eventType = wsMessage.type
  const correlationId = extractCorrelationId(data)
  const requestId = extractRequestId(data)
  const contractResult = validateContractEvent(eventType, data)

  if (contractResult.kind === 'unknown_event') {
    const signal = buildContractIntegritySignal({
      kind: contractResult.kind,
      incomingEventType: eventType,
      reason: contractResult.reason,
      incomingData: data,
      correlationId,
      requestId,
    })
    return {
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
      timestamp: new Date(wsMessage.timestamp * 1000).toISOString(),
      event_type: signal.eventType,
      severity: signal.severity,
      source: 'server',
      dataSource: 'audit_log',
      message: signal.message,
      correlation_id: correlationId,
      request_id: requestId,
      data: signal.data,
      _sourceType: 'websocket',
    }
  }

  if (contractResult.kind === 'mismatch') {
    const signal = buildContractIntegritySignal({
      kind: contractResult.kind,
      incomingEventType: eventType,
      reason: contractResult.reason,
      incomingData: data,
      correlationId,
      requestId,
    })
    return {
      id: `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
      timestamp: new Date(wsMessage.timestamp * 1000).toISOString(),
      event_type: signal.eventType,
      severity: signal.severity,
      source: 'server',
      dataSource: 'audit_log',
      esp_id: extractEspId(data),
      message: signal.message,
      correlation_id: correlationId,
      request_id: requestId,
      data: signal.data,
      _sourceType: 'websocket',
    }
  }

  // Extract common fields
  const espId = extractEspId(data)
  const gpio = typeof data.gpio === 'number' ? data.gpio : undefined
  const errorCode = extractErrorCode(data)
  const severity = determineSeverity(wsMessage, errorCode)
  const source = determineSource(eventType)
  const message = generateGermanMessage(wsMessage, errorCode)

  // ⭐ NEW: Determine dataSource for client-side filtering
  const dataSource = getDataSourceForEventType(eventType)

  return {
    id: `${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
    timestamp: new Date(wsMessage.timestamp * 1000).toISOString(),
    event_type: eventType,
    severity,
    source,
    dataSource,
    esp_id: espId,
    zone_id: typeof data.zone_id === 'string' ? data.zone_id : undefined,
    zone_name: typeof data.zone_name === 'string' ? data.zone_name : undefined,
    message,
    error_code: errorCode,
    error_category: errorCode ? detectCategory(errorCode) : undefined,
    gpio,
    device_type: typeof data.sensor_type === 'string' ? data.sensor_type : typeof data.actuator_type === 'string' ? data.actuator_type : undefined,
    correlation_id: correlationId,
    request_id: requestId,
    data,
    // Phase 4: Tag as WebSocket event (needs client-side filtering)
    _sourceType: 'websocket',
  }
}

function extractErrorCode(data: Record<string, unknown>): number | string | undefined {
  if (typeof data.error_code === 'number' || typeof data.error_code === 'string') {
    return data.error_code
  }
  return undefined
}

/**
 * Bestimmt Severity für Event-Anzeige.
 *
 * SERVER-CENTRIC: Nutzt primär data.severity vom Server.
 * Der Server hat die vollständige Error-Code-Logik (100+ Mappings)
 * und liefert bereits die korrekte Severity.
 *
 * Fallback: Nur wenn Server keine Severity schickt.
 */
function determineSeverity(wsMessage: WebSocketMessage, _errorCode?: number | string): UnifiedEvent['severity'] {
  const data = wsMessage.data as Record<string, unknown>

  // PRIMÄR: Server-Severity verwenden (wenn vorhanden)
  if (data.severity) {
    const serverSeverity = String(data.severity).toLowerCase()
    if (['info', 'warning', 'error', 'critical'].includes(serverSeverity)) {
      return serverSeverity as UnifiedEvent['severity']
    }
  }

  // FALLBACK: zentrale Semantik aus Contract-Mapper
  return inferFallbackSeverity(wsMessage.type, data)
}

function determineSource(eventType: string): UnifiedEvent['source'] {
  const espEvents = [
    'sensor_data', 'actuator_status', 'actuator_response', 'actuator_alert', 'esp_health',
    'config_response', 'zone_assignment', 'subzone_assignment', 'sensor_health',
    'intent_outcome', 'intent_outcome_lifecycle',
  ]
  const mqttEvents = ['sensor_data', 'actuator_status', 'esp_health']
  const logicEvents = [
    'logic_execution',
    'notification',
    'rule_degraded',
    'rule_recovered',
    'conflict.arbitration',
  ]
  const userEvents = ['device_approved', 'device_rejected']

  if (userEvents.includes(eventType)) return 'user'
  if (logicEvents.includes(eventType)) return 'logic'
  if (mqttEvents.includes(eventType)) return 'mqtt'
  if (espEvents.includes(eventType)) return 'esp'
  return 'server'
}

/**
 * Generiert deutsche Nachrichten für Events.
 *
 * SERVER-CENTRIC: Nutzt primär data.message vom Server.
 * Der Server liefert bereits menschenverständliche deutsche Messages.
 *
 * Fallback: Nur für Events ohne Server-Message.
 */
function generateGermanMessage(wsMessage: WebSocketMessage, _errorCode?: number | string): string {
  const data = wsMessage.data as Record<string, unknown>
  if (wsMessage.type === 'intent_outcome_lifecycle') {
    const et = String(data.event_type ?? '')
    const rc = String(data.reason_code ?? '')
    return `Zwischenstand (Konfiguration): ${et}${rc ? ` — ${rc}` : ''}`
  }
  if (wsMessage.type === 'intent_outcome') {
    const flow = String(data.flow ?? '')
    const outcome = String(data.outcome ?? '')
    const codeRaw = data.code
    const code = codeRaw != null && String(codeRaw).trim().length > 0 ? String(codeRaw) : ''
    const terminal =
      data.is_final === true || String(data.terminality ?? '').toLowerCase().includes('terminal')
    const prefix = terminal ? 'Ergebnis' : 'Vorgang'
    const cid = (extractCorrelationId(data) || '').trim()
    const shortC = cid.length <= 14 ? cid : `…${cid.slice(-10)}`
    let msg = `${prefix}: ${flow || '?'}/${outcome || '?'}` + (shortC ? ` (${shortC})` : '')
    if (code) msg += ` · Firmware-Code: ${code}`
    return msg
  }
  const serverMessage = typeof data.message === 'string' ? data.message.trim() : ''
  if (serverMessage.length > 0) {
    return serverMessage
  }
  const baseEvent: UnifiedEvent = {
    id: 'preview',
    timestamp: new Date(wsMessage.timestamp * 1000).toISOString(),
    event_type: wsMessage.type,
    severity: 'info',
    source: determineSource(wsMessage.type),
    message: typeof data.message === 'string' ? data.message : '',
    esp_id: extractEspId(data),
    gpio: typeof data.gpio === 'number' ? data.gpio : undefined,
    error_code: extractErrorCode(data),
    data,
  }

  const transformed = transformEventMessage(baseEvent)
  return transformed.summary || transformed.description || baseEvent.message || `Event: ${wsMessage.type}`
}

// ============================================================================
// Methods - Load Historical Events
// ============================================================================

/**
 * Build server-side filter parameters for API calls
 * Extracted to avoid code duplication between loadHistoricalEvents and handleLoadMore
 */
function buildServerFilterParams(options?: {
  hours?: number | null
  limitPerSource?: number
}) {
  // Severity filter only makes sense when audit_log is included
  const severityForServer = selectedDataSources.value.includes('audit_log')
    ? Array.from(filterLevels.value)
    : undefined

  // ESP-ID filter for server (if set)
  const espIdsForServer = filterEspId.value ? [filterEspId.value] : undefined

  return {
    sources: selectedDataSources.value,
    hours: options?.hours ?? eventLoadHours.value,
    limitPerSource: options?.limitPerSource ?? currentLimitPerSource.value,
    severity: severityForServer,
    espIds: espIdsForServer,
  }
}

/**
 * Load more historical events using cursor-based pagination
 *
 * Uses `before_timestamp` cursor from previous response to load older events.
 * This is the Infinite Scroll implementation.
 */
async function handleLoadMore(): Promise<void> {
  if (isLoadingMore.value || !hasMoreEvents.value) return

  isLoadingMore.value = true
  try {
    logger.debug('Load More', { cursor: paginationCursor.value ?? 'initial' })

    // Build params with pagination cursor
    const params = buildServerFilterParams()

    // Add pagination cursor if we have one (for subsequent loads)
    const response = await auditApi.getAggregatedEvents({
      ...params,
      beforeTimestamp: paginationCursor.value ?? undefined,
    })

    // Update pagination state from response
    hasMoreEvents.value = response.pagination.has_more
    paginationCursor.value = response.pagination.oldest_timestamp
    totalAvailableEvents.value = response.pagination.total_available

    // Transform and add to events list
    const historicalEvents = response.events.map(transformAggregatedEventToUnified)

    // Merge with existing events, avoiding duplicates
    const existingIds = new Set(unifiedEvents.value.map(e => e.id))
    const newEvents = historicalEvents.filter(e => !existingIds.has(e.id))

    // Append older events to end (cursor pagination guarantees oldest→newest order)
    // Existing events are already sorted newest-first, new events are older → append
    unifiedEvents.value = [...unifiedEvents.value, ...newEvents]

    // Safety-Limit: Warnung nur einmal bis wieder unterhalb des Limits.
    enforceMaxEvents('while loading more historical events')

    logger.debug('Loaded more events', { newEvents: newEvents.length, total: unifiedEvents.value.length, hasMore: hasMoreEvents.value })
  } catch (error) {
    logger.error('Failed to load more events', error)
  } finally {
    isLoadingMore.value = false
  }
}

/**
 * Load historical events from Aggregated Events API
 *
 * ⭐ CHANGED: Always loads ALL sources (client-side filtering handles visibility)
 * ⭐ NEW: By default loads ALL events (eventLoadHours=null), not just recent ones
 *
 * Uses the new multi-source aggregator that combines:
 * - audit_log: System events, config responses, errors
 * - sensor_data: Sensor readings from database
 * - esp_health: ESP device status/heartbeats
 * - actuators: Actuator command history
 */
async function loadHistoricalEvents(): Promise<void> {
  isLoading.value = true

  // Reset pagination state (fresh load, not "load more")
  paginationCursor.value = null
  hasMoreEvents.value = true

  try {
    const correlationId = filterCorrelationId.value.trim()
    if (correlationId.length > 0) {
      const correlatedLogs = await auditApi.getCorrelatedEvents(correlationId, 200)
      unifiedEvents.value = correlatedLogs
        .map(transformAuditLogToUnified)
        .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

      totalAvailableEvents.value = correlatedLogs.length
      hasMoreEvents.value = false
      paginationCursor.value = null

      enforceMaxEvents('while loading correlated events')
      logger.info(`Loaded ${unifiedEvents.value.length} correlated events for ${correlationId}`)
      logger.info(`Zeige ${filteredEvents.value.length} von ${unifiedEvents.value.length} Events (${unifiedEvents.value.length - filteredEvents.value.length} durch Filter versteckt)`)
      return
    }

    // Load events from user-selected data sources (persisted via DataSourceSelector)
    // Client-side filtering in filteredEvents handles additional visibility filters
    logger.debug('loadHistoricalEvents called', { sources: selectedDataSources.value, hours: eventLoadHours.value ?? 'ALL' })

    // WICHTIG: Sehr hoher limitPerSource um alle historischen Events zu laden
    // Virtual Scrolling in UnifiedEventList kickt ab 200 Events automatisch ein
    const response = await auditApi.getAggregatedEvents(buildServerFilterParams())

    // Update pagination state from aggregated response
    hasMoreEvents.value = response.pagination.has_more
    paginationCursor.value = response.pagination.oldest_timestamp
    totalAvailableEvents.value = response.pagination.total_available

    logger.debug('API response', {
      eventCount: response.events.length,
      totalLoaded: response.total_loaded,
      totalAvailable: response.total_available,
      sources: response.sources,
      sourceCounts: response.source_counts,
      firstEvent: response.events[0],
      eventTypes: [...new Set(response.events.map(e => e.source))]
    })

    // ⭐ CRITICAL DEBUG: Zeige Sensor-Events explizit
    const sensorEvents = response.events.filter(e => e.source === 'sensor_data')
    logger.debug('Sensor Events in Response', {
      count: sensorEvents.length,
      first5: sensorEvents.slice(0, 5).map(e => ({
        id: e.id,
        title: e.title,
        message: e.message,
        timestamp: e.timestamp
      }))
    })

    // Transform API events to frontend UnifiedEvent format
    const historicalEvents = response.events.map(transformAggregatedEventToUnified)

    logger.debug('After transform', {
      count: historicalEvents.length,
      firstEvent: historicalEvents[0],
      eventTypes: [...new Set(historicalEvents.map(e => e.event_type))],
      dataSources: [...new Set(historicalEvents.map(e => e.dataSource))],
      sensorEventsCount: historicalEvents.filter(e => e.dataSource === 'sensor_data').length
    })

    // Merge with existing events, avoiding duplicates
    const existingIds = new Set(unifiedEvents.value.map(e => e.id))
    const newEvents = historicalEvents.filter(e => !existingIds.has(e.id))

    logger.debug('After duplicate filter', {
      before: historicalEvents.length,
      after: newEvents.length,
      duplicatesRemoved: historicalEvents.length - newEvents.length,
      existingCount: existingIds.size,
      newSensorEvents: newEvents.filter(e => e.dataSource === 'sensor_data').length
    })

    // Add historical events (they come sorted by timestamp DESC from API)
    unifiedEvents.value = [...unifiedEvents.value, ...newEvents]

    // Sort by timestamp (newest first)
    unifiedEvents.value.sort((a, b) =>
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )

    // Safety-Limit: Warnung nur einmal bis wieder unterhalb des Limits.
    enforceMaxEvents('while loading historical events')

    // ⭐ CRITICAL DEBUG: Finale Filter-Statistiken
    logger.debug('Final unifiedEvents', {
      totalInMemory: unifiedEvents.value.length,
      byDataSource: {
        audit_log: unifiedEvents.value.filter(e => e.dataSource === 'audit_log').length,
        sensor_data: unifiedEvents.value.filter(e => e.dataSource === 'sensor_data').length,
        esp_health: unifiedEvents.value.filter(e => e.dataSource === 'esp_health').length,
        actuators: unifiedEvents.value.filter(e => e.dataSource === 'actuators').length,
        undefined: unifiedEvents.value.filter(e => !e.dataSource).length
      },
      filterSettings: {
        selectedDataSources: selectedDataSources.value,
        filterLevels: Array.from(filterLevels.value),
        filterEspId: filterEspId.value,
        filterTimeRange: filterTimeRange.value
      },
      filteredCount: filteredEvents.value.length
    })

    logger.info(`Loaded ${newEvents.length} historical events from ${response.sources.length} source(s)`)
    logger.info(`Zeige ${filteredEvents.value.length} von ${unifiedEvents.value.length} Events (${unifiedEvents.value.length - filteredEvents.value.length} durch Filter versteckt)`)
  } catch (error) {
    logger.error('Failed to load historical events', error)
  } finally {
    isLoading.value = false
  }
}

/**
 * Normalisiert einen Timestamp zu UTC ISO-Format.
 * Server sendet manchmal naive Timestamps (ohne 'Z'),
 * die der Browser fälschlich als Lokalzeit interpretiert.
 *
 * @param timestamp - ISO-String vom Server (z.B. "2026-01-26T17:32:02")
 * @returns ISO-String mit UTC-Marker (z.B. "2026-01-26T17:32:02Z")
 */
function normalizeToUTCIso(timestamp: string): string {
  // Prüfe ob bereits Timezone-Info vorhanden (Z, +00:00, -05:00, etc.)
  if (timestamp.endsWith('Z') || timestamp.includes('+') || timestamp.match(/-\d{2}:\d{2}$/)) {
    return timestamp
  }
  // Füge 'Z' hinzu um als UTC zu markieren
  return timestamp + 'Z'
}

/**
 * Transform aggregated API event to frontend UnifiedEvent format
 */
function transformAggregatedEventToUnified(apiEvent: UnifiedEventFromAPI): UnifiedEvent {
  const metadata = apiEvent.metadata || {}

  // Map API source to frontend source
  const sourceMapping: Record<string, UnifiedEvent['source']> = {
    'audit_log': 'server',
    'sensor_data': 'esp',
    'esp_health': 'esp',
    'actuators': 'esp',
  }

  // Map source-specific event types
  let eventType = 'system_event'
  if (apiEvent.source === 'sensor_data') {
    eventType = 'sensor_data'
  } else if (apiEvent.source === 'esp_health') {
    eventType = 'esp_health'
  } else if (apiEvent.source === 'actuators') {
    eventType = 'actuator_status'
  } else if (metadata.event_type) {
    eventType = String(metadata.event_type)
  }

  // ⭐ NEW: Keep original dataSource for client-side filtering
  const dataSource = apiEvent.source as DataSource

  return {
    id: apiEvent.id,
    timestamp: normalizeToUTCIso(apiEvent.timestamp),
    event_type: eventType,
    severity: apiEvent.severity,
    source: sourceMapping[apiEvent.source] || 'server',
    dataSource,
    esp_id: apiEvent.device_id || undefined,
    zone_id: metadata.zone_id as string | undefined,
    zone_name: metadata.zone_name as string | undefined,
    message: apiEvent.message,
    error_code: metadata.error_code as string | number | undefined,
    error_category: metadata.error_code ? detectCategory(metadata.error_code as string | number) : undefined,
    gpio: metadata.gpio as number | undefined,
    device_type: (metadata.sensor_type || metadata.actuator_type) as string | undefined,
    // Phase 3: Correlation ID for event tracking
    correlation_id: (metadata.correlation_id as string) || undefined,
    // Phase 4: Request ID for server-log correlation
    request_id: (metadata.request_id as string) || undefined,
    data: metadata,
    // Phase 4: Tag as server-loaded event (already filtered by server, skip client-side filter)
    _sourceType: 'server',
  }
}

function transformAuditLogToUnified(log: AuditLog): UnifiedEvent {
  const details = (log.details || {}) as Record<string, unknown>
  const sourceType = String(log.source_type || '').toLowerCase()
  const source: UnifiedEvent['source'] =
    sourceType === 'esp' || sourceType === 'esp32'
      ? 'esp'
      : sourceType === 'mqtt'
        ? 'mqtt'
        : sourceType === 'user'
          ? 'user'
          : sourceType === 'scheduler'
            ? 'logic'
            : 'server'

  const espFromDetails = typeof details.esp_id === 'string'
    ? details.esp_id
    : typeof details.device_id === 'string'
      ? details.device_id
      : undefined

  const fallbackEspId = source === 'esp' && typeof log.source_id === 'string' && log.source_id.length > 0
    ? log.source_id
    : undefined

  return {
    id: `audit_${log.id}`,
    timestamp: normalizeToUTCIso(log.created_at),
    event_type: log.event_type,
    severity: log.severity,
    source,
    dataSource: 'audit_log',
    esp_id: espFromDetails ?? fallbackEspId,
    zone_id: typeof details.zone_id === 'string' ? details.zone_id : undefined,
    zone_name: typeof details.zone_name === 'string' ? details.zone_name : undefined,
    message: log.message || '',
    error_code: log.error_code || undefined,
    error_category: log.error_code ? detectCategory(log.error_code) : undefined,
    correlation_id: log.correlation_id || undefined,
    request_id: log.request_id || undefined,
    data: details,
    _sourceType: 'server',
  }
}

// ============================================================================
// Methods - Health Summary
// ============================================================================

let healthRefreshInterval: ReturnType<typeof setInterval> | null = null

async function loadHealthData() {
  if (isMobile.value) return
  isHealthLoading.value = true
  try {
    const response = await getFleetHealth()
    healthDevices.value = response.devices
  } catch (error) {
    logger.error('Failed to load health data', error)
  } finally {
    isHealthLoading.value = false
  }
}

// ============================================================================
// Methods - UI Actions
// ============================================================================

function handleTabChange(tabId: TabId) {
  activeTab.value = tabId
}

function handleOpenAlerts() {
  inboxStore.toggleDrawer()
}

function handleFilterDevice(espId: string) {
  filterEspId.value = espId
  activeTab.value = 'events'
  selectedEvent.value = null

  // Show toast with filtered event count
  nextTick(() => {
    const count = filteredEvents.value.length
    showToast(`${count} Event${count !== 1 ? 's' : ''} für ${espId} gefunden`, 'info')
  })
}

function handleShowServerLogs(event: UnifiedEvent) {
  if (event.request_id) {
    // Phase 4: Precise log correlation via request_id
    logsRequestId.value = event.request_id
    logsStartTime.value = undefined
    logsEndTime.value = undefined
  } else {
    // Fallback: time window (±30s) for events without request_id
    logsRequestId.value = undefined
    const timestamp = new Date(event.timestamp).getTime()
    logsStartTime.value = new Date(timestamp - 30000).toISOString()
    logsEndTime.value = new Date(timestamp + 30000).toISOString()
  }
  activeTab.value = 'logs'
  selectedEvent.value = null
}

/**
 * Handle data source selection change
 *
 * ⭐ CHANGED: No reload needed - just update selection for client-side filtering
 * filteredEvents computed will handle visibility automatically
 */
async function handleDataSourcesChange(sources: DataSource[]): Promise<void> {
  selectedDataSources.value = sources
  // That's it! filteredEvents computed handles the rest via client-side filtering
}

function togglePause() {
  const waspaused = isPaused.value
  isPaused.value = !isPaused.value

  // On resume (Pause → Live): reload historical events to catch up on missed ones
  if (waspaused && !isPaused.value) {
    loadHistoricalEvents()
  }
}

function handleExport() {
  const data = JSON.stringify(filteredEvents.value, null, 2)
  const blob = new Blob([data], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `system-monitor-${activeTab.value}-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// NOTE: Refresh functionality removed from header - manual refresh via filter changes
// async function handleRefresh() {
//   await loadHistoricalEvents()
// }

function selectEvent(event: UnifiedEvent) {
  selectedEvent.value = event
}

function closeEventDetails() {
  selectedEvent.value = null
}

// NOTE: Stats toggle moved to Cleanup Panel - statistics accessible there
// function toggleStats() {
//   showStats.value = !showStats.value
//   if (showStats.value && !statistics.value) {
//     loadStatistics()
//   }
// }

// ============================================================================
// Methods - Audit Admin Features
// ============================================================================

async function loadStatistics() {
  try {
    statistics.value = await auditApi.getStatistics(statisticsTimeRange.value)
  } catch (err) {
    logger.error('Failed to load statistics', err)
  }
}

/**
 * Change statistics time range and reload
 */
async function changeStatisticsTimeRange(range: StatisticsTimeRange) {
  statisticsTimeRange.value = range
  await loadStatistics()
}

/**
 * Get computed label for error count
 */
const errorStatLabel = computed(() => `Fehler (${TIME_RANGE_LABELS[statisticsTimeRange.value]})`)

/**
 * Handler for cleanup panel success - reload stats
 */
async function handleCleanupSuccess() {
  await Promise.all([
    loadStatistics(),
    loadHistoricalEvents(),
  ])
}

function formatNumber(num: number): string {
  return new Intl.NumberFormat('de-DE').format(num)
}

// Mobile detection
function checkMobile() {
  isMobile.value = window.innerWidth < 768
}

function handleResize() {
  checkMobile()
}

const isCorrelationDeepLink = computed(() => filterCorrelationId.value.trim().length > 0)

function clearCorrelationFromRoute(): void {
  const next = { ...route.query } as Record<string, string | string[] | undefined>
  delete next.correlation
  void router.replace({ path: route.path, query: next })
}

/**
 * AUT-196 Paket C: Reset all "other" filters that could hide correlation events,
 * keeping the correlation focus active. Switches to the events tab so all
 * correlation-related events become visible.
 */
function resetFiltersForCorrelation(): void {
  activeTab.value = 'events'
  filterEspId.value = ''
  filterLevels.value = new Set(['info', 'warning', 'error', 'critical'])
  filterTimeRange.value = 'all'
  customStartDate.value = undefined
  customEndDate.value = undefined
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(async () => {
  // Initialize mobile detection
  checkMobile()
  window.addEventListener('resize', handleResize)

  // Read URL params for deep-linking (esp handled by watcher with immediate: true)
  // correlation= erzwingt Tab "events" und hat Vorrang vor ?tab= (AUT-196)
  if (route.query.correlation) {
    activeTab.value = 'events'
  } else if (route.query.tab) {
    const tab = String(route.query.tab) as TabId
    if (['events', 'logs', 'database', 'mqtt', 'health', 'diagnostics', 'reports', 'hierarchy'].includes(tab)) {
      activeTab.value = tab
    }
  }
  if (route.query.timeRange) {
    const range = String(route.query.timeRange)
    if (['all', '1h', '6h', '24h', '7d', '30d', 'custom'].includes(range)) {
      filterTimeRange.value = range as typeof filterTimeRange.value
    }
  }

  // Subscribe to all event types for live updates
  ALL_EVENT_TYPES.forEach(eventType => {
    wsUnsubscribers.push(on(eventType, handleWebSocketMessage))
  })

  // Load historical events from Audit Log
  await loadHistoricalEvents()

  // Load statistics for header display (total DB events)
  loadStatistics()

  // Ensure ESP Store has current data for header ESP count
  espStore.fetchAll()

  // Load health data for Health Summary Bar (desktop only)
  if (!isMobile.value) {
    loadHealthData()
    healthRefreshInterval = setInterval(() => {
      if (!isMobile.value && activeTab.value === 'events') {
        loadHealthData()
      }
    }, 30000)
  }
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  wsUnsubscribers.forEach(unsub => unsub())
  wsUnsubscribers.length = 0
  if (healthRefreshInterval) {
    clearInterval(healthRefreshInterval)
    healthRefreshInterval = null
  }
})

// Watch for URL changes (deep-linking from other views)
// immediate: true ensures this runs on mount, eliminating duplicate init in onMounted
watch(() => route.query.esp, (newEsp) => {
  filterEspId.value = newEsp ? String(newEsp) : ''
}, { immediate: true })

watch(() => route.query.correlation, (newCorrelation) => {
  filterCorrelationId.value = newCorrelation ? String(newCorrelation) : ''
  if (newCorrelation) {
    activeTab.value = 'events'
  }
}, { immediate: true })

watch(() => route.query.level, applyLevelQueryParam, { immediate: true })

watch(
  () => route.query.source,
  (newRaw, oldRaw) => {
    const norm = (x: unknown): string =>
      x === undefined || x === null
        ? ''
        : String(Array.isArray(x) ? x[0] : x)
            .trim()
            .toLowerCase()
    const v = norm(newRaw)
    if (v === 'alerts' || v === 'alert') {
      selectedDataSources.value = [...ALERT_FOCUS_DATA_SOURCES]
      return
    }
    const prev = norm(oldRaw)
    if ((prev === 'alerts' || prev === 'alert') && v === '') {
      selectedDataSources.value = [...DEFAULT_MONITOR_DATA_SOURCES]
    }
  },
  { immediate: true },
)

// Watch for server-side filter changes to trigger reload
// These filters are now sent to the server for efficient filtering
// All three affect buildServerFilterParams() - must trigger reload when changed
let filterReloadTimeout: ReturnType<typeof setTimeout> | null = null
watch(
  [selectedDataSources, filterLevels, filterEspId, filterCorrelationId],
  () => {
    // Debounce to avoid multiple rapid API calls
    if (filterReloadTimeout) {
      clearTimeout(filterReloadTimeout)
    }
    filterReloadTimeout = setTimeout(() => {
      // Only reload if we're on the events tab and not already loading
      if (activeTab.value === 'events' && !isLoading.value) {
        logger.debug('Server-side filters changed, reloading events')
        loadHistoricalEvents()
      }
    }, 300)  // 300ms debounce
  },
  { deep: true }
)

// Logs-Zeitfenster zurücksetzen bei Tab-Wechsel weg von logs
watch(activeTab, (newTab) => {
  if (newTab !== 'logs') {
    logsStartTime.value = undefined
    logsEndTime.value = undefined
    logsRequestId.value = undefined
  }
})

// Auto-scroll to active tab on mobile
watch(activeTab, (newTab) => {
  if (isMobile.value) {
    nextTick(() => {
      const tabElement = document.querySelector(`[data-tab="${newTab}"]`)
      if (tabElement) {
        tabElement.scrollIntoView({
          behavior: 'smooth',
          block: 'nearest',
          inline: 'center'
        })
      }
    })
  }
})
</script>

<template>
  <div class="system-monitor">
    <!-- Consolidated Tab Bar (Live Toggle + Tabs + Actions) -->
    <MonitorTabs
      :active-tab="activeTab"
      :event-counts="eventCounts"
      :is-paused="isPaused"
      :is-admin="authStore.isAdmin"
      @update:active-tab="handleTabChange"
      @toggle-pause="togglePause"
      @export="handleExport"
      @open-cleanup-panel="showCleanupPanel = true"
    />

    <div
      v-if="isCorrelationDeepLink"
      class="correlation-deep-link-banner"
      role="status"
    >
      <AlertTriangle class="correlation-deep-link-banner__icon" :size="16" />
      <span class="correlation-deep-link-banner__text">
        Korrelations-Deep-Link: Datenquellen-, Schweregrad-, Zeitraum- und ESP-Filter sind für diese Ansicht ausgeschaltet.
      </span>
      <button
        type="button"
        class="correlation-deep-link-banner__btn"
        @click="clearCorrelationFromRoute"
      >
        Korrelation schließen
      </button>
    </div>

    <RestRequestIdDevBar />

    <div v-if="opsBannerEntries.length > 0" class="ops-banner">
      <div class="ops-banner__title">High-Risk Jobs</div>
      <div class="ops-banner__list">
        <div
          v-for="entry in opsBannerEntries"
          :key="entry.id"
          class="ops-banner__item"
        >
          <span class="ops-banner__name">{{ entry.title }}</span>
          <span
            class="ops-banner__status"
            :class="`ops-banner__status--${entry.status}`"
          >
            {{ OPS_STATUS_LABELS[entry.status] }}
          </span>
          <span v-if="entry.execution_id" class="ops-banner__meta">
            {{ entry.execution_id }}
          </span>
        </div>
      </div>
    </div>

    <!-- Statistics Bar (collapsible) - ENTFERNT: showStats immer false, Stats nun via Cleanup-Panel -->
    <Transition name="slide-down">
      <div v-if="showStats && statistics" class="stats-bar grid-auto-sm">
        <!-- Gesamt (DB) -->
        <div class="stats-bar__item stats-bar__item--with-tooltip">
          <div class="stats-bar__content">
            <span class="stats-bar__label">Gesamt (DB)</span>
            <span class="stats-bar__value">{{ formatNumber(statistics.total_count) }}</span>
          </div>
          <div class="stats-bar__tooltip">
            Alle Events in der Datenbank gespeichert (inkl. archivierte).
            Im Header sehen Sie nur die geladenen Events.
          </div>
        </div>

        <!-- Fehler mit Zeitraum-Selector -->
        <div
          class="stats-bar__item stats-bar__item--error stats-bar__item--clickable stats-bar__item--with-tooltip"
          @click="showTimeRangeSelector = true"
        >
          <div class="stats-bar__content">
            <span class="stats-bar__label">{{ errorStatLabel }}</span>
            <span class="stats-bar__value">{{ formatNumber(statistics.count_by_severity.error || 0) }}</span>
          </div>
          <div class="stats-bar__tooltip">
            Fehler und kritische Events im gewählten Zeitraum.
            Klicken Sie, um den Zeitraum zu ändern.
          </div>
        </div>

        <!-- Speicher -->
        <div class="stats-bar__item stats-bar__item--with-tooltip">
          <div class="stats-bar__content">
            <span class="stats-bar__label">Speicher</span>
            <span class="stats-bar__value">{{ statistics.storage_estimate_mb }} MB</span>
          </div>
          <div class="stats-bar__tooltip">
            Geschätzter Speicherplatz aller Events in der Datenbank.
          </div>
        </div>

        <!-- Löschbar (statt "Zu bereinigen") -->
        <div class="stats-bar__item stats-bar__item--warning stats-bar__item--with-tooltip">
          <div class="stats-bar__content">
            <span class="stats-bar__label">Löschbar</span>
            <span class="stats-bar__value">{{ formatNumber(statistics.pending_cleanup_count) }}</span>
          </div>
          <div class="stats-bar__tooltip">
            Events die laut Retention-Regeln gelöscht werden können.
            Diese werden beim nächsten Auto-Cleanup entfernt
            (falls aktiviert) oder manuell via Bereinigungspanel.
          </div>
        </div>
      </div>
    </Transition>

    <!-- Content -->
    <main class="monitor-content">
      <!-- Flapping Alert Bar (PKG-20) -->
      <div v-if="espStore.hasFlappingDevices" class="flapping-alert-bar">
        <div class="flapping-alert-bar__indicator" />
        <AlertTriangle class="flapping-alert-bar__icon" />
        <span class="flapping-alert-bar__text">
          <strong>{{ espStore.flappingDeviceCount }}</strong>
          {{ espStore.flappingDeviceCount === 1 ? 'Gerät' : 'Geräte' }}
          mit Disconnect-Loop (≥3 Trennungen in 5 min)
        </span>
        <span class="flapping-alert-bar__devices">
          {{ espStore.flappingDeviceIds.join(', ') }}
        </span>
      </div>

      <!-- Health Summary Bar - nur im Events Tab, nur Desktop -->
      <HealthSummaryBar
        v-if="activeTab === 'events' && !isMobile"
        :devices="healthDevices"
        :is-loading="isHealthLoading"
        :expanded="healthExpanded"
        @update:expanded="healthExpanded = $event"
        @filter-device="handleFilterDevice"
      />

      <!-- AUT-196 Paket C: Correlation-Filter-Hinweis -->
      <div
        v-if="activeTab === 'events' && correlationFilterMismatchCount > 0"
        class="correlation-banner"
        role="status"
        data-testid="correlation-filter-banner"
      >
        <AlertTriangle class="correlation-banner__icon" />
        <span class="correlation-banner__text">
          <strong>{{ correlationFilterMismatchCount }}</strong>
          {{ correlationFilterMismatchCount === 1 ? 'Ereignis' : 'Ereignisse' }}
          durch aktive Filter ausgeblendet
        </span>
        <button
          type="button"
          class="correlation-banner__cta"
          data-testid="correlation-filter-reset"
          @click="resetFiltersForCorrelation"
        >
          Filter für Korrelation zurücksetzen
        </button>
      </div>

      <!-- Events Tab (with integrated filter controls) -->
      <EventsTab
        v-if="activeTab === 'events'"
        :filtered-events="filteredEvents"
        :grouped-events="groupedEvents"
        :grouping-enabled="groupingEnabled"
        :total-available-events="totalAvailableEvents"
        :has-more-events="hasMoreEvents"
        :is-loading-more="isLoadingMore"
        :is-paused="isPaused"
        :restored-event-ids="restoredEventIds"
        :filter-esp-id="filterEspId"
        :filter-levels="filterLevels"
        :filter-time-range="filterTimeRange"
        :unique-esp-ids="uniqueEspIds"
        :custom-start-date="customStartDate"
        :custom-end-date="customEndDate"
        @data-sources-change="handleDataSourcesChange"
        @update:filter-esp-id="filterEspId = $event"
        @update:filter-levels="filterLevels = $event"
        @update:filter-time-range="filterTimeRange = $event"
        @update:custom-start-date="customStartDate = $event"
        @update:custom-end-date="customEndDate = $event"
        @update:grouping-enabled="handleGroupingToggle"
        @load-more="handleLoadMore"
        @select="selectEvent"
      />

      <!-- Server Logs Tab -->
      <ServerLogsTab
        v-else-if="activeTab === 'logs'"
        :initial-start-time="logsStartTime"
        :initial-end-time="logsEndTime"
        :initial-request-id="logsRequestId"
      />

      <!-- Database Tab -->
      <DatabaseTab
        v-else-if="activeTab === 'database'"
      />

      <!-- Health Tab -->
      <HealthTab
        v-else-if="activeTab === 'health'"
        :filter-esp-id="filterEspId"
        @filter-device="handleFilterDevice"
        @open-alerts="handleOpenAlerts"
      />

      <!-- Diagnostics Tab -->
      <DiagnoseTab
        v-else-if="activeTab === 'diagnostics'"
      />

      <!-- Reports Tab -->
      <ReportsTab
        v-else-if="activeTab === 'reports'"
      />

      <!-- MQTT Traffic Tab -->
      <MqttTrafficTab
        v-else-if="activeTab === 'mqtt'"
        :esp-id="filterEspId || undefined"
      />

      <!-- Hierarchy Tab (Phase 6) -->
      <HierarchyTab
        v-else-if="activeTab === 'hierarchy'"
      />
    </main>

    <!-- Event Details Panel -->
    <Transition name="slide-up">
      <EventDetailsPanel
        v-if="selectedEvent"
        :event="selectedEvent"
        @close="closeEventDetails"
        @filter-device="handleFilterDevice"
        @show-server-logs="handleShowServerLogs"
        @select-event="selectEvent"
      />
    </Transition>

    <!-- Cleanup Panel (Consolidated Retention + Backup Management) -->
    <CleanupPanel
      :show="showCleanupPanel"
      @close="showCleanupPanel = false"
      @cleanup-success="handleCleanupSuccess"
      @restore-success="handleCleanupSuccess"
    />

    <!-- Time Range Selector Modal -->
    <Teleport to="body">
      <div v-if="showTimeRangeSelector" class="modal-overlay" @click.self="showTimeRangeSelector = false">
        <div class="modal-content modal-content--compact">
          <div class="modal-header">
            <h3 class="modal-title">Fehler-Zeitraum</h3>
            <button class="modal-close" @click="showTimeRangeSelector = false">
              <X class="w-5 h-5" />
            </button>
          </div>
          <div class="modal-body">
            <p class="text-sm mb-4" style="color: var(--color-text-secondary)">
              Wählen Sie den Zeitraum für die Fehler-Statistik:
            </p>
            <div class="time-range-buttons">
              <button
                v-for="(label, range) in TIME_RANGE_LABELS"
                :key="range"
                class="time-range-btn"
                :class="{ 'time-range-btn--active': statisticsTimeRange === range }"
                @click="changeStatisticsTimeRange(range as StatisticsTimeRange); showTimeRangeSelector = false"
              >
                {{ label }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Toast Notification -->
    <Teleport to="body">
      <Transition name="toast">
        <div
          v-if="toastMessage"
          class="toast"
          :class="`toast--${toastType}`"
          @click="hideToast"
        >
          <CheckCircle v-if="toastType === 'success'" class="toast__icon" />
          <span class="toast__message">{{ toastMessage }}</span>
          <button class="toast__close" @click.stop="hideToast">
            <X class="w-4 h-4" />
          </button>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.system-monitor {
  display: flex;
  flex-direction: column;
  min-height: 100vh;  /* ⭐ Page-Scroll: Mindesthöhe statt fixe Höhe */
  background-color: var(--color-bg-primary);
  color: var(--color-text-primary);
}

.correlation-deep-link-banner {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  padding: var(--space-2) var(--space-lg);
  border-bottom: 1px solid var(--glass-border);
  background: color-mix(in srgb, var(--color-info) 12%, var(--color-bg-secondary));
}

.correlation-deep-link-banner__icon {
  flex-shrink: 0;
  color: var(--color-info);
}

.correlation-deep-link-banner__text {
  flex: 1;
  min-width: 200px;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.4;
}

.correlation-deep-link-banner__btn {
  flex-shrink: 0;
  padding: var(--space-1) var(--space-3);
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.correlation-deep-link-banner__btn:hover {
  background: var(--color-bg-secondary);
  border-color: var(--glass-border-hover);
}

/* Content */
.monitor-content {
  flex: 1;
  display: flex;  /* ⭐ FIX: Flexbox für Kinder (EventsTab, ServerLogsTab, etc.) */
  flex-direction: column;
  /* ⭐ Page-Scroll: Kein overflow: hidden - Seite scrollt als Ganzes */
}

.ops-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-lg);
  border-bottom: 1px solid var(--glass-border);
  background: color-mix(in srgb, var(--color-bg-secondary) 96%, transparent);
}

.ops-banner__title {
  font-size: var(--text-xs);
  text-transform: uppercase;
  color: var(--color-text-secondary);
  margin-top: 0.375rem;
}

.ops-banner__list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.ops-banner__item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-xs);
  padding: 0.25rem 0.5rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--glass-border);
  background: var(--color-bg-tertiary);
}

.ops-banner__name {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.ops-banner__status {
  font-size: var(--text-xs);
  font-weight: 600;
}

.ops-banner__status--initiated {
  color: var(--color-info);
}

.ops-banner__status--running,
.ops-banner__status--partial {
  color: var(--color-warning);
}

.ops-banner__status--success {
  color: var(--color-success);
}

.ops-banner__status--failed {
  color: var(--color-error);
}

.ops-banner__meta {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
}

/* .monitor-tab-content ENTFERNT - nicht verwendet, könnte Verwirrung stiften */

/* ============================================================================
   Mobile: FAB (Floating Action Button) for Filters - Iridescent
   ============================================================================ */
.filter-fab {
  position: fixed;
  bottom: var(--space-lg);
  right: var(--space-lg);
  z-index: var(--z-fixed);
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  background: var(--gradient-iridescent);
  box-shadow:
    0 4px 20px color-mix(in srgb, var(--color-accent-bright) 40%, transparent),
    var(--glass-shadow-glow);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border: 2px solid color-mix(in srgb, var(--color-text-inverse) 20%, transparent);
  color: var(--color-text-inverse);
  transition: all var(--transition-slow);
}

/* Animated glow ring */
.filter-fab::before {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: var(--radius-full);
  background: var(--gradient-iridescent-full);
  opacity: 0;
  z-index: -1;
  transition: opacity var(--transition-base);
  animation: pulse-glow 2s ease-in-out infinite;
}

@keyframes pulse-glow {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.1); opacity: 0.5; }
}

.filter-fab:hover {
  transform: scale(1.1) translateY(-2px);
  box-shadow:
    0 8px 30px color-mix(in srgb, var(--color-accent-bright) 50%, transparent),
    0 0 40px color-mix(in srgb, var(--color-accent-bright) 30%, transparent);
}

.filter-fab:hover::before {
  opacity: 0.6;
}

.filter-fab:active {
  transform: scale(0.95);
}

/* Active state - Magenta shift */
.filter-fab--active {
  background: linear-gradient(135deg,
    var(--color-iridescent-3) 0%,
    var(--color-iridescent-4) 100%
  );
  box-shadow:
    0 4px 20px color-mix(in srgb, var(--color-iridescent-3) 40%, transparent),
    0 0 30px color-mix(in srgb, var(--color-iridescent-4) 30%, transparent);
}

.filter-fab--active::before {
  background: linear-gradient(135deg, var(--color-iridescent-3) 0%, var(--color-iridescent-4) 100%);
}

.filter-fab--active:hover {
  box-shadow:
    0 8px 30px color-mix(in srgb, var(--color-iridescent-3) 50%, transparent),
    0 0 50px color-mix(in srgb, var(--color-iridescent-4) 40%, transparent);
}

/* Badge */
.filter-fab__badge {
  position: absolute;
  top: -6px;
  right: -6px;
  background: linear-gradient(135deg, var(--color-error) 0%, var(--gradient-danger-end) 100%);
  color: var(--color-text-inverse);
  font-size: 0.75rem;
  font-weight: 700;
  padding: 0.125rem 0.5rem;
  border-radius: var(--radius-full);
  min-width: 22px;
  text-align: center;
  box-shadow: 0 2px 8px color-mix(in srgb, var(--color-error) 50%, transparent);
  border: 2px solid var(--color-bg-primary);
}

/* ============================================================================
   Mobile: Backdrop for Filter Panel - Glassmorphism
   ============================================================================ */
.filter-backdrop {
  position: fixed;
  inset: 0;
  background: color-mix(in srgb, var(--color-bg-primary) 70%, transparent);
  z-index: calc(var(--z-fixed) - 1);
  backdrop-filter: blur(6px);
}

/* ============================================================================
   Transitions - Smooth & Modern
   ============================================================================ */

/* Slide up (for mobile filter panel and details panel) */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all var(--transition-slow);
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

/* Slide down (for desktop filter panel and stats bar) */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all var(--transition-slow);
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-1rem);
  max-height: 0;
}

.slide-down-enter-to,
.slide-down-leave-from {
  max-height: 500px;
}

/* Fade (for backdrop) */
.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--transition-slow);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ============================================================================
   Mobile Responsive
   ============================================================================ */
@media (max-width: 768px) {
  /* Touch-friendly spacing */
  .monitor-content {
    padding-bottom: 5rem; /* Space for FAB */
  }

  /* Full-width modals on mobile */
  .modal-overlay {
    padding: 0;
  }

  .modal-content {
    max-width: 100%;
    max-height: 100%;
    border-radius: 0;
  }

  .modal-content--wide {
    max-width: 100%;
  }
}

/* ============================================================================
   Statistics Bar - Iridescent Cards
   ============================================================================ */
.stats-bar {
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--glass-bg-light);
  border-bottom: 1px solid var(--glass-border);
  backdrop-filter: blur(8px);
}

.stats-bar__item {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  transition: all var(--transition-base);
  position: relative;
  overflow: visible; /* Changed from hidden to allow tooltip overflow */
}

/* Tooltip Support */
.stats-bar__item--with-tooltip {
  cursor: help;
}

.stats-bar__tooltip {
  position: absolute;
  top: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-sticky);
  padding: var(--space-sm) var(--space-md);
  background: color-mix(in srgb, var(--color-bg-primary) 95%, transparent);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  font-size: 0.75rem;
  line-height: 1.5;
  text-align: center;
  min-width: 220px;
  max-width: 280px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s, visibility 0.2s;
  box-shadow:
    0 4px 16px color-mix(in srgb, var(--color-bg-primary) 40%, transparent),
    0 0 1px color-mix(in srgb, var(--color-text-inverse) 10%, transparent);
  pointer-events: none;
}

.stats-bar__tooltip::before {
  content: '';
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-bottom-color: color-mix(in srgb, var(--color-bg-primary) 95%, transparent);
}

.stats-bar__item--with-tooltip:hover .stats-bar__tooltip {
  opacity: 1;
  visibility: visible;
}

/* Iridescent border glow on hover */
.stats-bar__item::before {
  content: '';
  position: absolute;
  inset: -2px;
  background: var(--gradient-iridescent-full);
  border-radius: var(--radius-xl);
  opacity: 0;
  z-index: -1;
  transition: opacity var(--transition-base);
}

.stats-bar__item:hover::before {
  opacity: 0.2;
}

.stats-bar__item:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 24px color-mix(in srgb, var(--color-bg-primary) 20%, transparent);
}

/* Error Card - Red glow */
.stats-bar__item--error {
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--color-error) 8%, transparent) 0%,
    color-mix(in srgb, var(--color-error) 3%, transparent) 100%
  );
  border-color: color-mix(in srgb, var(--color-error) 25%, transparent);
}

.stats-bar__item--error::before {
  background: linear-gradient(135deg, var(--color-error) 0%, var(--gradient-danger-end) 100%);
}

.stats-bar__item--error:hover {
  box-shadow: 0 0 25px color-mix(in srgb, var(--color-error) 25%, transparent);
}

.stats-bar__item--error .stats-bar__value {
  color: var(--color-error);
}

/* Warning Card - Amber glow */
.stats-bar__item--warning {
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--color-warning) 8%, transparent) 0%,
    color-mix(in srgb, var(--color-warning) 3%, transparent) 100%
  );
  border-color: color-mix(in srgb, var(--color-warning) 25%, transparent);
}

.stats-bar__item--warning::before {
  background: linear-gradient(135deg, var(--color-warning) 0%, var(--gradient-warning-end) 100%);
}

.stats-bar__item--warning:hover {
  box-shadow: 0 0 25px color-mix(in srgb, var(--color-warning) 25%, transparent);
}

.stats-bar__item--warning .stats-bar__value {
  color: var(--color-warning);
}

/* Clickable Stats Card */
.stats-bar__item--clickable {
  cursor: pointer;
  position: relative;
}

.stats-bar__item--clickable::after {
  content: '▼';
  position: absolute;
  top: var(--space-xs);
  right: var(--space-xs);
  font-size: 0.5rem;
  color: var(--color-text-muted);
  opacity: 0;
  transition: opacity var(--transition-base);
}

.stats-bar__item--clickable:hover::after {
  opacity: 1;
}

/* Time Range Buttons - Iridescent */
.time-range-buttons {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-sm);
}

.time-range-btn {
  padding: var(--space-md) var(--space-lg);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  color: var(--color-text-secondary);
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all var(--transition-base);
  text-align: center;
}

.time-range-btn:hover {
  background: var(--color-bg-quaternary);
  border-color: var(--glass-border-hover);
  color: var(--color-text-primary);
  transform: translateY(-2px);
}

.time-range-btn--active {
  background: var(--gradient-iridescent);
  border-color: var(--color-iridescent-1);
  color: var(--color-text-inverse);
  box-shadow: var(--glass-shadow-glow);
}

.time-range-btn--active:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 30px color-mix(in srgb, var(--color-accent-bright) 40%, transparent);
}

/* Stats content layout */
.stats-bar__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.stats-bar__label {
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.stats-bar__value {
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--color-text-primary);
  font-variant-numeric: tabular-nums;
  line-height: 1;
}

@media (max-width: 1024px) {
  .stats-bar__value {
    font-size: 1.25rem;
  }
}

@media (max-width: 768px) {
  .stats-bar {
    padding: var(--space-sm) var(--space-md);
    gap: var(--space-sm);
    grid-template-columns: repeat(2, 1fr);
  }

  .stats-bar__item {
    padding: var(--space-sm) var(--space-md);
  }

  .stats-bar__value {
    font-size: 1.125rem;
  }

  .stats-bar__label {
    font-size: 0.6875rem;
  }
}

/* ============================================================================
   Modal Styles - Glassmorphism & Iridescent
   ============================================================================ */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal-backdrop);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-lg);
  background-color: var(--backdrop-color);
  backdrop-filter: blur(8px);
}

.modal-content {
  width: 100%;
  max-width: 28rem;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-2xl);
  box-shadow:
    var(--glass-shadow),
    0 0 40px color-mix(in srgb, var(--color-accent-bright) 10%, transparent);
  overflow: hidden;
}

.modal-content--wide {
  max-width: 42rem;
}

.modal-content--compact {
  max-width: 20rem;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-lg) var(--space-xl);
  border-bottom: 1px solid var(--glass-border);
  flex-shrink: 0;
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--color-accent-bright) 5%, transparent) 0%,
    transparent 100%
  );
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

/* Iridescent title effect */
.modal-title::before {
  content: '';
  display: block;
  width: 4px;
  height: 1.5em;
  background: var(--gradient-iridescent);
  border-radius: var(--radius-full);
  margin-right: var(--space-xs);
}

.modal-close {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-muted);
  transition: all var(--transition-base);
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  cursor: pointer;
}

.modal-close:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-quaternary);
  border-color: var(--glass-border-hover);
  transform: rotate(90deg);
}

.modal-body {
  padding: var(--space-xl);
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  display: flex;
  gap: var(--space-md);
  padding: var(--space-lg) var(--space-xl);
  border-top: 1px solid var(--glass-border);
  flex-shrink: 0;
  background: linear-gradient(0deg,
    color-mix(in srgb, var(--color-accent-bright) 3%, transparent) 0%,
    transparent 100%
  );
}

/* Form elements in modals - Modern Design */
.label {
  display: block;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: var(--space-sm);
}

.input {
  width: 100%;
  padding: var(--space-sm) var(--space-md);
  font-size: 0.875rem;
  background: var(--color-bg-tertiary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  transition: all var(--transition-base);
}

.input:focus {
  outline: none;
  border-color: var(--color-iridescent-1);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-accent-bright) 15%, transparent);
  background: var(--color-bg-quaternary);
}

.input:hover:not(:focus) {
  border-color: var(--glass-border-hover);
}

/* Utility classes */
.space-y-4 > * + * {
  margin-top: 1rem;
}

.space-y-1 > * + * {
  margin-top: 0.25rem;
}

.grid {
  display: grid;
}

.grid-cols-2 {
  grid-template-columns: repeat(2, 1fr);
}

.gap-4 {
  gap: 1rem;
}

.gap-3 {
  gap: 0.75rem;
}

.flex-1 {
  flex: 1;
}

.mb-2 {
  margin-bottom: 0.5rem;
}

.mt-2 {
  margin-top: 0.5rem;
}

.mr-1 {
  margin-right: 0.25rem;
}

.mr-2 {
  margin-right: 0.5rem;
}

.p-4 {
  padding: 1rem;
}

.rounded-lg {
  border-radius: var(--radius-md);
}

.text-sm {
  font-size: 0.875rem;
}

.font-medium {
  font-weight: 500;
}

.font-bold {
  font-weight: 700;
}

.font-mono {
  font-family: ui-monospace, monospace;
}

.capitalize {
  text-transform: capitalize;
}

.inline-block {
  display: inline-block;
}

.w-4 {
  width: 1rem;
}

.h-4 {
  height: 1rem;
}

.w-5 {
  width: 1.25rem;
}

.h-5 {
  height: 1.25rem;
}

@media (min-width: 640px) {
  .sm\:grid-cols-4 {
    grid-template-columns: repeat(4, 1fr);
  }
}

/* Buttons - Iridescent Design */
.btn-primary,
.btn-secondary,
.btn-danger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-lg);
  font-size: 0.875rem;
  font-weight: 600;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-base);
  border: 1px solid transparent;
  position: relative;
  overflow: hidden;
}

/* Primary - Accent */
.btn-primary {
  background: var(--color-accent);
  color: var(--color-text-inverse);
  border-color: var(--color-accent);
  box-shadow: var(--elevation-raised);
}

.btn-primary:hover {
  background: color-mix(in srgb, var(--color-accent) 88%, white);
  border-color: color-mix(in srgb, var(--color-accent) 88%, white);
  transform: translateY(-2px);
  box-shadow: var(--elevation-raised);
}

.btn-primary:active {
  transform: translateY(0);
}

/* Secondary */
.btn-secondary {
  background: var(--color-bg-tertiary);
  color: var(--color-text-secondary);
  border-color: var(--glass-border);
}

.btn-secondary:hover {
  background: var(--color-bg-quaternary);
  color: var(--color-text-primary);
  border-color: var(--glass-border-hover);
  transform: translateY(-1px);
}

/* Danger - Red Glow */
.btn-danger {
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--color-error) 90%, transparent) 0%,
    color-mix(in srgb, var(--gradient-danger-end) 90%, transparent) 100%
  );
  color: var(--color-text-inverse);
  border-color: color-mix(in srgb, var(--color-error) 50%, transparent);
}

.btn-danger:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 25px color-mix(in srgb, var(--color-error) 40%, transparent);
}

.btn-primary:disabled,
.btn-secondary:disabled,
.btn-danger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

/* ============================================================================
   Toast Notification - Success/Error/Info
   ============================================================================ */
.toast {
  position: fixed;
  bottom: var(--space-xl);
  left: 50%;
  transform: translateX(-50%);
  z-index: var(--z-toast);
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-md) var(--space-lg);
  background: var(--color-bg-secondary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-xl);
  box-shadow:
    var(--glass-shadow),
    0 8px 32px color-mix(in srgb, var(--color-bg-primary) 40%, transparent);
  backdrop-filter: blur(12px);
  cursor: pointer;
  max-width: calc(100vw - 2rem);
}

.toast--success {
  border-color: color-mix(in srgb, var(--color-success) 40%, transparent);
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--color-success) 15%, transparent) 0%,
    color-mix(in srgb, var(--color-success) 5%, transparent) 100%
  );
}

.toast--error {
  border-color: color-mix(in srgb, var(--color-error) 40%, transparent);
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--color-error) 15%, transparent) 0%,
    color-mix(in srgb, var(--color-error) 5%, transparent) 100%
  );
}

.toast--info {
  border-color: color-mix(in srgb, var(--color-info) 40%, transparent);
  background: linear-gradient(135deg,
    color-mix(in srgb, var(--color-info) 15%, transparent) 0%,
    color-mix(in srgb, var(--color-info) 5%, transparent) 100%
  );
}

.toast__icon {
  width: 1.25rem;
  height: 1.25rem;
  flex-shrink: 0;
}

.toast--success .toast__icon {
  color: var(--color-success);
}

.toast--error .toast__icon {
  color: var(--color-error);
}

.toast--info .toast__icon {
  color: var(--color-info);
}

.toast__message {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-primary);
}

.toast__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-base);
  flex-shrink: 0;
}

.toast__close:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-tertiary);
}

/* Toast Transition */
.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(100%);
}

@media (max-width: 640px) {
  .toast {
    bottom: 5rem; /* Space for FAB */
    left: var(--space-md);
    right: var(--space-md);
    transform: none;
    max-width: none;
  }

  .toast-enter-from,
  .toast-leave-to {
    transform: translateY(100%);
  }
}

/* ============================================================================
   Flapping Alert Bar (PKG-20)
   ============================================================================ */
.flapping-alert-bar {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  padding: var(--space-sm) var(--space-lg);
  background: linear-gradient(135deg,
    rgba(251, 191, 36, 0.08) 0%,
    rgba(251, 191, 36, 0.03) 100%
  );
  border-bottom: 1px solid rgba(251, 191, 36, 0.25);
  color: var(--color-warning);
  font-size: var(--text-sm);
  animation: flapping-bar-pulse 3s ease-in-out infinite;
}

.flapping-alert-bar__indicator {
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  background: var(--color-warning);
  box-shadow: 0 0 6px rgba(251, 191, 36, 0.5);
  flex-shrink: 0;
  animation: flapping-dot 1.5s ease-in-out infinite;
}

@keyframes flapping-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.flapping-alert-bar__icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.flapping-alert-bar__text {
  color: var(--color-text-primary);
}

.flapping-alert-bar__text strong {
  color: var(--color-warning);
}

.flapping-alert-bar__devices {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@keyframes flapping-bar-pulse {
  0%, 100% { border-bottom-color: rgba(251, 191, 36, 0.25); }
  50% { border-bottom-color: rgba(251, 191, 36, 0.5); }
}

@media (prefers-reduced-motion: reduce) {
  .flapping-alert-bar,
  .flapping-alert-bar__indicator {
    animation: none;
  }
}

@media (max-width: 768px) {
  .flapping-alert-bar {
    flex-wrap: wrap;
    gap: var(--space-sm);
    padding: var(--space-sm) var(--space-md);
  }

  .flapping-alert-bar__devices {
    width: 100%;
  }
}
</style>
