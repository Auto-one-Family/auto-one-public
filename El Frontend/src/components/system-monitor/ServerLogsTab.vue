<script setup lang="ts">
/**
 * ServerLogsTab - Server Logs Tab for System Monitor
 *
 * Features:
 * - Compact horizontal filter bar
 * - Polling with Play/Pause button (3s interval)
 * - CSV export functionality
 * - Expandable log entries with full details
 * - Human-readable summaries (original message always preserved)
 * - Border + glow design per log level (consistent with Events tab)
 * - Log management panel for file cleanup
 * - Mobile-responsive design
 *
 * @see El Servador/god_kaiser_server/src/core/logging_config.py - Logging Configuration
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { logsApi, type LogEntry, type LogLevel, type LogFile, type LogQueryParams } from '@/api/logs'
import { generateSummary, formatCategoryLabel, type LogSummary } from '@/utils/logSummaryGenerator'
import LogManagementPanel from './LogManagementPanel.vue'
import {
  Play,
  Pause,
  RefreshCw,
  Download,
  Trash2,
  Search,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  Info,
  AlertTriangle,
  Bug,
  XCircle,
  FileText,
  Copy,
  Check,
  Settings,
  FileJson,
  Clock,
  X,
  Maximize2,
} from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'
import { tokens } from '@/utils/cssTokens'

const log = createLogger('ServerLogsTab')

// ============================================================================
// Props
// ============================================================================

const props = defineProps<{
  initialStartTime?: string
  initialEndTime?: string
  initialRequestId?: string
}>()

// ============================================================================
// Constants
// ============================================================================

const POLL_INTERVAL = 3000 // 3 seconds
const PAGE_SIZE = 100

// Log level configuration
const LOG_LEVELS: { value: LogLevel | ''; label: string; icon: typeof Info; color: string }[] = [
  { value: '', label: 'Alle', icon: FileText, color: 'text-gray-400' },
  { value: 'DEBUG', label: 'Debug', icon: Bug, color: 'text-gray-400' },
  { value: 'INFO', label: 'Info', icon: Info, color: 'text-blue-400' },
  { value: 'WARNING', label: 'Warnung', icon: AlertTriangle, color: 'text-yellow-400' },
  { value: 'ERROR', label: 'Fehler', icon: XCircle, color: 'text-red-400' },
  { value: 'CRITICAL', label: 'Kritisch', icon: AlertCircle, color: 'text-red-600' },
]

// Level colors for border + glow (consistent with Events tab)
const LEVEL_COLORS: Record<string, { border: string; glow: string; tint: string }> = {
  DEBUG: {
    border: tokens.statusOffline,
    glow: 'rgba(107, 114, 128, 0.4)',
    tint: 'transparent',
  },
  INFO: {
    border: tokens.accent,
    glow: 'rgba(59, 130, 246, 0.4)',
    tint: 'rgba(59, 130, 246, 0.02)',
  },
  WARNING: {
    border: tokens.warning,
    glow: 'rgba(245, 158, 11, 0.4)',
    tint: 'rgba(245, 158, 11, 0.03)',
  },
  ERROR: {
    border: tokens.error,
    glow: 'rgba(239, 68, 68, 0.4)',
    tint: 'rgba(239, 68, 68, 0.04)',
  },
  CRITICAL: {
    border: tokens.error,
    glow: 'rgba(220, 38, 38, 0.5)',
    tint: 'rgba(239, 68, 68, 0.06)',
  },
}

function getLevelColors(level: string) {
  return LEVEL_COLORS[level] || LEVEL_COLORS.DEBUG
}

// ============================================================================
// State
// ============================================================================

const logs = ref<LogEntry[]>([])
const logFiles = ref<LogFile[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const totalCount = ref(0)
const hasMore = ref(false)

// Polling state
const isPolling = ref(false)
const pollInterval = ref<ReturnType<typeof setInterval> | null>(null)

// Filter state
const selectedFile = ref('')
const selectedLevel = ref<LogLevel | ''>('')
const moduleFilter = ref('')
const searchQuery = ref('')
const page = ref(1)

// Zeitfenster-Filter (Feature 1.2)
const startTime = ref<string>('')
const endTime = ref<string>('')

// Request-ID-Filter (Phase 4: precise log correlation)
const requestId = ref<string>('')

// Expanded state
const expandedIds = ref<Set<number>>(new Set())
const copiedMessageId = ref<number | null>(null)
const copiedJsonId = ref<number | null>(null)

// Management panel state
const showManagement = ref(false)

// Summary cache
const summaryCache = new WeakMap<LogEntry, LogSummary | null>()

// ============================================================================
// Computed
// ============================================================================

const currentQueryParams = computed<LogQueryParams>(() => ({
  level: selectedLevel.value || undefined,
  module: moduleFilter.value || undefined,
  search: searchQuery.value || undefined,
  file: selectedFile.value || undefined,
  page: page.value,
  page_size: PAGE_SIZE,
  start_time: startTime.value || undefined,
  end_time: endTime.value || undefined,
  request_id: requestId.value || undefined,
}))

// ============================================================================
// Methods - Data Loading
// ============================================================================

async function loadLogFiles(): Promise<void> {
  try {
    const response = await logsApi.listFiles()
    logFiles.value = response.files

    // Select current file by default
    const currentFile = response.files.find(f => f.is_current)
    if (currentFile && !selectedFile.value) {
      selectedFile.value = currentFile.name
    }
  } catch (err) {
    log.error(' Failed to load log files:', err)
  }
}

async function loadLogs(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    const response = await logsApi.queryLogs(currentQueryParams.value)
    logs.value = response.logs
    totalCount.value = response.total_count
    hasMore.value = response.has_more
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { detail?: string } } }
    error.value = axiosError.response?.data?.detail || 'Logs konnten nicht geladen werden'
  } finally {
    isLoading.value = false
  }
}

async function loadMore(): Promise<void> {
  page.value++
  isLoading.value = true

  try {
    const response = await logsApi.queryLogs(currentQueryParams.value)
    logs.value = [...logs.value, ...response.logs]
    totalCount.value = response.total_count
    hasMore.value = response.has_more
  } catch (err: unknown) {
    const axiosError = err as { response?: { data?: { detail?: string } } }
    error.value = axiosError.response?.data?.detail || 'Weitere Logs konnten nicht geladen werden'
    page.value--
  } finally {
    isLoading.value = false
  }
}

// ============================================================================
// Methods - Polling
// ============================================================================

function togglePolling() {
  isPolling.value = !isPolling.value

  if (isPolling.value) {
    pollInterval.value = setInterval(() => {
      loadLogs()
    }, POLL_INTERVAL)
  } else {
    if (pollInterval.value) {
      clearInterval(pollInterval.value)
      pollInterval.value = null
    }
  }
}

function stopPolling() {
  if (pollInterval.value) {
    clearInterval(pollInterval.value)
    pollInterval.value = null
  }
  isPolling.value = false
}

// ============================================================================
// Methods - UI Actions
// ============================================================================

function applyFilters() {
  page.value = 1
  loadLogs()
}

function formatTimeWindow(start: string, end: string): string {
  const s = new Date(start)
  const e = new Date(end)
  return `${s.toLocaleTimeString('de-DE')} - ${e.toLocaleTimeString('de-DE')}`
}

function clearTimeWindow() {
  startTime.value = ''
  endTime.value = ''
  page.value = 1
  loadLogs()
}

function clearRequestIdFilter() {
  requestId.value = ''
  page.value = 1
  loadLogs()
}

function expandTimeWindow() {
  if (!startTime.value || !endTime.value) return

  const start = new Date(startTime.value)
  const end = new Date(endTime.value)
  const center = new Date((start.getTime() + end.getTime()) / 2)

  // Expand to ±5 minutes (instead of ±30 seconds)
  startTime.value = new Date(center.getTime() - 5 * 60 * 1000).toISOString()
  endTime.value = new Date(center.getTime() + 5 * 60 * 1000).toISOString()

  // Clear file selection to search across all log files
  selectedFile.value = ''
  page.value = 1
  loadLogs()
}

function clearLogs() {
  logs.value = []
  expandedIds.value.clear()
}

function toggleExpand(index: number) {
  if (expandedIds.value.has(index)) {
    expandedIds.value.delete(index)
  } else {
    expandedIds.value.add(index)
  }
}

function getSummary(log: LogEntry): LogSummary | null {
  if (summaryCache.has(log)) {
    return summaryCache.get(log)!
  }
  const summary = generateSummary(log)
  summaryCache.set(log, summary)
  return summary
}

async function copyMessage(logEntry: LogEntry, index: number) {
  try {
    await navigator.clipboard.writeText(logEntry.message)
    copiedMessageId.value = index
    setTimeout(() => { copiedMessageId.value = null }, 2000)
  } catch (e) {
    log.error('Failed to copy', e)
  }
}

async function copyAsJson(logEntry: LogEntry, index: number) {
  try {
    await navigator.clipboard.writeText(JSON.stringify(logEntry, null, 2))
    copiedJsonId.value = index
    setTimeout(() => { copiedJsonId.value = null }, 2000)
  } catch (e) {
    log.error('Failed to copy', e)
  }
}

function handleCleanupSuccess() {
  loadLogFiles()
  loadLogs()
}

// ============================================================================
// Methods - Export
// ============================================================================

function exportToCsv() {
  const headers = ['Zeitstempel', 'Level', 'Logger', 'Modul', 'Funktion', 'Zeile', 'Nachricht']
  const rows = [headers.join(';')]

  logs.value.forEach(log => {
    const row = [
      formatTimestamp(log.timestamp),
      log.level,
      log.logger || '',
      log.module || '',
      log.function || '',
      log.line?.toString() || '',
      `"${(log.message || '').replace(/"/g, '""')}"`,
    ]
    rows.push(row.join(';'))
  })

  const csvContent = rows.join('\n')
  const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `server-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ============================================================================
// Methods - Formatting
// ============================================================================

function formatTimestamp(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleString('de-DE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return timestamp
  }
}

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString('de-DE', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return timestamp
  }
}

function getLevelConfig(level: string) {
  return LOG_LEVELS.find(l => l.value === level) || LOG_LEVELS[0]
}

function getLevelClass(level: string): string {
  switch (level) {
    case 'DEBUG': return 'log-level--debug'
    case 'INFO': return 'log-level--info'
    case 'WARNING': return 'log-level--warning'
    case 'ERROR': return 'log-level--error'
    case 'CRITICAL': return 'log-level--critical'
    default: return 'log-level--debug'
  }
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(async () => {
  // Feature 1.2: Props initialisieren falls vorhanden
  if (props.initialRequestId) {
    // Phase 4: Precise log correlation via request_id
    requestId.value = props.initialRequestId
    // Clear time filters when using request_id
    startTime.value = ''
    endTime.value = ''
  } else {
    if (props.initialStartTime) {
      startTime.value = props.initialStartTime
    }
    if (props.initialEndTime) {
      endTime.value = props.initialEndTime
    }
  }

  await loadLogFiles()

  // When time window or request_id is set from props, clear file selection
  // so the backend searches across ALL log files
  if ((startTime.value && endTime.value) || requestId.value) {
    selectedFile.value = ''
  }

  await loadLogs()
})

onUnmounted(() => {
  stopPolling()
})

watch(selectedFile, () => {
  page.value = 1
  loadLogs()
})
</script>

<template>
  <div class="logs-tab">
    <!-- Toolbar / Filter Bar -->
    <div class="logs-toolbar">
      <div class="logs-toolbar__filters">
        <!-- File Selector -->
        <select v-model="selectedFile" class="logs-select logs-select--file">
          <option v-for="file in logFiles" :key="file.name" :value="file.name">
            {{ file.name }}
          </option>
        </select>

        <!-- Level Selector -->
        <select v-model="selectedLevel" class="logs-select" @change="applyFilters">
          <option v-for="level in LOG_LEVELS" :key="level.value" :value="level.value">
            {{ level.label }}
          </option>
        </select>

        <!-- Module Filter -->
        <input
          v-model="moduleFilter"
          type="text"
          class="logs-input logs-input--module"
          placeholder="Modul..."
          @keyup.enter="applyFilters"
        />

        <!-- Search -->
        <div class="logs-search">
          <Search class="logs-search__icon" />
          <input
            v-model="searchQuery"
            type="text"
            class="logs-search__input"
            placeholder="Suchen..."
            @keyup.enter="applyFilters"
          />
        </div>
        <!-- Request-ID-Chip (Phase 4) -->
        <div v-if="requestId" class="time-window-chip">
          <FileText :size="14" />
          <span>Request-ID: {{ requestId.slice(0, 8) }}...</span>
          <button class="time-window-chip__clear" @click="clearRequestIdFilter" title="Request-ID Filter entfernen">
            <X :size="12" />
          </button>
        </div>
        <!-- Zeitfenster-Chip (Feature 1.2) -->
        <div v-if="startTime && endTime" class="time-window-chip">
          <Clock :size="14" />
          <span>{{ formatTimeWindow(startTime, endTime) }}</span>
          <button class="time-window-chip__expand" @click="expandTimeWindow" title="Zeitfenster auf ±5 Min erweitern">
            <Maximize2 :size="12" />
          </button>
          <button class="time-window-chip__clear" @click="clearTimeWindow" title="Zeitfilter entfernen">
            <X :size="12" />
          </button>
        </div>
      </div>

      <div class="logs-toolbar__actions">
        <!-- Polling Toggle -->
        <button
          class="btn-ghost btn-sm"
          :class="{ 'btn-ghost--active': isPolling }"
          @click="togglePolling"
        >
          <component :is="isPolling ? Pause : Play" class="w-4 h-4" />
          <span class="btn-label">{{ isPolling ? 'Stoppen' : 'Live' }}</span>
        </button>

        <!-- Refresh -->
        <button
          class="btn-ghost btn-sm"
          :disabled="isLoading"
          @click="loadLogs"
        >
          <RefreshCw :class="['w-4 h-4', isLoading && 'animate-spin']" />
          <span class="btn-label">Aktualisieren</span>
        </button>

        <!-- Export CSV -->
        <button
          class="btn-ghost btn-sm"
          :disabled="logs.length === 0"
          @click="exportToCsv"
        >
          <Download class="w-4 h-4" />
          <span class="btn-label">CSV</span>
        </button>

        <!-- Management -->
        <button
          class="btn-ghost btn-sm"
          @click="showManagement = true"
          title="Log-Verwaltung"
        >
          <Settings class="w-4 h-4" />
          <span class="btn-label">Verwaltung</span>
        </button>

        <!-- Clear -->
        <button
          class="btn-ghost btn-sm btn-ghost--danger"
          :disabled="logs.length === 0"
          @click="clearLogs"
        >
          <Trash2 class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- Info Bar -->
    <div class="logs-info">
      <span class="logs-info__count">
        {{ logs.length }} von {{ totalCount.toLocaleString() }} Eintraegen
      </span>
      <span v-if="isPolling" class="logs-info__polling">
        <span class="logs-info__dot"></span>
        Live-Aktualisierung
      </span>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="logs-error">
      <AlertCircle class="logs-error__icon" />
      <span class="logs-error__text">{{ error }}</span>
      <button class="logs-error__close" @click="error = null">&times;</button>
    </div>

    <!-- Log List -->
    <div class="logs-list">
      <!-- Loading State -->
      <div v-if="isLoading && logs.length === 0" class="logs-loading">
        <div class="logs-loading__spinner"></div>
        <span>Logs werden geladen...</span>
      </div>

      <!-- Empty State - Time Window -->
      <div v-else-if="logs.length === 0 && startTime && endTime" class="logs-empty">
        <FileText class="logs-empty__icon" />
        <p class="logs-empty__title">Keine Server-Logs in diesem Zeitfenster</p>
        <p class="logs-empty__text">
          Zwischen {{ formatTime(startTime) }} und {{ formatTime(endTime) }}
          wurden keine Log-Eintraege gefunden.
        </p>
        <div class="logs-empty__actions">
          <button class="btn-secondary btn-sm" @click="expandTimeWindow">
            <Maximize2 class="w-4 h-4" />
            Zeitfenster erweitern
          </button>
          <button class="btn-ghost btn-sm" @click="clearTimeWindow">
            Filter entfernen
          </button>
        </div>
      </div>

      <!-- Empty State - General -->
      <div v-else-if="logs.length === 0" class="logs-empty">
        <FileText class="logs-empty__icon" />
        <p class="logs-empty__text">Keine Log-Eintraege gefunden</p>
      </div>

      <!-- Log Entries -->
      <template v-else>
        <div
          v-for="(log, index) in logs"
          :key="index"
          class="log-entry"
          :class="{ 'log-entry--critical': log.level === 'CRITICAL' }"
          :style="{
            '--level-border': getLevelColors(log.level).border,
            '--level-glow': getLevelColors(log.level).glow,
            '--level-tint': getLevelColors(log.level).tint,
          }"
        >
          <!-- Entry Header -->
          <div class="log-entry__header" @click="toggleExpand(index)">
            <button class="log-entry__expand">
              <component :is="expandedIds.has(index) ? ChevronDown : ChevronRight" class="w-4 h-4" />
            </button>

            <span class="log-entry__time">{{ formatTime(log.timestamp) }}</span>

            <span :class="['log-level', getLevelClass(log.level)]">
              <component :is="getLevelConfig(log.level).icon" class="w-3 h-3" />
              {{ log.level }}
            </span>

            <span class="log-entry__logger">{{ log.logger }}</span>

            <span class="log-entry__message">{{ log.message }}</span>
          </div>

          <!-- Expanded Details -->
          <Transition name="expand">
            <div v-if="expandedIds.has(index)" class="log-entry__details">

              <!-- Summary (if available) -->
              <div v-if="getSummary(log)" class="log-detail-summary">
                <span class="log-detail-summary__icon">{{ getSummary(log)!.icon }}</span>
                <div class="log-detail-summary__content">
                  <span class="log-detail-summary__title">{{ getSummary(log)!.title }}</span>
                  <span
                    v-if="getSummary(log)!.description"
                    class="log-detail-summary__desc"
                  >{{ getSummary(log)!.description }}</span>
                </div>
              </div>

              <!-- Details Grid -->
              <div class="log-details__grid">
                <div class="log-details__item">
                  <span class="log-details__label">Zeitstempel</span>
                  <span class="log-details__value">{{ formatTimestamp(log.timestamp) }}</span>
                </div>
                <div class="log-details__item">
                  <span class="log-details__label">Level</span>
                  <span :class="['log-level', getLevelClass(log.level)]">
                    {{ log.level }}
                  </span>
                </div>
                <div class="log-details__item">
                  <span class="log-details__label">Modul</span>
                  <span class="log-details__value log-details__value--mono">{{ log.module || 'N/A' }}</span>
                </div>
                <div v-if="log.function" class="log-details__item">
                  <span class="log-details__label">Funktion</span>
                  <span class="log-details__value log-details__value--mono">{{ log.function }}</span>
                </div>
                <div v-if="log.line" class="log-details__item">
                  <span class="log-details__label">Zeile</span>
                  <span class="log-details__value log-details__value--mono">{{ log.line }}</span>
                </div>
                <div v-if="getSummary(log)" class="log-details__item">
                  <span class="log-details__label">Kategorie</span>
                  <span
                    class="log-category-badge"
                    :data-category="getSummary(log)!.category"
                  >{{ formatCategoryLabel(getSummary(log)!.category) }}</span>
                </div>
              </div>

              <!-- Original Message (ALWAYS shown in full) -->
              <div class="log-details__section">
                <div class="log-details__section-header">
                  <div class="log-details__section-title-group">
                    <span class="log-details__section-title">Original-Nachricht</span>
                    <span class="log-details__section-hint">(unveraendert)</span>
                  </div>
                </div>
                <pre class="log-details__code">{{ log.message }}</pre>
              </div>

              <!-- Exception (if present) -->
              <div v-if="log.exception" class="log-details__section log-details__section--error">
                <span class="log-details__section-title log-details__section-title--error">Exception</span>
                <pre class="log-details__code log-details__code--error">{{ log.exception }}</pre>
              </div>

              <!-- Extra Data (if present) -->
              <div v-if="log.extra && Object.keys(log.extra).length > 0" class="log-details__section">
                <span class="log-details__section-title">Zusaetzliche Daten</span>
                <pre class="log-details__code log-details__code--extra">{{ JSON.stringify(log.extra, null, 2) }}</pre>
              </div>

              <!-- Actions -->
              <div class="log-details__actions">
                <button
                  class="log-details__action-btn"
                  @click.stop="copyMessage(log, index)"
                >
                  <component :is="copiedMessageId === index ? Check : Copy" class="w-3.5 h-3.5" />
                  {{ copiedMessageId === index ? 'Kopiert!' : 'Nachricht kopieren' }}
                </button>
                <button
                  class="log-details__action-btn"
                  @click.stop="copyAsJson(log, index)"
                >
                  <component :is="copiedJsonId === index ? Check : FileJson" class="w-3.5 h-3.5" />
                  {{ copiedJsonId === index ? 'Kopiert!' : 'Als JSON kopieren' }}
                </button>
              </div>
            </div>
          </Transition>
        </div>

        <!-- Load More -->
        <div v-if="hasMore" class="logs-load-more">
          <button
            class="btn-secondary btn-sm"
            :disabled="isLoading"
            @click="loadMore"
          >
            <RefreshCw v-if="isLoading" class="w-4 h-4 mr-2 animate-spin" />
            Mehr laden
          </button>
        </div>
      </template>
    </div>

    <!-- Log Management Panel -->
    <Teleport to="body">
      <LogManagementPanel
        v-if="showManagement"
        @close="showManagement = false"
        @cleanup-success="handleCleanupSuccess"
      />
    </Teleport>
  </div>
</template>

<style scoped>
.logs-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* =============================================================================
   Toolbar
   ============================================================================= */
