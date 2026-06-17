/**
 * Database Store Unit Tests
 *
 * Tests for database explorer state management, table selection,
 * pagination, sorting, filtering, and record loading.
 */

import { describe, it, expect, vi, beforeAll, afterAll, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDatabaseStore } from '@/shared/stores/database.store'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'
import { mockTableSchema, mockTableData } from '../../mocks/handlers'

// MSW Server Lifecycle
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

// =============================================================================
// INITIAL STATE
// =============================================================================

describe('Database Store - Initial State', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('has empty tables array on initialization', () => {
    const store = useDatabaseStore()
    expect(store.tables).toEqual([])
  })

  it('has null currentTable on initialization', () => {
    const store = useDatabaseStore()
    expect(store.currentTable).toBeNull()
  })

  it('has null currentSchema on initialization', () => {
    const store = useDatabaseStore()
    expect(store.currentSchema).toBeNull()
  })

  it('has null currentData on initialization', () => {
    const store = useDatabaseStore()
    expect(store.currentData).toBeNull()
  })

  it('has null selectedRecord on initialization', () => {
    const store = useDatabaseStore()
    expect(store.selectedRecord).toBeNull()
  })

  it('has isLoading false initially', () => {
    const store = useDatabaseStore()
    expect(store.isLoading).toBe(false)
  })

  it('has null error initially', () => {
    const store = useDatabaseStore()
    expect(store.error).toBeNull()
  })

  it('has default queryParams on initialization', () => {
    const store = useDatabaseStore()
    expect(store.queryParams).toEqual({
      page: 1,
      page_size: 50,
      sort_order: 'desc'
    })
  })
})

// =============================================================================
// COMPUTED GETTERS
// =============================================================================

describe('Database Store - Computed Getters', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('tableNames', () => {
    it('returns empty array when no tables loaded', () => {
      const store = useDatabaseStore()
      expect(store.tableNames).toEqual([])
    })

    it('extracts table names from tables array', () => {
      const store = useDatabaseStore()
      store.tables = [
        { ...mockTableSchema, table_name: 'esp_devices' },
        { ...mockTableSchema, table_name: 'sensors' },
        { ...mockTableSchema, table_name: 'actuators' }
      ]
      expect(store.tableNames).toEqual(['esp_devices', 'sensors', 'actuators'])
    })
  })

  describe('currentColumns', () => {
    it('returns empty array when no schema loaded', () => {
      const store = useDatabaseStore()
      expect(store.currentColumns).toEqual([])
    })

    it('returns columns from currentSchema', () => {
      const store = useDatabaseStore()
      store.currentSchema = mockTableSchema
      expect(store.currentColumns).toEqual(mockTableSchema.columns)
    })
  })

  describe('totalRecords', () => {
    it('returns 0 when no data loaded', () => {
      const store = useDatabaseStore()
      expect(store.totalRecords).toBe(0)
    })

    it('returns total_count from currentData', () => {
      const store = useDatabaseStore()
      store.currentData = { ...mockTableData, total_count: 42 }
      expect(store.totalRecords).toBe(42)
    })
  })

  describe('totalPages', () => {
    it('returns 0 when no data loaded', () => {
      const store = useDatabaseStore()
      expect(store.totalPages).toBe(0)
    })

    it('returns total_pages from currentData', () => {
      const store = useDatabaseStore()
      store.currentData = { ...mockTableData, total_pages: 5 }
      expect(store.totalPages).toBe(5)
    })
  })

  describe('currentPage', () => {
    it('returns 1 when no data loaded', () => {
      const store = useDatabaseStore()
      expect(store.currentPage).toBe(1)
    })

    it('returns page from currentData', () => {
      const store = useDatabaseStore()
      store.currentData = { ...mockTableData, page: 3 }
      expect(store.currentPage).toBe(3)
    })
  })

  describe('hasData', () => {
    it('returns false when no data loaded', () => {
      const store = useDatabaseStore()
      expect(store.hasData).toBe(false)
    })

    it('returns false when data array is empty', () => {
      const store = useDatabaseStore()
      store.currentData = { ...mockTableData, data: [] }
      expect(store.hasData).toBe(false)
    })

    it('returns true when data array has items', () => {
      const store = useDatabaseStore()
      store.currentData = mockTableData
      expect(store.hasData).toBe(true)
    })
  })
})

