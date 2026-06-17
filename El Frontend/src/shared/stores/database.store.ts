/**
 * Database Explorer Store
 *
 * Pinia store for managing database explorer state.
 * Follows the pattern from src/stores/mockEsp.ts
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import databaseApi, {
  type TableSchema,
  type TableDataResponse,
  type TableQueryParams,
  type SortOrder,
  type RecordResponse
} from '@/api/database'

export const useDatabaseStore = defineStore('database', () => {
  // ==========================================================================
  // State
  // ==========================================================================

  const tables = ref<TableSchema[]>([])
  const currentTable = ref<string | null>(null)
  const currentSchema = ref<TableSchema | null>(null)
  const currentData = ref<TableDataResponse | null>(null)
  const selectedRecord = ref<RecordResponse | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Query parameters (persistent during session)
  const queryParams = ref<TableQueryParams>({
    page: 1,
    page_size: 50,
    sort_order: 'desc'
  })

  // ==========================================================================
  // Getters
  // ==========================================================================

  const tableNames = computed(() => tables.value.map(t => t.table_name))

  const currentColumns = computed(() => currentSchema.value?.columns || [])

  const totalRecords = computed(() => currentData.value?.total_count || 0)

  const totalPages = computed(() => currentData.value?.total_pages || 0)

  const currentPage = computed(() => currentData.value?.page || 1)

  const hasData = computed(() => (currentData.value?.data.length || 0) > 0)

  // ==========================================================================
  // Actions
  // ==========================================================================

  /**
   * Load list of all available tables
   */
  async function loadTables(): Promise<void> {
    isLoading.value = true
    error.value = null

    try {
      tables.value = await databaseApi.listTables()
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || 'Failed to load tables'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Select a table and load its schema and data
   */
  async function selectTable(tableName: string): Promise<void> {
    if (!tableNames.value.includes(tableName)) {
      throw new Error(`Table '${tableName}' not found`)
    }

    currentTable.value = tableName

    // Reset query params when selecting new table
    queryParams.value = {
      page: 1,
      page_size: 50,
      sort_order: 'desc'
    }

    selectedRecord.value = null
    isLoading.value = true
    error.value = null

    try {
      // Load schema and data in parallel
      const [schema, data] = await Promise.all([
        databaseApi.getTableSchema(tableName),
        databaseApi.queryTable(tableName, queryParams.value)
      ])

      currentSchema.value = schema
      currentData.value = data

      // Set default sort column
      if (schema.columns.length > 0) {
        const timestampCol = schema.columns.find(c => c.name === 'timestamp')
        const createdAtCol = schema.columns.find(c => c.name === 'created_at')
        const idCol = schema.columns.find(c => c.primary_key)

        if (timestampCol) {
          queryParams.value.sort_by = 'timestamp'
        } else if (createdAtCol) {
          queryParams.value.sort_by = 'created_at'
        } else if (idCol) {
          queryParams.value.sort_by = idCol.name
        }
      }
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || `Failed to load table '${tableName}'`
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Refresh data with current query parameters
   */
  async function refreshData(): Promise<void> {
    if (!currentTable.value) return

    isLoading.value = true
    error.value = null

    try {
      currentData.value = await databaseApi.queryTable(
        currentTable.value,
        queryParams.value
      )
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || 'Failed to refresh data'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Change page
   */
  async function setPage(page: number): Promise<void> {
    queryParams.value.page = page
    await refreshData()
  }

  /**
   * Change page size
   */
  async function setPageSize(size: number): Promise<void> {
    queryParams.value.page_size = size
    queryParams.value.page = 1 // Reset to first page
    await refreshData()
  }

  /**
   * Set sorting
   */
  async function setSort(column: string, order: SortOrder): Promise<void> {
    queryParams.value.sort_by = column
    queryParams.value.sort_order = order
    await refreshData()
  }

  /**
   * Toggle sort order for a column
   */
  async function toggleSort(column: string): Promise<void> {
    if (queryParams.value.sort_by === column) {
      // Toggle order
      const newOrder = queryParams.value.sort_order === 'asc' ? 'desc' : 'asc'
      await setSort(column, newOrder)
    } else {
      // New column, default to desc
      await setSort(column, 'desc')
    }
  }

  /**
   * Set filters
   */
  async function setFilters(filters: Record<string, unknown>): Promise<void> {
    queryParams.value.filters = filters
    queryParams.value.page = 1 // Reset to first page
    await refreshData()
  }

  /**
   * Clear all filters
   */
  async function clearFilters(): Promise<void> {
    queryParams.value.filters = undefined
    queryParams.value.page = 1
    await refreshData()
  }

  /**
   * Load a single record
   */
  async function loadRecord(recordId: string): Promise<void> {
    if (!currentTable.value) return

    isLoading.value = true
    error.value = null

    try {
      selectedRecord.value = await databaseApi.getRecord(currentTable.value, recordId)
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || 'Failed to load record'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Close record detail modal
   */
  function closeRecord(): void {
    selectedRecord.value = null
  }

  /**
   * Reset store state
   */
  function reset(): void {
    currentTable.value = null
    currentSchema.value = null
    currentData.value = null
    selectedRecord.value = null
    queryParams.value = {
      page: 1,
      page_size: 50,
      sort_order: 'desc'
    }
    error.value = null
  }

  /**
   * Clear error
   */
  function clearError(): void {
    error.value = null
  }

  return {
    // State
    tables,
    currentTable,
    currentSchema,
    currentData,
    selectedRecord,
    isLoading,
    error,
    queryParams,

    // Getters
    tableNames,
    currentColumns,
    totalRecords,
    totalPages,
    currentPage,
    hasData,

    // Actions
    loadTables,
    selectTable,
    refreshData,
    setPage,
    setPageSize,
    setSort,
    toggleSort,
    setFilters,
    clearFilters,
    loadRecord,
    closeRecord,
    reset,
    clearError
  }
})
