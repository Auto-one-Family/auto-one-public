/**
 * Notifications API Client
 *
 * Handles notification inbox, preferences, and test-email endpoints.
 * Server endpoints: /v1/notifications/*
 *
 * @see El Servador/god_kaiser_server/src/api/v1/notifications.py
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export type NotificationSeverity = 'critical' | 'warning' | 'info'
export type AlertStatus = 'active' | 'acknowledged' | 'resolved'
export type NotificationCategory =
  | 'connectivity'
  | 'data_quality'
  | 'infrastructure'
  | 'lifecycle'
  | 'maintenance'
  | 'security'
  | 'system'
  | 'ai_anomaly'
export type NotificationSource =
  | 'logic_engine'
  | 'mqtt_handler'
  | 'grafana'
  | 'sensor_threshold'
  | 'device_event'
  | 'autoops'
  | 'manual'
  | 'system'
  | 'ai_anomaly_service'
  | 'freshness_reminder'
  | 'calibration_reminder'

export interface NotificationDTO {
  id: string
  user_id: number
  channel: string
  severity: NotificationSeverity
  category: NotificationCategory
  title: string
  body: string | null
  metadata: Record<string, unknown>
  source: NotificationSource
  is_read: boolean
  is_archived: boolean
  digest_sent: boolean
  parent_notification_id: string | null
  fingerprint: string | null
  created_at: string | null
  updated_at: string | null
  read_at: string | null
  // Phase 4B: Alert lifecycle fields
  status: AlertStatus
  acknowledged_at: string | null
  acknowledged_by: number | null
  resolved_at: string | null
  correlation_id: string | null
}

export interface NotificationListFilters {
  severity?: NotificationSeverity
  category?: NotificationCategory
  source?: NotificationSource
  /** Grouped sources: system = manual|system|device_event|autoops (server-side, AUT-196) */
  source_bucket?: 'system'
  status?: AlertStatus
  is_read?: boolean
  /** When true, list includes ISA-18.2 audit rows with channel=suppressed */
  show_suppressed?: boolean
  page?: number
  page_size?: number
}

export interface PaginationMeta {
  page: number
  page_size: number
  total_items: number
  total_pages: number
}

export interface NotificationListResponse {
  success: boolean
  data: NotificationDTO[]
  pagination: PaginationMeta
}

export interface NotificationUnreadCountResponse {
  success: boolean
  unread_count: number
  highest_severity: NotificationSeverity | null
}

export interface NotificationSendRequest {
  title: string
  body?: string
  severity?: NotificationSeverity
  category?: NotificationCategory
  source?: NotificationSource
  channel?: string
  metadata?: Record<string, unknown>
}

export interface NotificationPreferencesDTO {
  user_id: number
  websocket_enabled: boolean
  email_enabled: boolean
  email_address: string | null
  email_severities: string[]
  quiet_hours_enabled: boolean
  quiet_hours_start: string | null
  quiet_hours_end: string | null
  digest_interval_minutes: number
  browser_notifications: boolean
  created_at: string | null
  updated_at: string | null
}

export interface NotificationPreferencesUpdate {
  websocket_enabled?: boolean
  email_enabled?: boolean
  email_address?: string | null
  email_severities?: string[]
  quiet_hours_enabled?: boolean
  quiet_hours_start?: string | null
  quiet_hours_end?: string | null
  digest_interval_minutes?: number
  browser_notifications?: boolean
}

export interface TestEmailRequest {
  email?: string | null
}

export interface TestEmailResponse {
  success: boolean
  message: string
  provider: string | null
  recipient: string | null
}

// Phase C V1.1: Email log types (V1.2: permanently_failed)
export type EmailLogStatus = 'sent' | 'failed' | 'pending' | 'permanently_failed'

export interface EmailLogEntry {
  id: string
  notification_id: string | null
  to_address: string
  subject: string
  template: string | null
  provider: string
  status: EmailLogStatus
  sent_at: string | null
  error_message: string | null
  retry_count: number
  created_at: string | null
}

export interface EmailLogListResponse {
  success: boolean
  data: EmailLogEntry[]
  pagination: PaginationMeta
}

export interface EmailLogListFilters {
  status?: EmailLogStatus
  date_from?: string
  date_to?: string
  template?: string
  page?: number
  page_size?: number
}

export interface EmailLogStatsDTO {
  success: boolean
  total: number
  sent: number
  failed: number
  by_status: Record<string, number>
  by_provider: Record<string, number>
}

// Phase 4B: Alert lifecycle types
export interface AlertActiveListFilters {
  severity?: NotificationSeverity
  category?: NotificationCategory
  status?: AlertStatus
  page?: number
  page_size?: number
}