// =============================================================================
// LOAD TABLES
// =============================================================================

describe('Database Store - loadTables', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads tables successfully', async () => {
    const store = useDatabaseStore()

    await store.loadTables()

    expect(store.tables).toEqual([mockTableSchema])
    expect(store.error).toBeNull()
  })

  it('sets isLoading during load', async () => {
    const store = useDatabaseStore()

    const loadPromise = store.loadTables()
    expect(store.isLoading).toBe(true)

    await loadPromise
    expect(store.isLoading).toBe(false)
  })

  it('clears previous error on new load', async () => {
    const store = useDatabaseStore()
    store.error = 'Previous error'

    await store.loadTables()

    expect(store.error).toBeNull()
  })

  it('sets error on load failure', async () => {
    server.use(
      http.get('/api/v1/debug/db/tables', () => {
        return HttpResponse.json(
          { detail: 'Database connection failed' },
          { status: 500 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.loadTables()).rejects.toThrow()
    expect(store.error).toBe('Database connection failed')
  })

  it('sets generic error message when detail not available', async () => {
    server.use(
      http.get('/api/v1/debug/db/tables', () => {
        return HttpResponse.json(
          { error: 'Something went wrong' },
          { status: 500 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.loadTables()).rejects.toThrow()
    expect(store.error).toBe('Failed to load tables')
  })

  it('sets isLoading to false even on error', async () => {
    server.use(
      http.get('/api/v1/debug/db/tables', () => {
        return HttpResponse.json(
          { detail: 'Error' },
          { status: 500 }
        )
      })
    )

    const store = useDatabaseStore()

    try {
      await store.loadTables()
    } catch {
      // Expected
    }

    expect(store.isLoading).toBe(false)
  })
})

// =============================================================================
// SELECT TABLE
// =============================================================================

describe('Database Store - selectTable', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables() // Pre-load tables
  })

  it('throws error when table not in list', async () => {
    const store = useDatabaseStore()

    await expect(store.selectTable('nonexistent_table')).rejects.toThrow(
      "Table 'nonexistent_table' not found"
    )
  })

  it('loads schema and data in parallel', async () => {
    const store = useDatabaseStore()

    await store.selectTable('esp_devices')

    expect(store.currentTable).toBe('esp_devices')
    expect(store.currentSchema).toEqual(mockTableSchema)
    expect(store.currentData).toEqual(expect.objectContaining({
      table_name: 'esp_devices',
      data: expect.any(Array)
    }))
  })

  it('resets queryParams when selecting new table', async () => {
    const store = useDatabaseStore()
    store.queryParams = {
      page: 5,
      page_size: 100,
      sort_by: 'name',
      sort_order: 'asc',
      filters: { status: 'active' }
    }

    await store.selectTable('esp_devices')

    // After selectTable, queryParams should be reset except for sort_by (set after loading schema)
    expect(store.queryParams.page).toBe(1)
    expect(store.queryParams.page_size).toBe(50)
    expect(store.queryParams.sort_order).toBe('desc')
    expect(store.queryParams.filters).toBeUndefined()
    expect(store.queryParams.sort_by).toBe('created_at') // Default from mock schema
  })

  it('clears selectedRecord when selecting table', async () => {
    const store = useDatabaseStore()
    store.selectedRecord = {
      success: true,
      table_name: 'esp_devices',
      record: { id: '1', name: 'Test' }
    }

    await store.selectTable('esp_devices')

    expect(store.selectedRecord).toBeNull()
  })

  it('sets default sort column to timestamp if available', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/schema', () => {
        return HttpResponse.json({
          ...mockTableSchema,
          columns: [
            { name: 'id', type: 'uuid', nullable: false, primary_key: true },
            { name: 'timestamp', type: 'datetime', nullable: false, primary_key: false },
            { name: 'name', type: 'string', nullable: true, primary_key: false }
          ]
        })
      })
    )

    const store = useDatabaseStore()
    await store.selectTable('esp_devices')

    expect(store.queryParams.sort_by).toBe('timestamp')
  })

  it('sets default sort column to created_at if no timestamp', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/schema', () => {
        return HttpResponse.json({
          ...mockTableSchema,
          columns: [
            { name: 'id', type: 'uuid', nullable: false, primary_key: true },
            { name: 'created_at', type: 'datetime', nullable: false, primary_key: false },
            { name: 'name', type: 'string', nullable: true, primary_key: false }
          ]
        })
      })
    )

    const store = useDatabaseStore()
    await store.selectTable('esp_devices')

    expect(store.queryParams.sort_by).toBe('created_at')
  })

  it('sets default sort column to primary key if no timestamp/created_at', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/schema', () => {
        return HttpResponse.json({
          ...mockTableSchema,
          columns: [
            { name: 'id', type: 'uuid', nullable: false, primary_key: true },
            { name: 'name', type: 'string', nullable: true, primary_key: false }
          ]
        })
      })
    )

    const store = useDatabaseStore()
    await store.selectTable('esp_devices')

    expect(store.queryParams.sort_by).toBe('id')
  })

  it('sets isLoading during selectTable', async () => {
    const store = useDatabaseStore()

    const selectPromise = store.selectTable('esp_devices')
    expect(store.isLoading).toBe(true)

    await selectPromise
    expect(store.isLoading).toBe(false)
  })

  it('clears previous error on new selectTable', async () => {
    const store = useDatabaseStore()
    store.error = 'Previous error'

    await store.selectTable('esp_devices')

    expect(store.error).toBeNull()
  })

  it('sets error on selectTable failure', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/schema', () => {
        return HttpResponse.json(
          { detail: 'Table schema not found' },
          { status: 404 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.selectTable('esp_devices')).rejects.toThrow()
    expect(store.error).toBe('Table schema not found')
  })

  it('sets generic error message on selectTable failure without detail', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/schema', () => {
        return HttpResponse.json(
          { error: 'Generic error' },
          { status: 500 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.selectTable('esp_devices')).rejects.toThrow()
    expect(store.error).toBe("Failed to load table 'esp_devices'")
  })
})

