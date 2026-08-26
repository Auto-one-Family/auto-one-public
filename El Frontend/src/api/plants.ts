/**
 * Plants API Client
 *
 * Plant inventory + lifecycle management.
 *
 * Server endpoints:
 *   - GET    /v1/plants                          (AUT-222)
 *   - POST   /v1/plants                          (AUT-222)
 *   - GET    /v1/plants/{id}                     (AUT-221)
 *   - PATCH  /v1/plants/{id}                     (AUT-222)
 *   - DELETE /v1/plants/{id}                     (AUT-221)
 *   - GET    /v1/plants/{id}/measurements        (AUT-221)
 *   - POST   /v1/plants/{id}/lifecycle-event     (AUT-221)
 *   - GET    /v1/plants/{id}/qr-code.png         (AUT-222, returns image/png)
 *
 * AUT-1178: unwrap() detects the `plants` envelope key from PlantListResponse
 * (`{ plants: [...], total: N }`) in addition to the legacy `data` envelope.
 *
 * @see El Servador/god_kaiser_server/src/api/v1/plants.py
 */

import api from './index'
import type {
  Plant,
  PlantCreate,
  PlantLifecycleEvent,
  PlantLifecycleEventCreate,
  PlantLifecycleEventStatusUpdate,
  PlantMeasurement,
  PlantTankIncidentEvent,
  PlantUpdate,
} from '@/types'

// =============================================================================
// Envelope helpers
// =============================================================================

/** Legacy `{ data: T }` envelope used by some endpoints. */
interface Envelope<T> {
  data?: T
}

/**
 * PlantListResponse envelope: `{ plants: Plant[], total: number }`.
 * This is what `GET /v1/plants` returns (AUT-1178).
 */
interface PlantListEnvelope {
  plants?: Plant[]
  total?: number
}

/**
 * LifecycleEventListResponse envelope:
 * `{ plant_id: string, total: number, events: PlantLifecycleEvent[],
 * tank_incidents: PlantTankIncidentEvent[] }`.
 * This is what `GET /v1/plants/{id}/lifecycle-events` returns (AUT-1181,
 * `tank_incidents` added AUT-1211).
 */
interface PlantLifecycleEventListEnvelope {
  plant_id?: string
  total?: number
  events?: PlantLifecycleEvent[]
  tank_incidents?: PlantTankIncidentEvent[]
}

/** Return shape of {@link plantsApi.getLifecycleEvents}. */
export interface PlantLifecycleEventsResult {
  events: PlantLifecycleEvent[]
  tankIncidents: PlantTankIncidentEvent[]
}

function parseLifecycleEventsPayload(
  payload: PlantLifecycleEventListEnvelope | PlantLifecycleEvent[],
): PlantLifecycleEventsResult {
  if (
    payload &&
    typeof payload === 'object' &&
    'events' in payload &&
    Array.isArray((payload as PlantLifecycleEventListEnvelope).events)
  ) {
    const envelope = payload as PlantLifecycleEventListEnvelope
    return {
      events: envelope.events ?? [],
      tankIncidents: envelope.tank_incidents ?? [],
    }
  }
  return {
    events: Array.isArray(payload) ? payload : [],
    tankIncidents: [],
  }
}

/**
 * Unwrap a server response that may arrive in one of three shapes:
 *   1) PlantListResponse `{ plants: [...], total: N }` — detected first
 *   2) Legacy data envelope `{ data: T }`
 *   3) Raw value T
 */
function unwrap<T>(payload: T | Envelope<T> | PlantListEnvelope): T {
  if (payload && typeof payload === 'object') {
    // Shape 1: PlantListResponse
    if ('plants' in payload && Array.isArray((payload as PlantListEnvelope).plants)) {
      return (payload as PlantListEnvelope).plants as unknown as T
    }
    // Shape 2: legacy data envelope
    if ('data' in payload) {
      const inner = (payload as Envelope<T>).data
      if (inner !== undefined) return inner
    }
  }
  // Shape 3: raw value
  return payload as T
}

// =============================================================================
// API
// =============================================================================

