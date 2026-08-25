/**
 * Stock Mix Recipes API Client (AUT-1361 / P9)
 *
 *   GET    /v1/stock-mix-recipes
 *   GET    /v1/stock-mix-recipes/lookup
 *   GET    /v1/stock-mix-recipes/{id}
 *   POST   /v1/stock-mix-recipes
 *   PATCH  /v1/stock-mix-recipes/{id}
 *   DELETE /v1/stock-mix-recipes/{id}
 */

import api from './index'

export interface StockMixComponent {
  name: string
  target_g_per_l: number
}

export interface StockMixRecipe {
  id: string
  label: string
  dose_role: string
  coverage: 'universal' | 'phase_specific'
  nutrient_phase: string | null
  components: StockMixComponent[]
  metadata: Record<string, unknown>
  /** AUT-1419 B2 — feedforward; always theoretical when present */
  computed_elements?: Record<string, unknown> | null
  computed_npk?: Record<string, unknown> | null
  npk_status?: 'complete' | 'incomplete' | string | null
  npk_missing_salts?: string[] | null
  npk_computed_at?: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface StockMixRecipeLookupParams {
  dose_role: string
  nutrient_phase?: string | null
}

/** AUT-1420 B3 — phase → Stock A/B (reuses server lookup). */
export interface StockMixPhaseResolve {
  nutrient_phase: string | null
  part_a: StockMixRecipe | null
  part_b: StockMixRecipe | null
  resolved: boolean
  detail: string | null
}

export const stockMixRecipesApi = {
  async list(params: {
    dose_role?: string
    nutrient_phase?: string
    coverage?: string
    include_inactive?: boolean
  } = {}): Promise<StockMixRecipe[]> {
    const response = await api.get<StockMixRecipe[]>('/stock-mix-recipes', { params })
    return Array.isArray(response.data) ? response.data : []
  },

  async lookup(params: StockMixRecipeLookupParams): Promise<StockMixRecipe> {
    const response = await api.get<StockMixRecipe>('/stock-mix-recipes/lookup', {
      params: {
        dose_role: params.dose_role,
        ...(params.nutrient_phase ? { nutrient_phase: params.nutrient_phase } : {}),
      },
    })
    return response.data
  },

  async resolvePhase(nutrientPhase: string | null | undefined): Promise<StockMixPhaseResolve> {
    const response = await api.get<StockMixPhaseResolve>('/stock-mix-recipes/resolve-phase', {
      params: nutrientPhase ? { nutrient_phase: nutrientPhase } : {},
    })
    return response.data
  },

  async get(id: string): Promise<StockMixRecipe> {
    const response = await api.get<StockMixRecipe>(`/stock-mix-recipes/${id}`)
    return response.data
  },

  /** AUT-1362: decisive g/L values editable via P9 CRUD. */
  async update(
    id: string,
    body: {
      label?: string
      components?: StockMixComponent[]
      metadata?: Record<string, unknown>
      active?: boolean
    },
  ): Promise<StockMixRecipe> {
    const response = await api.patch<StockMixRecipe>(`/stock-mix-recipes/${id}`, body)
    return response.data
  },
}
