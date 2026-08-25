/**
 * Subzone Management API Client
 *
 * Phase: 9 - Subzone Management
 * Status: IMPLEMENTED
 *
 * Provides methods for subzone assignment, removal, queries, and safe-mode control.
 * Follows the same patterns as zones.ts and other API clients.
 */

import api from './index'
import type {
  ActuatorSubzoneAssignRequest,
  ActuatorSubzoneAssignmentInfo,
  ActuatorSubzoneAssignmentsResponse,
  SafeModeRequest,
  SafeModeResponse,
  SensorSubzoneAssignRequest,
  SensorSubzoneAssignmentInfo,
  SensorSubzoneAssignmentsResponse,
  SubzoneAssignRequest,
  SubzoneAssignResponse,
  SubzoneInfo,
  SubzoneListResponse,
  SubzoneRemoveResponse
} from '@/types'

/**
 * Subzone Management API client
 */
export const subzonesApi = {
  // ===========================================================================
  // Subzone Assignment
  // ===========================================================================

  /**
   * Assign GPIO pins to a subzone
   *
   * Sends subzone assignment request to server, which publishes via MQTT to ESP.
   * ESP confirmation comes asynchronously via WebSocket subzone_assignment event.
   *
   * @param deviceId - ESP device ID (e.g., "ESP_AB12CD")
   * @param request - Subzone assignment details
   * @returns SubzoneAssignResponse with MQTT status
   */
  async assignSubzone(
    deviceId: string,
    request: SubzoneAssignRequest
  ): Promise<SubzoneAssignResponse> {
    const response = await api.post<SubzoneAssignResponse>(
      `/subzone/devices/${deviceId}/subzones/assign`,
      request
    )
    return response.data
  },

  /**
   * Remove a subzone from an ESP device
   *
   * Sends subzone removal request to ESP.
   * ESP will set all subzone GPIOs to safe-mode before removal.
   *
   * @param deviceId - ESP device ID
   * @param subzoneId - Subzone ID to remove
   * @returns SubzoneRemoveResponse with MQTT status
   */
  async removeSubzone(
    deviceId: string,
    subzoneId: string
  ): Promise<SubzoneRemoveResponse> {
    const response = await api.delete<SubzoneRemoveResponse>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}`
    )
    return response.data
  },

  // ===========================================================================
  // Subzone Queries
  // ===========================================================================

  /**
   * Get all subzones for an ESP device
   *
   * @param deviceId - ESP device ID
   * @returns SubzoneListResponse with all subzones
   */
  async getSubzones(deviceId: string): Promise<SubzoneListResponse> {
    const response = await api.get<SubzoneListResponse>(
      `/subzone/devices/${deviceId}/subzones`
    )
    return response.data
  },

  /**
   * Get a specific subzone
   *
   * @param deviceId - ESP device ID
   * @param subzoneId - Subzone ID
   * @returns SubzoneInfo or throws 404
   */
  async getSubzone(deviceId: string, subzoneId: string): Promise<SubzoneInfo> {
    const response = await api.get<SubzoneInfo>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}`
    )
    return response.data
  },

  // ===========================================================================
  // Safe-Mode Control
  // ===========================================================================

  /**
   * Enable safe-mode for a subzone
   *
   * All GPIO pins in the subzone will be set to INPUT_PULLUP.
   * All actuators in the subzone will be stopped.
   *
   * @param deviceId - ESP device ID
   * @param subzoneId - Subzone ID
   * @param reason - Reason for enabling safe-mode
   * @returns SafeModeResponse with result
   */
  async enableSafeMode(
    deviceId: string,
    subzoneId: string,
    reason: string = 'manual'
  ): Promise<SafeModeResponse> {
    const request: SafeModeRequest = { reason }
    const response = await api.post<SafeModeResponse>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/safe-mode`,
      request
    )
    return response.data
  },

  /**
   * Disable safe-mode for a subzone
   *
   * WARNING: This allows actuators to be controlled.
   * Ensure the subzone is safe before disabling safe-mode.
   *
   * @param deviceId - ESP device ID
   * @param subzoneId - Subzone ID
   * @param reason - Reason for disabling safe-mode
   * @returns SafeModeResponse with result
   */
  async disableSafeMode(
    deviceId: string,
    subzoneId: string,
    reason: string = 'manual'
  ): Promise<SafeModeResponse> {
    const request: SafeModeRequest = { reason }
    const response = await api.delete<SafeModeResponse>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/safe-mode`,
      { data: request }
    )
    return response.data
  },

  // ===========================================================================
  // Subzone Metadata
  // ===========================================================================

  /**
   * Update subzone-specific metadata (plant info, material, notes).
   * Merges with existing custom_data.
   * AUT-1241: optional position_label (omit to leave unchanged; '' clears).
   */
  async updateMetadata(
    deviceId: string,
    subzoneId: string,
    customData: Record<string, unknown>,
    positionLabel?: string | null
  ): Promise<SubzoneInfo> {
    const body: {
      custom_data: Record<string, unknown>
      position_label?: string | null
    } = { custom_data: customData }
    if (positionLabel !== undefined) {
      body.position_label = positionLabel
    }
    const response = await api.patch<SubzoneInfo>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/metadata`,
      body
    )
    return response.data
  },

  // ===========================================================================
  // Sensor↔Subzone n:m Junction (AUT-1155)
  // ===========================================================================
  //
  // Vorrangregel (Doppelpfad):
  // 1) Abdeckung lesen/schreiben → NUR diese Junction-Methoden
  // 2) Heimat-/GPIO-Zuordnung → assignSubzone / Sensor-Save (assigned_gpios)
  // 3) assigned_subzones JSON bleibt tot — weder lesen noch schreiben
  //

  /**
   * Assign a sensor_config to a subzone via the n:m junction table.
   * Server-side only (no MQTT). Path uses subzone slug, not UUID PK.
   */
  async assignSensor(
    deviceId: string,
    subzoneId: string,
    sensorConfigId: string
  ): Promise<SensorSubzoneAssignmentInfo> {
    const body: SensorSubzoneAssignRequest = {
      sensor_config_id: sensorConfigId,
    }
    const response = await api.post<SensorSubzoneAssignmentInfo>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/sensors`,
      body
    )
    return response.data
  },

  /**
   * Remove a sensor_config from a subzone in the n:m junction table.
   */
  async removeSensor(
    deviceId: string,
    subzoneId: string,
    sensorConfigId: string
  ): Promise<SubzoneRemoveResponse> {
    const response = await api.delete<SubzoneRemoveResponse>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/sensors/${sensorConfigId}`
    )
    return response.data
  },

  /**
   * List explicit n:m sensor assignments for a subzone.
   * Does not include GPIO-first-match membership.
   */
  async getSensorAssignments(
    deviceId: string,
    subzoneId: string
  ): Promise<SensorSubzoneAssignmentsResponse> {
    const response = await api.get<SensorSubzoneAssignmentsResponse>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/sensors`
    )
    return response.data
  },

  /**
   * Assign an actuator_config to a subzone via the n:m junction (Verortung).
   * Does not affect GPIO-first-match / Logic Engine control path.
   */
  async assignActuator(
    deviceId: string,
    subzoneId: string,
    actuatorConfigId: string
  ): Promise<ActuatorSubzoneAssignmentInfo> {
    const body: ActuatorSubzoneAssignRequest = {
      actuator_config_id: actuatorConfigId,
    }
    const response = await api.post<ActuatorSubzoneAssignmentInfo>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/actuators`,
      body
    )
    return response.data
  },

  /**
   * Remove an actuator_config from a subzone in the n:m junction table.
   */
  async removeActuator(
    deviceId: string,
    subzoneId: string,
    actuatorConfigId: string
  ): Promise<SubzoneRemoveResponse> {
    const response = await api.delete<SubzoneRemoveResponse>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/actuators/${actuatorConfigId}`
    )
    return response.data
  },

  /**
   * List explicit n:m actuator assignments for a subzone (Verortung).
   * Does not include GPIO-first-match membership.
   */
  async getActuatorAssignments(
    deviceId: string,
    subzoneId: string
  ): Promise<ActuatorSubzoneAssignmentsResponse> {
    const response = await api.get<ActuatorSubzoneAssignmentsResponse>(
      `/subzone/devices/${deviceId}/subzones/${subzoneId}/actuators`
    )
    return response.data
  },
}

