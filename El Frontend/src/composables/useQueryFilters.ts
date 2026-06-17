/**
 * Query Filters Composable
 *
 * Syncs filter state with URL query parameters for deep-linking support.
 * Used by System Monitor for ESP-Card → System Monitor navigation.
 *
 * @example
 * // In SystemMonitorView.vue
 * const { filters, syncFromURL, syncToURL, resetFilters } = useQueryFilters()
 *
 * // URL: /system-monitor?category=events&esp=ESP_00B19C&level=ERROR
 */

import { reactive, watch, computed, onMounted, toRefs } from 'vue'
import { useRoute, useRouter, type LocationQueryValue } from 'vue-router'

// =============================================================================
// TYPES
// =============================================================================

export type MonitorCategory = 'events' | 'logs' | 'database' | 'mqtt'
export type SeverityLevel = 'info' | 'warning' | 'error' | 'critical'
export type TimeRange = '15m' | '1h' | '6h' | '24h' | '7d' | 'custom'

export interface MonitorFilters {
  /** Active tab/category */
  category: MonitorCategory
  /** Filter by ESP device ID */
  esp: string | null
  /** Filter by severity levels (multi-select) */
  level: SeverityLevel[]
  /** Time range preset */
  timeRange: TimeRange
  /** Custom start time (ISO string) */
  startTime: string | null
  /** Custom end time (ISO string) */
  endTime: string | null
  /** Full-text search query */
  search: string
  /** Event type filter (for events tab) */
  eventType: string | null
  /** Table name filter (for database tab) */
  table: string | null
  /** Topic pattern filter (for MQTT tab) */
  topicPattern: string | null
}

export interface UseQueryFiltersOptions {
  /** Default category if not in URL */
  defaultCategory?: MonitorCategory
  /** Default time range */
  defaultTimeRange?: TimeRange
  /** Debounce delay for URL updates (ms) */
  debounceMs?: number
  /** Auto-sync from URL on mount */
  autoSync?: boolean
}

// =============================================================================
// DEFAULTS
// =============================================================================

const DEFAULT_FILTERS: MonitorFilters = {
  category: 'events',
  esp: null,
  level: [],
  timeRange: '1h',
  startTime: null,
  endTime: null,
  search: '',
  eventType: null,
  table: null,
  topicPattern: null
}

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

function parseQueryValue(value: LocationQueryValue | LocationQueryValue[]): string | null {
  if (Array.isArray(value)) {
    return value[0] ?? null
  }
  return value ?? null
}

function parseQueryArray(value: LocationQueryValue | LocationQueryValue[]): string[] {
  if (Array.isArray(value)) {
    return value.filter((v): v is string => typeof v === 'string')
  }
  if (typeof value === 'string') {
    return value.split(',').filter(Boolean)
  }
  return []
}

function isValidCategory(value: string | null): value is MonitorCategory {
  return value !== null && ['events', 'logs', 'database', 'mqtt'].includes(value)
}

function isValidTimeRange(value: string | null): value is TimeRange {
  return value !== null && ['15m', '1h', '6h', '24h', '7d', 'custom'].includes(value)
}

function isValidSeverity(value: string): value is SeverityLevel {
  return ['info', 'warning', 'error', 'critical'].includes(value)
}

// =============================================================================
// COMPOSABLE
// =============================================================================