.logs-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background: linear-gradient(
    135deg,
    rgba(59, 130, 246, 0.04) 0%,
    rgba(139, 92, 246, 0.04) 50%,
    rgba(236, 72, 153, 0.04) 100%
  );
  border-bottom: 1px solid var(--glass-border);
  flex-wrap: wrap;
}

.logs-toolbar__filters {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.logs-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
}

.logs-select,
.logs-input {
  padding: 0.375rem 0.625rem;
  font-size: 0.8125rem;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
}

.logs-select {
  min-width: 5rem;
}

.logs-select--file {
  max-width: 10rem;
}

.logs-input--module {
  width: 8rem;
}

.logs-search {
  position: relative;
  flex: 1;
  min-width: 8rem;
  max-width: 16rem;
}

.logs-search__icon {
  position: absolute;
  left: 0.625rem;
  top: 50%;
  transform: translateY(-50%);
  width: 0.875rem;
  height: 0.875rem;
  color: var(--color-text-muted);
  pointer-events: none;
}

.logs-search__input {
  width: 100%;
  padding: 0.375rem 0.625rem 0.375rem 2rem;
  font-size: 0.8125rem;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
}

.logs-search__input::placeholder {
  color: var(--color-text-muted);
}

.btn-ghost--active {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
}

.btn-ghost--danger:hover {
  color: var(--color-danger);
}

