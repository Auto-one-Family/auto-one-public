/**
 * Intent outcomes REST API (parity with WS intent_outcome). Base URL is /api/v1.
 */
import api from './index'

export interface IntentOutcomeRow {
  intent_id?: string
  correlation_id?: string | null
  esp_id?: string | null
  flow?: string | null
  outcome?: string | null
  code?: string | null
  reason?: string | null
  terminality?: string | null
  severity?: string | null
  [key: string]: unknown
}

export async function listIntentOutcomes(params?: {
  limit?: number
  esp_id?: string
  flow?: string
  outcome?: string
}): Promise<IntentOutcomeRow[]> {
  const res = await api.get<{ status: string; data: IntentOutcomeRow[] }>('intent-outcomes', {
    params: {
      limit: params?.limit ?? 100,
      esp_id: params?.esp_id,
      flow: params?.flow,
      outcome: params?.outcome,
    },
  })
  return res.data.data ?? []
}

export async function getIntentOutcomeById(intentId: string): Promise<IntentOutcomeRow> {
  const res = await api.get<{ status: string; data: IntentOutcomeRow }>(`intent-outcomes/${encodeURIComponent(intentId)}`)
  return res.data.data
}
