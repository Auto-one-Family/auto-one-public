import { beforeEach, describe, expect, it, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useTankStore } from '@/shared/stores/tank.store'

const mockListTanks = vi.fn()

vi.mock('@/api/tanks', () => ({
  tanksApi: {
    listTanks: (...args: unknown[]) => mockListTanks(...args),
  },
}))

vi.mock('@/utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}))

describe('tank.store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('fetchTanks() loads from server GET /v1/tanks and replaces state (AUT-1224)', async () => {
    const serverTanks = [
      {
        id: 't1',
        zone_id: 'z1',
        name: 'Tank A',
        operation_mode: 'drain_to_waste' as const,
        created_at: '2026-07-21T00:00:00Z',
        updated_at: '2026-07-21T00:00:00Z',
      },
    ]
    mockListTanks.mockResolvedValue(serverTanks)

    const store = useTankStore()
    const result = await store.fetchTanks()

    expect(mockListTanks).toHaveBeenCalledTimes(1)
    expect(result).toEqual(serverTanks)
    expect(store.tanks).toEqual(serverTanks)
    expect(store.isLoading).toBe(false)
  })

  it('fetchTanks() does not fall back to localStorage on error — propagates instead', async () => {
    localStorage.setItem(
      'autoone.known_tanks.v1',
      JSON.stringify([{ id: 'stale', zone_id: 'z0', name: 'Stale Tank' }]),
    )
    mockListTanks.mockRejectedValue(new Error('network down'))

    const store = useTankStore()
    await expect(store.fetchTanks()).rejects.toThrow('network down')
    expect(store.error).toBe('network down')
  })
})
