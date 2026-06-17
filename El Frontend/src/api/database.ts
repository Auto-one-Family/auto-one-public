/**
 * Database Explorer API
 * 
 * Provides methods to interact with the database explorer endpoints.
 * Follows the pattern from src/api/debug.ts
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export type SortOrder = 'asc' | 'desc'

export type ColumnType = 'string' | 'integer' | 'float' | 'boolean' | 'datetime' | 'json' | 'uuid'

export interface ColumnSchema {
  name: string            // Technical column name (used for data access)
  label?: string          // Human-readable label (optional, defaults to name)
  type: ColumnType
  nullable: boolean
  primary_key: boolean
  foreign_key?: string | null
}

export interface TableSchema {
  table_name: string
  columns: ColumnSchema[]
  row_count: number
  primary_key: string
}

export interface TableListResponse {
  success: boolean
  tables: TableSchema[]
}

export interface TableDataResponse {
  success: boolean
  table_name: string
  data: Record<string, unknown>[]
  total_count: number
  page: number
  page_size: number
  total_pages: number
}

export interface RecordResponse {
  success: boolean
  table_name: string
  record: Record<string, unknown>
}

export interface TableQueryParams {
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: SortOrder
  filters?: Record<string, unknown>
}

// =============================================================================
// API Functions
// =============================================================================

export const databaseApi = {
  /**
   * Get list of all accessible database tables with metadata
   */
  async listTables(): Promise<TableSchema[]> {
    const response = await api.get<TableListResponse>('/debug/db/tables')
    return response.data.tables
  },

  /**
   * Get detailed schema information for a specific table
   */
  async getTableSchema(tableName: string): Promise<TableSchema> {
    const response = await api.get<TableSchema>(`/debug/db/${tableName}/schema`)
    return response.data
  },

  /**
   * Query data from a database table with pagination, sorting, and filtering
   */
  async queryTable(
    tableName: string,
    params: TableQueryParams = {}
  ): Promise<TableDataResponse> {
    const queryParams = new URLSearchParams()

    if (params.page !== undefined) {
      queryParams.set('page', params.page.toString())
    }
    if (params.page_size !== undefined) {
      queryParams.set('page_size', params.page_size.toString())
    }
    if (params.sort_by) {
      queryParams.set('sort_by', params.sort_by)
    }
    if (params.sort_order) {
      queryParams.set('sort_order', params.sort_order)
    }
    if (params.filters && Object.keys(params.filters).length > 0) {
      queryParams.set('filters', JSON.stringify(params.filters))
    }

    const query = queryParams.toString()
    const url = `/debug/db/${tableName}${query ? '?' + query : ''}`
    
    const response = await api.get<TableDataResponse>(url)
    return response.data
  },

  /**
   * Get a single record from a database table by its primary key
   */
  async getRecord(tableName: string, recordId: string): Promise<RecordResponse> {
    const response = await api.get<RecordResponse>(`/debug/db/${tableName}/${recordId}`)
    return response.data
  }
}

export default databaseApi





















