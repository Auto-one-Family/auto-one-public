import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { server } from '../../mocks/server'
import { zonesApi } from '@/api/zones'

// The axios interceptors (api/index.ts) call useAuthStore(); stub it so the
// client works without an active Pinia (same approach as tokenRefreshConcurrency).
const mockState = vi.hoisted(() => ({
  authStore: {
    accessToken: null as string | null,
    refreshToken: null as string | null,
    refreshTokens: vi.fn(),
    clearAuth: vi.fn(),
  },
}))

vi.mock('@/shared/stores/auth.store', () => ({
  useAuthStore: () => mockState.authStore,
}))

/**
 * Regression test for the GET /v1/zones contract mismatch:
 * The list endpoint serializes `ZoneListEntry` with `zone_name` (+ counts),
 * while the frontend `ZoneEntity` contract expects `name`. The API client
 * normalizes `zone_name` -> `name` so consumers (e.g. the editor dropdown)
 * show readable zone labels instead of empty entries.
 */
describe('zonesApi.listZoneEntities', () => {
  beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
  afterEach(() => server.resetHandlers())
  afterAll(() => server.close())

  it('normalisiert zone_name (ZoneListEntry) auf name (ZoneEntity)', async () => {
    server.use(
      http.get('/api/v1/zones', () =>
        HttpResponse.json({
          zones: [
            {
              zone_id: 'aut873_test',
              zone_name: 'AUT873 Test',
              status: 'active',
              device_count: 1,
              sensor_count: 2,
              actuator_count: 0,
            },
          ],
          total: 1,
        }),
      ),
    )

    const result = await zonesApi.listZoneEntities('active')

    expect(result.zones).toHaveLength(1)
    expect(result.zones[0].name).toBe('AUT873 Test')
    expect(result.zones[0].zone_id).toBe('aut873_test')
  })

  it('faellt auf zone_id zurueck, wenn weder name noch zone_name gesetzt sind', async () => {
    server.use(
      http.get('/api/v1/zones', () =>
        HttpResponse.json({
          zones: [
            {
              zone_id: 'fallback_zone',
              zone_name: null,
              status: 'active',
              device_count: 0,
              sensor_count: 0,
              actuator_count: 0,
            },
          ],
          total: 1,
        }),
      ),
    )

    const result = await zonesApi.listZoneEntities('active')

    expect(result.zones[0].name).toBe('fallback_zone')
  })

  it('bevorzugt vorhandenes name-Feld (ZoneResponse-kompatible Antwort)', async () => {
    server.use(
      http.get('/api/v1/zones', () =>
        HttpResponse.json({
          zones: [
            {
              zone_id: 'greenhouse_1',
              name: 'Gewaechshaus 1',
              zone_name: 'Sollte ignoriert werden',
              status: 'active',
            },
          ],
          total: 1,
        }),
      ),
    )

    const result = await zonesApi.listZoneEntities('active')

    expect(result.zones[0].name).toBe('Gewaechshaus 1')
  })
})
