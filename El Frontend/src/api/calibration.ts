import axios from 'axios'
import api from './index'

export interface CalibrationPoint {
  raw: number
  reference: number
  /** AUT-487: ec_linear_2point uses reference_low + reference_high roles */
  point_role?: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'air' | 'reference_low' | 'reference_high'
  point_id?: string
}

export interface CalibrateRequest {
  esp_id: string
  gpio: number
  sensor_type: string
  calibration_points: CalibrationPoint[]
  method?: 'linear' | 'offset'
  save_to_config?: boolean
}

export interface CalibrateResponse {
  success: boolean
  calibration: Record<string, unknown>
  sensor_type: string
  method: string
  saved: boolean
  message: string | null
}

// ─── Session-based Calibration Types (S-P3) ─────────────────────────────────

export interface CalibrationSessionResponse {
  id: string
  esp_id: string
  gpio: number
  sensor_type: string
  status: string
  method: string
  expected_points: number
  points_collected?: number
  calibration_points: {
    points: Array<CalibrationPoint & { id?: string; point_role?: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'air' | 'reference_low' | 'reference_high' }>
    history?: Array<Record<string, unknown>>
  } | null
  calibration_result: Record<string, unknown> | null
  correlation_id: string | null
  initiated_by: string | null
  created_at: string
  updated_at?: string
  completed_at: string | null
  failure_reason: string | null
}

/** Aligniert mit Backend Session-Start; Feuchte kanonisch `moisture_2point`. */
export type CalibrationSessionMethod =
  | 'linear_2point'
  | 'moisture_2point'
  | 'offset'
  | 'ph_2point'
  | 'ec_1point'
  | 'ec_2point'
  /** AUT-487: EC 2-point linear with reference_low + reference_high roles */
  | 'ec_linear_2point'
  | string

export interface StartSessionRequest {
  esp_id: string
  gpio: number
  sensor_type: string
  method?: CalibrationSessionMethod
  expected_points?: number
  /** AUT-299: Solution temperature in °C for temperature compensation. Default: 25.0 */
  calibration_temperature?: number
  /** Optional provenance for calibration_temperature (manual/config:auto-discovery). */
  calibration_temperature_source?: string
}

export interface AddPointRequest {
  raw_value: number
  reference_value: number
  /** AUT-487: ec_linear_2point adds reference_low + reference_high */
  point_role: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'air' | 'reference_low' | 'reference_high'
  overwrite?: boolean
  quality?: string
  intent_id?: string
  measured_at?: string
  correlation_id?: string
}

export interface UpdatePointRequest {
  raw_value: number
  reference_value: number
  /** AUT-487: ec_linear_2point adds reference_low + reference_high */
  point_role: 'dry' | 'wet' | 'buffer_high' | 'buffer_low' | 'reference' | 'air' | 'reference_low' | 'reference_high'
  quality?: string
  intent_id?: string
  measured_at?: string
  correlation_id?: string
}

function getRequiredPoints(method?: CalibrateRequest['method']): number {
  return method === 'offset' ? 1 : 2
}

const VALID_POINT_ROLES = new Set(['dry', 'wet', 'buffer_high', 'buffer_low', 'reference', 'air', 'reference_low', 'reference_high'])

/** Pass through the wizard role unchanged; server accepts all semantic roles. */
function toServerPointRole(role: string): string {
  const normalized = role.trim().toLowerCase()
  return VALID_POINT_ROLES.has(normalized) ? normalized : 'dry'
}

function normalizeCalibrationPoints(points: CalibrationPoint[]): CalibrationPoint[] {
  return points.filter((point) =>
    Number.isFinite(point.raw) && Number.isFinite(point.reference),
  )
}

export function normalizeCalibrationSensorType(sensorType: string): string {
  const normalized = sensorType.trim().toLowerCase()
  return normalized === 'soil_moisture' ? 'moisture' : normalized
}

/**
 * Calibration API client.
 *
 * The /api/v1/sensors/calibrate endpoint uses X-API-Key auth (not JWT).
 * When VITE_CALIBRATION_API_KEY is set, calls go directly via axios.
 * Without an API key, frontend uses the JWT-authenticated
 * session-based workflow (/api/v1/calibration/sessions/*).
 */