// =============================================================================
// REFRESH DATA
// =============================================================================

describe('Database Store - refreshData', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
  })

  it('refetches data with current queryParams', async () => {
    const store = useDatabaseStore()
    store.queryParams.page = 2
    store.queryParams.sort_by = 'name'
    store.queryParams.sort_order = 'asc'

    await store.refreshData()

    expect(store.currentData?.page).toBe(2)
  })

  it('does nothing if no currentTable', async () => {
    const store = useDatabaseStore()
    store.currentTable = null

    await store.refreshData()

    // Should not throw, just no-op
    expect(store.isLoading).toBe(false)
  })

  it('sets isLoading during refresh', async () => {
    const store = useDatabaseStore()

    const refreshPromise = store.refreshData()
    expect(store.isLoading).toBe(true)

    await refreshPromise
    expect(store.isLoading).toBe(false)
  })

  it('clears previous error on refresh', async () => {
    const store = useDatabaseStore()
    store.error = 'Previous error'

    await store.refreshData()

    expect(store.error).toBeNull()
  })

  it('sets error on refresh failure', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices', () => {
        return HttpResponse.json(
          { detail: 'Query failed' },
          { status: 500 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.refreshData()).rejects.toThrow()
    expect(store.error).toBe('Query failed')
  })

  it('sets generic error message on refresh failure without detail', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices', () => {
        return HttpResponse.json(
          { error: 'Generic error' },
          { status: 500 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.refreshData()).rejects.toThrow()
    expect(store.error).toBe('Failed to refresh data')
  })
})

// =============================================================================
// SET PAGE
// =============================================================================

