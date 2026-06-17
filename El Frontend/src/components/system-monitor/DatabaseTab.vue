<script setup lang="ts">
/**
 * DatabaseTab - Database Explorer Tab for System Monitor
 *
 * Features:
 * - PostgreSQL table exploration (Mock Store removed)
 * - Integration with databaseColumnTranslator for German labels
 * - JSON export with translated column names
 * - Compact layout for System Monitor integration
 * - Mobile-responsive design
 *
 * Reuses existing components:
 * - TableSelector, DataTable, FilterPanel, Pagination, RecordDetailModal
 *
 * @see El Servador/god_kaiser_server/src/api/v1/debug.py - Database Debug API
 */

import { ref, computed, onMounted } from 'vue'
import { useDatabaseStore } from '@/shared/stores/database.store'
import {
  getColumnLabel,
  formatCellValue,
  getTableLabel,
  getPrimaryColumnKeys,
  getTableConfig
} from '@/utils/databaseColumnTranslator'
import {
  Database,
  RefreshCw,
  Download,
  AlertCircle,
  ChevronDown,
} from 'lucide-vue-next'
import { createLogger } from '@/utils/logger'

// Database Sub-Components
import FilterPanel from '@/components/database/FilterPanel.vue'
import DataTable from '@/components/database/DataTable.vue'
import Pagination from '@/components/database/Pagination.vue'
import RecordDetailModal from '@/components/database/RecordDetailModal.vue'

const log = createLogger('DatabaseTab')

// Time-series tables and their timestamp columns (mirrors backend debug_db.py TIME_SERIES_TABLES)
const TIME_SERIES_TABLE_COLS: Record<string, string> = {
  sensor_data: 'timestamp',
  actuator_history: 'timestamp',
  logic_execution_history: 'timestamp',
  audit_logs: 'created_at',
}

const TIME_RANGE_OPTIONS = [
  { value: '24h', label: 'Letzte 24h' },
  { value: '7d', label: 'Letzte 7 Tage' },
  { value: '30d', label: 'Letzte 30 Tage' },
  { value: 'all', label: 'Alle Daten' },
] as const

type TimeRangeValue = typeof TIME_RANGE_OPTIONS[number]['value']

// ============================================================================
// Store
// ============================================================================

const store = useDatabaseStore()

// ============================================================================
// State
// ============================================================================

const showFilterPanel = ref(false)
const selectedTimeRange = ref<TimeRangeValue>('24h')

// ============================================================================
// Computed
// ============================================================================

const isTimeSeriesTable = computed(() =>
  store.currentTable ? store.currentTable in TIME_SERIES_TABLE_COLS : false
)

// ============================================================================
// Computed - Column Translation
// ============================================================================

/**
 * Get translated columns with German labels
 * FILTERED by defaultVisible from databaseColumnTranslator
 *
 * Robin's Prinzipien:
 * - Timestamps IMMER sichtbar (created_at, last_seen)
 * - IDs NIEMALS sichtbar (id, zone_id, user_id)
 * - Namen statt IDs (zone_name statt zone_id)
 */
const translatedColumns = computed(() => {
  if (!store.currentTable || !store.currentColumns) return []

  // Get the visible column keys from translator config
  const tableConfig = getTableConfig(store.currentTable)
  const visibleKeys = tableConfig
    ? getPrimaryColumnKeys(store.currentTable)
    : store.currentColumns.map(col => col.name) // Fallback: show all if no config

  // Filter and translate columns - keep order from translator config
  const columnsMap = new Map(store.currentColumns.map(col => [col.name, col]))

  // Build ordered list based on translator config order
  const orderedColumns: typeof store.currentColumns = []
  if (tableConfig) {
    // Use order from translator config (important: timestamp first!)
    for (const key of visibleKeys) {
      const col = columnsMap.get(key)
      if (col) {
        orderedColumns.push(col)
      }
    }
  } else {
    // Fallback: use backend order
    orderedColumns.push(...store.currentColumns)
  }

  return orderedColumns.map(col => ({
    ...col,
    label: getColumnLabel(store.currentTable!, col.name),
  }))
})

/**
 * Get translated data with formatted values
 */
const translatedData = computed(() => {
  if (!store.currentTable || !store.currentData?.data) return []

  return store.currentData.data.map(row => {
    const translatedRow: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(row)) {
      translatedRow[key] = value // Keep original value for sorting/filtering
    }
    return translatedRow
  })
})

