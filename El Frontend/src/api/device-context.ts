/**
 * Device Context API Client (T13-R2)
 *
 * Manages active zone/subzone context for multi-zone and mobile devices.
 * Follows the same patterns as other API clients (zones.ts, sensors.ts).
 */

import api from './index'
import type { DeviceContextSet, DeviceContextResponse } from '@/types'

export const deviceContextApi = {
  /**
   * Set active zone/subzone context for a sensor or actuator config.
   */
  async setContext(
    configType: 'sensor' | 'actuator',
    configId: string,
    body: DeviceContextSet,
  ): Promise<DeviceContextResponse> {
    const response = await api.put<DeviceContextResponse>(
      `/device-context/${configType}/${configId}`,
      body,
    )
    return response.data
  },

  /**
   * Get current active context for a sensor or actuator config.
   */
  async getContext(
    configType: 'sensor' | 'actuator',
    configId: string,
  ): Promise<DeviceContextResponse> {
    const response = await api.get<DeviceContextResponse>(
      `/device-context/${configType}/${configId}`,
    )
    return response.data
  },

  /**
   * Clear active context (reset to no active zone).
   */
  async clearContext(
    configType: 'sensor' | 'actuator',
    configId: string,
  ): Promise<DeviceContextResponse> {
    const response = await api.delete<DeviceContextResponse>(
      `/device-context/${configType}/${configId}`,
    )
    return response.data
  },
}