describe('Database Store - setPage', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
  })

  it('updates queryParams.page', async () => {
    const store = useDatabaseStore()

    await store.setPage(3)

    expect(store.queryParams.page).toBe(3)
  })

  it('calls refreshData after updating page', async () => {
    const store = useDatabaseStore()
    const initialDataPage = store.currentData?.page

    await store.setPage(2)

    // Verify refreshData was called by checking data changed
    expect(store.currentData?.page).not.toBe(initialDataPage)
  })

  it('updates currentData with new page', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices', ({ request }) => {
        const url = new URL(request.url)
        const page = url.searchParams.get('page')
        return HttpResponse.json({
          ...mockTableData,
          page: Number(page)
        })
      })
    )

    const store = useDatabaseStore()
    await store.setPage(4)

    expect(store.currentData?.page).toBe(4)
  })
})

// =============================================================================
// SET PAGE SIZE
// =============================================================================

describe('Database Store - setPageSize', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
    store.queryParams.page = 5 // Set to non-1 page
  })

  it('updates queryParams.page_size', async () => {
    const store = useDatabaseStore()

    await store.setPageSize(100)

    expect(store.queryParams.page_size).toBe(100)
  })

  it('resets page to 1 when changing page size', async () => {
    const store = useDatabaseStore()
    expect(store.queryParams.page).toBe(5) // Verify precondition

    await store.setPageSize(100)

    expect(store.queryParams.page).toBe(1)
  })

  it('calls refreshData after updating page size', async () => {
    const store = useDatabaseStore()
    const initialPageSize = store.currentData?.page_size

    await store.setPageSize(25)

    // Verify refreshData was called by checking data changed
    expect(store.currentData).not.toBeNull()
    expect(store.currentData?.page_size).toBe(25)
  })
})

// =============================================================================
// SET SORT
// =============================================================================

describe('Database Store - setSort', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
  })

  it('updates queryParams.sort_by and sort_order', async () => {
    const store = useDatabaseStore()

    await store.setSort('name', 'asc')

    expect(store.queryParams.sort_by).toBe('name')
    expect(store.queryParams.sort_order).toBe('asc')
  })

  it('calls refreshData after updating sort', async () => {
    const store = useDatabaseStore()

    await store.setSort('name', 'asc')

    // Verify refreshData was called by checking data is loaded
    expect(store.currentData).not.toBeNull()
  })
})

// =============================================================================
// TOGGLE SORT
// =============================================================================

describe('Database Store - toggleSort', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
  })

  it('toggles from asc to desc for same column', async () => {
    const store = useDatabaseStore()
    store.queryParams.sort_by = 'name'
    store.queryParams.sort_order = 'asc'

    await store.toggleSort('name')

    expect(store.queryParams.sort_order).toBe('desc')
  })

  it('toggles from desc to asc for same column', async () => {
    const store = useDatabaseStore()
    store.queryParams.sort_by = 'name'
    store.queryParams.sort_order = 'desc'

    await store.toggleSort('name')

    expect(store.queryParams.sort_order).toBe('asc')
  })

  it('defaults to desc for new column', async () => {
    const store = useDatabaseStore()
    store.queryParams.sort_by = 'name'
    store.queryParams.sort_order = 'asc'

    await store.toggleSort('status')

    expect(store.queryParams.sort_by).toBe('status')
    expect(store.queryParams.sort_order).toBe('desc')
  })

  it('calls refreshData after toggle', async () => {
    const store = useDatabaseStore()

    await store.toggleSort('name')

    // Verify refreshData was called by checking data is loaded
    expect(store.currentData).not.toBeNull()
  })
})

// =============================================================================
// SET FILTERS
// =============================================================================

describe('Database Store - setFilters', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
    store.queryParams.page = 3 // Set to non-1 page
  })

  it('updates queryParams.filters', async () => {
    const store = useDatabaseStore()
    const filters = { status: 'online', zone_id: 'zone_1' }

    await store.setFilters(filters)

    expect(store.queryParams.filters).toEqual(filters)
  })

  it('resets page to 1 when setting filters', async () => {
    const store = useDatabaseStore()
    expect(store.queryParams.page).toBe(3) // Verify precondition

    await store.setFilters({ status: 'online' })

    expect(store.queryParams.page).toBe(1)
  })

  it('calls refreshData after setting filters', async () => {
    const store = useDatabaseStore()

    await store.setFilters({ status: 'online' })

    // Verify refreshData was called by checking data is loaded
    expect(store.currentData).not.toBeNull()
  })
})

