/**
 * Zone Assignment API Client
 *
 * Provides methods for zone assignment operations with the backend.
 * Follows the same patterns as other API clients (sensors.ts, actuators.ts).
 */

import api from './index'
import type {
  ZoneAssignRequest, ZoneAssignResponse, ZoneRemoveResponse, ZoneInfo, ZoneListResponse,
  ZoneEntity, ZoneEntityCreate, ZoneEntityUpdate, ZoneEntityListResponse, ZoneStatus,
} from '@/types'
import type { ZoneMonitorData } from '@/types/monitor'

/**
 * Zone Assignment API client
 */
export const zonesApi = {
  /**
   * Get all zones including empty ones (from ZoneContext table).
   * Used by MonitorView L1 to show zones without devices.
   */
  async getAllZones(): Promise<ZoneListResponse> {
    const response = await api.get<ZoneListResponse>('/zone/zones')
    return response.data
  },

  /**
   * Assign ESP to a zone
   *
   * Sends zone assignment request to server, which publishes via MQTT to ESP.
   * ESP confirmation comes asynchronously via WebSocket zone_assignment event.
   */
  async assignZone(
    deviceId: string,
    request: ZoneAssignRequest
  ): Promise<ZoneAssignResponse> {
    const response = await api.post<ZoneAssignResponse>(
      `/zone/devices/${deviceId}/assign`,
      request
    )
    return response.data
  },

  /**
   * Remove zone assignment from ESP
   *
   * Sends empty zone assignment to ESP to clear its configuration.
   */
  async removeZone(deviceId: string): Promise<ZoneRemoveResponse> {
    const response = await api.delete<ZoneRemoveResponse>(
      `/zone/devices/${deviceId}/zone`
    )
    return response.data
  },

  /**
   * Get zone information for an ESP
   */
  async getZoneInfo(deviceId: string): Promise<ZoneInfo> {
    const response = await api.get<ZoneInfo>(`/zone/devices/${deviceId}`)
    return response.data
  },

  /**
   * Get all ESPs in a specific zone
   */
  async getZoneDevices(zoneId: string): Promise<ZoneInfo[]> {
    const response = await api.get<ZoneInfo[]>(`/zone/${zoneId}/devices`)
    return response.data
  },

  /**
   * Get all unassigned ESPs (without zone_id)
   */
  async getUnassignedDevices(): Promise<string[]> {
    const response = await api.get<string[]>('/zone/unassigned')
    return response.data
  },

  /**
   * Get zone monitor data for L2 display (sensors/actuators grouped by subzone).

   * Used by MonitorView L2 for subzone accordion. GPIO-based grouping via subzone_configs.
   */
  async getZoneMonitorData(zoneId: string, signal?: AbortSignal): Promise<ZoneMonitorData> {
    const response = await api.get<ZoneMonitorData>(`/zone/${zoneId}/monitor-data`, { signal })
    return response.data
  },

  // ===========================================================================
  // Zone Entity CRUD (T13-R1) — /api/v1/zones
  // NOTE: Separate from /api/v1/zone/ (device assignment, MQTT bridge)
  // ===========================================================================

  /**
   * Create a new zone entity.
   */
  async createZoneEntity(data: ZoneEntityCreate): Promise<ZoneEntity> {
    const response = await api.post<ZoneEntity>('/zones', data)
    return response.data
  },

  /**
   * List zone entities, optionally filtered by status.
   */
  async listZoneEntities(status?: ZoneStatus): Promise<ZoneEntityListResponse> {
    const params = status ? { status } : undefined
    const response = await api.get<ZoneEntityListResponse>('/zones', { params })
    return response.data
  },

  /**
   * Get a single zone entity by zone_id.
   */
  async getZoneEntity(zoneId: string): Promise<ZoneEntity> {
    const response = await api.get<ZoneEntity>(`/zones/${zoneId}`)
    return response.data
  },

  /**
   * Update zone entity name/description.
   */
  async updateZoneEntity(zoneId: string, data: ZoneEntityUpdate): Promise<ZoneEntity> {
    const response = await api.patch<ZoneEntity>(`/zones/${zoneId}`, data)
    return response.data
  },

  /**
   * Archive a zone (soft-delete, status → 'archived').
   */
  async archiveZoneEntity(zoneId: string): Promise<ZoneEntity> {
    const response = await api.post<ZoneEntity>(`/zones/${zoneId}/archive`)
    return response.data
  },

  /**
   * Reactivate an archived zone (status → 'active').
   */
  async reactivateZoneEntity(zoneId: string): Promise<ZoneEntity> {
    const response = await api.post<ZoneEntity>(`/zones/${zoneId}/reactivate`)
    return response.data
  },

  /**
   * Delete a zone entity (server-side soft-delete).
   */
  async deleteZoneEntity(zoneId: string): Promise<{ success: boolean; message: string }> {
    const response = await api.delete<{ success: boolean; message: string }>(`/zones/${zoneId}`)
    return response.data
  },
}

















