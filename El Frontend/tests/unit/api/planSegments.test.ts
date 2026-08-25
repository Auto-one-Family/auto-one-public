import { beforeEach, describe, expect, it, vi } from 'vitest'
import { planSegmentsApi } from '@/api/planSegments'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import api from '@/api/index'

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}

describe('planSegmentsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should GET /plan-segments with optional window params (AUT-1234)', async () => {
    mockedApi.get.mockResolvedValue({
      data: [
        {
          id: 'seg-1',
          zone_id: 'z1',
          domain: 'nutrient_solution',
          measure: 'target_ec',
          value: 1.8,
          recipe_ref: null,
          from_ts: '2026-07-20T00:00:00Z',
          to_ts: null,
          interp: 'step',
          phase_ref: null,
          status: 'planned',
          tolerance: null,
          created_at: '2026-07-20T00:00:00Z',
          updated_at: '2026-07-20T00:00:00Z',
        },
      ],
    })

    const list = await planSegmentsApi.list({
      from_ts: '2026-07-15T00:00:00.000Z',
      to_ts: '2026-07-29T00:00:00.000Z',
    })

    expect(mockedApi.get).toHaveBeenCalledWith('/plan-segments', {
      params: {
        from_ts: '2026-07-15T00:00:00.000Z',
        to_ts: '2026-07-29T00:00:00.000Z',
      },
    })
    expect(list).toHaveLength(1)
    expect(list[0].id).toBe('seg-1')
  })

  it('should POST /plan-segments for create (AUT-1235)', async () => {
    mockedApi.post.mockResolvedValue({
      data: { id: 'new-1', zone_id: 'z1', value: 2.0 },
    })
    const created = await planSegmentsApi.create({
      zone_id: 'z1',
      domain: 'nutrient_solution',
      measure: 'target_ec',
      value: 2.0,
      from_ts: '2026-07-20T00:00:00.000Z',
      to_ts: '2026-07-22T00:00:00.000Z',
    })
    expect(mockedApi.post).toHaveBeenCalledWith('/plan-segments', expect.objectContaining({
      zone_id: 'z1',
      value: 2.0,
    }))
    expect(created.id).toBe('new-1')
  })

  it('should PATCH and DELETE via the same router (AUT-1235)', async () => {
    mockedApi.patch.mockResolvedValue({ data: { id: 'seg-1', value: 2.4 } })
    mockedApi.delete.mockResolvedValue({})
    await planSegmentsApi.update('seg-1', { value: 2.4 })
    await planSegmentsApi.remove('seg-1')
    expect(mockedApi.patch).toHaveBeenCalledWith('/plan-segments/seg-1', { value: 2.4 })
    expect(mockedApi.delete).toHaveBeenCalledWith('/plan-segments/seg-1')
  })

  it('should return empty array when payload is not an array', async () => {
    mockedApi.get.mockResolvedValue({ data: null })
    const list = await planSegmentsApi.list()
    expect(list).toEqual([])
  })
})