// =============================================================================
// CLEAR FILTERS
// =============================================================================

describe('Database Store - clearFilters', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
    store.queryParams.filters = { status: 'online', zone_id: 'zone_1' }
    store.queryParams.page = 3
  })

  it('removes filters from queryParams', async () => {
    const store = useDatabaseStore()
    expect(store.queryParams.filters).toBeDefined()

    await store.clearFilters()

    expect(store.queryParams.filters).toBeUndefined()
  })

  it('resets page to 1 when clearing filters', async () => {
    const store = useDatabaseStore()
    expect(store.queryParams.page).toBe(3) // Verify precondition

    await store.clearFilters()

    expect(store.queryParams.page).toBe(1)
  })

  it('calls refreshData after clearing filters', async () => {
    const store = useDatabaseStore()

    await store.clearFilters()

    // Verify refreshData was called by checking data is loaded
    expect(store.currentData).not.toBeNull()
  })
})

// =============================================================================
// LOAD RECORD
// =============================================================================

describe('Database Store - loadRecord', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
  })

  it('loads single record successfully', async () => {
    const store = useDatabaseStore()

    await store.loadRecord('uuid-1')

    expect(store.selectedRecord).toEqual({
      success: true,
      table_name: 'esp_devices',
      record: expect.objectContaining({
        id: 'uuid-1',
        esp_id: 'ESP_TEST_001'
      })
    })
    expect(store.error).toBeNull()
  })

  it('does nothing if no currentTable', async () => {
    const store = useDatabaseStore()
    store.currentTable = null

    await store.loadRecord('uuid-1')

    expect(store.selectedRecord).toBeNull()
    expect(store.isLoading).toBe(false)
  })

  it('sets isLoading during loadRecord', async () => {
    const store = useDatabaseStore()

    const loadPromise = store.loadRecord('uuid-1')
    expect(store.isLoading).toBe(true)

    await loadPromise
    expect(store.isLoading).toBe(false)
  })

  it('clears previous error on loadRecord', async () => {
    const store = useDatabaseStore()
    store.error = 'Previous error'

    await store.loadRecord('uuid-1')

    expect(store.error).toBeNull()
  })

  it('sets error on loadRecord failure', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/uuid-999', () => {
        return HttpResponse.json(
          { detail: 'Record not found' },
          { status: 404 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.loadRecord('uuid-999')).rejects.toThrow()
    expect(store.error).toBe('Record not found')
  })

  it('sets generic error message on loadRecord failure without detail', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/uuid-1', () => {
        return HttpResponse.json(
          { error: 'Generic error' },
          { status: 500 }
        )
      })
    )

    const store = useDatabaseStore()

    await expect(store.loadRecord('uuid-1')).rejects.toThrow()
    expect(store.error).toBe('Failed to load record')
  })
})

// =============================================================================
// CLOSE RECORD
// =============================================================================

describe('Database Store - closeRecord', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('sets selectedRecord to null', () => {
    const store = useDatabaseStore()
    store.selectedRecord = {
      success: true,
      table_name: 'esp_devices',
      record: { id: '1', name: 'Test' }
    }

    store.closeRecord()

    expect(store.selectedRecord).toBeNull()
  })

  it('is safe to call when selectedRecord already null', () => {
    const store = useDatabaseStore()
    expect(store.selectedRecord).toBeNull()

    store.closeRecord()

    expect(store.selectedRecord).toBeNull()
  })
})

// =============================================================================
// RESET
// =============================================================================