export const plantsApi = {
  /** List all plants. */
  async getList(): Promise<Plant[]> {
    const response = await api.get<Plant[] | Envelope<Plant[]> | PlantListEnvelope>('/plants')
    const value = unwrap<Plant[]>(response.data as Plant[] | Envelope<Plant[]> | PlantListEnvelope)
    return Array.isArray(value) ? value : []
  },

  /** Load a single plant including lifecycle_events / audit_logs. */
  async getById(id: string): Promise<Plant> {
    const response = await api.get<Plant | Envelope<Plant>>(`/plants/${id}`)
    return unwrap(response.data)
  },

  /** Create a new plant. */
  async create(data: PlantCreate): Promise<Plant> {
    const response = await api.post<Plant | Envelope<Plant>>('/plants', data)
    return unwrap(response.data)
  },

  /** Patch an existing plant. */
  async update(id: string, data: PlantUpdate): Promise<Plant> {
    const response = await api.patch<Plant | Envelope<Plant>>(`/plants/${id}`, data)
    return unwrap(response.data)
  },

  /** Soft-delete a plant. */
  async delete(id: string): Promise<void> {
    await api.delete(`/plants/${id}`)
  },

  /** Load MultispeQ measurements (Phi2/Fv-Fm/NPQ time series) for a plant. */
  async getMeasurements(id: string, days = 30): Promise<PlantMeasurement[]> {
    const response = await api.get<PlantMeasurement[] | Envelope<PlantMeasurement[]>>(
      `/plants/${id}/measurements`,
      { params: { days } },
    )
    const value = unwrap(response.data)
    return Array.isArray(value) ? value : []
  },

  /**
   * Load all lifecycle events for a plant from the dedicated endpoint.
   *
   * Server: GET /v1/plants/{id}/lifecycle-events
   * Response envelope: { plant_id, total, events: PlantLifecycleEvent[],
   * tank_incidents: PlantTankIncidentEvent[] }
   * Events are ordered by event_timestamp ASC (oldest first) on the server.
   * Pages through ``skip`` / ``limit`` (max 500) so a full first page of
   * older rows does not drop newer measures after Eintragen.
   *
   * AUT-1181: Befund 2 — use the dedicated endpoint instead of the embedded
   * field on the plant detail response (which the server does not populate).
   *
   * AUT-1211: tank_incidents are system-wide tank incidents affecting this
   * plant via its subzone/tank assignment — kept separate from `events`
   * since they are not per-plant lifecycle events.
   */
  async getLifecycleEvents(id: string): Promise<PlantLifecycleEventsResult> {
    const pageSize = 500
    const events: PlantLifecycleEvent[] = []
    let tankIncidents: PlantTankIncidentEvent[] = []
    let skip = 0

    while (true) {
      const response = await api.get<PlantLifecycleEventListEnvelope | PlantLifecycleEvent[]>(
        `/plants/${id}/lifecycle-events`,
        { params: { skip, limit: pageSize } },
      )
      const page = parseLifecycleEventsPayload(response.data)
      if (skip === 0) {
        tankIncidents = page.tankIncidents
      }
      events.push(...page.events)
      if (page.events.length < pageSize) break
      skip += pageSize
    }

    return { events, tankIncidents }
  },

  /** Append a lifecycle event (phase change, note, harvest, ...). */
  async addLifecycleEvent(
    id: string,
    event: PlantLifecycleEventCreate,
  ): Promise<PlantLifecycleEvent> {
    const response = await api.post<PlantLifecycleEvent | Envelope<PlantLifecycleEvent>>(
      `/plants/${id}/lifecycle-event`,
      event,
    )
    return unwrap(response.data)
  },

  /**
   * Change the truth status of an existing lifecycle event (AUT-1207) —
   * e.g. mark it as 'reverted' with a reason. The only mutable field on an
   * otherwise append-only event.
   */
  async updateLifecycleEventStatus(
    id: string,
    eventId: string,
    update: PlantLifecycleEventStatusUpdate,
  ): Promise<PlantLifecycleEvent> {
    const response = await api.patch<PlantLifecycleEvent | Envelope<PlantLifecycleEvent>>(
      `/plants/${id}/lifecycle-event/${eventId}/status`,
      update,
    )
    return unwrap(response.data)
  },

  /**
   * Path to the QR-code PNG for `<img :src="...">`.
   *
   * Note: JWT auth is header-based (Authorization: Bearer ...) — direct
   * `<img>` requests do NOT carry the token. Use `downloadQRCode()` for
   * authenticated downloads/print-dialog. This URL only works in dev
   * proxies that pass session cookies, not in production.
   */
  getQRCodeUrl(id: string): string {
    return `/api/v1/plants/${id}/qr-code.png`
  },

  /**
   * Download the QR-code PNG via the authenticated axios instance and
   * trigger a browser download. Returns the blob in case the caller
   * wants to preview it instead of saving.
   */
  async downloadQRCode(id: string, filename?: string): Promise<Blob> {
    const response = await api.get<Blob>(`/plants/${id}/qr-code.png`, {
      responseType: 'blob',
    })
    const blob = response.data
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = filename ?? `qr-${id}.png`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    // Defer revoke to allow the browser to start the download
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    return blob
  },
}