.btn-label {
  display: none;
}

@media (min-width: 768px) {
  .btn-label {
    display: inline;
    margin-left: 0.375rem;
  }
}

/* =============================================================================
   Info Bar
   ============================================================================= */
.logs-info {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 1rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  background-color: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--glass-border);
}

.logs-info__polling {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  color: var(--color-success);
}

.logs-info__dot {
  width: 0.5rem;
  height: 0.5rem;
  background-color: var(--color-success);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* =============================================================================
   Error
   ============================================================================= */
.logs-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  background-color: rgba(239, 68, 68, 0.1);
  border-bottom: 1px solid rgba(239, 68, 68, 0.3);
}

.logs-error__icon {
  width: 1rem;
  height: 1rem;
  color: var(--color-danger);
  flex-shrink: 0;
}

.logs-error__text {
  flex: 1;
  font-size: 0.8125rem;
  color: var(--color-danger);
}

.logs-error__close {
  padding: 0.25rem;
  font-size: 1.25rem;
  line-height: 1;
  color: var(--color-danger);
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0.7;
}

.logs-error__close:hover {
  opacity: 1;
}

/* =============================================================================
   Log List
   ============================================================================= */
.logs-list {
  flex: 1;
  overflow-y: auto;
}

.logs-loading,
.logs-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
  text-align: center;
  gap: 0.75rem;
}