// ============================================================================
// Methods - Data Loading
// ============================================================================

async function handleSelectTable(tableName: string): Promise<void> {
  selectedTimeRange.value = '24h' // Reset to default when switching tables
  try {
    await store.selectTable(tableName)
    showFilterPanel.value = false
  } catch (err) {
    log.error(' Failed to select table:', err)
  }
}

function buildTimeRangeFilter(range: TimeRangeValue, table: string): Record<string, string> | undefined {
  if (range === '24h') return undefined // Server applies 24h default automatically
  const col = TIME_SERIES_TABLE_COLS[table]
  if (!col) return undefined
  const now = Date.now()
  const msMap: Record<string, number> = { '7d': 7 * 86400000, '30d': 30 * 86400000 }
  const from = range === 'all' ? new Date('2000-01-01') : new Date(now - msMap[range])
  return { [`${col}__gte`]: from.toISOString() }
}

async function handleTimeRangeChange(range: TimeRangeValue): Promise<void> {
  selectedTimeRange.value = range
  if (!store.currentTable) return
  const tsCol = TIME_SERIES_TABLE_COLS[store.currentTable]
  // Preserve non-timestamp filters, replace only the timestamp filter
  const existing = { ...(store.queryParams.filters ?? {}) }
  if (tsCol) {
    delete existing[`${tsCol}__gte`]
    delete existing[`${tsCol}__lte`]
    delete existing[tsCol]
  }
  const tsFilter = buildTimeRangeFilter(range, store.currentTable)
  const merged = tsFilter ? { ...existing, ...tsFilter } : existing
  if (Object.keys(merged).length > 0) {
    await store.setFilters(merged)
  } else {
    await store.clearFilters()
  }
}

async function handleRefresh(): Promise<void> {
  try {
    await store.refreshData()
  } catch (err) {
    log.error(' Failed to refresh:', err)
  }
}

// ============================================================================
// Methods - Sorting & Filtering
// ============================================================================

async function handleSort(column: string): Promise<void> {
  try {
    await store.toggleSort(column)
  } catch (err) {
    log.error(' Failed to sort:', err)
  }
}

async function handleApplyFilters(filters: Record<string, unknown>): Promise<void> {
  try {
    await store.setFilters(filters)
  } catch (err) {
    log.error(' Failed to apply filters:', err)
  }
}

async function handleClearFilters(): Promise<void> {
  try {
    await store.clearFilters()
  } catch (err) {
    log.error(' Failed to clear filters:', err)
  }
}

// ============================================================================
// Methods - Pagination
// ============================================================================

async function handlePageChange(page: number): Promise<void> {
  try {
    await store.setPage(page)
  } catch (err) {
    log.error(' Failed to change page:', err)
  }
}

async function handlePageSizeChange(size: number): Promise<void> {
  try {
    await store.setPageSize(size)
  } catch (err) {
    log.error(' Failed to change page size:', err)
  }
}

// ============================================================================
// Methods - Row Actions
// ============================================================================

async function handleRowClick(record: Record<string, unknown>): Promise<void> {
  const pkColumn = store.currentSchema?.columns.find(c => c.primary_key)
  const pkValue = pkColumn
    ? String(record[pkColumn.name] || '')
    : String(record['id'] || '')

  if (pkValue) {
    try {
      await store.loadRecord(pkValue)
    } catch (err) {
      log.error('Failed to load record:', err)
    }
  }
}

async function handleNavigateToForeignKey(table: string, id: string): Promise<void> {
  store.closeRecord()

  if (store.tableNames.includes(table)) {
    await handleSelectTable(table)
    await store.setFilters({ id })
  }
}

// ============================================================================
// Methods - Export
// ============================================================================

function exportToJson(): void {
  if (!store.currentTable || !store.currentData?.data) return

  // Build translated export data
  const exportData = store.currentData.data.map(row => {
    const translatedRow: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(row)) {
      const label = getColumnLabel(store.currentTable!, key)
      translatedRow[label] = formatCellValue(store.currentTable!, key, value)
    }
    return translatedRow
  })

  const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${store.currentTable}-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// ============================================================================
// Lifecycle
// ============================================================================

onMounted(async () => {
  if (store.tables.length === 0) {
    await store.loadTables()
  }
})
</script>

