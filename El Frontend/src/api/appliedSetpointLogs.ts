/**
 * Applied Setpoint Logs API Client (AUT-1236 T6 / AUT-1243 origin)
 *
 *   GET /v1/applied-setpoint-logs
 *
 * Read-only — immutable table written by T3 (plan_setpoint_resolver).
 */

import api from './index'
import type {
  AppliedSetpointLog,
  AppliedSetpointLogListParams,
} from '@/types/planSegment'

export const appliedSetpointLogsApi = {
  /**
   * List applied setpoint log rows for a filter window.
   * Returns [] on empty payload; throws on transport/auth errors.
   */
  async list(params: AppliedSetpointLogListParams = {}): Promise<AppliedSetpointLog[]> {
    const response = await api.get<AppliedSetpointLog[]>('/applied-setpoint-logs', {
      params,
    })
    return Array.isArray(response.data) ? response.data : []
  },
}
