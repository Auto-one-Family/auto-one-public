/**
 * Plan Segments API Client (AUT-1234 T4 / AUT-1235 T5 / AUT-1240)
 *
 *   GET    /v1/plan-segments
 *   GET    /v1/plan-segments/climate-at
 *   POST   /v1/plan-segments
 *   PATCH  /v1/plan-segments/{id}
 *   DELETE /v1/plan-segments/{id}
 *
 * Single edit path — Phase-1a router `src/api/v1/plan_segments.py`.
 */

import api from './index'
import type {
  ClimateTargetsAt,
  PlanSegment,
  PlanSegmentCreate,
  PlanSegmentListParams,
  PlanSegmentUpdate,
} from '@/types/planSegment'

export const planSegmentsApi = {
  /**
   * List plan segments overlapping an optional time window.
   * Returns [] on empty payload; throws on transport/auth errors (store handles).
   */
  async list(params: PlanSegmentListParams = {}): Promise<PlanSegment[]> {
    const response = await api.get<PlanSegment[]>('/plan-segments', { params })
    return Array.isArray(response.data) ? response.data : []
  },

  /** Point-in-time climate Soll + derived VPD band (AUT-1239). */
  async climateAt(params: {
    zone_id: string
    at?: string
    subzone_config_id?: string
  }): Promise<ClimateTargetsAt> {
    const response = await api.get<ClimateTargetsAt>('/plan-segments/climate-at', {
      params,
    })
    return response.data
  },

  async create(payload: PlanSegmentCreate): Promise<PlanSegment> {
    const response = await api.post<PlanSegment>('/plan-segments', payload)
    return response.data
  },

  async update(id: string, payload: PlanSegmentUpdate): Promise<PlanSegment> {
    const response = await api.patch<PlanSegment>(`/plan-segments/${id}`, payload)
    return response.data
  },

  async remove(id: string): Promise<void> {
    await api.delete(`/plan-segments/${id}`)
  },
}