<template>
  <div class="db-tab">
    <!-- Toolbar -->
    <div class="db-toolbar">
      <div class="db-toolbar__left">
        <!-- Table Selector (Compact) -->
        <div class="db-table-select">
          <Database class="db-table-select__icon" />
          <select
            :value="store.currentTable || ''"
            class="db-table-select__dropdown"
            @change="handleSelectTable(($event.target as HTMLSelectElement).value)"
          >
            <option value="" disabled>Tabelle auswählen...</option>
            <option v-for="table in store.tables" :key="table.table_name" :value="table.table_name">
              {{ getTableLabel(table.table_name) }}
              ({{ table.row_count.toLocaleString() }})
            </option>
          </select>
          <ChevronDown class="db-table-select__arrow" />
        </div>

        <!-- Time Range Selector (only for time-series tables) -->
        <div v-if="isTimeSeriesTable" class="db-time-range">
          <select
            :value="selectedTimeRange"
            class="db-table-select__dropdown db-time-range__select"
            @change="handleTimeRangeChange(($event.target as HTMLSelectElement).value as TimeRangeValue)"
          >
            <option v-for="opt in TIME_RANGE_OPTIONS" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </option>
          </select>
          <ChevronDown class="db-table-select__arrow" />
        </div>

        <!-- Record Count -->
        <span v-if="store.currentData" class="db-toolbar__count">
          {{ store.currentData.total_count.toLocaleString() }} Einträge
        </span>
      </div>

      <div class="db-toolbar__right">
        <!-- Toggle Filters -->
        <button
          v-if="store.currentTable"
          class="btn-ghost btn-sm"
          :class="{ 'btn-ghost--active': showFilterPanel }"
          @click="showFilterPanel = !showFilterPanel"
        >
          Filter
        </button>

        <!-- Refresh -->
        <button
          v-if="store.currentTable"
          class="btn-ghost btn-sm"
          :disabled="store.isLoading"
          @click="handleRefresh"
        >
          <RefreshCw :class="['w-4 h-4', store.isLoading && 'animate-spin']" />
          <span class="btn-label">Aktualisieren</span>
        </button>

        <!-- Export -->
        <button
          v-if="store.currentTable && store.currentData?.data.length"
          class="btn-ghost btn-sm"
          @click="exportToJson"
        >
          <Download class="w-4 h-4" />
          <span class="btn-label">JSON</span>
        </button>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="store.error" class="db-error">
      <AlertCircle class="db-error__icon" />
      <span class="db-error__text">{{ store.error }}</span>
      <button class="db-error__close" @click="store.clearError()">&times;</button>
    </div>

    <!-- Filter Panel (Collapsible) -->
    <Transition name="slide-down">
      <div v-if="showFilterPanel && store.currentTable" class="db-filter-panel">
        <FilterPanel
          :columns="store.currentColumns"
          :current-filters="store.queryParams.filters"
          @apply="handleApplyFilters"
          @clear="handleClearFilters"
        />
      </div>
    </Transition>

    <!-- Content -->
    <div class="db-content">
      <!-- Empty State - No Table Selected -->
      <div v-if="!store.currentTable && !store.isLoading" class="db-empty">
        <Database class="db-empty__icon" />
        <p class="db-empty__title">Keine Tabelle ausgewählt</p>
        <p class="db-empty__subtitle">
          Wähle eine Tabelle aus dem Dropdown oben um die Daten zu erkunden
        </p>
      </div>

      <!-- Loading -->
      <div v-else-if="store.isLoading && !store.currentData" class="db-loading">
        <div class="db-loading__spinner"></div>
        <span>Daten werden geladen...</span>
      </div>

      <!-- Data Table -->
      <template v-else-if="store.currentTable">
        <div class="db-table-wrapper">
          <DataTable
            :columns="translatedColumns"
            :data="translatedData"
            :loading="store.isLoading"
            :sort-by="store.queryParams.sort_by"
            :sort-order="store.queryParams.sort_order"
            @sort="handleSort"
            @row-click="handleRowClick"
          />
        </div>

        <!-- Pagination -->
        <div v-if="store.currentData" class="db-pagination">
          <Pagination
            :page="store.currentData.page"
            :total-pages="store.currentData.total_pages"
            :total-count="store.currentData.total_count"
            :page-size="store.queryParams.page_size || 50"
            @page-change="handlePageChange"
            @page-size-change="handlePageSizeChange"
          />
        </div>
      </template>
    </div>

    <!-- Record Detail Modal -->
    <RecordDetailModal
      v-if="store.selectedRecord"
      :table-name="store.currentTable || ''"
      :record="store.selectedRecord.record"
      @close="store.closeRecord()"
      @navigate-to-foreign-key="handleNavigateToForeignKey"
    />
  </div>
