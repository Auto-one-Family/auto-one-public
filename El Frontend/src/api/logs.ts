/**
 * Log Viewer API
 *
 * Provides methods to interact with server log endpoints.
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL'

export interface LogEntry {
  timestamp: string
  level: LogLevel
  logger: string
  message: string
  module?: string
  function?: string
  line?: number
  exception?: string
  request_id?: string
  extra?: Record<string, unknown>
}

export interface LogsResponse {
  success: boolean
  logs: LogEntry[]
  total_count: number
  page: number
  page_size: number
  has_more: boolean
}

export interface LogFile {
  name: string
  path: string
  size_bytes: number
  size_human: string
  modified: string
  is_current: boolean
}

export interface LogFilesResponse {
  success: boolean
  files: LogFile[]
  log_directory: string
}

export interface LogQueryParams {
  level?: LogLevel
  module?: string
  search?: string
  start_time?: string
  end_time?: string
  request_id?: string
  file?: string
  page?: number
  page_size?: number
}

// Log Management Types
export interface LogFileInfo {
  name: string
  size_mb: number
  size_bytes: number
  modified_at: string
  entry_count: number | null
  is_current: boolean
}

export interface LogStatisticsResponse {
  success: boolean
  total_size_mb: number
  total_size_bytes: number
  file_count: number
  files: LogFileInfo[]
}

export interface LogCleanupResponse {
  success: boolean
  dry_run: boolean
  files_to_delete: string[]
  total_size_mb: number
  deleted_count: number
  backup_url: string | null
}

export interface LogDeleteResponse {
  success: boolean
  deleted: boolean
  filename: string
  size_mb: number
  backup_url: string | null
}

// =============================================================================
// API Functions
// =============================================================================

export const logsApi = {
  /**
   * Get list of available log files
   */
  async listFiles(): Promise<LogFilesResponse> {
    const response = await api.get<LogFilesResponse>('/debug/logs/files')
    return response.data
  },

  /**
   * Query logs with filtering and pagination
   */
  async queryLogs(params: LogQueryParams = {}): Promise<LogsResponse> {
    const queryParams = new URLSearchParams()

    if (params.level) queryParams.set('level', params.level)
    if (params.module) queryParams.set('module', params.module)
    if (params.search) queryParams.set('search', params.search)
    if (params.start_time) queryParams.set('start_time', params.start_time)
    if (params.end_time) queryParams.set('end_time', params.end_time)
    if (params.request_id) queryParams.set('request_id', params.request_id)
    if (params.file) queryParams.set('file', params.file)
    if (params.page) queryParams.set('page', params.page.toString())
    if (params.page_size) queryParams.set('page_size', params.page_size.toString())

    const query = queryParams.toString()
    const url = `/debug/logs${query ? '?' + query : ''}`

    const response = await api.get<LogsResponse>(url)
    return response.data
  },

  /**
   * Get log file statistics (sizes, counts)
   */
  async getStatistics(): Promise<LogStatisticsResponse> {
    const response = await api.get<LogStatisticsResponse>('/debug/logs/statistics')
    return response.data
  },

  /**
   * Cleanup log files with dry-run support
   */
  async cleanup(params: {
    dryRun?: boolean
    files?: string[]
    createBackup?: boolean
  } = {}): Promise<LogCleanupResponse> {
    const queryParams = new URLSearchParams()
    if (params.dryRun !== undefined) queryParams.set('dry_run', params.dryRun.toString())
    if (params.createBackup !== undefined) queryParams.set('create_backup', params.createBackup.toString())
    if (params.files) {
      params.files.forEach(f => queryParams.append('files', f))
    }

    const query = queryParams.toString()
    const response = await api.post<LogCleanupResponse>(`/debug/logs/cleanup${query ? '?' + query : ''}`)
    return response.data
  },

  /**
   * Delete a single log file
   */
  async deleteFile(filename: string, createBackup = false): Promise<LogDeleteResponse> {
    const queryParams = new URLSearchParams()
    if (createBackup) queryParams.set('create_backup', 'true')
    const query = queryParams.toString()

    const response = await api.delete<LogDeleteResponse>(
      `/debug/logs/${encodeURIComponent(filename)}${query ? '?' + query : ''}`
    )
    return response.data
  },

  /**
   * Get backup download URL
   */
  getBackupDownloadUrl(backupUrl: string): string {
    return `${api.defaults.baseURL}${backupUrl}`
  },
}

export default logsApi
