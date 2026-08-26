import { beforeEach, describe, expect, it, vi } from 'vitest'
import { plantsApi } from '@/api/plants'

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
}

function event(id: string) {
  return {
    event_id: id,
    plant_id: 'p1',
    event_type: 'topping',
    event_timestamp: '2026-07-22T12:00:00.000Z',
    created_at: '2026-07-22T12:00:00.000Z',
    event_status: 'occurred',
  }
}

describe('plantsApi.getLifecycleEvents', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should page past the default oldest-first 100-row window', async () => {
    const firstPage = Array.from({ length: 500 }, (_, i) => event(`old-${i}`))
    const newest = event('newest')
    mockedApi.get
      .mockResolvedValueOnce({
        data: { plant_id: 'p1', total: 500, events: firstPage, tank_incidents: [] },
      })
      .mockResolvedValueOnce({
        data: { plant_id: 'p1', total: 1, events: [newest], tank_incidents: [] },
      })

    const result = await plantsApi.getLifecycleEvents('p1')

    expect(mockedApi.get).toHaveBeenNthCalledWith(1, '/plants/p1/lifecycle-events', {
      params: { skip: 0, limit: 500 },
    })
    expect(mockedApi.get).toHaveBeenNthCalledWith(2, '/plants/p1/lifecycle-events', {
      params: { skip: 500, limit: 500 },
    })
    expect(result.events).toHaveLength(501)
    expect(result.events[500]?.event_id).toBe('newest')
  })
})
