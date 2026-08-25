/**
 * Tank / Nutrient Ledger API Client (AUT-1215 / AUT-1217 / AUT-1223 / AUT-1225)
 *
 *   GET    /v1/tanks
 *   GET    /v1/tanks/{tank_id}
 *   GET    /v1/tanks/{tank_id}/targets
 *   GET    /v1/tanks/{tank_id}/volume
 *   POST   /v1/tanks
 *   POST   /v1/tanks/{tank_id}/subzones
 *   DELETE /v1/tanks/{tank_id}/subzones/{subzone_config_id}
 *   POST   /v1/tanks/{tank_id}/assist/dose-expectation
 *   POST   /v1/tanks/{tank_id}/batches
 *
 * Device↔tank assignment UI-SSOT (AUT-1358): PATCH /esp/devices/{id} {tank_id}.
 * Server still exposes PUT/DELETE /tanks/{id}/devices/{esp} as alias — not wired in FE.
 *
 * @see El Servador/god_kaiser_server/src/api/v1/tanks.py
 */

import api from './index'
import type {
  NutrientBatch,
  NutrientBatchCreate,
  Tank,
  TankCreate,
  TankUpdate,
  TankSubzoneAssignRequest,
  TankSubzoneAssignmentInfo,
  TankTargetsResponse,
  TankVolumeResponse,
  SaltCalculatorAssistRequest,
  SaltCalculatorAssistResponse,
} from '@/types'

export const tanksApi = {
  /** List all tanks (AUT-1223 Q3 — feeds the device↔tank assignment dropdown). */
  async listTanks(): Promise<Tank[]> {
    const response = await api.get<Tank[]>('/tanks')
    return response.data
  },

  /** Get a single tank by id. */
  async getTank(tankId: string): Promise<Tank> {
    const response = await api.get<Tank>(`/tanks/${tankId}`)
    return response.data
  },

  /**
   * Resolve the tank's Soll targets (target_ec / target_ph) from
   * plan_segment@now, plus the currently assigned ESP device_ids for the
   * Ist lookup (AUT-1225 Q4). Canonical Soll source — never tank fields.
   */
  async getTargets(tankId: string): Promise<TankTargetsResponse> {
    const response = await api.get<TankTargetsResponse>(`/tanks/${tankId}/targets`)
    return response.data
  },

  /**
   * Running volume (Ist) = „20 Liter“-Anker ± Flow-Delta GPIO14 (AUT-1377).
   * Fail-closed: volume_l may be null. nominal_volume_l is NOT Ist.
   */
  async getVolume(tankId: string): Promise<TankVolumeResponse> {
    const response = await api.get<TankVolumeResponse>(`/tanks/${tankId}/volume`)
    return response.data
  },

  /** Create a nutrient-solution tank in an existing zone. */
  async createTank(data: TankCreate): Promise<Tank> {
    const response = await api.post<Tank>('/tanks', data)
    return response.data
  },

  /** Partial update (AUT-1381 — Frischwasser/Volumen-Felder). */
  async updateTank(tankId: string, data: TankUpdate): Promise<Tank> {
    const response = await api.patch<Tank>(`/tanks/${tankId}`, data)
    return response.data
  },

  /** Assign tank → subzone_config (n:m). */
  async assignSubzone(
    tankId: string,
    request: TankSubzoneAssignRequest,
  ): Promise<TankSubzoneAssignmentInfo> {
    const response = await api.post<TankSubzoneAssignmentInfo>(
      `/tanks/${tankId}/subzones`,
      request,
    )
    return response.data
  },

  /** Remove a tank↔subzone assignment (tank itself is not deleted). */
  async removeSubzone(
    tankId: string,
    subzoneConfigId: string,
  ): Promise<{ success: boolean; message: string; tank_id: string; subzone_config_id: string }> {
    const response = await api.delete<{
      success: boolean
      message: string
      tank_id: string
      subzone_config_id: string
    }>(`/tanks/${tankId}/subzones/${subzoneConfigId}`)
    return response.data
  },

  /** Append a nutrient-solution ledger entry (incl. system_incident). */
  async createBatch(tankId: string, data: NutrientBatchCreate): Promise<NutrientBatch> {
    const response = await api.post<NutrientBatch>(`/tanks/${tankId}/batches`, data)
    return response.data
  },

  /**
   * Salt calculator assist — read-only dose expectation (AUT-1343 / AUT-1344).
   * Does not persist and does not dose actuators.
   */
  async computeDoseExpectation(
    tankId: string,
    data: SaltCalculatorAssistRequest,
  ): Promise<SaltCalculatorAssistResponse> {
    const response = await api.post<SaltCalculatorAssistResponse>(
      `/tanks/${tankId}/assist/dose-expectation`,
      data,
    )
    return response.data
  },
}