describe('Database Store - reset', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')
    await store.loadRecord('uuid-1')
    store.error = 'Some error'
    store.queryParams = {
      page: 5,
      page_size: 100,
      sort_by: 'name',
      sort_order: 'asc',
      filters: { status: 'online' }
    }
  })

  it('resets currentTable to null', () => {
    const store = useDatabaseStore()
    expect(store.currentTable).not.toBeNull()

    store.reset()

    expect(store.currentTable).toBeNull()
  })

  it('resets currentSchema to null', () => {
    const store = useDatabaseStore()
    expect(store.currentSchema).not.toBeNull()

    store.reset()

    expect(store.currentSchema).toBeNull()
  })

  it('resets currentData to null', () => {
    const store = useDatabaseStore()
    expect(store.currentData).not.toBeNull()

    store.reset()

    expect(store.currentData).toBeNull()
  })

  it('resets selectedRecord to null', () => {
    const store = useDatabaseStore()
    expect(store.selectedRecord).not.toBeNull()

    store.reset()

    expect(store.selectedRecord).toBeNull()
  })

  it('resets queryParams to defaults', () => {
    const store = useDatabaseStore()
    expect(store.queryParams.page).not.toBe(1)

    store.reset()

    expect(store.queryParams).toEqual({
      page: 1,
      page_size: 50,
      sort_order: 'desc'
    })
  })

  it('clears error', () => {
    const store = useDatabaseStore()
    expect(store.error).not.toBeNull()

    store.reset()

    expect(store.error).toBeNull()
  })

  it('does not reset tables array', () => {
    const store = useDatabaseStore()
    const tables = store.tables
    expect(tables.length).toBeGreaterThan(0)

    store.reset()

    expect(store.tables).toBe(tables)
  })
})

// =============================================================================
// CLEAR ERROR
// =============================================================================

describe('Database Store - clearError', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('sets error to null', () => {
    const store = useDatabaseStore()
    store.error = 'Some error message'

    store.clearError()

    expect(store.error).toBeNull()
  })

  it('is safe to call when error already null', () => {
    const store = useDatabaseStore()
    expect(store.error).toBeNull()

    store.clearError()

    expect(store.error).toBeNull()
  })
})

// =============================================================================
// ERROR HANDLING - ISLOADING LIFECYCLE
// =============================================================================

describe('Database Store - Error Handling', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('ensures isLoading is false after loadTables success', async () => {
    const store = useDatabaseStore()

    await store.loadTables()

    expect(store.isLoading).toBe(false)
  })

  it('ensures isLoading is false after loadTables error', async () => {
    server.use(
      http.get('/api/v1/debug/db/tables', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 500 })
      })
    )

    const store = useDatabaseStore()

    try {
      await store.loadTables()
    } catch {
      // Expected
    }

    expect(store.isLoading).toBe(false)
  })

  it('ensures isLoading is false after selectTable success', async () => {
    const store = useDatabaseStore()
    await store.loadTables()

    await store.selectTable('esp_devices')

    expect(store.isLoading).toBe(false)
  })

  it('ensures isLoading is false after selectTable error', async () => {
    server.use(
      http.get('/api/v1/debug/db/esp_devices/schema', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 500 })
      })
    )

    const store = useDatabaseStore()
    await store.loadTables()

    try {
      await store.selectTable('esp_devices')
    } catch {
      // Expected
    }

    expect(store.isLoading).toBe(false)
  })

  it('ensures isLoading is false after refreshData success', async () => {
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')

    await store.refreshData()

    expect(store.isLoading).toBe(false)
  })

  it('ensures isLoading is false after refreshData error', async () => {
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')

    server.use(
      http.get('/api/v1/debug/db/esp_devices', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 500 })
      })
    )

    try {
      await store.refreshData()
    } catch {
      // Expected
    }

    expect(store.isLoading).toBe(false)
  })

  it('ensures isLoading is false after loadRecord success', async () => {
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')

    await store.loadRecord('uuid-1')

    expect(store.isLoading).toBe(false)
  })

  it('ensures isLoading is false after loadRecord error', async () => {
    const store = useDatabaseStore()
    await store.loadTables()
    await store.selectTable('esp_devices')

    server.use(
      http.get('/api/v1/debug/db/esp_devices/uuid-1', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 404 })
      })
    )

    try {
      await store.loadRecord('uuid-1')
    } catch {
      // Expected
    }

    expect(store.isLoading).toBe(false)
  })
})