.logs-loading__spinner {
  width: 1.5rem;
  height: 1.5rem;
  border: 2px solid var(--glass-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.logs-empty__icon {
  width: 3rem;
  height: 3rem;
  color: var(--color-text-muted);
  opacity: 0.3;
}

.logs-empty__text {
  font-size: 0.875rem;
  color: var(--color-text-muted);
  margin: 0;
}

/* =============================================================================
   Log Entry - Border + Glow Design
   ============================================================================= */
.log-entry {
  border-bottom: 1px solid var(--glass-border);
  border-left: 3px solid var(--level-border);
  box-shadow: inset 3px 0 8px var(--level-glow, transparent);
  background-color: var(--level-tint, transparent);
  transition: background-color 0.2s ease;
}

.log-entry:hover {
  background-color: rgba(255, 255, 255, 0.04);
}

.log-entry--critical {
  animation: pulse-critical 2s ease-in-out infinite;
}

@keyframes pulse-critical {
  0%, 100% { background-color: rgba(239, 68, 68, 0.06); }
  50% { background-color: rgba(239, 68, 68, 0.12); }
}

.log-entry__header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  cursor: pointer;
}

.log-entry__expand {
  padding: 0;
  color: var(--color-text-muted);
  background: none;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
}

.log-entry__time {
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--color-text-muted);
  flex-shrink: 0;
  width: 4.5rem;
}

