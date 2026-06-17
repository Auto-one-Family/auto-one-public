/**
 * Audit Log API Client
 * 
 * Provides access to audit log endpoints:
 * - List and filter audit logs
 * - Get statistics and error rates
 * - Manage retention policies
 * - Run manual cleanup
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface AuditLog {
  id: string
  event_type: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  source_type: string
  source_id: string | null
  status: string
  message: string | null
  details: Record<string, unknown>
  error_code: string | null
  error_description: string | null
  ip_address: string | null
  correlation_id: string | null
  request_id: string | null
  created_at: string
}

export interface AuditLogListResponse {
  data: AuditLog[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface AuditLogFilters {
  event_type?: string
  severity?: string
  source_type?: string
  source_id?: string
  status?: string
  error_code?: string
  start_time?: string
  end_time?: string
  hours?: number
  page?: number
  page_size?: number
}

export interface RetentionConfig {
  enabled: boolean
  default_days: number
  severity_days: Record<string, number>
  max_records: number
  batch_size: number
  preserve_emergency_stops: boolean
  last_cleanup: string | null
}

export interface RetentionConfigUpdate {
  enabled?: boolean
  default_days?: number
  severity_days?: Record<string, number>
  max_records?: number
  batch_size?: number
  preserve_emergency_stops?: boolean
}

export interface CleanupPreviewEvent {
  id: string  // UUID as string
  event_type: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  message: string
  device_id: string | null
  created_at: string | null
}

export interface CleanupResult {
  deleted_count: number
  deleted_by_severity: Record<string, number>
  duration_ms: number
  dry_run: boolean
  errors: string[]
  retention_enabled?: boolean
  backup_id?: string | null
  skipped?: boolean
  reason?: string
  preview_events?: CleanupPreviewEvent[]
  preview_limited?: boolean
}

export interface BackupInfo {
  backup_id: string
  created_at: string
  expires_at: string | null  // null = never expires
  expired: boolean
  event_count: number
  metadata: Record<string, unknown>
}

/**
 * Backup retention configuration
 */
export interface BackupRetentionConfig {
  retention_days: number  // 0 = never expire
  max_backups: number
  max_retention_days: number
  never_expire_value: number  // Always 0
}

/**
 * Backup retention configuration update request
 */
export interface BackupRetentionConfigUpdate {
  retention_days: number  // 0-365, 0 = never expire
}

export interface BackupListResponse {
  backups: BackupInfo[]
  total: number
}

export interface BackupRestoreResult {
  backup_id: string
  restored_count: number
  skipped_duplicates: number
  total_in_backup: number
  backup_deleted: boolean
  restored_event_ids: string[]
}

export interface AuditStatistics {
  total_count: number
  count_by_severity: Record<string, number>
  count_by_event_type: Record<string, number>
  oldest_entry: string | null
  newest_entry: string | null
  storage_estimate_mb: number
  pending_cleanup_count: number
  pending_cleanup_by_severity: Record<string, number>
  retention_config: RetentionConfig
}

/**
 * Data source types for event aggregation
 */
export type DataSource = 'audit_log' | 'sensor_data' | 'esp_health' | 'actuators'

/**
 * Unified event from aggregated sources
 */
export interface UnifiedEventFromAPI {
  id: string
  timestamp: string
  source: string
  category: string
  title: string
  message: string
  severity: 'info' | 'warning' | 'error' | 'critical'
  device_id: string | null
  metadata: Record<string, unknown>
}

/**
 * Count information for a single data source
 */
export interface SourceCounts {
  loaded: number
  available: number
}

/**
 * Pagination information for cursor-based infinite scroll
 */
export interface PaginationInfo {
  has_more: boolean
  oldest_timestamp: string | null
  total_available: number
}

/**
 * Response for aggregated events
 */
export interface AggregatedEventsResponse {
  events: UnifiedEventFromAPI[]
  total_loaded: number
  total_available: number
  source_counts: Record<DataSource, SourceCounts>
  sources: DataSource[]
  time_range_hours: number
  limit_per_source: number
  pagination: PaginationInfo
}

export interface ErrorRate {
  period_hours: number
  total_events: number
  error_events: number
  error_rate_percent: number
}

export interface EventTypeInfo {
  value: string
  description: string
  category: string
}

export interface SeverityInfo {
  value: string
  description: string
  color: string
}

/**
 * Time range options for statistics error count filter
 */
export type StatisticsTimeRange = '24h' | '7d' | '30d' | 'all'

/**
 * Preview of what the next auto-cleanup would delete
 */
export interface NextCleanupPreview {
  would_delete: number
  breakdown: Record<string, number>
}

/**
 * Auto-cleanup system status for UI transparency
 */
export interface AutoCleanupStatus {
  enabled: boolean
  last_run: string | null
  next_run: string | null
  schedule: string
  config: RetentionConfig
  next_cleanup_preview: NextCleanupPreview
}

