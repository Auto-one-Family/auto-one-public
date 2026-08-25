/**
 * Salt Compositions API Client (AUT-1418 / B1, AUT-1422 / B5)
 *
 *   GET    /v1/salt-compositions
 *   GET    /v1/salt-compositions/{id}
 *   POST   /v1/salt-compositions
 *   PATCH  /v1/salt-compositions/{id}
 *   DELETE /v1/salt-compositions/{id}  (soft)
 */

import api from './index'

export type SaltSourceType = 'stoichiometric' | 'manufacturer_label' | 'beleg_offen'

export interface SaltComposition {
  id: string
  name: string
  formula: string | null
  n_pct: number | null
  p_pct: number | null
  k_pct: number | null
  ca_pct: number | null
  mg_pct: number | null
  s_pct: number | null
  source_type: SaltSourceType
  source_note: string
  active: boolean
  created_at: string
  updated_at: string
}

export interface SaltCompositionWriteBody {
  name: string
  formula?: string | null
  n_pct?: number | null
  p_pct?: number | null
  k_pct?: number | null
  ca_pct?: number | null
  mg_pct?: number | null
  s_pct?: number | null
  source_type: SaltSourceType
  source_note?: string
  active?: boolean
}

export const SALT_SOURCE_TYPE_LABELS: Record<SaltSourceType, string> = {
  stoichiometric: 'stöchiometrisch abgeleitet',
  manufacturer_label: 'Hersteller-Etikett',
  beleg_offen: '[BELEG offen]',
}

export function saltSourceTypeLabel(sourceType: string): string {
  if (sourceType in SALT_SOURCE_TYPE_LABELS) {
    return SALT_SOURCE_TYPE_LABELS[sourceType as SaltSourceType]
  }
  return sourceType
}

/** True when at least one elemental % is a finite number. */
export function hasAnyElementPct(body: Partial<SaltCompositionWriteBody>): boolean {
  const keys = ['n_pct', 'p_pct', 'k_pct', 'ca_pct', 'mg_pct', 's_pct'] as const
  return keys.some((k) => {
    const v = body[k]
    return typeof v === 'number' && Number.isFinite(v)
  })
}

/**
 * Guardrail (AUT-1422): numbers without a real evidence source are rejected.
 * Empty/open rows may stay beleg_offen.
 */
export function validateSaltCompositionWrite(
  body: SaltCompositionWriteBody,
): string | null {
  const name = body.name?.trim()
  if (!name) return 'Salzname fehlt'
  if (!body.source_type) return 'Herkunft muss gesetzt sein'
  if (hasAnyElementPct(body) && body.source_type === 'beleg_offen') {
    return 'Mit Elementwerten Herkunft „Hersteller-Etikett“ oder „stöchiometrisch“ wählen — nicht [BELEG offen]'
  }
  if (hasAnyElementPct(body) && body.source_type === 'manufacturer_label') {
    const note = (body.source_note ?? '').trim()
    if (!note) return 'Quellenangabe (Etikett/Charge) fehlt'
  }
  return null
}

export const saltCompositionsApi = {
  async list(params: { source_type?: string; include_inactive?: boolean } = {}): Promise<
    SaltComposition[]
  > {
    const response = await api.get<SaltComposition[]>('/salt-compositions', { params })
    return Array.isArray(response.data) ? response.data : []
  },

  async get(id: string): Promise<SaltComposition> {
    const response = await api.get<SaltComposition>(`/salt-compositions/${id}`)
    return response.data
  },

  async create(body: SaltCompositionWriteBody): Promise<SaltComposition> {
    const response = await api.post<SaltComposition>('/salt-compositions', body)
    return response.data
  },

  async update(
    id: string,
    body: Partial<SaltCompositionWriteBody>,
  ): Promise<SaltComposition> {
    const response = await api.patch<SaltComposition>(`/salt-compositions/${id}`, body)
    return response.data
  },

  async softDelete(id: string): Promise<void> {
    await api.delete(`/salt-compositions/${id}`)
  },
}
