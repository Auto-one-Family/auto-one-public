import type { AxiosError } from 'axios'
import { parseApiError } from './parseApiError'

export type UiRetryability = 'yes' | 'no' | 'unknown'

export type UiApiError = {
  message: string
  numeric_code: number | null
  request_id: string | null
  retryability: UiRetryability
  status: number
}

export function toUiApiError(error: unknown, fallbackMessage = 'Unbekannter API-Fehler'): UiApiError {
  const axiosError = error as AxiosError
  const parsed = parseApiError(axiosError)

  return {
    message: buildUiMessage(parsed.statusCode, parsed.message, fallbackMessage),
    numeric_code: parsed.numericCode,
    request_id: parsed.requestId,
    retryability: inferRetryability(parsed.statusCode),
    status: parsed.statusCode,
  }
}

export function formatUiApiError(error: UiApiError): string {
  const details: string[] = [error.message]
  if (error.request_id) details.push(`Request-ID: ${error.request_id}`)
  if (error.numeric_code !== null) details.push(`Fehlercode: ${error.numeric_code}`)
  if (error.retryability === 'yes') details.push('Hinweis: Erneut versuchen möglich.')
  return details.join('\n')
}

function buildUiMessage(status: number, message: string, fallbackMessage: string): string {
  if (status === 403) {
    return 'Zugriff verweigert. Sie haben keine Berechtigung für diese Aktion.'
  }
  if (status === 401) {
    return 'Sitzung nicht mehr gültig. Bitte erneut anmelden.'
  }
  if (status >= 500) {
    return message || 'Server-Störung. Die Aktion konnte nicht abgeschlossen werden.'
  }
  if (status === 0) {
    return message || 'Netzwerkfehler. Bitte Verbindung prüfen und erneut versuchen.'
  }
  return message || fallbackMessage
}

function inferRetryability(status: number): UiRetryability {
  if (status === 403 || status === 401 || status === 400 || status === 404) return 'no'
  if (status === 0 || status === 408 || status === 429 || status >= 500) return 'yes'
  return 'unknown'
}