// =============================================================================
// API Functions
// =============================================================================

export const auditApi = {
  /**
   * List audit logs with filters
   */
  async list(filters: AuditLogFilters = {}): Promise<AuditLogListResponse> {
    const params = new URLSearchParams()

    if (filters.event_type) params.append('event_type', filters.event_type)
    if (filters.severity) params.append('severity', filters.severity)
    if (filters.source_type) params.append('source_type', filters.source_type)
    if (filters.source_id) params.append('source_id', filters.source_id)
    if (filters.status) params.append('status', filters.status)
    if (filters.error_code) params.append('error_code', filters.error_code)
    if (filters.start_time) params.append('start_time', filters.start_time)
    if (filters.end_time) params.append('end_time', filters.end_time)
    if (filters.hours) params.append('hours', filters.hours.toString())
    if (filters.page) params.append('page', filters.page.toString())
    if (filters.page_size) params.append('page_size', filters.page_size.toString())

    const response = await api.get<AuditLogListResponse>(
      `/audit?${params.toString()}`
    )
    return response.data
  },

  /**
   * Get aggregated events from multiple data sources
   *
   * @param options.sources - Data sources to aggregate (default: ['audit_log'])
   * @param options.hours - Time range in hours (default: 6). Set to `null` to load ALL events.
   * @param options.limitPerSource - Maximum events per source (default: 500)
   * @param options.severity - Filter by severity levels (only applies to audit_log source)
   * @param options.espIds - Filter by ESP device IDs
   * @param options.beforeTimestamp - Cursor for pagination: load events BEFORE this timestamp
   */
  async getAggregatedEvents(options: {
    sources?: DataSource[]
    hours?: number | null
    limitPerSource?: number
    severity?: string[]
    espIds?: string[]
    beforeTimestamp?: string
  } = {}): Promise<AggregatedEventsResponse> {
    const params = new URLSearchParams()

    // Add sources as separate query params (FastAPI expects repeated params for lists)
    const sources = options.sources ?? ['audit_log']
    sources.forEach(source => {
      params.append('sources', source)
    })

    // Add hours only if specified (null or undefined = load all events)
    if (options.hours !== null && options.hours !== undefined) {
      params.append('hours', options.hours.toString())
    }

    if (options.limitPerSource) {
      params.append('limit_per_source', options.limitPerSource.toString())
    }

    // Add severity filter (only applies to audit_log source on server)
    if (options.severity && options.severity.length > 0) {
      options.severity.forEach(sev => {
        params.append('severity', sev)
      })
    }

    // Add ESP-ID filter
    if (options.espIds && options.espIds.length > 0) {
      options.espIds.forEach(id => {
        params.append('esp_ids', id)
      })
    }

    // Add pagination cursor (for infinite scroll)
    if (options.beforeTimestamp) {
      params.append('before_timestamp', options.beforeTimestamp)
    }

    const response = await api.get<AggregatedEventsResponse>(
      `/audit/events/aggregated?${params.toString()}`
    )
    return response.data
  },

  /**
   * Get all events with the same correlation_id.
   * Enables tracking of related events (e.g., config_published → config_response).
   */
  async getCorrelatedEvents(correlationId: string, limit: number = 50): Promise<AuditLog[]> {
    // Backend validates limit <= 200 (FastAPI Query constraint).
    // Clamp defensively to prevent 422s from UI callers.
    const safeLimit = Math.max(1, Math.min(200, Math.floor(limit)))
    const response = await api.get<AuditLog[]>(
      `/audit/events/correlated/${encodeURIComponent(correlationId)}?limit=${safeLimit}`
    )
    return response.data
  },

  /**
   * Get recent errors
   */
  async getErrors(hours: number = 24, limit: number = 100): Promise<AuditLog[]> {
    const response = await api.get<AuditLog[]>(
      `/audit/errors?hours=${hours}&limit=${limit}`
    )
    return response.data
  },

  /**
   * Get config history for ESP device
   */
  async getEspConfigHistory(espId: string, limit: number = 50): Promise<AuditLog[]> {
    const response = await api.get<AuditLog[]>(
      `/audit/esp/${espId}/config-history?limit=${limit}`
    )
    return response.data
  },

  /**
   * Get audit statistics
   *
   * @param timeRange - Filter for error counts: 24h, 7d, 30d, or all (default: 24h)
   */
  async getStatistics(timeRange: StatisticsTimeRange = '24h'): Promise<AuditStatistics> {
    const response = await api.get<AuditStatistics>(`/audit/statistics?time_range=${timeRange}`)
    return response.data
  },

  /**
   * Get error rate for period
   */
  async getErrorRate(hours: number = 24): Promise<ErrorRate> {
    const response = await api.get<ErrorRate>(`/audit/error-rate?hours=${hours}`)
    return response.data
  },

  /**
   * Get auto-cleanup system status
   *
   * Returns complete status including:
   * - enabled: Is auto-cleanup activated?
   * - last_run: When was the last cleanup?
   * - next_run: When is the next cleanup scheduled?
   * - config: Current retention configuration
   * - next_cleanup_preview: What would be deleted in next run?
   */
  async getRetentionStatus(): Promise<AutoCleanupStatus> {
    const response = await api.get<AutoCleanupStatus>('/audit/retention/status')
    return response.data
  },

  /**
   * Get retention config
   */
  async getRetentionConfig(): Promise<RetentionConfig> {
    const response = await api.get<RetentionConfig>('/audit/retention/config')
    return response.data
  },

  /**
   * Update retention config
   */
  async updateRetentionConfig(config: RetentionConfigUpdate): Promise<RetentionConfig> {
    const response = await api.put<RetentionConfig>('/audit/retention/config', config)
    return response.data
  },

  /**
   * Run retention cleanup
   *
   * @param options.dryRun - Preview only, don't delete
   * @param options.includePreviewEvents - Include event details in preview
   * @param options.previewLimit - Maximum events to include in preview (1-100)
   */
  async runCleanup(options: {
    dryRun?: boolean
    includePreviewEvents?: boolean
    previewLimit?: number
  } = {}): Promise<CleanupResult> {
    const params = new URLSearchParams()
    params.append('dry_run', String(options.dryRun ?? false))
    if (options.includePreviewEvents) {
      params.append('include_preview_events', 'true')
    }
    if (options.previewLimit) {
      params.append('preview_limit', String(options.previewLimit))
    }
    const response = await api.post<CleanupResult>(
      `/audit/retention/cleanup?${params.toString()}`
    )
    return response.data
  },

  /**
   * Get available event types
   */
  async getEventTypes(): Promise<EventTypeInfo[]> {
    const response = await api.get<EventTypeInfo[]>('/audit/event-types')
    return response.data
  },

  /**
   * Get available severities
   */
  async getSeverities(): Promise<SeverityInfo[]> {
    const response = await api.get<SeverityInfo[]>('/audit/severities')
    return response.data
  },

  /**
   * Get available source types
   */
  async getSourceTypes(): Promise<string[]> {
    const response = await api.get<string[]>('/audit/source-types')
    return response.data
  },

  // =========================================================================
  // Backup Management
  // =========================================================================

  /**
   * List available backups
   */
  async listBackups(includeExpired: boolean = false): Promise<BackupListResponse> {
    const response = await api.get<BackupListResponse>(
      `/audit/backups?include_expired=${includeExpired}`
    )
    return response.data
  },

  /**
   * Get backup details
   */
  async getBackup(backupId: string): Promise<BackupInfo> {
    const response = await api.get<BackupInfo>(`/audit/backups/${backupId}`)
    return response.data
  },

  /**
   * Restore events from backup
   *
   * @param backupId - The backup ID to restore
   * @param deleteAfterRestore - Whether to delete the backup after successful restore (default: true)
   *
   * When deleteAfterRestore is true (default), the backup file is automatically
   * deleted after successful restoration. The restored events will have metadata
   * marking them as restored, and the frontend will be notified via WebSocket.
   */
  async restoreBackup(
    backupId: string,
    deleteAfterRestore: boolean = true
  ): Promise<BackupRestoreResult> {
    const params = new URLSearchParams()
    params.append('delete_after_restore', String(deleteAfterRestore))

    const response = await api.post<BackupRestoreResult>(
      `/audit/backups/${backupId}/restore?${params.toString()}`
    )
    return response.data
  },

  /**
   * Delete a backup
   */
  async deleteBackup(backupId: string): Promise<{ deleted: boolean; backup_id: string }> {
    const response = await api.delete<{ deleted: boolean; backup_id: string }>(
      `/audit/backups/${backupId}`
    )
    return response.data
  },

  /**
   * Cleanup expired backups
   */
  async cleanupExpiredBackups(): Promise<{ deleted_count: number; message: string }> {
    const response = await api.post<{ deleted_count: number; message: string }>(
      '/audit/backups/cleanup'
    )
    return response.data
  },

  // =========================================================================
  // Backup Retention Configuration
  // =========================================================================

  /**
   * Get backup retention configuration
   */
  async getBackupRetentionConfig(): Promise<BackupRetentionConfig> {
    const response = await api.get<BackupRetentionConfig>(
      '/audit/backups/retention/config'
    )
    return response.data
  },

  /**
   * Update backup retention configuration
   *
   * @param config.retention_days - Days until backup expires (0 = never expire, max 365)
   *
   * Note: This affects only NEW backups. Existing backups keep their original expiration.
   */
  async updateBackupRetentionConfig(
    config: BackupRetentionConfigUpdate
  ): Promise<BackupRetentionConfig> {
    const response = await api.put<BackupRetentionConfig>(
      '/audit/backups/retention/config',
      config
    )
    return response.data
  },
}

export default auditApi


















