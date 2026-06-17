/**
 * Error Code Translation API Client
 *
 * Provides cached access to error code translations from the server.
 * Used for historical events that need translation (e.g., in EventDetailsPanel).
 *
 * Server-Centric: All translations come from esp32_error_mapping.py + server_error_mapping.py.
 * Real-time error_events already include translations via WebSocket.
 * This API is for on-demand lookups of historical/stored events and
 * auto-enrichment of API errors that carry a numeric_code.
 *
 * Used by: ErrorDetailsModal (auto-enrichment), History-View (planned).
 * See also: parseApiError.ts for REST API error parsing.
 */

import api from './index'

// =============================================================================
// Types
// =============================================================================

export interface TranslatedError {
  error_code: number
  title?: string
  category: string
  severity: string
  message: string
  troubleshooting: string[]
  docs_link?: string | null
  recoverable: boolean
  user_action_required: boolean
}

// =============================================================================
// In-Memory Cache
// =============================================================================

const translationCache = new Map<number, TranslatedError>()

// =============================================================================
// API Functions
// =============================================================================

/**
 * Translate a single error code. Results are cached.
 *
 * @param code - Error code (ESP32: 1000-4999, Server: 5000-5999)
 * @returns Translated error info, or fallback for unknown codes
 */
export async function translateErrorCode(code: number): Promise<TranslatedError> {
  // Check cache first
  const cached = translationCache.get(code)
  if (cached) return cached

  try {
    const response = await api.get<TranslatedError>(`/errors/codes/${code}`)
    const result = response.data
    translationCache.set(code, result)
    return result
  } catch {
    // Fallback for unknown or unreachable codes
    const fallback: TranslatedError = {
      error_code: code,
      title: `Fehler ${code}`,
      category: 'unknown',
      severity: 'error',
      message: `Fehlercode ${code} ist nicht dokumentiert.`,
      troubleshooting: [],
      recoverable: true,
      user_action_required: false,
    }
    return fallback
  }
}

/**
 * Batch-translate multiple error codes. Uses cache where available.
 */
export async function translateErrorCodes(codes: number[]): Promise<Map<number, TranslatedError>> {
  const results = new Map<number, TranslatedError>()
  const promises = codes
    .filter((c, i, arr) => arr.indexOf(c) === i) // deduplicate
    .map(async (code) => {
      const translated = await translateErrorCode(code)
      results.set(code, translated)
    })
  await Promise.all(promises)
  return results
}

/**
 * Clear the translation cache (e.g., on language change or server update).
 */
export function clearTranslationCache(): void {
  translationCache.clear()
}
