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
 * @see El Servador/god_kaiser_server/src/api/v1/plants.py
 */

import api from './index'
import type {
  Plant,
  PlantCreate,
  PlantLifecycleEvent,
  PlantLifecycleEventCreate,
  PlantMeasurement,
  PlantUpdate,
} from '@/types'

// =============================================================================
// Envelope helpers
// =============================================================================

interface Envelope<T> {
  data?: T
}

function unwrap<T>(payload: T | Envelope<T>): T {
  if (payload && typeof payload === 'object' && 'data' in payload) {
    const inner = (payload as Envelope<T>).data
    if (inner !== undefined) return inner
  }
  return payload as T
}

// =============================================================================
// API
// =============================================================================

export const plantsApi = {
  /** List all plants. */
  async getList(): Promise<Plant[]> {
    const response = await api.get<Plant[] | Envelope<Plant[]>>('/plants')
    const value = unwrap(response.data)
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