.log-level {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
}

.log-level--debug {
  background-color: rgba(156, 163, 175, 0.15);
  color: rgb(156, 163, 175);
}

.log-level--info {
  background-color: rgba(59, 130, 246, 0.15);
  color: rgb(96, 165, 250);
}

.log-level--warning {
  background-color: rgba(251, 191, 36, 0.15);
  color: rgb(251, 191, 36);
}

.log-level--error {
  background-color: rgba(239, 68, 68, 0.15);
  color: rgb(248, 113, 113);
}

.log-level--critical {
  background-color: rgba(220, 38, 38, 0.2);
  color: rgb(252, 165, 165);
}

.log-entry__logger {
  font-size: 0.75rem;
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  flex-shrink: 0;
  max-width: 12rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log-entry__message {
  flex: 1;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* =============================================================================
   Log Details - Glasmorphism Panel
   ============================================================================= */
.log-entry__details {
  margin: 0.5rem 1rem 0.75rem 2.5rem;
  padding: 1rem;
  border-radius: var(--radius-md);
  background: rgba(15, 15, 20, 0.85);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

/* Summary Section */
.log-detail-summary {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  padding: 0.75rem;
  margin-bottom: 1rem;
  border-radius: var(--radius-md);
  background: linear-gradient(
    135deg,
    rgba(59, 130, 246, 0.08) 0%,
    rgba(139, 92, 246, 0.08) 100%
  );
  border: 1px solid rgba(139, 92, 246, 0.15);
}

.log-detail-summary__icon {
  font-size: 1.5rem;
  line-height: 1;
  flex-shrink: 0;
}

.log-detail-summary__content {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
}

.log-detail-summary__title {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-primary);
}

.log-detail-summary__desc {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

/* Details Grid */
.log-details__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.log-details__item {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.log-details__label {
  font-size: 0.6875rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.log-details__value {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
}

.log-details__value--mono {
  font-family: var(--font-mono);
}

/* Category Badge */
.log-category-badge {
  display: inline-block;
  padding: 0.125rem 0.5rem;
  font-size: 0.6875rem;
  font-weight: 500;
  border-radius: var(--radius-xs);
  width: fit-content;
}

.log-category-badge[data-category="scheduler"] {
  background-color: rgba(168, 85, 247, 0.15);
  color: rgb(192, 132, 252);
}

.log-category-badge[data-category="sensor"] {
  background-color: rgba(16, 185, 129, 0.15);
  color: rgb(52, 211, 153);
}

.log-category-badge[data-category="heartbeat"] {
  background-color: rgba(59, 130, 246, 0.15);
  color: rgb(96, 165, 250);
}

.log-category-badge[data-category="mqtt"] {
  background-color: rgba(20, 184, 166, 0.15);
  color: rgb(45, 212, 191);
}

.log-category-badge[data-category="config"] {
  background-color: rgba(107, 114, 128, 0.2);
  color: rgb(156, 163, 175);
}

.log-category-badge[data-category="maintenance"] {
  background-color: rgba(245, 158, 11, 0.15);
  color: rgb(251, 191, 36);
}

.log-category-badge[data-category="websocket"] {
  background-color: rgba(99, 102, 241, 0.15);
  color: rgb(129, 140, 248);
}

.log-category-badge[data-category="actuator"] {
  background-color: rgba(236, 72, 153, 0.15);
  color: rgb(244, 114, 182);
}

.log-category-badge[data-category="auth"] {
  background-color: rgba(251, 191, 36, 0.15);
  color: rgb(251, 191, 36);
}

.log-category-badge[data-category="error"] {
  background-color: rgba(239, 68, 68, 0.15);
  color: rgb(248, 113, 113);
}

.log-category-badge[data-category="system"] {
  background-color: rgba(107, 114, 128, 0.15);
  color: rgb(156, 163, 175);
}

/* Sections */
.log-details__section {
  margin-bottom: 0.75rem;
}

.log-details__section:last-of-type {
  margin-bottom: 0;
}

.log-details__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.375rem;
}

.log-details__section-title-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.log-details__section-title {
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-muted);
}

.log-details__section-title--error {
  color: rgb(248, 113, 113);
}

.log-details__section-hint {
  font-size: 0.6875rem;
  font-style: italic;
  color: rgba(156, 163, 175, 0.5);
}

.log-details__section--error .log-details__section-title {
  color: var(--color-danger);
}

.log-details__code {
  padding: 0.75rem;
  font-size: 0.75rem;
  font-family: var(--font-mono);
  line-height: 1.5;
  color: var(--color-text-secondary);
  background-color: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}

.log-details__code--error {
  background-color: rgba(220, 38, 38, 0.1);
  color: rgb(248, 113, 113);
  border-color: rgba(239, 68, 68, 0.15);
}

.log-details__code--extra {
  background-color: rgba(59, 130, 246, 0.08);
  color: rgb(147, 197, 253);
  border-color: rgba(59, 130, 246, 0.15);
}

/* Actions */
.log-details__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.log-details__action-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.75rem;
  font-size: 0.75rem;
  color: var(--color-text-muted);
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all 0.15s ease;
}

.log-details__action-btn:hover {
  color: var(--color-text-primary);
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
}

/* =============================================================================
   Load More
   ============================================================================= */
.logs-load-more {
  display: flex;
  justify-content: center;
  padding: 1rem;
  border-top: 1px solid var(--glass-border);
}

/* =============================================================================
   Transitions
   ============================================================================= */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.15s ease-out;
}

.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  transform: translateY(-0.25rem);
}

