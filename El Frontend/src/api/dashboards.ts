/**
 * Dashboard Layout API Client
 *
 * CRUD operations for server-persisted dashboards.
 * Server endpoint: /api/v1/dashboards (see El Servador dashboards.py)
 *
 * Response format follows BaseResponse pattern:
 * { success: boolean, data: ..., message?: string, pagination?: ... }
 */

import api from './index'

/** Widget config as sent to/from server */
export interface DashboardWidgetDTO {
  id: string
  type: string
  x: number
  y: number
  w: number
  h: number
  config: Record<string, unknown>
}

/** Server dashboard response */
export interface DashboardDTO {
  id: string
  name: string
  description: string | null
  owner_id: number
  is_shared: boolean
  widgets: DashboardWidgetDTO[]
  scope: string | null
  zone_id: string | null
  auto_generated: boolean
  sensor_id: string | null
  target: Record<string, unknown> | null
  created_at: string | null
  updated_at: string | null
}

/** Paginated list response */
interface DashboardListResponse {
  success: boolean
  data: DashboardDTO[]
  pagination: {
    page: number
    page_size: number
    total_items: number
    total_pages: number
  } | null
}

/** Single dashboard response */
interface DashboardDataResponse {
  success: boolean
  data: DashboardDTO | null
  message?: string
}

/** Create request payload */
export interface DashboardCreatePayload {
  name: string
  description?: string
  widgets?: DashboardWidgetDTO[]
  is_shared?: boolean
  scope?: 'zone' | 'zone-tile' | 'cross-zone' | 'sensor-detail'
  zone_id?: string
  auto_generated?: boolean
  sensor_id?: string
  target?: Record<string, unknown> | null
}

/** Update request payload (all fields optional) */
export interface DashboardUpdatePayload {
  name?: string
  description?: string
  widgets?: DashboardWidgetDTO[]
  is_shared?: boolean
  scope?: 'zone' | 'zone-tile' | 'cross-zone' | 'sensor-detail'
  zone_id?: string
  auto_generated?: boolean
  sensor_id?: string
  target?: Record<string, unknown> | null
}

export const dashboardsApi = {
  /** List all dashboards visible to current user */
  async list(page = 1, pageSize = 50): Promise<DashboardListResponse> {
    const response = await api.get<DashboardListResponse>('/dashboards', {
      params: { page, page_size: pageSize },
    })
    return response.data
  },

  /** Get a single dashboard by ID */
  async get(dashboardId: string): Promise<DashboardDataResponse> {
    const response = await api.get<DashboardDataResponse>(`/dashboards/${dashboardId}`)
    return response.data
  },

  /** Create a new dashboard */
  async create(payload: DashboardCreatePayload): Promise<DashboardDataResponse> {
    const response = await api.post<DashboardDataResponse>('/dashboards', payload)
    return response.data
  },

  /** Update an existing dashboard */
  async update(dashboardId: string, payload: DashboardUpdatePayload): Promise<DashboardDataResponse> {
    const response = await api.put<DashboardDataResponse>(`/dashboards/${dashboardId}`, payload)
    return response.data
  },

  /** Delete a dashboard */
  async delete(dashboardId: string): Promise<DashboardDataResponse> {
    const response = await api.delete<DashboardDataResponse>(`/dashboards/${dashboardId}`)
    return response.data
  },
}