export function useQueryFilters(options: UseQueryFiltersOptions = {}) {
  const {
    defaultCategory = 'events',
    defaultTimeRange = '1h',
    debounceMs = 300,
    autoSync = true
  } = options

  const route = useRoute()
  const router = useRouter()

  // Reactive filter state
  const filters = reactive<MonitorFilters>({
    ...DEFAULT_FILTERS,
    category: defaultCategory,
    timeRange: defaultTimeRange
  })

  // Debounce timer
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // =============================================================================
  // URL SYNCHRONIZATION
  // =============================================================================

  /**
   * Read filters from URL query parameters
   */
  function syncFromURL(): void {
    const query = route.query

    // Category
    const categoryValue = parseQueryValue(query.category)
    if (isValidCategory(categoryValue)) {
      filters.category = categoryValue
    }

    // ESP filter
    filters.esp = parseQueryValue(query.esp)

    // Severity levels (comma-separated or array)
    const levelValues = parseQueryArray(query.level)
    filters.level = levelValues.filter(isValidSeverity)

    // Time range
    const timeRangeValue = parseQueryValue(query.timeRange)
    if (isValidTimeRange(timeRangeValue)) {
      filters.timeRange = timeRangeValue
    }

    // Custom time range
    filters.startTime = parseQueryValue(query.startTime)
    filters.endTime = parseQueryValue(query.endTime)

    // Search
    filters.search = parseQueryValue(query.search) ?? ''

    // Tab-specific filters
    filters.eventType = parseQueryValue(query.eventType)
    filters.table = parseQueryValue(query.table)
    filters.topicPattern = parseQueryValue(query.topicPattern)
  }

  /**
   * Write filters to URL query parameters
   */
  function syncToURL(): void {
    // Build query object with only non-default values
    const query: Record<string, string | string[]> = {}

    if (filters.category !== defaultCategory) {
      query.category = filters.category
    }

    if (filters.esp) {
      query.esp = filters.esp
    }

    if (filters.level.length > 0) {
      query.level = filters.level.join(',')
    }

    if (filters.timeRange !== defaultTimeRange) {
      query.timeRange = filters.timeRange
    }

    if (filters.timeRange === 'custom') {
      if (filters.startTime) query.startTime = filters.startTime
      if (filters.endTime) query.endTime = filters.endTime
    }

    if (filters.search) {
      query.search = filters.search
    }

    if (filters.eventType) {
      query.eventType = filters.eventType
    }

    if (filters.table) {
      query.table = filters.table
    }

    if (filters.topicPattern) {
      query.topicPattern = filters.topicPattern
    }

    // Replace URL without navigation (preserves history)
    router.replace({
      path: route.path,
      query
    })
  }

  /**
   * Debounced URL sync (to avoid excessive history entries)
   */
  function syncToURLDebounced(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }
    debounceTimer = setTimeout(syncToURL, debounceMs)
  }

  // =============================================================================
  // FILTER MANIPULATION
  // =============================================================================

  /**
   * Reset all filters to defaults
   */
  function resetFilters(): void {
    Object.assign(filters, {
      ...DEFAULT_FILTERS,
      category: filters.category, // Keep current tab
      timeRange: defaultTimeRange
    })
    syncToURL()
  }

  /**
   * Set a single filter value
   */
  function setFilter<K extends keyof MonitorFilters>(key: K, value: MonitorFilters[K]): void {
    filters[key] = value
    syncToURLDebounced()
  }

  /**
   * Set category (tab) and optionally reset tab-specific filters
   */
  function setCategory(category: MonitorCategory, resetTabFilters = true): void {
    filters.category = category

    if (resetTabFilters) {
      // Reset tab-specific filters when switching tabs
      filters.eventType = null
      filters.table = null
      filters.topicPattern = null
    }

    syncToURL()
  }

  /**
   * Toggle a severity level in the filter array
   */
  function toggleLevel(level: SeverityLevel): void {
    const index = filters.level.indexOf(level)
    if (index >= 0) {
      filters.level.splice(index, 1)
    } else {
      filters.level.push(level)
    }
    syncToURLDebounced()
  }

  /**
   * Set ESP filter (for deep-linking from ESP-Card)
   */
  function setEspFilter(espId: string | null): void {
    filters.esp = espId
    syncToURL()
  }

  /**
   * Set time range with optional custom bounds
   */
  function setTimeRange(range: TimeRange, startTime?: string, endTime?: string): void {
    filters.timeRange = range

    if (range === 'custom') {
      filters.startTime = startTime ?? null
      filters.endTime = endTime ?? null
    } else {
      filters.startTime = null
      filters.endTime = null
    }

    syncToURL()
  }

  /**
   * Set search query
   */
  function setSearch(query: string): void {
    filters.search = query
    syncToURLDebounced()
  }

  // =============================================================================
  // COMPUTED
  // =============================================================================

  /**
   * Check if any filters are active (non-default)
   */
  const hasActiveFilters = computed<boolean>(() => {
    return (
      filters.esp !== null ||
      filters.level.length > 0 ||
      filters.timeRange !== defaultTimeRange ||
      filters.search !== '' ||
      filters.eventType !== null ||
      filters.table !== null ||
      filters.topicPattern !== null
    )
  })

  /**
   * Get count of active filters
   */
  const activeFilterCount = computed<number>(() => {
    let count = 0
    if (filters.esp) count++
    if (filters.level.length > 0) count++
    if (filters.timeRange !== defaultTimeRange) count++
    if (filters.search) count++
    if (filters.eventType) count++
    if (filters.table) count++
    if (filters.topicPattern) count++
    return count
  })

  /**
   * Calculate time bounds based on time range preset
   */
  const timeBounds = computed<{ start: Date; end: Date }>(() => {
    const now = new Date()
    const end = now

    let start: Date

    switch (filters.timeRange) {
      case '15m':
        start = new Date(now.getTime() - 15 * 60 * 1000)
        break
      case '1h':
        start = new Date(now.getTime() - 60 * 60 * 1000)
        break
      case '6h':
        start = new Date(now.getTime() - 6 * 60 * 60 * 1000)
        break
      case '24h':
        start = new Date(now.getTime() - 24 * 60 * 60 * 1000)
        break
      case '7d':
        start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
        break
      case 'custom':
        start = filters.startTime ? new Date(filters.startTime) : new Date(now.getTime() - 60 * 60 * 1000)
        return {
          start,
          end: filters.endTime ? new Date(filters.endTime) : end
        }
      default:
        start = new Date(now.getTime() - 60 * 60 * 1000)
    }

    return { start, end }
  })

  // =============================================================================
  // LIFECYCLE
  // =============================================================================

  // Watch route changes (e.g., browser back/forward)
  watch(
    () => route.query,
    () => {
      syncFromURL()
    },
    { deep: true }
  )

  // Auto-sync on mount
  onMounted(() => {
    if (autoSync) {
      syncFromURL()
    }
  })

  // =============================================================================
  // RETURN
  // =============================================================================

  return {
    // Reactive filter state
    filters,
    ...toRefs(filters),

    // URL sync
    syncFromURL,
    syncToURL,

    // Filter manipulation
    resetFilters,
    setFilter,
    setCategory,
    toggleLevel,
    setEspFilter,
    setTimeRange,
    setSearch,

    // Computed
    hasActiveFilters,
    activeFilterCount,
    timeBounds
  }
}
