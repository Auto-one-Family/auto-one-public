import { ref, readonly, type DeepReadonly, type Ref } from 'vue'

const lastServerRequestId: Ref<string | null> = ref(null)

/**
 * Normalisiert den Wert des HTTP-Headers X-Request-ID (Axios: string | string[]).
 */
export function normalizeXRequestIdHeader(value: string | string[] | undefined): string | null {
  if (value == null) return null
  const s = Array.isArray(value) ? value[0] : value
  if (typeof s !== 'string') return null
  const t = s.trim()
  return t.length > 0 ? t : null
}

/**
 * Wird aus Axios-Interceptors aufgerufen. Außerhalb von Vite-Development keine Speicherung.
 */
export function recordLastServerRequestIdFromHeaders(headers: unknown): void {
  if (!import.meta.env.DEV) return
  if (!headers || typeof headers !== 'object') return
  const h = headers as Record<string, string | string[] | undefined>
  const raw = h['x-request-id'] ?? h['X-Request-ID']
  lastServerRequestId.value = normalizeXRequestIdHeader(raw)
}

export function useLastServerRequestId(): DeepReadonly<Ref<string | null>> {
  return readonly(lastServerRequestId)
}
