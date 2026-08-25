/**
 * Plan Segment types (AUT-1232 / AUT-1234 T4)
 *
 * Mirrors server schemas in
 * `El Servador/god_kaiser_server/src/schemas/plan_segment.py`.
 */

import type { PlanDomain, PlanMeasure } from '@/types/logic'

export type PlanSegmentStatus = 'planned' | 'active' | 'occurred' | 'withdrawn'
export type PlanSegmentInterp = 'step' | 'linear'

/** Response from GET /v1/plan-segments (and single-item endpoints). */
export interface PlanSegment {
  id: string
  zone_id: string
  domain: PlanDomain | string
  measure: PlanMeasure | string
  value: number | null
  recipe_ref: string | null
  from_ts: string
  to_ts: string | null
  interp: PlanSegmentInterp | string
  phase_ref: string | null
  status: PlanSegmentStatus | string
  tolerance: number | null
  created_at: string
  updated_at: string
}

/** Query params for GET /v1/plan-segments. */
export interface PlanSegmentListParams {
  zone_id?: string
  subzone_config_id?: string
  domain?: string
  measure?: string
  from_ts?: string
  to_ts?: string
}

/** Body for POST /v1/plan-segments (mirrors PlanSegmentCreate). */
export interface PlanSegmentCreate {
  zone_id: string
  domain: PlanDomain | string
  measure: PlanMeasure | string
  value?: number | null
  recipe_ref?: string | null
  from_ts: string
  to_ts?: string | null
  interp?: PlanSegmentInterp | string
  phase_ref?: string | null
  /** plan_segment.status — NOT PlantLifecycleEvent.event_status */
  status?: PlanSegmentStatus | string
  tolerance?: number | null
}

/** Body for PATCH /v1/plan-segments/{id} (partial). */
export interface PlanSegmentUpdate {
  domain?: PlanDomain | string
  measure?: PlanMeasure | string
  value?: number | null
  recipe_ref?: string | null
  from_ts?: string
  to_ts?: string | null
  interp?: PlanSegmentInterp | string
  phase_ref?: string | null
  status?: PlanSegmentStatus | string
  tolerance?: number | null
}

/** Origin of an applied setpoint (AUT-1232 / T3 write, T6 read). */
export type AppliedSetpointOrigin = 'plan_segment' | 'static_fallback'

/** Response from GET /v1/applied-setpoint-logs (immutable audit rows). */
export interface AppliedSetpointLog {
  id: string
  zone_id: string
  subzone_config_id: string | null
  domain: PlanDomain | string
  measure: PlanMeasure | string
  applied_value: number
  effective_at: string
  rule_id: string | null
  segment_id: string | null
  origin: AppliedSetpointOrigin | string
  created_at: string
}

/** Query params for GET /v1/applied-setpoint-logs. */
export interface AppliedSetpointLogListParams {
  zone_id?: string
  subzone_config_id?: string
  domain?: string
  measure?: string
  rule_id?: string
  from_ts?: string
  to_ts?: string
  limit?: number
}

/** Derived VPD band from planned T/RH (AUT-1239) — never a stored measure. */
export interface PlannedVpdBand {
  computable: boolean
  reason: string | null
  vpd_kpa: number | null
  vpd_min_kpa: number | null
  vpd_max_kpa: number | null
  source: string
}

export interface ClimateMeasureTarget {
  measure: string
  value: number | null
  tolerance: number | null
  segment_id: string | null
  from_ts: string | null
  to_ts: string | null
  resolved_via: string
}

/** Response from GET /v1/plan-segments/climate-at. */
export interface ClimateTargetsAt {
  zone_id: string
  subzone_config_id: string | null
  at: string
  domain: string
  targets: ClimateMeasureTarget[]
  vpd_band: PlannedVpdBand
}