</template>

<style scoped>
.db-tab {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* =============================================================================
   Toolbar
   ============================================================================= */
.db-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  background-color: var(--color-bg-secondary);
  border-bottom: 1px solid var(--glass-border);
  flex-wrap: wrap;
}

.db-toolbar__left,
.db-toolbar__right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.db-toolbar__count {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
}

/* Table Selector */
.db-table-select {
  position: relative;
  display: flex;
  align-items: center;
}

.db-table-select__icon {
  position: absolute;
  left: 0.625rem;
  width: 1rem;
  height: 1rem;
  color: var(--color-text-muted);
  pointer-events: none;
}

.db-table-select__dropdown {
  appearance: none;
  padding: 0.5rem 2rem 0.5rem 2.25rem;
  font-size: 0.8125rem;
  font-weight: 500;
  background-color: var(--color-bg-primary);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-primary);
  cursor: pointer;
  min-width: 12rem;
}

.db-table-select__dropdown:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-alpha);
}

.db-table-select__arrow {
  position: absolute;
  right: 0.625rem;
  width: 1rem;
  height: 1rem;
  color: var(--color-text-muted);
  pointer-events: none;
}

.db-time-range {
  position: relative;
  display: flex;
  align-items: center;
}

.db-time-range__select {
  min-width: 9rem;
  padding-left: 0.75rem;
}

.btn-ghost--active {
  background-color: var(--color-bg-tertiary);
  color: var(--color-text-primary);
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
   Error
   ============================================================================= */
.db-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.625rem 1rem;
  background-color: rgba(239, 68, 68, 0.1);
  border-bottom: 1px solid rgba(239, 68, 68, 0.3);
}

.db-error__icon {
  width: 1rem;
  height: 1rem;
  color: var(--color-danger);
  flex-shrink: 0;
}

.db-error__text {
  flex: 1;
  font-size: 0.8125rem;
  color: var(--color-danger);
}

.db-error__close {
  padding: 0.25rem;
  font-size: 1.25rem;
  line-height: 1;
  color: var(--color-danger);
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0.7;
}

.db-error__close:hover {
  opacity: 1;
}

/* =============================================================================
   Filter Panel
   ============================================================================= */
.db-filter-panel {
  padding: 0.75rem 1rem;
  background-color: var(--color-bg-tertiary);
  border-bottom: 1px solid var(--glass-border);
}

/* =============================================================================
   Content
   ============================================================================= */
.db-content {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.db-empty,
.db-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
  text-align: center;
  gap: 0.5rem;
}

.db-empty__icon {
  width: 3rem;
  height: 3rem;
  color: var(--color-text-muted);
  opacity: 0.3;
  margin-bottom: 0.5rem;
}

.db-empty__title {
  font-size: 1rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin: 0;
}

.db-empty__subtitle {
  font-size: 0.8125rem;
  color: var(--color-text-muted);
  margin: 0;
}

.db-loading__spinner {
  width: 1.5rem;
  height: 1.5rem;
  border: 2px solid var(--glass-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 0.5rem;
}

/* =============================================================================
   Table Wrapper
   ============================================================================= */
.db-table-wrapper {
  flex: 1;
  overflow: auto;
}

.db-table-wrapper :deep(.data-table) {
  min-width: 100%;
}

.db-table-wrapper :deep(th),
.db-table-wrapper :deep(td) {
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
}

/* =============================================================================
   Pagination
   ============================================================================= */
.db-pagination {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--glass-border);
  background-color: var(--color-bg-secondary);
}

/* =============================================================================
   Transitions
   ============================================================================= */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.2s ease-out;
}

.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-0.5rem);
}

/* =============================================================================
   Mobile Responsive
   ============================================================================= */
@media (max-width: 768px) {
  .db-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .db-toolbar__left {
    order: 1;
  }

  .db-toolbar__right {
    order: 2;
    justify-content: flex-end;
  }

  .db-table-select__dropdown {
    min-width: 100%;
  }

  .db-table-wrapper {
    overflow-x: auto;
  }

  .db-pagination :deep(.pagination) {
    flex-wrap: wrap;
    gap: 0.5rem;
  }
}
</style>