/* =============================================================================
   Mobile Responsive
   ============================================================================= */
@media (max-width: 479px) {
  .log-details__grid {
    grid-template-columns: 1fr;
  }

  .log-entry__details {
    margin-left: 0.5rem;
    margin-right: 0.5rem;
  }

  .log-details__actions {
    flex-direction: column;
  }

  .log-details__action-btn {
    justify-content: center;
  }
}

@media (max-width: 768px) {
  .logs-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .logs-toolbar__filters {
    order: 2;
  }

  .logs-toolbar__actions {
    order: 1;
    justify-content: flex-end;
  }

  .logs-select--file {
    max-width: none;
    flex: 1;
  }

  .logs-input--module {
    display: none;
  }

  .logs-search {
    max-width: none;
    flex: 1;
  }

  .log-entry__header {
    flex-wrap: wrap;
    padding: 0.5rem;
  }

  .log-entry__logger {
    display: none;
  }

  .log-entry__message {
    width: 100%;
    margin-top: 0.25rem;
    padding-left: 1.5rem;
    white-space: normal;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }

  .log-entry__details {
    margin-left: 0.75rem;
    margin-right: 0.75rem;
  }

  .log-details__grid {
    grid-template-columns: 1fr 1fr;
  }
}

/* =============================================================================
   Time Window Chip (Feature 1.2)
   ============================================================================= */
.time-window-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
  padding: 0.375rem 0.5rem 0.375rem 0.625rem;
  background: rgba(139, 92, 246, 0.15);
  border: 1px solid rgba(139, 92, 246, 0.25);
  border-radius: var(--radius-full);
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-mock);
}

.time-window-chip__expand,
.time-window-chip__clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  border-radius: 50%;
  background: transparent;
  border: none;
  color: inherit;
  cursor: pointer;
  transition: background 0.15s;
}

.time-window-chip__expand:hover {
  background: rgba(139, 92, 246, 0.2);
}

.time-window-chip__clear:hover {
  background: rgba(239, 68, 68, 0.2);
  color: var(--color-error);
}

/* =============================================================================
   Empty State Enhancements
   ============================================================================= */
.logs-empty__title {
  font-size: 1rem;
  font-weight: 500;
  color: var(--color-text-primary);
  margin: 0 0 0.25rem;
}

.logs-empty__actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 1rem;
}

@media (max-width: 479px) {
  .logs-empty__actions {
    flex-direction: column;
    width: 100%;
  }
  .logs-empty__actions .btn-secondary,
  .logs-empty__actions .btn-ghost {
    width: 100%;
    justify-content: center;
  }
}
</style>
