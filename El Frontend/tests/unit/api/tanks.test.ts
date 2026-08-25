import { beforeEach, describe, expect, it, vi } from 'vitest'
import { tanksApi } from '@/api/tanks'

vi.mock('@/api/index', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

import api from '@/api/index'

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  put: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
}

describe('tanksApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should GET /tanks for listTanks (AUT-1224)', async () => {
    mockedApi.get.mockResolvedValue({
      data: [
        {
          id: 't1',
          zone_id: 'z1',
          name: 'Tank A',
          operation_mode: 'drain_to_waste',
          created_at: '2026-07-21T00:00:00Z',
          updated_at: '2026-07-21T00:00:00Z',
        },
      ],
    })
    const tanks = await tanksApi.listTanks()
    expect(mockedApi.get).toHaveBeenCalledWith('/tanks')
    expect(tanks).toHaveLength(1)
    expect(tanks[0].id).toBe('t1')
  })

  it('should GET /tanks/{tankId}/targets for getTargets (AUT-1225 Q4)', async () => {
    mockedApi.get.mockResolvedValue({
      data: {
        tank_id: 't1',
        zone_id: 'z1',
        subzone_config_id: null,
        at: '2026-07-22T10:00:00Z',
        domain: 'nutrient_solution',
        targets: [
          {
            measure: 'target_ec',
            value: 1.8,
            unit: 'µS/cm',
            segment_id: 'seg-1',
            from_ts: '2026-07-22T00:00:00Z',
            to_ts: null,
            resolved_via: 'zone',
          },
          {
            measure: 'target_ph',
            value: null,
            unit: null,
            segment_id: null,
            from_ts: null,
            to_ts: null,
            resolved_via: 'none',
          },
        ],
        assigned_device_ids: ['ESP_1'],
      },
    })
    const result = await tanksApi.getTargets('t1')
    expect(mockedApi.get).toHaveBeenCalledWith('/tanks/t1/targets')
    expect(result.tank_id).toBe('t1')
    expect(result.assigned_device_ids).toEqual(['ESP_1'])
    expect(result.targets).toHaveLength(2)
    expect(result.targets[0].value).toBe(1.8)
    expect(result.targets[1].value).toBeNull()
    expect(result.targets[1].resolved_via).toBe('none')
  })

  it('should POST /tanks for createTank', async () => {
    mockedApi.post.mockResolvedValue({
      data: {
        id: 't1',
        zone_id: 'z1',
        name: 'Tank A',
        operation_mode: 'drain_to_waste',
        created_at: '2026-07-21T00:00:00Z',
        updated_at: '2026-07-21T00:00:00Z',
      },
    })
    const tank = await tanksApi.createTank({
      zone_id: 'z1',
      name: 'Tank A',
      operation_mode: 'drain_to_waste',
    })
    expect(mockedApi.post).toHaveBeenCalledWith('/tanks', {
      zone_id: 'z1',
      name: 'Tank A',
      operation_mode: 'drain_to_waste',
    })
    expect(tank.id).toBe('t1')
  })

  it('should POST /tanks/{tankId}/assist/dose-expectation for computeDoseExpectation (AUT-1344)', async () => {
    mockedApi.post.mockResolvedValue({
      data: {
        volume_alt_l: 20,
        volume_alt_source: 'ledger_prior_volume',
        volume_zugabe_l: 0,
        volume_neu_l: 20,
        ec_wasser_us_cm: 488,
        ec_after_dilution_us_cm: 1000,
        dose_a_ml: 1000,
        dose_b_ml: 1000,
        expected_ec_us_cm: 1400,
        concentration: 4,
        suggestion_kind: 'dose_up',
        fresh_water_suggest_l: null,
        operator_message: 'Vorschlag zum Aufdosieren — dosiert nichts.',
        notes: ['Fall 1: Aufdosieren.'],
      },
    })
    const result = await tanksApi.computeDoseExpectation('t1', {
      current_ec_us_cm: 1000,
      target_ec_us_cm: 1400,
      concentration: 4,
    })
    expect(mockedApi.post).toHaveBeenCalledWith('/tanks/t1/assist/dose-expectation', {
      current_ec_us_cm: 1000,
      target_ec_us_cm: 1400,
      concentration: 4,
    })
    expect(result.dose_a_ml).toBe(1000)
    expect(result.dose_b_ml).toBe(1000)
    expect(result.expected_ec_us_cm).toBe(1400)
  })

  it('should POST ledger entry with never-measured flags', async () => {
    mockedApi.post.mockResolvedValue({
      data: {
        id: 'b1',
        tank_id: 't1',
        entry_type: 'full_reset',
        volume_l: 18,
        components: [],
        ec_was_measured: false,
        ph_was_measured: false,
        acquisition_method: 'manual_entry',
        qualifier: 'approximate',
        occurred_at: '2026-07-21T00:00:00Z',
        created_at: '2026-07-21T00:00:00Z',
      },
    })
    const batch = await tanksApi.createBatch('t1', {
      entry_type: 'full_reset',
      volume_l: 18,
      components: [
        { kind: 'product', name: 'Grow A', dose_ml_per_l: 2 },
        { kind: 'salt', name: 'MgSO4', conc_g_per_l: 0.3 },
      ],
      acquisition_method: 'manual_entry',
      qualifier: 'approximate',
      ec_was_measured: false,
      ph_was_measured: false,
    })
    expect(mockedApi.post).toHaveBeenCalledWith(
      '/tanks/t1/batches',
      expect.objectContaining({
        entry_type: 'full_reset',
        ec_was_measured: false,
        ph_was_measured: false,
      }),
    )
    expect(batch.ec_was_measured).toBe(false)
  })
})
