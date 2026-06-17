/**
 * Inventory API Client — Zone Context Endpoints
 *
 * Provides methods for zone-level business context: plants, variety,
 * substrate, growth phase, cycle management.
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface ZoneContextData {
  id: number
  zone_id: string
  zone_name: string | null
  plant_count: number | null
  variety: string | null
  substrate: string | null
  growth_phase: string | null
  planted_date: string | null
  expected_harvest: string | null
  responsible_person: string | null
  work_hours_weekly: number | null
  notes: string | null
  custom_data: Record<string, unknown>
  cycle_history: CycleEntry[]
  created_at: string
  updated_at: string
  plant_age_days: number | null
  days_to_harvest: number | null
}

export interface CycleEntry {
  variety: string | null
  substrate: string | null
  growth_phase: string | null
  planted_date: string | null
  expected_harvest: string | null
  plant_count: number | null
  notes: string | null
  custom_data: Record<string, unknown>
  archived_at: string
  archived_by: string
  plant_age_days: number | null
}

export interface ZoneContextUpdate {
  zone_name?: string | null
  plant_count?: number | null
  variety?: string | null
  substrate?: string | null
  growth_phase?: string | null
  planted_date?: string | null
  expected_harvest?: string | null
  responsible_person?: string | null
  work_hours_weekly?: number | null
  notes?: string | null
  custom_data?: Record<string, unknown>
}

interface ZoneContextListResponse {
  success: boolean
  data: ZoneContextData[]
  total_count: number
}

interface CycleArchiveResponse {
  success: boolean
  message: string
  zone_id: string
  archived_cycle: CycleEntry
  cycle_number: number
}

interface CycleHistoryResponse {
  success: boolean
  zone_id: string
  cycles: CycleEntry[]
  total_count: number
}

// =============================================================================
// API Client
// =============================================================================

export const inventoryApi = {
  // ── Zone Context ──

  /**
   * Get all zone contexts.
   */
  async listZoneContexts(page = 1, pageSize = 50): Promise<ZoneContextListResponse> {
    const response = await api.get<ZoneContextListResponse>(
      '/zone/context',
      { params: { page, page_size: pageSize } }
    )
    return response.data
  },

  /**
   * Get context for a specific zone.
   */
  async getZoneContext(zoneId: string): Promise<ZoneContextData> {
    const response = await api.get<ZoneContextData>(`/zone/context/${zoneId}`)
    return response.data
  },

  /**
   * Create or update zone context (upsert).
   */
  async upsertZoneContext(zoneId: string, data: ZoneContextUpdate): Promise<ZoneContextData> {
    const response = await api.put<ZoneContextData>(`/zone/context/${zoneId}`, data)
    return response.data
  },

  /**
   * Partial update of zone context.
   */
  async patchZoneContext(zoneId: string, data: Partial<ZoneContextUpdate>): Promise<ZoneContextData> {
    const response = await api.patch<ZoneContextData>(`/zone/context/${zoneId}`, data)
    return response.data
  },

  /**
   * Archive the current growing cycle.
   */
  async archiveCycle(zoneId: string): Promise<CycleArchiveResponse> {
    const response = await api.post<CycleArchiveResponse>(
      `/zone/context/${zoneId}/archive-cycle`
    )
    return response.data
  },

  /**
   * Get cycle history for a zone.
   */
  async getCycleHistory(zoneId: string): Promise<CycleHistoryResponse> {
    const response = await api.get<CycleHistoryResponse>(
      `/zone/context/${zoneId}/history`
    )
    return response.data
  },
}