export interface AlertStatsDTO {
  success: boolean
  active_count: number
  acknowledged_count: number
  resolved_today_count: number
  critical_active: number
  warning_active: number
  mean_time_to_acknowledge_s: number | null
  mean_time_to_resolve_s: number | null
}

export interface AlertBulkResolveResponse {
  success: boolean
  message: string
  resolved_count: number
}

// =============================================================================
// Notifications API
// =============================================================================

export const notificationsApi = {
  /**
   * List notifications with optional filters
   */
  async list(filters?: NotificationListFilters): Promise<NotificationListResponse> {
    const response = await api.get<NotificationListResponse>('/notifications', {
      params: filters,
    })
    return response.data
  },

  /**
   * Get unread notification count (for badge)
   */
  async getUnreadCount(): Promise<NotificationUnreadCountResponse> {
    const response = await api.get<NotificationUnreadCountResponse>(
      '/notifications/unread-count',
    )
    return response.data
  },

  /**
   * Get a single notification by ID
   */
  async getById(id: string): Promise<NotificationDTO> {
    const response = await api.get<NotificationDTO>(`/notifications/${id}`)
    return response.data
  },

  /**
   * Mark a single notification as read
   */
  async markRead(id: string): Promise<NotificationDTO> {
    const response = await api.patch<NotificationDTO>(
      `/notifications/${id}/read`,
    )
    return response.data
  },

  /**
   * Mark all notifications as read
   */
  async markAllRead(): Promise<{ success: boolean; message: string }> {
    const response = await api.patch<{ success: boolean; message: string }>(
      '/notifications/read-all',
    )
    return response.data
  },

  /**
   * Admin: Send a notification manually
   */
  async send(request: NotificationSendRequest): Promise<NotificationDTO> {
    const response = await api.post<NotificationDTO>(
      '/notifications/send',
      request,
    )
    return response.data
  },

  /**
   * Get user notification preferences
   */
  async getPreferences(): Promise<NotificationPreferencesDTO> {
    const response = await api.get<NotificationPreferencesDTO>(
      '/notifications/preferences',
    )
    return response.data
  },

  /**
   * Update user notification preferences
   */
  async updatePreferences(
    prefs: NotificationPreferencesUpdate,
  ): Promise<NotificationPreferencesDTO> {
    const response = await api.put<NotificationPreferencesDTO>(
      '/notifications/preferences',
      prefs,
    )
    return response.data
  },

  /**
   * Send a test email to verify configuration
   */
  async sendTestEmail(request?: TestEmailRequest): Promise<TestEmailResponse> {
    const response = await api.post<TestEmailResponse>(
      '/notifications/test-email',
      request ?? {},
    )
    return response.data
  },

  // =========================================================================
  // Alert Lifecycle (Phase 4B)
  // =========================================================================

  /**
   * Acknowledge an alert (active → acknowledged)
   */
  async acknowledgeAlert(id: string): Promise<NotificationDTO> {
    const response = await api.patch<NotificationDTO>(
      `/notifications/${id}/acknowledge`,
    )
    return response.data
  },

  /**
   * Resolve an alert (active/acknowledged → resolved)
   */
  async resolveAlert(id: string): Promise<NotificationDTO> {
    const response = await api.patch<NotificationDTO>(
      `/notifications/${id}/resolve`,
    )
    return response.data
  },

  /**
   * Resolve all unresolved alerts (active + acknowledged) for current user.
   */
  async resolveAllAlerts(): Promise<AlertBulkResolveResponse> {
    const response = await api.patch<AlertBulkResolveResponse>('/notifications/resolve-all')
    return response.data
  },

  /**
   * Get active alerts with filters
   */
  async getActiveAlerts(filters?: AlertActiveListFilters): Promise<NotificationListResponse> {
    const response = await api.get<NotificationListResponse>(
      '/notifications/alerts/active',
      { params: filters },
    )
    return response.data
  },

  /**
   * Get alert ISA-18.2 statistics (MTTA, MTTR, counts)
   */
  async getAlertStats(): Promise<AlertStatsDTO> {
    const response = await api.get<AlertStatsDTO>('/notifications/alerts/stats')
    return response.data
  },

  // =========================================================================
  // Email Log (Phase C V1.1)
  // =========================================================================

  /**
   * Get paginated email sending log (admin only)
   */
  async getEmailLog(filters?: EmailLogListFilters): Promise<EmailLogListResponse> {
    const response = await api.get<EmailLogListResponse>('/notifications/email-log', {
      params: filters,
    })
    return response.data
  },

  /**
   * Get email sending statistics (admin only)
   */
  async getEmailLogStats(): Promise<EmailLogStatsDTO> {
    const response = await api.get<EmailLogStatsDTO>('/notifications/email-log/stats')
    return response.data
  },
}