export const calibrationApi = {
  async calibrate(request: CalibrateRequest): Promise<CalibrateResponse> {
    const requiredPoints = getRequiredPoints(request.method)
    const normalizedPoints = normalizeCalibrationPoints(request.calibration_points)

    if (normalizedPoints.length < requiredPoints) {
      throw new Error(
        `Kalibrierung benötigt ${requiredPoints} gueltige Punkte, vorhanden: ${normalizedPoints.length}.`,
      )
    }

    const apiKey = import.meta.env.VITE_CALIBRATION_API_KEY as string | undefined

    if (apiKey) {
      const response = await axios.post<CalibrateResponse>(
        '/api/v1/sensors/calibrate',
        {
          ...request,
          calibration_points: normalizedPoints,
        },
        { headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' } },
      )
      return response.data
    }

    // JWT fallback path: run the newer session-based lifecycle.
    const normalizedSensorType = normalizeCalibrationSensorType(request.sensor_type)
    const sessionMethod: CalibrationSessionMethod =
      request.method === 'offset'
        ? 'offset'
        : normalizedSensorType === 'moisture'
          ? 'moisture_2point'
          : 'linear_2point'

    const session = await calibrationApi.startSession({
      esp_id: request.esp_id,
      gpio: request.gpio,
      sensor_type: normalizedSensorType,
      method: sessionMethod,
      expected_points: requiredPoints,
    })

    let lastSessionState: CalibrationSessionResponse = session
    for (let index = 0; index < requiredPoints; index += 1) {
      const point = normalizedPoints[index]
      const role: 'dry' | 'wet' = index === 0 ? 'dry' : 'wet'
      lastSessionState = await calibrationApi.addPoint(session.id, {
        raw_value: point.raw,
        reference_value: point.reference,
        point_role: role,
      })

      if (
        typeof lastSessionState.points_collected === 'number' &&
        lastSessionState.points_collected < index + 1
      ) {
        throw new Error(
          `Kalibrierpunkt ${index + 1} konnte nicht bestaetigt werden (Server meldet ${lastSessionState.points_collected} Punkte).`,
        )
      }
    }

    if (
      typeof lastSessionState.points_collected === 'number' &&
      lastSessionState.points_collected < requiredPoints
    ) {
      throw new Error(
        `Kalibrierung unvollstaendig: ${lastSessionState.points_collected}/${requiredPoints} Punkte gespeichert.`,
      )
    }

    let terminalSession = await calibrationApi.finalizeSession(session.id)

    if (request.save_to_config !== false) {
      terminalSession = await calibrationApi.applySession(session.id)
    }

    const sessionStatus = String(terminalSession.status || '').toLowerCase()
    const isApplied = sessionStatus === 'applied'
    const isFinalized = sessionStatus === 'finalizing'

    return {
      success: isApplied || isFinalized,
      calibration:
        terminalSession.calibration_result &&
        typeof terminalSession.calibration_result === 'object'
          ? terminalSession.calibration_result
          : {},
      sensor_type: terminalSession.sensor_type || request.sensor_type,
      method: terminalSession.method || sessionMethod,
      saved: request.save_to_config === false ? false : isApplied,
      message: terminalSession.failure_reason ?? null,
    }
  },

  // ─── Session-based Calibration (S-P3 / F-P2) ────────────────────────────

  /** Start a new calibration session */
  async startSession(request: StartSessionRequest): Promise<CalibrationSessionResponse> {
    const response = await api.post<CalibrationSessionResponse>(
      '/calibration/sessions',
      request,
    )
    return response.data
  },

  /** Get a calibration session by ID */
  async getSession(sessionId: string): Promise<CalibrationSessionResponse> {
    const response = await api.get<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}`,
    )
    return response.data
  },

  /** Add a measurement point to the session */
  async addPoint(
    sessionId: string,
    point: AddPointRequest,
  ): Promise<CalibrationSessionResponse> {
    const response = await api.post<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}/points`,
      { ...point, point_role: toServerPointRole(point.point_role) },
    )
    return response.data
  },

  /** Update an existing calibration point in-session */
  async updatePoint(
    sessionId: string,
    pointId: string,
    point: UpdatePointRequest,
  ): Promise<CalibrationSessionResponse> {
    const response = await api.put<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}/points/${pointId}`,
      { ...point, point_role: toServerPointRole(point.point_role) },
    )
    return response.data
  },

  /** Delete a single calibration point by point ID */
  async deletePoint(
    sessionId: string,
    pointId: string,
  ): Promise<CalibrationSessionResponse> {
    const response = await api.delete<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}/points/${pointId}`,
    )
    return response.data
  },

  /** Finalize the session (compute calibration) */
  async finalizeSession(sessionId: string): Promise<CalibrationSessionResponse> {
    const response = await api.post<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}/finalize`,
    )
    return response.data
  },

  /** Apply computed calibration to sensor config */
  async applySession(sessionId: string): Promise<CalibrationSessionResponse> {
    const response = await api.post<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}/apply`,
    )
    return response.data
  },

  /** Reject/abort a calibration session */
  async rejectSession(
    sessionId: string,
    reason?: string,
  ): Promise<CalibrationSessionResponse> {
    const response = await api.post<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}/reject`,
      { reason: reason ?? 'User rejected' },
    )
    return response.data
  },

  /** Discard session (explicit delete semantic) */
  async deleteSession(
    sessionId: string,
    reason?: string,
  ): Promise<CalibrationSessionResponse> {
    const response = await api.delete<CalibrationSessionResponse>(
      `/calibration/sessions/${sessionId}`,
      {
        params: { reason: reason ?? 'User discarded session' },
      },
    )
    return response.data
  },

  /** Get calibration history for a sensor */
  async getSensorHistory(
    espId: string,
    gpio: number,
  ): Promise<CalibrationSessionResponse[]> {
    const response = await api.get<CalibrationSessionResponse[]>(
      `/calibration/sessions/sensor/${espId}/${gpio}`,
    )
    return response.data
  },
}
