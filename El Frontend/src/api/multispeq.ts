/**
 * MultispeQ Audit API Client
 *
 * Handles photosynthesis audit measurement imports from MultispeQ devices.
 * Server endpoints: /v1/sensors/multispeq/*
 *
 * @see El Servador/god_kaiser_server/src/api/v1/sensors.py (AUT-217)
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface MultispeqImportParams {
  file: File
  device_serial: string
  zone_id: string
  subzone_id?: string
  /** ISO date string "YYYY-MM-DD" */
  calibration_date: string
  dry_run?: boolean
}

export interface MultispeqImportResponse {
  imported: number
  skipped_duplicates: number
  needs_review: number
  warnings: string[]
  errors: string[]
  /** Optional: snapshots without plant assignment, returned when needs_review > 0 */
  needs_review_snapshots?: NeedsReviewSnapshot[]
}

export interface NeedsReviewSnapshot {
  /** UUID */
  id: string
  /** ISO timestamp */
  timestamp: string
  /** phi2, fv_fm, npq, etc. */
  sensor_values: Record<string, number>
}

export interface AssignPlantResponse {
  success: boolean
  message?: string
}

/** Boxplot aggregate entry returned by /sensors/multispeq/aggregates (AUT-220) */
export interface AggregateEntry {
  group_label: string
  min: number
  q1: number
  median: number
  q3: number
  max: number
  n: number
}

/** Correlation scatter point returned by /sensors/multispeq/correlation (AUT-220) */
export interface CorrelationPoint {
  x: number
  y: number
  label: string
  metadata_phase?: string
}

// =============================================================================
// API
// =============================================================================

export const multispeqApi = {
  /**
   * Import a MultispeQ measurement file (CSV or JSON).
   *
   * Uses multipart/form-data because file upload is required.
   * When dry_run is true, the server validates without persisting.
   */
  async importMeasurement(
    params: MultispeqImportParams,
  ): Promise<MultispeqImportResponse> {
    const formData = new FormData()
    formData.append('file', params.file)
    formData.append('device_serial', params.device_serial)
    formData.append('zone_id', params.zone_id)
    if (params.subzone_id) {
      formData.append('subzone_id', params.subzone_id)
    }
    formData.append('calibration_date', params.calibration_date)
    if (params.dry_run) {
      formData.append('dry_run', 'true')
    }

    const response = await api.post<MultispeqImportResponse | { data: MultispeqImportResponse }>(
      '/sensors/multispeq/import',
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    )
    // Server may wrap response in { data: ... } envelope
    const payload = response.data as MultispeqImportResponse | { data: MultispeqImportResponse }
    return (payload as { data: MultispeqImportResponse }).data ?? (payload as MultispeqImportResponse)
  },

  /**
   * Assign a snapshot (UUID) to a plant.
   * Used to resolve "needs_review" snapshots after import.
   */
  async assignPlant(snapshotId: string, plantId: string): Promise<void> {
    await api.patch(`/sensors/multispeq/${snapshotId}/assign-plant`, {
      plant_id: plantId,
    })
  },

  /**
   * Fetch boxplot aggregates per group (AUT-220).
   *
   * @param sensor_type — MultispeQ sensor type key (e.g. 'phi2', 'fv_fm')
   * @param group_by — Grouping dimension ('zone_id' | 'subzone_id' | 'plant_id')
   * @param date_range — Time window ('7d' | '30d' | '90d' | 'season')
   */
  async getAggregates(
    sensor_type: string,
    group_by: string,
    date_range: string,
  ): Promise<AggregateEntry[]> {
    const response = await api.get<AggregateEntry[] | { data: AggregateEntry[] }>(
      '/sensors/multispeq/aggregates',
      { params: { sensor_type, group_by, date_range } },
    )
    const payload = response.data as AggregateEntry[] | { data: AggregateEntry[] }
    return (payload as { data: AggregateEntry[] }).data ?? (payload as AggregateEntry[])
  },

  /**
   * Fetch correlation points x_sensor vs y_metadata (AUT-220).
   *
   * @param x_type — Sensor type for X-axis (e.g. 'ppfd')
   * @param y_metadata_key — Metadata key for Y-axis (e.g. 'yield_g')
   * @param date_range — Time window ('7d' | '30d' | '90d' | 'season')
   */
  async getCorrelation(
    x_type: string,
    y_metadata_key: string,
    date_range: string,
  ): Promise<CorrelationPoint[]> {
    const response = await api.get<CorrelationPoint[] | { data: CorrelationPoint[] }>(
      '/sensors/multispeq/correlation',
      { params: { x_type, y_metadata_key, date_range } },
    )
    const payload = response.data as CorrelationPoint[] | { data: CorrelationPoint[] }
    return (payload as { data: CorrelationPoint[] }).data ?? (payload as CorrelationPoint[])
  },
}
